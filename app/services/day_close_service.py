import io
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.metas import color_conteo, color_tiempo, descripcion_conteo, descripcion_tiempo
from app.core.time import LIMA_TZ, ahora_lima
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.services.activity_indicator_service import ActivityIndicatorService
from app.services.report_service import ReportService

ESTADOS_CONFIRMADOS = ("Aprobado", "Entregado")
MAX_FILAS_PEDIDOS = 40
MAX_FILAS_SIN_ATENDER = 15

COLORES_SEMAFORO = {
    "verde": ("#dcfce7", "#166534"),
    "naranja": ("#ffedd5", "#9a3412"),
    "rojo": ("#fee2e2", "#991b1b"),
    None: ("#f1f5f9", "#64748b"),
}


def _hora(valor: Optional[datetime]) -> str:
    return valor.astimezone(LIMA_TZ).strftime("%H:%M") if valor else "—"


def _estilo_tabla(extra: Optional[list] = None) -> TableStyle:
    comandos = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]
    return TableStyle(comandos + (extra or []))


def generar_cierre_dia_pdf(db: Session, dia: Optional[date] = None) -> io.BytesIO:
    dia = dia or ahora_lima().date()
    inicio = datetime.combine(dia, time(0, 0), tzinfo=LIMA_TZ)
    fin = inicio + timedelta(days=1)

    pedidos = list(
        db.scalars(
            select(Pedido)
            .options(selectinload(Pedido.cliente))
            .where(Pedido.fecha_pedido >= inicio, Pedido.fecha_pedido < fin)
            .order_by(Pedido.fecha_pedido.asc())
        ).all()
    )
    confirmados = [p for p in pedidos if str(p.estado) in ESTADOS_CONFIRMADOS]
    ventas = sum(float(p.monto_total or 0) for p in confirmados)

    cotizaciones = list(
        db.scalars(
            select(SolicitudCliente)
            .options(selectinload(SolicitudCliente.detalles), selectinload(SolicitudCliente.cliente))
            .where(SolicitudCliente.fecha_solicitud >= inicio, SolicitudCliente.fecha_solicitud < fin)
            .order_by(SolicitudCliente.fecha_solicitud.asc())
        ).all()
    )

    total_sin_atender = db.scalar(
        select(func.count(SolicitudCliente.id)).where(SolicitudCliente.estado == "Pendiente")
    ) or 0
    sin_atender = list(
        db.scalars(
            select(SolicitudCliente)
            .options(selectinload(SolicitudCliente.detalles), selectinload(SolicitudCliente.cliente))
            .where(SolicitudCliente.estado == "Pendiente")
            .order_by(SolicitudCliente.id.desc())
            .limit(MAX_FILAS_SIN_ATENDER)
        ).all()
    )
    pedidos_pendientes = db.scalar(
        select(func.count(Pedido.id)).where(Pedido.estado == "Pendiente")
    ) or 0

    ncca = ActivityIndicatorService._contar_solicitudes(db, inicio, fin)
    npp = ActivityIndicatorService._contar_pedidos(db, inicio, fin)
    tptd_dec = ActivityIndicatorService._tiempo_promedio_decision_segundos(db, inicio, fin)
    tptd = round(float(tptd_dec)) if tptd_dec is not None else None

    estilos = getSampleStyleSheet()
    celda = ParagraphStyle("Celda", parent=estilos["Normal"], fontSize=8, leading=10)
    cabecera = ParagraphStyle(
        "Cabecera", parent=estilos["Normal"], fontSize=8, leading=10,
        textColor=colors.whitesmoke, fontName="Helvetica-Bold",
    )
    seccion = ParagraphStyle(
        "Seccion", parent=estilos["Heading3"], textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=14, spaceAfter=6, keepWithNext=1,
    )

    def tabla(columnas: List[str], filas: List[List[str]], anchos=None, extra=None) -> Table:
        datos = [[Paragraph(c, cabecera) for c in columnas]]
        datos += [[Paragraph(str(v), celda) for v in fila] for fila in filas]
        t = Table(datos, repeatRows=1, colWidths=anchos)
        t.setStyle(_estilo_tabla(extra))
        return t

    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28
    )
    elementos = [
        Paragraph("<b>EL PRÍNCIPE</b>", estilos["Heading1"]),
        Paragraph(f"<b>Cierre del día — {dia.strftime('%d/%m/%Y')}</b>", estilos["Heading2"]),
        Paragraph(f"Fecha de emisión: {ahora_lima().strftime('%d/%m/%Y %H:%M')}", estilos["Normal"]),
        Spacer(1, 12),
        ReportService._kpi_cards(
            [
                ("Ventas del día", f"S/ {ventas:,.2f}", "#16a34a"),
                ("Pedidos confirmados", str(len(confirmados)), "#1E3A8A"),
                ("Cotizaciones del día", str(len(cotizaciones)), "#ea580c"),
                ("Pedidos pendientes", str(pedidos_pendientes), "#dc2626"),
            ]
        ),
    ]

    elementos.append(Paragraph("Indicadores del día", seccion))
    descripcion_ncca = descripcion_conteo("NCCA", "cotizaciones")
    descripcion_npp = descripcion_conteo("NPP", "pedidos")
    descripcion_tptd = descripcion_tiempo()
    semaforos = [
        color_conteo("NCCA", ncca),
        color_conteo("NPP", npp),
        color_tiempo(tptd) if tptd is not None else None,
    ]
    filas_indicadores = [
        ["Cotizaciones atendidas (NCCA)", str(ncca), semaforos[0] or "sin datos", descripcion_ncca["meta"]],
        ["Pedidos procesados (NPP)", str(npp), semaforos[1] or "sin datos", descripcion_npp["meta"]],
        [
            "Tiempo promedio de decisión (TPTD)",
            f"{tptd} s" if tptd is not None else "sin pedidos aprobados",
            semaforos[2] or "sin datos",
            descripcion_tptd["meta"],
        ],
    ]
    extra = []
    for fila, color in enumerate(semaforos, start=1):
        fondo, _ = COLORES_SEMAFORO[color]
        extra.append(("BACKGROUND", (2, fila), (2, fila), colors.HexColor(fondo)))
    elementos.append(
        tabla(["Indicador", "Valor", "Semáforo", "Meta"], filas_indicadores, [190, 110, 80, 150], extra)
    )

    elementos.append(Paragraph(f"Pedidos del día ({len(pedidos)})", seccion))
    if pedidos:
        filas = [
            [
                p.codigo_pedido,
                p.cliente.razon_social if p.cliente else "Cliente general",
                str(p.estado),
                _hora(p.fecha_pedido),
                f"S/ {float(p.monto_total or 0):,.2f}",
            ]
            for p in pedidos[:MAX_FILAS_PEDIDOS]
        ]
        elementos.append(tabla(["Código", "Cliente", "Estado", "Hora", "Total"], filas, [90, 200, 70, 50, 70]))
        if len(pedidos) > MAX_FILAS_PEDIDOS:
            elementos.append(Paragraph(f"Se muestran {MAX_FILAS_PEDIDOS} de {len(pedidos)} pedidos.", celda))
    else:
        elementos.append(Paragraph("No se registraron pedidos en este día.", celda))

    elementos.append(Paragraph(f"Cotizaciones del día ({len(cotizaciones)})", seccion))
    if cotizaciones:
        filas = [
            [
                c.codigo_solicitud,
                c.cliente.razon_social if c.cliente else f"Cliente #{c.cliente_id}",
                str(c.estado),
                str(len(c.detalles)),
                _hora(c.fecha_solicitud),
            ]
            for c in cotizaciones[:MAX_FILAS_PEDIDOS]
        ]
        elementos.append(tabla(["Código", "Cliente", "Estado", "Ítems", "Hora"], filas, [100, 200, 70, 40, 70]))
    else:
        elementos.append(Paragraph("No se registraron cotizaciones en este día.", celda))

    elementos.append(Paragraph(f"Cotizaciones sin atender ({total_sin_atender})", seccion))
    if sin_atender:
        ahora = ahora_lima()
        filas = [
            [
                c.codigo_solicitud,
                c.cliente.razon_social if c.cliente else f"Cliente #{c.cliente_id}",
                c.fecha_solicitud.astimezone(LIMA_TZ).strftime("%d/%m/%Y"),
                f"{max(0, (ahora - c.fecha_solicitud).days)} días",
            ]
            for c in sin_atender
        ]
        elementos.append(tabla(["Código", "Cliente", "Fecha", "Antigüedad"], filas, [100, 220, 80, 80]))
        if total_sin_atender > len(sin_atender):
            elementos.append(
                Paragraph(f"Se muestran las {len(sin_atender)} más recientes de {total_sin_atender}.", celda)
            )
    else:
        elementos.append(Paragraph("No hay cotizaciones pendientes.", celda))

    documento.build(elementos)
    buffer.seek(0)
    return buffer
