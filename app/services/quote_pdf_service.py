import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.core.time import LIMA_TZ, ahora_lima
from app.models.customer_request import SolicitudCliente
from app.models.product import Producto
from app.services.desglose_documentos import ahorro_por_descuento, bloque_totales_pdf, descuento_pactado

CIUDAD = "Trujillo, La Libertad, Perú"


def generar_cotizacion_pdf(db: Session, solicitud: SolicitudCliente) -> io.BytesIO:
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("Normal8", parent=estilos["Normal"], fontSize=9, leading=12)
    derecha = ParagraphStyle("Derecha", parent=normal, alignment=TA_RIGHT)
    cabecera = ParagraphStyle(
        "Cab", parent=normal, textColor=colors.whitesmoke, fontName="Helvetica-Bold"
    )
    nota = ParagraphStyle("Nota", parent=normal, fontSize=8, textColor=colors.HexColor("#64748b"))

    cliente = solicitud.cliente
    fecha = solicitud.fecha_solicitud.astimezone(LIMA_TZ).strftime("%d/%m/%Y %H:%M")

    filas = [[Paragraph(t, cabecera) for t in ("Producto", "Cant.", "Precio unit.", "Subtotal")]]
    total = Decimal("0")
    lineas_descuento = []
    for det in solicitud.detalles:
        precio = det.precio_esperado
        if precio is None and det.producto_id:
            producto = db.get(Producto, det.producto_id)
            precio = producto.precio_unitario if producto else None
        subtotal = (precio or Decimal("0")) * det.cantidad_solicitada
        total += subtotal
        if precio is not None and det.producto_id:
            producto_linea = db.get(Producto, det.producto_id)
            lineas_descuento.append(
                (det.cantidad_solicitada, precio, producto_linea.precio_unitario if producto_linea else None)
            )
        filas.append(
            [
                Paragraph(det.nombre_producto_solicitado, normal),
                Paragraph(str(det.cantidad_solicitada), derecha),
                Paragraph(f"S/ {float(precio):,.2f}" if precio is not None else "por confirmar", derecha),
                Paragraph(f"S/ {float(subtotal):,.2f}" if precio is not None else "—", derecha),
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

    datos_cliente = [
        f"<b>Cliente:</b> {cliente.razon_social if cliente else f'#{solicitud.cliente_id}'}",
    ]
    if cliente and cliente.ruc_dni:
        datos_cliente.append(f"<b>RUC/DNI:</b> {cliente.ruc_dni}")
    if cliente and cliente.direccion:
        datos_cliente.append(f"<b>Dirección:</b> {cliente.direccion}")
    if cliente and cliente.telefono:
        datos_cliente.append(f"<b>Teléfono:</b> {cliente.telefono}")

    porcentaje = descuento_pactado(db, solicitud.cliente_id)
    ahorro = ahorro_por_descuento(lineas_descuento, porcentaje)

    elementos = [
        Paragraph("<b>EL PRÍNCIPE</b>", estilos["Heading1"]),
        Paragraph(CIUDAD, nota),
        Spacer(1, 10),
        Paragraph(f"<b>COTIZACIÓN {solicitud.codigo_solicitud}</b>", estilos["Heading2"]),
        Paragraph(f"<b>Fecha:</b> {fecha}", normal),
        Paragraph(f"<b>Emitida:</b> {ahora_lima().strftime('%d/%m/%Y %H:%M')}", normal),
        Spacer(1, 8),
        *[Paragraph(linea, normal) for linea in datos_cliente],
        Spacer(1, 14),
        tabla,
        Spacer(1, 10),
        *bloque_totales_pdf(total, porcentaje, ahorro, "TOTAL APROXIMADO"),
        Spacer(1, 18),
        Paragraph(
            "Documento informativo. Los precios y la disponibilidad están sujetos a confirmación.",
            nota,
        ),
    ]

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    ).build(elementos)
    buffer.seek(0)
    return buffer
