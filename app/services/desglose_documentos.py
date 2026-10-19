from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numero_letras import monto_en_letras
from app.models.commercial_term import CondicionComercial

TASA_IGV = Decimal("0.18")
TOLERANCIA_PRECIO = Decimal("0.02")


def _centimos(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def desglose_igv(total) -> Tuple[Decimal, Decimal, Decimal]:
    total_q = _centimos(Decimal(str(total or 0)))
    valor_venta = _centimos(total_q / (1 + TASA_IGV))
    return valor_venta, total_q - valor_venta, total_q


def descuento_pactado(db: Session, cliente_id: Optional[int]) -> Decimal:
    if not cliente_id:
        return Decimal("0")
    condicion = db.scalar(
        select(CondicionComercial)
        .where(CondicionComercial.cliente_id == cliente_id, CondicionComercial.tipo_condicion == "Descuento")
        .order_by(CondicionComercial.id.desc())
    )
    if condicion and condicion.porcentaje_descuento:
        return Decimal(str(condicion.porcentaje_descuento))
    return Decimal("0")


def ahorro_por_descuento(lineas: Iterable[Tuple[int, Decimal, Optional[Decimal]]], porcentaje: Decimal) -> Decimal:
    if porcentaje <= 0:
        return Decimal("0")
    factor = (Decimal("100") - porcentaje) / Decimal("100")
    ahorro = Decimal("0")
    for cantidad, precio, catalogo in lineas:
        if precio is None or not catalogo:
            continue
        precio_d, catalogo_d = Decimal(str(precio)), Decimal(str(catalogo))
        if abs(precio_d - catalogo_d * factor) <= TOLERANCIA_PRECIO and catalogo_d > precio_d:
            ahorro += Decimal(str(cantidad)) * (catalogo_d - precio_d)
    return _centimos(ahorro)


def _soles(valor: Decimal) -> str:
    return f"S/ {float(valor):,.2f}"


def bloque_totales_pdf(total, porcentaje: Decimal, ahorro: Decimal, etiqueta_total: str = "TOTAL") -> List:
    valor_venta, igv, total_q = desglose_igv(total)
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("TotNormal", parent=estilos["Normal"], fontSize=9, leading=12, alignment=TA_RIGHT)
    negrita = ParagraphStyle("TotNegrita", parent=normal, fontName="Helvetica-Bold", fontSize=11, leading=14)
    nota = ParagraphStyle("TotNota", parent=normal, fontSize=8, textColor=colors.HexColor("#64748b"))

    filas = []
    if ahorro > 0:
        filas.append(
            [
                Paragraph(f"Ahorro por descuento pactado ({float(porcentaje):g} %)", normal),
                Paragraph(_soles(ahorro), normal),
            ]
        )
    filas.append([Paragraph("Op. gravada", normal), Paragraph(_soles(valor_venta), normal)])
    filas.append([Paragraph("IGV (18 %)", normal), Paragraph(_soles(igv), normal)])
    filas.append([Paragraph(etiqueta_total, negrita), Paragraph(_soles(total_q), negrita)])

    tabla = Table(filas, colWidths=[250, 100], hAlign="RIGHT")
    tabla.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, len(filas) - 1), (-1, len(filas) - 1), 0.8, colors.HexColor("#1E3A8A")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elementos = [tabla, Paragraph(f"<b>{monto_en_letras(total_q)}</b>", normal)]
    if ahorro > 0:
        elementos.append(Paragraph("Los precios de la tabla ya incluyen el descuento pactado.", nota))
    elementos.append(Paragraph("Precios incluyen IGV.", nota))
    return elementos
