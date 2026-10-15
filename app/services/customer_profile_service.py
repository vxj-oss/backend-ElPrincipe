from typing import Any, Dict, Optional

from sqlalchemy import desc, distinct, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import LIMA_TZ, ahora_lima
from app.models.commercial_term import CondicionComercial
from app.models.customer import Cliente
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto

MAX_PRODUCTOS = 5
MAX_COTIZACIONES = 5
MAX_PEDIDOS = 5


def _iso(valor) -> Optional[str]:
    return valor.astimezone(LIMA_TZ).isoformat() if valor else None


def _texto_condicion(c: CondicionComercial) -> str:
    if c.tipo_condicion == "Credito":
        return f"Crédito {c.dias_plazo_pactados or 0} días"
    if c.tipo_condicion == "Descuento":
        return f"Descuento {float(c.porcentaje_descuento or 0):g}%"
    return f"Pago {c.forma_pago_pactada or 'Contado'}"


def obtener_ficha(db: Session, cliente_id: int) -> Optional[Dict[str, Any]]:
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        return None

    total, cantidad, primera, ultima = db.execute(
        select(
            func.coalesce(func.sum(Pedido.monto_total), 0),
            func.count(Pedido.id),
            func.min(Pedido.fecha_pedido),
            func.max(Pedido.fecha_pedido),
        ).where(Pedido.cliente_id == cliente_id, Pedido.estado != "Cancelado")
    ).one()

    productos = db.execute(
        select(
            Producto.nombre,
            func.sum(DetallePedido.cantidad).label("unidades"),
            func.count(distinct(DetallePedido.pedido_id)).label("veces"),
        )
        .join(DetallePedido, DetallePedido.producto_id == Producto.id)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(Pedido.cliente_id == cliente_id, Pedido.estado != "Cancelado")
        .group_by(Producto.id, Producto.nombre)
        .order_by(desc("unidades"))
        .limit(MAX_PRODUCTOS)
    ).all()

    pendientes_total = db.scalar(
        select(func.count(SolicitudCliente.id)).where(
            SolicitudCliente.cliente_id == cliente_id, SolicitudCliente.estado == "Pendiente"
        )
    ) or 0
    pendientes = db.scalars(
        select(SolicitudCliente)
        .options(selectinload(SolicitudCliente.detalles))
        .where(SolicitudCliente.cliente_id == cliente_id, SolicitudCliente.estado == "Pendiente")
        .order_by(SolicitudCliente.id.desc())
        .limit(MAX_COTIZACIONES)
    ).all()

    pedidos = db.scalars(
        select(Pedido)
        .where(Pedido.cliente_id == cliente_id)
        .order_by(Pedido.fecha_pedido.desc())
        .limit(MAX_PEDIDOS)
    ).all()

    condiciones = db.scalars(
        select(CondicionComercial)
        .where(CondicionComercial.cliente_id == cliente_id)
        .order_by(CondicionComercial.id.desc())
    ).all()

    dias_sin_comprar = (ahora_lima().date() - ultima.astimezone(LIMA_TZ).date()).days if ultima else None

    return {
        "cliente_id": cliente.id,
        "resumen": {
            "total_comprado": float(total or 0),
            "pedidos": cantidad,
            "ticket_promedio": float(total or 0) / cantidad if cantidad else 0,
            "primera_compra": _iso(primera),
            "ultima_compra": _iso(ultima),
            "dias_sin_comprar": dias_sin_comprar,
        },
        "productos_frecuentes": [
            {"nombre": nombre, "unidades": int(unidades), "veces": int(veces)}
            for nombre, unidades, veces in productos
        ],
        "cotizaciones_pendientes": {
            "total": pendientes_total,
            "items": [
                {
                    "id": c.id,
                    "codigo": c.codigo_solicitud,
                    "fecha": _iso(c.fecha_solicitud),
                    "items": len(c.detalles),
                }
                for c in pendientes
            ],
        },
        "ultimos_pedidos": [
            {
                "id": p.id,
                "codigo": p.codigo_pedido,
                "fecha": _iso(p.fecha_pedido),
                "estado": str(p.estado),
                "total": float(p.monto_total or 0),
            }
            for p in pedidos
        ],
        "condiciones": [_texto_condicion(c) for c in condiciones],
    }
