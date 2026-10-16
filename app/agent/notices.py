from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.anomalies import detectar_anomalias
from app.core.time import ahora_lima
from app.models.order import Pedido
from app.services import analytics_service as an
from app.services.config_service import ConfigService
from app.services.profit_service import rango_periodo, resumen_rentabilidad

DIAS_ALERTA_STOCK = 7
DIAS_URGENTE_STOCK = 3
HORA_REVISION_META = 15
PORCENTAJE_META_MINIMO = 50
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


def _aviso_recompra(db: Session) -> List[Dict[str, Any]]:
    filas = an.cadencia_clientes(db, limite=30)
    if not filas:
        return []
    n = len(filas)
    return [
        {
            "id": "recompra",
            "nivel": "media",
            "titulo": f"{n} {_plural(n, 'cliente está', 'clientes están')} en su momento de recompra",
            "detalle": f"Por ejemplo: {filas[0]['nombre']}.",
            "accion": {"tipo": "pregunta", "etiqueta": "Ver quiénes", "texto": "¿A quién le toca comprar?"},
        }
    ]


def _aviso_seguimiento(db: Session) -> List[Dict[str, Any]]:
    n = an.cotizaciones_sin_seguimiento(db)
    if not n:
        return []
    return [
        {
            "id": "seguimiento",
            "nivel": "media",
            "titulo": f"{n} {_plural(n, 'cotización sin seguimiento', 'cotizaciones sin seguimiento')}",
            "detalle": "Llevan más de un día sin convertirse en pedido.",
            "accion": {"tipo": "enlace", "etiqueta": "Abrir cotizaciones", "ruta": "/solicitudes"},
        }
    ]


def _aviso_pendientes(db: Session) -> List[Dict[str, Any]]:
    limite = ahora_lima() - timedelta(hours=24)
    n = db.scalar(
        select(func.count(Pedido.id)).where(Pedido.estado == "Pendiente", Pedido.fecha_pedido < limite)
    ) or 0
    if not n:
        return []
    return [
        {
            "id": "pendientes",
            "nivel": "media",
            "titulo": f"{n} {_plural(n, 'pedido pendiente', 'pedidos pendientes')} hace más de un día",
            "detalle": "Conviene confirmarlos o revisarlos.",
            "accion": {"tipo": "pregunta", "etiqueta": "Ver pendientes", "texto": "¿Qué pedidos están pendientes de confirmar?"},
        }
    ]


def _aviso_meta(db: Session) -> List[Dict[str, Any]]:
    ahora = ahora_lima()
    if ahora.hour < HORA_REVISION_META:
        return []
    meta = float(ConfigService.get(db).meta_diaria_ventas)
    if not meta:
        return []
    ventas = resumen_rentabilidad(db, *rango_periodo("hoy"))["ventas"]
    porcentaje = ventas / meta * 100
    if porcentaje >= PORCENTAJE_META_MINIMO:
        return []
    return [
        {
            "id": "meta",
            "nivel": "info",
            "titulo": f"Llevas el {porcentaje:.0f} % de la meta diaria",
            "detalle": f"Faltan S/ {max(0.0, meta - ventas):,.2f} para cumplirla.",
            "accion": {"tipo": "pregunta", "etiqueta": "Ver avance", "texto": "¿Cuál es mi avance de meta diaria?"},
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
            "nivel": "alta" if any(h["nivel"] == "alta" for h in hallazgos) else "media",
            "titulo": f"{n} {_plural(n, 'dato inusual', 'datos inusuales')} por revisar",
            "detalle": hallazgos[0]["titulo"] + ".",
            "accion": {"tipo": "pregunta", "etiqueta": "Ver qué es", "texto": "¿Hay algo raro en mis ventas?"},
        }
    ]


def avisos_proactivos(db: Session) -> List[Dict[str, Any]]:
    avisos: List[Dict[str, Any]] = []
    for generador in (_aviso_stock, _aviso_recompra, _aviso_seguimiento, _aviso_pendientes, _aviso_meta, _aviso_anomalias):
        avisos += generador(db)
    avisos.sort(key=lambda a: ORDEN_NIVEL[a["nivel"]])
    return avisos
