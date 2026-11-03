import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.numero_letras import monto_en_letras
from app.core.time import LIMA_TZ, ahora_lima
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.services.ticket_render import FUENTE, Ticket, desglose

ESTADOS_VENDIDOS = ("Aprobado", "Entregado")
CLIENTE_GENERAL = "CLIENTES VARIOS"


def _rango(dia: date):
    inicio = datetime.combine(dia, time(0, 0), tzinfo=LIMA_TZ)
    return inicio, inicio + timedelta(days=1)


def resumen_ventas_dia(db: Session, dia: Optional[date] = None) -> Dict[str, Any]:
    dia = dia or ahora_lima().date()
    inicio, fin = _rango(dia)
    pedidos = list(
        db.scalars(
            select(Pedido)
            .options(
                selectinload(Pedido.cliente),
                selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
            )
            .where(Pedido.fecha_pedido >= inicio, Pedido.fecha_pedido < fin)
            .order_by(Pedido.fecha_pedido.asc())
        ).all()
    )
    vendidos = [p for p in pedidos if str(p.estado) in ESTADOS_VENDIDOS]
    excluidos = [p for p in pedidos if str(p.estado) not in ESTADOS_VENDIDOS]

    agrupado: Dict[tuple, Dict[str, Any]] = {}
    for pedido in vendidos:
        for det in pedido.detalles:
            nombre = det.producto.nombre if det.producto else f"Producto #{det.producto_id}"
            clave = (det.producto_id, Decimal(str(det.precio_unitario)))
            fila = agrupado.setdefault(
                clave,
                {
                    "producto_id": det.producto_id,
                    "nombre": nombre,
                    "precio_unitario": float(det.precio_unitario),
                    "cantidad": 0,
                    "total": Decimal("0"),
                    "pedidos": [],
                },
            )
            fila["cantidad"] += int(det.cantidad)
            fila["total"] += Decimal(str(det.subtotal))
            if pedido.codigo_pedido not in fila["pedidos"]:
                fila["pedidos"].append(pedido.codigo_pedido)

    lineas = sorted(agrupado.values(), key=lambda f: (f["nombre"].lower(), f["precio_unitario"]))
    total_lineas = sum((f["total"] for f in lineas), Decimal("0"))
    total_pedidos = sum((Decimal(str(p.monto_total or 0)) for p in vendidos), Decimal("0"))
    total, valor_venta, igv = desglose(total_lineas)
    diferencia = (total_pedidos - total_lineas).quantize(Decimal("0.01"))

    return {
        "fecha": dia.isoformat(),
        "lineas": [
            {**f, "total": float(f["total"]), "numero_pedidos": len(f["pedidos"])} for f in lineas
        ],
        "unidades": sum(f["cantidad"] for f in lineas),
        "total": float(total),
        "valor_venta": float(valor_venta),
        "igv": float(igv),
        "son": monto_en_letras(total),
        "pedidos": [
            {
                "codigo": p.codigo_pedido,
                "cliente": p.cliente.razon_social if p.cliente else CLIENTE_GENERAL,
                "hora": p.fecha_pedido.astimezone(LIMA_TZ).strftime("%H:%M"),
                "estado": str(p.estado),
                "total": float(p.monto_total or 0),
            }
            for p in vendidos
        ],
        "excluidos": {
            "cantidad": len(excluidos),
            "monto": float(sum((Decimal(str(p.monto_total or 0)) for p in excluidos), Decimal("0"))),
            "codigos": [p.codigo_pedido for p in excluidos][:10],
        },
        "total_pedidos": float(total_pedidos),
        "diferencia": float(diferencia),
        "coincide": diferencia == 0,
    }


def generar_ticket_cierre(
    db: Session, dia: Optional[date] = None, lineas_editadas: Optional[List[Dict[str, Any]]] = None
) -> io.BytesIO:
    resumen = resumen_ventas_dia(db, dia)
    ahora = ahora_lima()
    dia_texto = datetime.fromisoformat(resumen["fecha"]).strftime("%d/%m/%Y")

    if lineas_editadas is None:
        lineas = [
            (f["cantidad"], f["nombre"], f["precio_unitario"], Decimal(str(f["total"]))) for f in resumen["lineas"]
        ]
    else:
        lineas = []
        for f in lineas_editadas:
            precio = Decimal(str(f["precio_unitario"]))
            lineas.append((f["cantidad"], f["nombre"], precio, (precio * f["cantidad"]).quantize(Decimal("0.01"))))
    total = sum((l[3] for l in lineas), Decimal("0"))

    t = Ticket()
    t.cabecera_empresa()
    t.caja_titulo(["RESUMEN DE VENTAS DEL DÍA", f"Fecha: {dia_texto}"])
    t.espacio(2)
    t.campo("Cliente", CLIENTE_GENERAL)
    t.campo("Documento", "-")
    t.campo("Fecha", f"{dia_texto}   Hora: {ahora.strftime('%H:%M')}")
    t.campo("Moneda", "SOLES")
    t.campo("Forma de pago", "Contado")
    t.campo("Pedidos incluidos", str(len(resumen["pedidos"])))
    t.espacio(3)

    t.encabezado_producto()
    if lineas:
        for cantidad, nombre, precio, subtotal in lineas:
            t.fila_producto(cantidad, nombre, precio, subtotal)
    else:
        t.izquierda("Sin ventas confirmadas en este día.")
    t.totales(total)
    t.espacio(4)
    t.qr(f"CIERRE|{resumen['fecha']}|{len(resumen['pedidos'])} pedidos|{total:.2f}")
    t.separador()
    t.centrado("Resumen de ventas", FUENTE, 6.5)
    t.espacio(4)
    t.centrado(f"Emitido {ahora.strftime('%d/%m/%Y %H:%M')}", FUENTE, 7)
    t.espacio(10)
    return t.construir()
