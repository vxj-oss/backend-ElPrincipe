import io
from typing import Any, Dict, List

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.time import ahora_lima

PALETA = ["#1E3A8A", "#f59e0b", "#16a34a", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]
ANCHO_GRAFICO = 480
ALTO_GRAFICO = 230
MAX_ETIQUETA = 30
REEMPLAZOS = {"−": "-", "Σ": "suma de ", "≤": "<=", "≥": ">=", "→": "->", "÷": "/", "…": "...", "•": "-"}


def _limpio(texto: Any) -> str:
    resultado = str(texto if texto is not None else "")
    for origen, destino in REEMPLAZOS.items():
        resultado = resultado.replace(origen, destino)
    return resultado.encode("cp1252", errors="replace").decode("cp1252")


def _corto(texto: str) -> str:
    texto = _limpio(texto)
    return texto if len(texto) <= MAX_ETIQUETA else texto[: MAX_ETIQUETA - 1] + "."


def _numero(valor: float, prefijo: str) -> str:
    return f"{_limpio(prefijo)}{float(valor or 0):,.2f}"


def _dibujo(datos: Dict[str, Any]) -> Drawing:
    etiquetas: List[str] = [_corto(e) for e in datos.get("labels", [])]
    series: List[Dict[str, Any]] = datos.get("series", [])
    tipo = datos.get("grafico", "bar")
    dibujo = Drawing(ANCHO_GRAFICO, ALTO_GRAFICO)

    if tipo == "doughnut":
        valores = [float(v or 0) for v in (series[0]["valores"] if series else [])]
        torta = Pie()
        torta.x, torta.y, torta.width, torta.height = 20, 20, 190, 190
        torta.data = valores or [1]
        torta.labels = None
        for i in range(len(valores)):
            torta.slices[i].fillColor = colors.HexColor(PALETA[i % len(PALETA)])
            torta.slices[i].strokeColor = colors.white
        dibujo.add(torta)
        leyenda = Legend()
        leyenda.x, leyenda.y = 240, 190
        leyenda.fontSize = 8
        leyenda.alignment = "right"
        leyenda.dx, leyenda.dy = 8, 8
        leyenda.deltay = 12
        leyenda.colorNamePairs = [
            (colors.HexColor(PALETA[i % len(PALETA)]), f"{etiquetas[i]}") for i in range(len(valores))
        ]
        dibujo.add(leyenda)
        return dibujo

    series_dibujo = [s for s in series if tipo == "line" or s.get("tipo") != "linea"] or series
    datos_series = [[float(v or 0) for v in s.get("valores", [])] for s in series_dibujo] or [[0]]
    if tipo == "line":
        grafico = HorizontalLineChart()
        for i in range(len(datos_series)):
            grafico.lines[i].strokeColor = colors.HexColor(PALETA[i % len(PALETA)])
            grafico.lines[i].strokeWidth = 1.8
    elif datos.get("horizontal"):
        grafico = HorizontalBarChart()
        grafico.barSpacing = 1
        grafico.groupSpacing = 4
        for i in range(len(datos_series)):
            grafico.bars[i].fillColor = colors.HexColor(PALETA[i % len(PALETA)])
            grafico.bars[i].strokeColor = None
        grafico.categoryAxis.reverseDirection = 1
    else:
        grafico = VerticalBarChart()
        grafico.barSpacing = 1
        grafico.groupSpacing = 6
        for i in range(len(datos_series)):
            grafico.bars[i].fillColor = colors.HexColor(PALETA[i % len(PALETA)])
            grafico.bars[i].strokeColor = None

    horizontal = bool(datos.get("horizontal")) and tipo != "line"
    if horizontal:
        grafico.x, grafico.y, grafico.width, grafico.height = 150, 30, ANCHO_GRAFICO - 175, ALTO_GRAFICO - 55
    else:
        grafico.x, grafico.y, grafico.width, grafico.height = 50, 45, ANCHO_GRAFICO - 70, ALTO_GRAFICO - 80
    grafico.data = datos_series
    grafico.categoryAxis.categoryNames = etiquetas
    grafico.categoryAxis.labels.fontSize = 7
    if len(etiquetas) > 6 and not horizontal:
        grafico.categoryAxis.labels.angle = 30
        grafico.categoryAxis.labels.dy = -8
        grafico.categoryAxis.labels.boxAnchor = "ne"
    maximo = max((max(serie) for serie in datos_series if serie), default=0)
    grafico.valueAxis.valueMin = 0
    grafico.valueAxis.valueMax = maximo * 1.15 if maximo > 0 else 1
    grafico.valueAxis.labels.fontName = "Helvetica"
    grafico.categoryAxis.labels.fontName = "Helvetica"
    grafico.valueAxis.labels.fontSize = 7
    grafico.valueAxis.gridStrokeColor = colors.HexColor("#e2e8f0")
    grafico.valueAxis.visibleGrid = True
    dibujo.add(grafico)

    if len(series_dibujo) > 1:
        leyenda = Legend()
        leyenda.x, leyenda.y = 60, ALTO_GRAFICO - 8
        leyenda.fontSize = 8
        leyenda.alignment = "right"
        leyenda.columnMaximum = 1
        leyenda.deltax = 90
        leyenda.colorNamePairs = [
            (colors.HexColor(PALETA[i % len(PALETA)]), _limpio(s.get("nombre", f"Serie {i + 1}"))) for i, s in enumerate(series_dibujo)
        ]
        dibujo.add(leyenda)
    return dibujo


