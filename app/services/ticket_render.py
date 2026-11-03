import io
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List, Optional, Tuple

from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas

from app.core import empresa
from app.core.numero_letras import monto_en_letras

ANCHO = 80 * mm
MARGEN = 8
UTIL = ANCHO - 2 * MARGEN
FUENTE = "Helvetica"
FUENTE_NEGRITA = "Helvetica-Bold"
TAM = 8
INTERLINEA = 10.5
TASA_IGV = Decimal("0.18")

ANCHO_CANT = 22
ANCHO_PU = 40
ANCHO_TOTAL = 44
ANCHO_NOMBRE = UTIL - ANCHO_CANT - ANCHO_PU - ANCHO_TOTAL - 4


def soles(valor) -> str:
    return f"{float(valor):,.2f}"


def desglose(total: Decimal) -> Tuple[Decimal, Decimal, Decimal]:
    total = Decimal(str(total or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    valor_venta = (total / (1 + TASA_IGV)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return total, valor_venta, total - valor_venta


class Ticket:
    def __init__(self) -> None:
        self.elementos: List[Tuple[float, Callable]] = []

    def centrado(self, texto: str, fuente: str = FUENTE, tam: float = TAM) -> None:
        for linea in simpleSplit(texto, fuente, tam, UTIL):
            self.elementos.append(
                (
                    tam + 3,
                    lambda c, y, linea=linea, fuente=fuente, tam=tam: (
                        c.setFont(fuente, tam),
                        c.drawCentredString(ANCHO / 2, y - tam, linea),
                    ),
                )
            )

    def izquierda(self, texto: str, fuente: str = FUENTE, tam: float = TAM) -> None:
        for linea in simpleSplit(texto, fuente, tam, UTIL):
            self.elementos.append(
                (
                    INTERLINEA,
                    lambda c, y, linea=linea, fuente=fuente, tam=tam: (
                        c.setFont(fuente, tam),
                        c.drawString(MARGEN, y - tam, linea),
                    ),
                )
            )

    def dos_columnas(self, izq: str, der: str, fuente: str = FUENTE, tam: float = TAM) -> None:
        self.elementos.append(
            (
                INTERLINEA,
                lambda c, y: (
                    c.setFont(fuente, tam),
                    c.drawString(MARGEN, y - tam, izq),
                    c.drawRightString(ANCHO - MARGEN, y - tam, der),
                ),
            )
        )

    def campo(self, etiqueta: str, valor: str) -> None:
        self.izquierda(f"{etiqueta}: {valor}")

    def separador(self) -> None:
        self.elementos.append(
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

    def linea_solida(self) -> None:
        self.elementos.append(
            (
                4,
                lambda c, y: (
                    c.setLineWidth(0.8),
                    c.line(MARGEN, y - 2, ANCHO - MARGEN, y - 2),
                ),
            )
        )

    def espacio(self, alto: float = 6) -> None:
        self.elementos.append((alto, lambda c, y: None))

    def caja_titulo(self, lineas: List[str]) -> None:
        alto = 6 + len(lineas) * 11

        def dibujar(c, y):
            c.setLineWidth(0.8)
            c.roundRect(MARGEN, y - alto + 2, UTIL, alto - 2, 6, stroke=1, fill=0)
            c.setFont(FUENTE_NEGRITA, 8.5)
            for i, linea in enumerate(lineas):
                c.drawCentredString(ANCHO / 2, y - 13 - i * 11, linea)

        self.elementos.append((alto + 4, dibujar))

    def encabezado_producto(self) -> None:
        def dibujar(c, y):
            c.setFont(FUENTE_NEGRITA, 7)
            c.drawString(MARGEN, y - 7, "CANT")
            c.drawString(MARGEN + ANCHO_CANT, y - 7, "PRODUCTO")
            c.drawRightString(ANCHO - MARGEN - ANCHO_TOTAL, y - 7, "P/U")
            c.drawRightString(ANCHO - MARGEN, y - 7, "TOTAL")

        self.elementos.append((10, dibujar))
        self.linea_solida()

    def fila_producto(self, cantidad, nombre: str, precio, total) -> None:
        lineas = simpleSplit(nombre, FUENTE, 7.5, ANCHO_NOMBRE) or [""]

        def dibujar(c, y):
            c.setFont(FUENTE, 7.5)
            c.drawString(MARGEN, y - 8, f"{cantidad}")
            for i, linea in enumerate(lineas):
                c.drawString(MARGEN + ANCHO_CANT, y - 8 - i * 9, linea)
            c.drawRightString(ANCHO - MARGEN - ANCHO_TOTAL, y - 8, soles(precio))
            c.drawRightString(ANCHO - MARGEN, y - 8, soles(total))

        self.elementos.append((len(lineas) * 9 + 3, dibujar))

    def qr(self, contenido: str, lado: float = 78) -> None:
        def dibujar(c, y):
            widget = qr.QrCodeWidget(contenido, barLevel="M")
            x0, y0, x1, y1 = widget.getBounds()
            dibujo = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
            dibujo.add(widget)
            renderPDF.draw(dibujo, c, (ANCHO - lado) / 2, y - lado)

        self.elementos.append((lado + 6, dibujar))

    def cabecera_empresa(self) -> None:
        self.centrado(empresa.NOMBRE_COMERCIAL, FUENTE_NEGRITA, 14)
        self.centrado(empresa.SUBTITULO, FUENTE_NEGRITA, 7)
        self.espacio(4)
        self.centrado(empresa.RAZON_SOCIAL, FUENTE_NEGRITA, 8)
        self.centrado(f"R.U.C.: {empresa.RUC}", FUENTE, 8)
        self.centrado(empresa.DIRECCION, FUENTE, 7)
        self.centrado(f"Teléfono: {empresa.TELEFONO}", FUENTE, 7.5)
        self.espacio(5)

    def totales(self, total: Decimal, extra: Optional[List[Tuple[str, str]]] = None) -> None:
        total, valor_venta, igv = desglose(total)
        self.linea_solida()
        for etiqueta, valor in extra or []:
            self.dos_columnas(etiqueta, valor)
        self.dos_columnas("Venta gravada", f"S/ {soles(valor_venta)}")
        self.dos_columnas("Total I.G.V. (18 %)", f"S/ {soles(igv)}")
        self.dos_columnas("TOTAL PRECIO DE VENTA", f"S/ {soles(total)}", FUENTE_NEGRITA, 9)
        self.espacio(3)
        self.izquierda(monto_en_letras(total), FUENTE_NEGRITA, 7.5)
        self.izquierda("Los precios incluyen IGV", FUENTE, 7)

    def construir(self) -> io.BytesIO:
        alto = 2 * 10 + sum(altura for altura, _ in self.elementos)
        buffer = io.BytesIO()
        lienzo = canvas.Canvas(buffer, pagesize=(ANCHO, alto))
        y = alto - 10
        for altura, dibujar in self.elementos:
            dibujar(lienzo, y)
            y -= altura
        lienzo.showPage()
        lienzo.save()
        buffer.seek(0)
        return buffer
