import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agent.anomalies import detectar_anomalias
from app.agent.tools import CommercialTools
from app.core.metas import METAS_INDICADORES
from app.core.time import ahora_lima
from app.models.customer_request import SolicitudCliente
from app.services import analytics_service as an

TTL_SEGUNDOS = 60
MAX_PUNTOS = 6
MAX_DETALLE = 4
DIAS_ALERTA_STOCK = 7
UMBRAL_CAIDA_ALTA = -20.0
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
        nivel = "alta" if pct <= UMBRAL_CAIDA_ALTA else ("media" if pct < 0 else "ok")
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


def _punto_recompra(db: Session) -> Optional[Dict[str, Any]]:
    filas = an.cadencia_clientes(db, limite=30)
    if not filas:
        return None
    n = len(filas)
    detalle = [
        {
            "texto": f"{f['nombre']} — compra cada {f['intervalo_dias']} días, lleva {f['dias_sin_comprar']} sin comprar",
            "accion": {"tipo": "pregunta", "etiqueta": "Cotizar", "texto": f"Arma una cotización para {f['nombre']}"},
        }
        for f in filas[:MAX_DETALLE]
    ]
    return {
        "id": "recompra",
        "nivel": "media",
        "icono": "recompra",
        "valor": f"{n} {'cliente' if n == 1 else 'clientes'}",
        "sugerencia": f"Escribe hoy a {filas[0]['nombre']} con una cotización de su compra habitual.",
        "titulo": "Clientes por recomprar",
        "texto": f"{n} {'cliente ya está' if n == 1 else 'clientes ya están'} en su momento habitual de recompra; el primero es {filas[0]['nombre']}.",
        "detalle": detalle,
        "accion": {"tipo": "pregunta", "etiqueta": "Ver quiénes", "texto": "¿A quién le toca comprar?"},
    }


def _punto_seguimiento(db: Session) -> Optional[Dict[str, Any]]:
    n = an.cotizaciones_sin_seguimiento(db)
    if not n:
        return None
    ahora = ahora_lima()
    filas = db.scalars(
        select(SolicitudCliente)
        .options(selectinload(SolicitudCliente.cliente))
        .where(
            SolicitudCliente.estado == "Pendiente",
            SolicitudCliente.fecha_solicitud < ahora - timedelta(hours=24),
            SolicitudCliente.fecha_solicitud >= ahora - timedelta(days=14),
        )
        .order_by(SolicitudCliente.fecha_solicitud.asc())
        .limit(MAX_DETALLE)
    ).all()
    detalle = [
        {
            "texto": f"{s.codigo_solicitud} — {s.cliente.razon_social if s.cliente else 'Cliente'}, hace {(ahora - s.fecha_solicitud).days} días",
            "accion": {"tipo": "pregunta", "etiqueta": "Ver", "texto": f"detalle de la cotización {s.codigo_solicitud}"},
        }
        for s in filas
    ]
    return {
        "id": "seguimiento",
        "nivel": "media",
        "icono": "seguimiento",
        "valor": f"{n} {'cotización' if n == 1 else 'cotizaciones'}",
        "sugerencia": "Haz seguimiento por llamada o WhatsApp, empezando por las más antiguas.",
        "titulo": "Cotizaciones sin seguimiento",
        "texto": f"{n} {'cotización lleva' if n == 1 else 'cotizaciones llevan'} más de un día sin convertirse en pedido.",
        "detalle": detalle,
        "accion": {"tipo": "enlace", "etiqueta": "Abrir cotizaciones", "ruta": "/solicitudes?estado=Pendiente"},
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
        "nivel": "alta" if any(h["nivel"] == "alta" for h in hallazgos) else "media",
        "icono": "anomalias",
        "valor": f"{n} {'dato' if n == 1 else 'datos'}",
        "sugerencia": "Confirma si fueron correctos y corrígelos antes de cerrar el día.",
        "titulo": "Datos inusuales",
        "texto": f"{n} {'dato se aleja' if n == 1 else 'datos se alejan'} de lo habitual en los últimos 14 días: {hallazgos[0]['titulo'].lower()}.",
        "detalle": [{"texto": f"{h['titulo']}. {h['detalle']}", "accion": h.get("accion")} for h in hallazgos[:MAX_DETALLE]],
        "accion": {"tipo": "pregunta", "etiqueta": "Revisar", "texto": "¿Hay algo raro en mis ventas?"},
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
        lambda: _punto_recompra(db),
        lambda: _punto_seguimiento(db),
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
