import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agent.anomalies import detectar_anomalias
from app.agent.tools import CommercialTools
from app.core.metas import METAS_INDICADORES
from app.core.time import ahora_lima
from app.services import analytics_service as an

TTL_SEGUNDOS = 60
MAX_PUNTOS = 6
MAX_DETALLE = 4
DIAS_ALERTA_STOCK = 7
ORDEN_NIVEL = {"alta": 0, "media": 1, "info": 2, "ok": 3}

_cache: Dict[str, Any] = {"momento": 0.0, "datos": None}


def _soles(valor: float) -> str:
    return f"S/ {valor:,.2f}"


def _variacion(actual: float, previo: float) -> Optional[float]:
    if not previo:
        return None
    return (actual - previo) / previo * 100


def _punto_ventas(db: Session, periodo: str, etiqueta: str) -> Optional[Dict[str, Any]]:
    d = an.diagnostico(db, periodo)
    actual, previo = d["actual"], d["anterior"]
    if not actual["ventas"] and not previo["ventas"]:
        return None
    pct = _variacion(actual["ventas"], previo["ventas"])
    previo_etiqueta = an.ETIQUETAS[d["previo"]]
    contra = "al " + previo_etiqueta[3:] if previo_etiqueta.startswith("el ") else previo_etiqueta
    detalle: List[Dict[str, Any]] = []
    valor = None
    sugerencia = "Registra más ventas en el periodo para poder comparar."
    if pct is None:
        texto = f"Las ventas de {etiqueta} suman {_soles(actual['ventas'])}; {contra} no hubo ventas con las que comparar."
        nivel = "info"
        tendencia = "neutra"
    else:
        sube = pct >= 0
        texto = (
            f"Las ventas de {etiqueta} suman {_soles(actual['ventas'])}, "
            f"{'por encima' if sube else 'por debajo'} {'del' if contra.startswith('al ') else 'de'} {contra[3:] if contra.startswith('al ') else contra} (mismos días)."
        )
        causas = d["subidas_producto"] if sube else d["caidas_producto"]
        clientes = d["subidas_cliente"] if sube else d["caidas_cliente"]
        nivel = "ok" if pct >= 0 else "info"
        tendencia = "sube" if sube else "baja"
        if causas and clientes:
            if sube:
                sugerencia = f"Mantén stock de {causas[0][0]} y sigue atendiendo a {clientes[0][0]}, que impulsan el avance."
            else:
                sugerencia = f"Contacta a {clientes[0][0]} y revisa el precio y el stock de {causas[0][0]}: son lo que más explica la caída."
        elif causas:
            sugerencia = (f"Aprovecha el impulso de {causas[0][0]}." if sube else f"Revisa el precio y el stock de {causas[0][0]}, que explica la caída.")
        else:
            sugerencia = "Revisa los productos y clientes con menos movimiento esta semana." if not sube else "Mantén el ritmo de seguimiento a tus clientes."
        for nombre, dif, act, pre in causas[:3]:
            detalle.append(
                {"texto": f"{nombre}: {'+' if dif >= 0 else '−'}{_soles(abs(dif))} ({_soles(act)} vs {_soles(pre)})", "tipo": "producto"}
            )
        for nombre, dif, act, pre in clientes[:2]:
            detalle.append(
                {
                    "texto": f"Cliente {nombre}: {'+' if dif >= 0 else '−'}{_soles(abs(dif))}",
                    "accion": {"tipo": "pregunta", "etiqueta": "Ver cliente", "texto": f"resumen del cliente {nombre}"},
                }
            )
    return {
        "id": f"ventas_{periodo}",
        "nivel": nivel,
        "icono": "ventas",
        "tendencia": tendencia,
        "valor": valor,
        "sugerencia": sugerencia,
        "titulo": f"Ventas de {etiqueta}",
        "texto": texto,
        "detalle": detalle,
        "accion": {"tipo": "pregunta", "etiqueta": "¿Por qué?", "texto": f"¿Por qué cambiaron las ventas {etiqueta}?"},
    }


