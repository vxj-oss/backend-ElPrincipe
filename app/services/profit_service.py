from datetime import datetime, time, timedelta
from typing import Dict, Tuple

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.time import LIMA_TZ, ahora_lima
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto

ESTADOS_CONFIRMADOS = ("Aprobado", "Entregado")


def rango_periodo(periodo: str) -> Tuple[datetime, datetime]:
    hoy = ahora_lima().date()
    if periodo == "semana":
        inicio_fecha = hoy - timedelta(days=hoy.weekday())
    elif periodo == "mes":
        inicio_fecha = hoy.replace(day=1)
    else:
        inicio_fecha = hoy
    inicio = datetime.combine(inicio_fecha, time(0, 0), tzinfo=LIMA_TZ)
    fin = datetime.combine(hoy + timedelta(days=1), time(0, 0), tzinfo=LIMA_TZ)
    return inicio, fin


def resumen_rentabilidad(db: Session, inicio: datetime, fin: datetime) -> Dict[str, float]:
    ventas, costo, pedidos = db.execute(
        select(
            func.coalesce(func.sum(DetallePedido.subtotal), 0),
            func.coalesce(func.sum(Producto.precio_costo * DetallePedido.cantidad), 0),
            func.count(distinct(Pedido.id)),
        )
        .select_from(DetallePedido)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .join(Producto, Producto.id == DetallePedido.producto_id)
        .where(
            Pedido.estado.in_(ESTADOS_CONFIRMADOS),
            Pedido.fecha_pedido >= inicio,
            Pedido.fecha_pedido < fin,
        )
    ).one()
    ventas = float(ventas or 0)
    costo = float(costo or 0)
    margen = ventas - costo
    return {
        "ventas": ventas,
        "costo": costo,
        "margen": margen,
        "margen_pct": (margen / ventas * 100) if ventas else 0.0,
        "pedidos": int(pedidos or 0),
    }


def productos_mas_vendidos(db: Session, inicio: datetime, fin: datetime, limite: int = 5):
    return db.execute(
        select(
            Producto.nombre,
            func.sum(DetallePedido.cantidad).label("unidades"),
            func.sum(DetallePedido.subtotal).label("ventas"),
        )
        .join(DetallePedido, DetallePedido.producto_id == Producto.id)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(
            Pedido.estado.in_(ESTADOS_CONFIRMADOS),
            Pedido.fecha_pedido >= inicio,
            Pedido.fecha_pedido < fin,
        )
        .group_by(Producto.id, Producto.nombre)
        .order_by(func.sum(DetallePedido.cantidad).desc())
        .limit(limite)
    ).all()
