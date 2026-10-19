from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.agent.anomalies import detectar_anomalias
from app.services import analytics_service as an

DIAS_ALERTA_STOCK = 7
DIAS_URGENTE_STOCK = 3
ORDEN_NIVEL = {"alta": 0, "media": 1, "info": 2}


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _aviso_stock(db: Session) -> List[Dict[str, Any]]:
    filas = [
        f for f in an.cobertura_stock(db, limite=20)
        if f["dias_cobertura"] is None or f["dias_cobertura"] <= DIAS_ALERTA_STOCK
    ]
    if not filas:
        return []
    urgente = any(f["dias_cobertura"] is not None and f["dias_cobertura"] <= DIAS_URGENTE_STOCK for f in filas)
    primero = filas[0]
    if len(filas) == 1 and primero["dias_cobertura"] is not None:
        titulo = f"{primero['nombre']} se agota pronto"
        detalle = f"Le quedan unos {primero['dias_cobertura']} días de stock. Sugerido: pedir {primero['sugerido']} u."
    else:
        titulo = f"{len(filas)} productos se agotarían en menos de {DIAS_ALERTA_STOCK + 1} días"
        detalle = f"El más urgente: {primero['nombre']}."
    return [
        {
            "id": "stock",
            "nivel": "alta" if urgente else "media",
            "titulo": titulo,
            "detalle": detalle,
            "accion": {"tipo": "pregunta", "etiqueta": "Ver qué reponer", "texto": "¿Qué debo reponer?"},
        }
    ]


def _espera(horas: int) -> str:
    if horas < 1:
        return "hace menos de una hora"
    if horas < 24:
        return f"hace {horas} h"
    dias = horas // 24
    return f"hace {dias} {_plural(dias, 'día', 'días')}"


def _aviso_recompra(db: Session) -> List[Dict[str, Any]]:
    filas = an.cadencia_clientes(db, limite=30)
    if not filas:
        return []
    n = len(filas)
    primero = filas[0]
    habituales = an.productos_habituales(db, primero["id"], 2)
    detalle = (
        f"{primero['nombre']} suele pedir {' y '.join(habituales)}; arma su cotización con un clic."
        if habituales
        else f"{primero['nombre']} ya está en su momento habitual de compra."
    )
    return [
        {
            "id": "recompra",
            "nivel": "info",
            "titulo": f"{n} {_plural(n, 'cliente con pedido habitual', 'clientes con pedido habitual')}",
            "detalle": detalle,
            "accion": {
                "tipo": "pregunta",
                "etiqueta": "Armar cotización",
                "texto": f"Hazle a {primero['nombre']} lo mismo que la última vez",
            },
        }
    ]


def _aviso_por_convertir(db: Session) -> List[Dict[str, Any]]:
    datos = an.cotizaciones_por_convertir(db)
    if not datos["total"]:
        return []
    n = datos["total"]
    primera = datos["items"][0]
    demora = any(i["horas"] >= 24 for i in datos["items"])
    return [
        {
            "id": "por_convertir",
            "nivel": "media" if demora else "info",
            "titulo": f"{n} {_plural(n, 'cotización lista para convertir en pedido', 'cotizaciones listas para convertir en pedido')}",
            "detalle": f"La más antigua es {primera['codigo']} de {primera['cliente']} ({_espera(primera['horas'])}).",
            "accion": {"tipo": "enlace", "etiqueta": "Abrir cotizaciones", "ruta": "/solicitudes?estado=Pendiente"},
        }
    ]


def _aviso_por_aprobar(db: Session) -> List[Dict[str, Any]]:
    datos = an.pedidos_por_aprobar(db)
    if not datos["total"]:
        return []
    n = datos["total"]
    primero = datos["items"][0]
    demora = primero["horas"] >= 4
    return [
        {
            "id": "por_aprobar",
            "nivel": "media" if demora else "info",
            "titulo": f"{n} {_plural(n, 'pedido esperando aprobación', 'pedidos esperando aprobación')}",
            "detalle": f"El primero es {primero['codigo']} de {primero['cliente']} ({_espera(primero['horas'])}).",
            "accion": {"tipo": "pregunta", "etiqueta": "Ver pedidos", "texto": "¿Qué pedidos están pendientes de confirmar?"},
        }
    ]


def _aviso_anomalias(db: Session) -> List[Dict[str, Any]]:
    hallazgos = [h for h in detectar_anomalias(db) if h["nivel"] != "info"]
    if not hallazgos:
        return []
    n = len(hallazgos)
    return [
        {
            "id": "anomalias",
            "nivel": "media",
            "titulo": f"{n} {_plural(n, 'dato de pedido por verificar', 'datos de pedidos por verificar')}",
            "detalle": hallazgos[0]["titulo"] + ".",
            "accion": {"tipo": "pregunta", "etiqueta": "Ver qué es", "texto": "¿Hay algo raro en mis pedidos?"},
        }
    ]


def avisos_proactivos(db: Session) -> List[Dict[str, Any]]:
    avisos: List[Dict[str, Any]] = []
    for generador in (_aviso_stock, _aviso_por_aprobar, _aviso_por_convertir, _aviso_recompra, _aviso_anomalias):
        avisos += generador(db)
    avisos.sort(key=lambda a: ORDEN_NIVEL[a["nivel"]])
    return avisos
