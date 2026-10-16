import math
from datetime import date, timedelta
from statistics import mean, median, pstdev
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import LIMA_TZ, ahora_lima
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.services import analytics_service as an
from app.services.config_service import ConfigService
from app.services.profit_service import ESTADOS_CONFIRMADOS

DIAS_HISTORIA = 56
DIAS_NIVEL = 28
PESO_ESTACIONAL = 0.5
TOPE_TENDENCIA = 0.3
INCERTIDUMBRE_MIN = 0.15
INCERTIDUMBRE_MAX = 0.6
MIN_DIAS_ACTIVOS = 10
DIAS_DEMANDA_PRODUCTO = 30
VECES_MEDIANA_TOPE = 2.5
MIN_DIAS_TOPE = 5
PESO_RECIENTE = 0.6
FRENO_RECIENTE = 0.4


def _historia(db: Session, hoy: date) -> List[float]:
    inicio = hoy - timedelta(days=DIAS_HISTORIA - 1)
    por_dia = an.ventas_por_dia(db, f"{an.PREFIJO_RANGO}{inicio.isoformat()}:{hoy.isoformat()}")
    return [por_dia.get(inicio + timedelta(days=i), 0.0) for i in range(DIAS_HISTORIA)]


def _acotar(valores: List[float]) -> List[float]:
    activos = [v for v in valores if v > 0]
    if len(activos) < MIN_DIAS_TOPE:
        return list(valores)
    tope = VECES_MEDIANA_TOPE * median(activos)
    return [min(v, tope) for v in valores]


def _factores_dia(valores: List[float], hoy: date) -> Dict[int, float]:
    media = mean(valores) if valores else 0.0
    factores = {d: 1.0 for d in range(7)}
    if not media:
        return factores
    inicio = hoy - timedelta(days=DIAS_HISTORIA - 1)
    for dia in range(7):
        propios = [v for i, v in enumerate(valores) if (inicio + timedelta(days=i)).weekday() == dia]
        if propios:
            crudo = mean(propios) / media
            factores[dia] = 1 + (crudo - 1) * PESO_ESTACIONAL
    return factores


def proyectar_ventas(db: Session, horizonte: int, hasta_fin_de_mes: bool = False) -> Dict[str, Any]:
    hoy = ahora_lima().date()
    crudos = _historia(db, hoy)
    valores = _acotar(crudos)
    reciente = valores[-DIAS_NIVEL:]
    nivel = PESO_RECIENTE * mean(valores[-14:]) + (1 - PESO_RECIENTE) * mean(reciente) if reciente else 0.0
    ultimos = mean(valores[-14:])
    previos = mean(valores[-28:-14])
    tendencia = max(-TOPE_TENDENCIA, min(TOPE_TENDENCIA, (ultimos - previos) / previos)) if previos else 0.0
    nivel_ajustado = nivel * (1 + tendencia * 0.5)
    factores = _factores_dia(valores, hoy)

    if hasta_fin_de_mes:
        siguiente = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1)
        horizonte = max(0, (siguiente - hoy).days - 1)
    futuro = []
    for i in range(1, horizonte + 1):
        dia = hoy + timedelta(days=i)
        futuro.append((dia, round(nivel_ajustado * factores[dia.weekday()], 2)))
    total = round(sum(v for _, v in futuro), 2)

    variabilidad = (pstdev(reciente) / nivel) if nivel and len(reciente) > 1 else 0.0
    relativa = max(INCERTIDUMBRE_MIN, min(INCERTIDUMBRE_MAX, variabilidad / math.sqrt(max(horizonte, 1))))
    activos = sum(1 for v in crudos if v > 0)
    comparable = sum(crudos[-horizonte:]) if 0 < horizonte <= DIAS_HISTORIA else None
    meta = float(ConfigService.get(db).meta_diaria_ventas or 0)

    return {
        "hoy": hoy,
        "historia": [(hoy - timedelta(days=len(crudos) - 1 - i), v) for i, v in enumerate(crudos)],
        "futuro": futuro,
        "total": total,
        "bajo": round(total * (1 - relativa), 2),
        "alto": round(total * (1 + relativa), 2),
        "tendencia": tendencia,
        "dias_activos": activos,
        "pocos_datos": activos < MIN_DIAS_ACTIVOS,
        "comparable": comparable,
        "promedio_diario": round(total / horizonte, 2) if horizonte else 0.0,
        "meta_diaria": meta,
        "horizonte": horizonte,
        "vendido_mes": None,
        "si_sigue_igual": round(mean(crudos[-7:]) * horizonte, 2),
        "frenado": mean(crudos[-7:]) < FRENO_RECIENTE * mean(crudos[-28:]) if mean(crudos[-28:]) else False,
    }


def ventas_del_mes_hasta_hoy(db: Session) -> float:
    return float(an.total_periodo(db, "mes")["ventas"])


def demanda_producto(db: Session, producto_ids: List[int]) -> Dict[str, Any]:
    hoy = ahora_lima().date()
    inicio = hoy - timedelta(days=DIAS_DEMANDA_PRODUCTO - 1)
    desde, hasta = an.rango(f"{an.PREFIJO_RANGO}{inicio.isoformat()}:{hoy.isoformat()}")
    filas = db.execute(
        select(Pedido.fecha_pedido, DetallePedido.cantidad)
        .join(DetallePedido, DetallePedido.pedido_id == Pedido.id)
        .where(
            DetallePedido.producto_id.in_(producto_ids),
            Pedido.estado.in_(ESTADOS_CONFIRMADOS),
            Pedido.fecha_pedido >= desde,
            Pedido.fecha_pedido < hasta,
        )
    ).all()
    por_dia: Dict[date, float] = {}
    for fecha, cantidad in filas:
        dia = fecha.astimezone(LIMA_TZ).date()
        por_dia[dia] = por_dia.get(dia, 0.0) + float(cantidad or 0)
    unidades = sum(por_dia.values())
    stock = db.scalar(select(func.coalesce(func.sum(Producto.stock_actual), 0)).where(Producto.id.in_(producto_ids))) or 0
    return {
        "unidades_30d": unidades,
        "ritmo_diario": unidades / DIAS_DEMANDA_PRODUCTO,
        "dias_con_venta": len(por_dia),
        "stock": int(stock),
        "serie": [por_dia.get(inicio + timedelta(days=i), 0.0) for i in range(DIAS_DEMANDA_PRODUCTO)],
        "inicio": inicio,
    }