def _punto_stock(db: Session) -> Optional[Dict[str, Any]]:
    filas = [
        f for f in an.cobertura_stock(db, limite=30)
        if f["dias_cobertura"] is None or f["dias_cobertura"] <= DIAS_ALERTA_STOCK
    ]
    if not filas:
        return None
    primero = filas[0]
    detalle_primero = (
        f"{primero['nombre']} dura unos {primero['dias_cobertura']} días"
        if primero["dias_cobertura"] is not None
        else f"{primero['nombre']} está bajo el mínimo"
    )
    n = len(filas)
    detalle = [
        {
            "texto": (
                f"{f['nombre']} — {f['dias_cobertura']} días de stock, pedir {f['sugerido']} u."
                if f["dias_cobertura"] is not None
                else f"{f['nombre']} — bajo el mínimo, pedir {f['sugerido']} u."
            ),
            "accion": {"tipo": "pregunta", "etiqueta": "Reponer", "texto": f"repon el stock de {f['nombre']}"},
        }
        for f in filas[:MAX_DETALLE]
    ]
    urgente = any(f["dias_cobertura"] is not None and f["dias_cobertura"] <= 3 for f in filas)
    return {
        "id": "stock",
        "nivel": "alta" if urgente else "media",
        "icono": "stock",
        "valor": f"{n} {'producto' if n == 1 else 'productos'}",
        "sugerencia": f"Prioriza reponer {primero['nombre']} (unas {primero['sugerido']} u.) antes de que se agote.",
        "titulo": "Stock en riesgo",
        "texto": f"{n} {'producto' if n == 1 else 'productos'} se agotaría{'' if n == 1 else 'n'} en menos de una semana; el más urgente: {detalle_primero}.",
        "detalle": detalle,
        "accion": {"tipo": "pregunta", "etiqueta": "¿Qué reponer?", "texto": "¿Qué debo reponer?"},
    }


def _espera(horas: int) -> str:
    if horas < 1:
        return "hace menos de una hora"
    if horas < 24:
        return f"hace {horas} h"
    dias = horas // 24
    return f"hace {dias} {'día' if dias == 1 else 'días'}"


def _punto_recompra(db: Session) -> Optional[Dict[str, Any]]:
    filas = an.cadencia_clientes(db, limite=30)
    if not filas:
        return None
    n = len(filas)
    detalle = []
    for f in filas[:MAX_DETALLE]:
        habituales = an.productos_habituales(db, f["id"], 2)
        pide = f"suele pedir {' y '.join(habituales)}" if habituales else f"compra cada {f['intervalo_dias']} días"
        detalle.append(
            {
                "texto": f"{f['nombre']} — {pide}",
                "accion": {"tipo": "pregunta", "etiqueta": "Armar cotización", "texto": f"Hazle a {f['nombre']} lo mismo que la última vez"},
            }
        )
    primero = filas[0]
    return {
        "id": "recompra",
        "nivel": "info",
        "icono": "recompra",
        "valor": f"{n} {'cliente' if n == 1 else 'clientes'}",
        "sugerencia": f"Arma con un clic la cotización de {primero['nombre']} con lo que suele pedir.",
        "titulo": "Clientes con pedido habitual",
        "texto": f"{n} {'cliente suele' if n == 1 else 'clientes suelen'} repetir su pedido por estas fechas; el primero es {primero['nombre']}.",
        "detalle": detalle,
        "accion": {"tipo": "pregunta", "etiqueta": "Ver quiénes", "texto": "¿A quién le toca comprar?"},
    }


