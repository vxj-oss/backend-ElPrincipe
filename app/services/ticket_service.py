import io
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import object_session

from app.core.time import LIMA_TZ, ahora_lima
from app.models.order import Pedido
from app.services.desglose_documentos import ahorro_por_descuento, descuento_pactado
from app.services.ticket_render import FUENTE, Ticket, soles


def generar_ticket_pedido(pedido: Pedido, url_qr: Optional[str] = None) -> io.BytesIO:
    t = Ticket()
    cliente = pedido.cliente
    fecha = pedido.fecha_pedido.astimezone(LIMA_TZ)

    t.cabecera_empresa()
    t.caja_titulo(["TICKET DE PEDIDO", pedido.codigo_pedido])
    t.espacio(2)
    t.campo("Cliente", cliente.razon_social if cliente else f"#{pedido.cliente_id}")
    t.campo("Documento", cliente.ruc_dni if cliente and cliente.ruc_dni else "-")
    if cliente and cliente.direccion:
        t.campo("Dirección", cliente.direccion)
    t.campo("Fecha", f"{fecha.strftime('%d/%m/%Y')}   Hora: {fecha.strftime('%H:%M')}")
    t.campo("Moneda", "SOLES")
    t.campo("Forma de pago", str(pedido.forma_pago))
    t.campo("Estado", str(pedido.estado))
    t.espacio(3)

    t.encabezado_producto()
    for det in pedido.detalles:
        nombre = det.producto.nombre if det.producto else f"Producto #{det.producto_id}"
        t.fila_producto(det.cantidad, nombre, det.precio_unitario, det.subtotal)

    sesion = object_session(pedido)
    porcentaje = descuento_pactado(sesion, pedido.cliente_id) if sesion is not None else Decimal("0")
    ahorro = ahorro_por_descuento(
        [
            (det.cantidad, det.precio_unitario, det.producto.precio_unitario if det.producto else None)
            for det in pedido.detalles
        ],
        porcentaje,
    )
    extra = []
    if ahorro > 0:
        extra.append((f"Ahorro dscto. {float(porcentaje):g} %", f"S/ {soles(ahorro)}"))
    t.totales(pedido.monto_total, extra)
    if ahorro > 0:
        t.izquierda("Precios ya incluyen el descuento", FUENTE, 7)
    t.espacio(4)
    t.qr(url_qr or f"PEDIDO|{pedido.codigo_pedido}|{fecha.strftime('%Y-%m-%d')}|{soles(pedido.monto_total)}")
    t.separador()
    t.centrado("Comprobante del pedido", FUENTE, 6.5)
    t.espacio(4)
    t.centrado("¡Gracias por tu compra!")
    t.centrado(f"Emitido {ahora_lima().strftime('%d/%m/%Y %H:%M')}", FUENTE, 7)
    t.espacio(10)
    return t.construir()
