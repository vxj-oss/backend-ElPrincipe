import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.time import LIMA_TZ, ahora_lima
from sqlalchemy.orm import object_session

from app.models.order import Pedido
from app.services.desglose_documentos import ahorro_por_descuento, bloque_totales_pdf, descuento_pactado

CIUDAD = "Trujillo, La Libertad, Perú"


def generar_pedido_pdf(pedido: Pedido) -> io.BytesIO:
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("Normal9", parent=estilos["Normal"], fontSize=9, leading=12)
    derecha = ParagraphStyle("Derecha", parent=normal, alignment=TA_RIGHT)
    cabecera = ParagraphStyle(
        "Cab", parent=normal, textColor=colors.whitesmoke, fontName="Helvetica-Bold"
    )
    nota = ParagraphStyle("Nota", parent=normal, fontSize=8, textColor=colors.HexColor("#64748b"))

    cliente = pedido.cliente
    sesion = object_session(pedido)
    porcentaje = descuento_pactado(sesion, pedido.cliente_id) if sesion is not None else 0
    ahorro = ahorro_por_descuento(
        [
            (det.cantidad, det.precio_unitario, det.producto.precio_unitario if det.producto else None)
            for det in pedido.detalles
        ],
        porcentaje,
    )
    fecha = pedido.fecha_pedido.astimezone(LIMA_TZ).strftime("%d/%m/%Y %H:%M")

    filas = [[Paragraph(t, cabecera) for t in ("Producto", "Cant.", "Precio unit.", "Subtotal")]]
    for det in pedido.detalles:
        nombre = det.producto.nombre if det.producto else f"Producto #{det.producto_id}"
        filas.append(
            [
                Paragraph(nombre, normal),
                Paragraph(str(det.cantidad), derecha),
                Paragraph(f"S/ {float(det.precio_unitario):,.2f}", derecha),
                Paragraph(f"S/ {float(det.subtotal):,.2f}", derecha),
            ]
        )

    tabla = Table(filas, colWidths=[270, 50, 85, 85], repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )

    datos_pedido = [
        f"<b>Fecha:</b> {fecha}",
        f"<b>Estado:</b> {pedido.estado}",
        f"<b>Condición de pago:</b> {pedido.forma_pago}",
    ]
    if pedido.fecha_entrega:
        datos_pedido.append(
            f"<b>Entrega:</b> {pedido.fecha_entrega.astimezone(LIMA_TZ).strftime('%d/%m/%Y')}"
        )

    datos_cliente = [
        f"<b>Cliente:</b> {cliente.razon_social if cliente else f'#{pedido.cliente_id}'}",
    ]
    if cliente and cliente.ruc_dni:
        datos_cliente.append(f"<b>RUC/DNI:</b> {cliente.ruc_dni}")
    if cliente and cliente.direccion:
        datos_cliente.append(f"<b>Dirección:</b> {cliente.direccion}")
    if cliente and cliente.telefono:
        datos_cliente.append(f"<b>Teléfono:</b> {cliente.telefono}")

    elementos = [
        Paragraph("<b>EL PRÍNCIPE</b>", estilos["Heading1"]),
        Paragraph(CIUDAD, nota),
        Spacer(1, 10),
        Paragraph(f"<b>PEDIDO {pedido.codigo_pedido}</b>", estilos["Heading2"]),
        *[Paragraph(linea, normal) for linea in datos_pedido],
        Paragraph(f"<b>Emitido:</b> {ahora_lima().strftime('%d/%m/%Y %H:%M')}", normal),
        Spacer(1, 8),
        *[Paragraph(linea, normal) for linea in datos_cliente],
        Spacer(1, 14),
        tabla,
        Spacer(1, 10),
        *bloque_totales_pdf(pedido.monto_total, porcentaje, ahorro),
        Spacer(1, 18),
        Paragraph("Gracias por tu compra.", nota),
    ]

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    ).build(elementos)
    buffer.seek(0)
    return buffer