def generar_pdf_informe(datos: Dict[str, Any]) -> io.BytesIO:
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("N", parent=estilos["Normal"], fontSize=9.5, leading=13)
    titulo = ParagraphStyle("T", parent=estilos["Title"], fontSize=16, leading=20, alignment=0, textColor=colors.HexColor("#0f172a"))
    marca = ParagraphStyle("M", parent=normal, fontSize=8, textColor=colors.HexColor("#64748b"))
    seccion = ParagraphStyle("S", parent=normal, fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, spaceAfter=3, textColor=colors.HexColor("#1E3A8A"))
    ahora = ahora_lima().strftime("%d/%m/%Y %H:%M")

    historia: List[Any] = [
        Paragraph("EL PRINCIPE - Sistema de Gestion Comercial", marca),
        Paragraph(_limpio(datos.get("titulo") or "Informe"), titulo),
        Paragraph(f"Generado por el agente el {ahora} (hora de Lima)", marca),
        Spacer(1, 6),
    ]
    grafico = datos.get("grafico")
    if grafico and grafico.get("labels"):
        historia += [_dibujo(grafico), Spacer(1, 4)]
    for bloque in datos.get("secciones", []):
        historia.append(Paragraph(_limpio(bloque.get("titulo", "")), seccion))
        for linea in bloque.get("lineas", []):
            historia.append(Paragraph(f"- {_limpio(linea)}", normal))

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=letter, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=_limpio(datos.get("titulo") or "Informe"),
    ).build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_grafico(datos: Dict[str, Any]) -> io.BytesIO:
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("N", parent=estilos["Normal"], fontSize=9, leading=12)
    titulo = ParagraphStyle("T", parent=estilos["Title"], fontSize=15, leading=19, alignment=0, textColor=colors.HexColor("#0f172a"))
    marca = ParagraphStyle("M", parent=normal, fontSize=8, textColor=colors.HexColor("#64748b"))
    seccion = ParagraphStyle("S", parent=normal, fontName="Helvetica-Bold", fontSize=10, spaceBefore=8, spaceAfter=3)

    prefijo = datos.get("prefijo", "")
    etiquetas = datos.get("labels", [])
    series = datos.get("series", [])
    ahora = ahora_lima().strftime("%d/%m/%Y %H:%M")

    historia: List[Any] = [
        Paragraph("EL PRINCIPE - Sistema de Gestion Comercial", marca),
        Paragraph(_limpio(datos.get("titulo") or "Grafico"), titulo),
        Paragraph(f"Generado el {ahora} (hora de Lima)", marca),
        Spacer(1, 6),
        _dibujo(datos),
        Spacer(1, 8),
        Paragraph("Datos del grafico", seccion),
    ]

    cabecera = ["Etiqueta"] + [_limpio(s.get("nombre", "Valor")) for s in series]
    filas = [cabecera]
    for i, etiqueta in enumerate(etiquetas):
        fila = [_limpio(etiqueta)]
        for s in series:
            valores = s.get("valores", [])
            fila.append(_numero(valores[i], prefijo) if i < len(valores) else "-")
        filas.append(fila)
    tabla = Table(filas, repeatRows=1, hAlign="LEFT")
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    historia.append(tabla)

    explicacion = datos.get("explicacion") or {}
    if explicacion:
        historia.append(Paragraph("Como se calculo", seccion))
        if explicacion.get("resumen"):
            historia.append(Paragraph(_limpio(explicacion["resumen"]), normal))
        for fuente in explicacion.get("fuentes", []) or []:
            historia.append(Paragraph(f"- {_limpio(fuente)}", normal))
        if explicacion.get("periodo"):
            historia.append(Paragraph(f"<b>Periodo:</b> {_limpio(explicacion['periodo'])}", normal))
        if explicacion.get("formula"):
            historia.append(Paragraph(f"<b>Formula:</b> {_limpio(explicacion['formula'])}", normal))

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=letter, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=_limpio(datos.get("titulo") or "Grafico"),
    ).build(historia)
    buffer.seek(0)
    return buffer