def _punto_por_convertir(db: Session) -> Optional[Dict[str, Any]]:
    datos = an.cotizaciones_por_convertir(db)
    if not datos["total"]:
        return None
    n = datos["total"]
    detalle = [
        {
            "texto": f"{i['codigo']} — {i['cliente']}, {_espera(i['horas'])}",
            "accion": {"tipo": "pregunta", "etiqueta": "Crear pedido", "texto": f"crea el pedido de la cotización {i['codigo']}"},
        }
        for i in datos["items"]
    ]
    demora = any(i["horas"] >= 24 for i in datos["items"])
    return {
        "id": "por_convertir",
        "nivel": "media" if demora else "info",
        "icono": "seguimiento",
        "valor": f"{n} {'cotización' if n == 1 else 'cotizaciones'}",
        "sugerencia": "Conviértelas en pedido con un clic para reducir el tiempo de registro.",
        "titulo": "Cotizaciones por convertir en pedido",
        "texto": f"{n} {'cotización está lista' if n == 1 else 'cotizaciones están listas'} para convertirse en pedido.",
        "detalle": detalle,
        "accion": {"tipo": "enlace", "etiqueta": "Abrir cotizaciones", "ruta": "/solicitudes?estado=Pendiente"},
    }


def _punto_por_aprobar(db: Session) -> Optional[Dict[str, Any]]:
    datos = an.pedidos_por_aprobar(db)
    if not datos["total"]:
        return None
    n = datos["total"]
    detalle = [
        {
            "texto": f"{i['codigo']} — {i['cliente']}, {_soles(i['monto'])}, {_espera(i['horas'])}",
            "accion": {"tipo": "pregunta", "etiqueta": "Ver", "texto": f"detalle del pedido {i['codigo']}"},
        }
        for i in datos["items"]
    ]
    demora = datos["items"][0]["horas"] >= 4
    return {
        "id": "por_aprobar",
        "nivel": "media" if demora else "info",
        "icono": "pedidos",
        "valor": f"{n} {'pedido' if n == 1 else 'pedidos'}",
        "sugerencia": "Aprobarlos pronto acorta el tiempo de decisión.",
        "titulo": "Pedidos esperando aprobación",
        "texto": f"{n} {'pedido espera' if n == 1 else 'pedidos esperan'} aprobación.",
        "detalle": detalle,
        "accion": {"tipo": "pregunta", "etiqueta": "Ver pedidos", "texto": "¿Qué pedidos están pendientes de confirmar?"},
    }


def _sugerencia_indicadores(alertas: List[str]) -> str:
    texto = " ".join(alertas)
    pasos = []
    if "NCCA" in texto:
        pasos.append("atiende primero las cotizaciones pendientes")
    if "NPP" in texto:
        pasos.append("convierte en pedido las cotizaciones ya aceptadas")
    if "TPTD" in texto:
        pasos.append("agiliza la aprobación de los pedidos en espera")
    return pasos[0].capitalize() + (", luego " + " y ".join(pasos[1:]) if len(pasos) > 1 else "") + "."


