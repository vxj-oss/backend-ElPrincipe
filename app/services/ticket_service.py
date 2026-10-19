import io
from typing import Callable, List, Tuple

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

from decimal import ROUND_HALF_UP, Decimal

from app.core.numero_letras import monto_en_letras
from app.core.time import LIMA_TZ, ahora_lima
from sqlalchemy.orm import object_session

from app.models.order import Pedido
from app.services.desglose_documentos import ahorro_por_descuento, descuento_pactado

ANCHO = 80 * mm
MARGEN = 8
UTIL = ANCHO - 2 * MARGEN
FUENTE = "Helvetica"
FUENTE_NEGRITA = "Helvetica-Bold"
TAM = 8
INTERLINEA = 10.5
TASA_IGV = Decimal('0.18')


def generar_ticket_pedido(pedido: Pedido) -> io.BytesIO:
    elementos: List[Tuple[float, Callable]] = []

    def centrado(texto: str, fuente: str = FUENTE, tam: float = TAM) -> None:
        lineas = simpleSplit(texto, fuente, tam, UTIL)
        for linea in lineas:
            elementos.append(
                (
                    tam + 3,
                    lambda c, y, linea=linea, fuente=fuente, tam=tam: (
                        c.setFont(fuente, tam),
                        c.drawCentredString(ANCHO / 2, y - tam, linea),
                    ),
                )
            )

    def izquierda(texto: str, fuente: str = FUENTE, tam: float = TAM) -> None:
        for linea in simpleSplit(texto, fuente, tam, UTIL):
            elementos.append(
                (
                    INTERLINEA,
                    lambda c, y, linea=linea, fuente=fuente, tam=tam: (
                        c.setFont(fuente, tam),
                        c.drawString(MARGEN, y - tam, linea),
                    ),
                )
            )

    def dos_columnas(izq: str, der: str, fuente: str = FUENTE, tam: float = TAM) -> None:
        elementos.append(
            (
                INTERLINEA,
                lambda c, y: (
                    c.setFont(fuente, tam),
                    c.drawString(MARGEN, y - tam, izq),
                    c.drawRightString(ANCHO - MARGEN, y - tam, der),
                ),
            )
        )

    def separador() -> None:
        elementos.append(
            (
                8,
                lambda c, y: (
                    c.setDash(2, 2),
                    c.setLineWidth(0.5),
                    c.line(MARGEN, y - 4, ANCHO - MARGEN, y - 4),
                    c.setDash(),
                ),
            )
        )

    def espacio(alto: float = 6) -> None:
        elementos.append((alto, lambda c, y: None))

    cliente = pedido.cliente
    fecha = pedido.fecha_pedido.astimezone(LIMA_TZ).strftime("%d/%m/%Y %H:%M")

    centrado("EL PRÍNCIPE", FUENTE_NEGRITA, 13)
    centrado("Trujillo, La Libertad, Perú")
    espacio()
    separador()
    centrado(f"PEDIDO {pedido.codigo_pedido}", FUENTE_NEGRITA, 9)
    izquierda(f"Fecha: {fecha}")
    izquierda(f"Estado: {pedido.estado}")
    izquierda(f"Pago: {pedido.forma_pago}")
    izquierda(f"Cliente: {cliente.razon_social if cliente else f'#{pedido.cliente_id}'}")
    if cliente and cliente.ruc_dni:
        izquierda(f"RUC/DNI: {cliente.ruc_dni}")
    separador()

    for det in pedido.detalles:
        nombre = det.producto.nombre if det.producto else f"Producto #{det.producto_id}"
        izquierda(nombre, FUENTE_NEGRITA)
        dos_columnas(
            f"{det.cantidad} x S/ {float(det.precio_unitario):,.2f}",
            f"S/ {float(det.subtotal):,.2f}",
        )
        espacio(3)

    separador()
    total = Decimal(str(pedido.monto_total or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    valor_venta = (total / (1 + TASA_IGV)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    igv = total - valor_venta
    sesion = object_session(pedido)
    porcentaje = descuento_pactado(sesion, pedido.cliente_id) if sesion is not None else Decimal("0")
    ahorro = ahorro_por_descuento(
        [
            (det.cantidad, det.precio_unitario, det.producto.precio_unitario if det.producto else None)
            for det in pedido.detalles
        ],
        porcentaje,
    )
    if ahorro > 0:
        dos_columnas(f"Ahorro dscto. {float(porcentaje):g} %", f"S/ {float(ahorro):,.2f}")
        izquierda("Precios ya incluyen el descuento", FUENTE, 7)
    dos_columnas("Op. gravada", f"S/ {float(valor_venta):,.2f}")
    dos_columnas("IGV (18 %)", f"S/ {float(igv):,.2f}")
    dos_columnas("TOTAL", f"S/ {float(total):,.2f}", FUENTE_NEGRITA, 10)
    espacio(2)
    izquierda(monto_en_letras(total), FUENTE_NEGRITA, 7.5)
    izquierda("Precios incluyen IGV", FUENTE, 7)
    separador()
    espacio()
    centrado("Comprobante de pedido. No es boleta ni factura electrónica.", FUENTE, 6.5)
    espacio(4)
    centrado("¡Gracias por tu compra!")
    centrado(f"Emitido {ahora_lima().strftime('%d/%m/%Y %H:%M')}", FUENTE, 7)
    espacio(10)

    alto = 2 * 10 + sum(altura for altura, _ in elementos)

    buffer = io.BytesIO()
    lienzo = canvas.Canvas(buffer, pagesize=(ANCHO, alto))
    y = alto - 10
    for altura, dibujar in elementos:
        dibujar(lienzo, y)
        y -= altura
    lienzo.showPage()
    lienzo.save()
    buffer.seek(0)
    return buffer