def _punto_indicadores(db: Session) -> Optional[Dict[str, Any]]:
    datos = CommercialTools.get_indicadores_actividad(db)
    alertas: List[str] = []
    detalle: List[Dict[str, Any]] = []
    for sigla, nombre in (("NCCA", "Cotizaciones atendidas"), ("NPP", "Pedidos procesados")):
        bloque = datos[sigla]
        meta = METAS_INDICADORES[sigla]["verde_desde"]
        detalle.append({"texto": f"{sigla} — {nombre}: {bloque['valor_hoy']} de {meta} ({bloque['color_semaforo']})", "color": bloque["color_semaforo"]})
        if bloque["color_semaforo"] != "verde":
            alertas.append(f"{sigla} en {bloque['color_semaforo']} ({bloque['valor_hoy']} de {meta})")
    tptd = datos["TPTD"]
    if tptd["valor_hoy_segundos"] is not None:
        meta_t = METAS_INDICADORES["TPTD"]["verde_antes_de"]
        detalle.append({"texto": f"TPTD — Tiempo de decisión: {tptd['valor_hoy_segundos']} s, meta menos de {meta_t} s ({tptd['color_semaforo']})", "color": tptd["color_semaforo"]})
        if tptd["color_semaforo"] != "verde":
            alertas.append(f"TPTD en {tptd['color_semaforo']} ({tptd['valor_hoy_segundos']} s)")
    else:
        detalle.append({"texto": "TPTD — Tiempo de decisión: aún sin pedidos aprobados hoy", "color": "gris"})
    if not alertas:
        return {
            "id": "indicadores",
            "nivel": "ok",
            "icono": "indicadores",
            "valor": "En verde",
            "sugerencia": "Mantén el ritmo actual; no hace falta intervenir.",
            "titulo": "Indicadores de hoy",
            "texto": "Los indicadores de hoy están en verde.",
            "detalle": detalle,
            "accion": {"tipo": "pregunta", "etiqueta": "Ver gráfico", "texto": "gráfico de los indicadores de los últimos 7 días"},
        }
    rojo = any("rojo" in a for a in alertas)
    return {
        "id": "indicadores",
        "nivel": "alta" if rojo else "media",
        "icono": "indicadores",
        "valor": f"{len(alertas)} en alerta",
        "sugerencia": _sugerencia_indicadores(alertas),
        "titulo": "Indicadores de hoy",
        "texto": "Indicadores de hoy: " + "; ".join(alertas) + ".",
        "detalle": detalle,
        "accion": {"tipo": "pregunta", "etiqueta": "¿Cómo mejoro?", "texto": "¿Cómo mejoro los indicadores?"},
    }


def _punto_anomalias(db: Session) -> Optional[Dict[str, Any]]:
    hallazgos = [h for h in detectar_anomalias(db) if h["nivel"] != "info"]
    if not hallazgos:
        return None
    n = len(hallazgos)
    return {
        "id": "anomalias",
        "nivel": "media",
        "icono": "anomalias",
        "valor": f"{n} {'dato' if n == 1 else 'datos'}",
        "sugerencia": "Confirma que se digitaron bien; si hubo un error, corrígelo desde el pedido.",
        "titulo": "Pedidos por verificar",
        "texto": f"{n} {'dato de pedido conviene verificarse' if n == 1 else 'datos de pedidos conviene verificarlos'} (monto, precio o cantidad): {hallazgos[0]['titulo'].lower()}.",
        "detalle": [{"texto": f"{h['titulo']}. {h['detalle']}", "accion": h.get("accion")} for h in hallazgos[:MAX_DETALLE]],
        "accion": {"tipo": "pregunta", "etiqueta": "Revisar", "texto": "¿Hay algo raro en mis pedidos?"},
    }


def lectura_dashboard(db: Session, forzar: bool = False) -> Dict[str, Any]:
    ahora = time.monotonic()
    if not forzar and _cache["datos"] is not None and ahora - _cache["momento"] < TTL_SEGUNDOS:
        return _cache["datos"]

    puntos: List[Dict[str, Any]] = []
    for generador in (
        lambda: _punto_ventas(db, "semana", "esta semana"),
        lambda: _punto_indicadores(db),
        lambda: _punto_stock(db),
        lambda: _punto_por_aprobar(db),
        lambda: _punto_por_convertir(db),
        lambda: _punto_recompra(db),
        lambda: _punto_anomalias(db),
    ):
        punto = generador()
        if punto:
            puntos.append(punto)
    puntos.sort(key=lambda p: ORDEN_NIVEL[p["nivel"]])

    datos = {
        "generado": ahora_lima().strftime("%H:%M"),
        "puntos": puntos[:MAX_PUNTOS],
        "urgentes": sum(1 for p in puntos if p["nivel"] == "alta"),
    }
    _cache["momento"] = ahora
    _cache["datos"] = datos
    return datos
