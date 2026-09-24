import io
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.customer import Cliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.services.indicator_service import IndicatorService


class ReportService:
    @staticmethod
    def _kpi_cards(kpis: List[Tuple[str, str, str]]) -> Table:
        styles = getSampleStyleSheet()
        label_style = ParagraphStyle(
            "KpiLabel", parent=styles["Normal"], fontSize=7,
            textColor=colors.HexColor("#64748b"), leading=9,
        )
        tarjetas = []
        for label, valor, color in kpis:
            valor_style = ParagraphStyle(
                "KpiValor", parent=styles["Normal"], fontSize=16,
                textColor=colors.HexColor(color), leading=18, fontName="Helvetica-Bold",
            )
            contenido = Table(
                [[Paragraph(label.upper(), label_style)], [Paragraph(str(valor), valor_style)]],
                colWidths=[125],
            )
            contenido.setStyle(TableStyle([
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]))
            tarjeta = Table([[contenido]], colWidths=[135])
            tarjeta.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor(color)),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]))
            tarjetas.append(tarjeta)
        fila = Table([tarjetas], hAlign="LEFT")
        fila.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return fila

    @staticmethod
    def _grafico_barras(datos: Dict[str, float], titulo: str, color: str = "#1E3A8A") -> Drawing:
        d = Drawing(460, 190)
        d.add(String(0, 178, titulo, fontSize=8, fillColor=colors.HexColor("#334155")))
        bc = VerticalBarChart()
        bc.x = 40
        bc.y = 25
        bc.height = 130
        bc.width = 400
        bc.data = [list(datos.values())]
        bc.categoryAxis.categoryNames = list(datos.keys())
        bc.categoryAxis.labels.fontSize = 7
        bc.valueAxis.labels.fontSize = 7
        bc.valueAxis.valueMin = 0
        bc.bars[0].fillColor = colors.HexColor(color)
        bc.barWidth = 12
        bc.groupSpacing = 12
        d.add(bc)
        return d

    @staticmethod
    def _grafico_barras_comparativo(
        categorias: List[str], series: Dict[str, List[float]], titulo: str
    ) -> Drawing:
        paleta = ["#1E3A8A", "#94a3b8", "#ea580c"]
        d = Drawing(460, 200)
        d.add(String(0, 188, titulo, fontSize=8, fillColor=colors.HexColor("#334155")))
        bc = VerticalBarChart()
        bc.x = 40
        bc.y = 35
        bc.height = 130
        bc.width = 340
        bc.data = list(series.values())
        bc.categoryAxis.categoryNames = categorias
        bc.categoryAxis.labels.fontSize = 7
        bc.valueAxis.labels.fontSize = 7
        bc.valueAxis.valueMin = 0
        bc.barWidth = 9
        bc.groupSpacing = 16
        for i in range(len(series)):
            bc.bars[i].fillColor = colors.HexColor(paleta[i % len(paleta)])
        d.add(bc)

        leyenda = Legend()
        leyenda.x = 390
        leyenda.y = 110
        leyenda.dx = 8
        leyenda.dy = 8
        leyenda.fontSize = 7
        leyenda.alignment = "left"
        leyenda.colorNamePairs = [
            (colors.HexColor(paleta[i % len(paleta)]), nombre) for i, nombre in enumerate(series.keys())
        ]
        d.add(leyenda)
        return d

    @staticmethod
    def _grafico_pie(datos: Dict[str, float], titulo: str, colores_lista: Optional[List[str]] = None) -> Drawing:
        paleta = colores_lista or ["#1e3a8a", "#3b82f6", "#f97316", "#dc2626", "#16a34a", "#94a3b8"]
        d = Drawing(460, 180)
        d.add(String(0, 168, titulo, fontSize=8, fillColor=colors.HexColor("#334155")))
        pie = Pie()
        pie.x = 60
        pie.y = 10
        pie.width = 130
        pie.height = 130
        pie.data = list(datos.values())
        pie.labels = [f"{k} ({v})" for k, v in datos.items()]
        pie.slices.strokeWidth = 0.75
        pie.slices.strokeColor = colors.white
        pie.simpleLabels = 0
        pie.slices.fontSize = 7
        for i in range(len(datos)):
            pie.slices[i].fillColor = colors.HexColor(paleta[i % len(paleta)])
        d.add(pie)
        return d

    @staticmethod
    def _crear_pdf_base(
        titulo: str,
        columnas: list,
        filas: list,
        kpis: Optional[List[Tuple[str, str, str]]] = None,
        graficos: Optional[List[Drawing]] = None,
    ) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=24,
            leftMargin=24,
            topMargin=24,
            bottomMargin=24,
        )
        elements = []
        styles = getSampleStyleSheet()

        cell_style = ParagraphStyle(
            "CellStyle",
            parent=styles["Normal"],
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#0f172a"),
        )
        header_style = ParagraphStyle(
            "HeaderStyle",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.whitesmoke,
            fontName="Helvetica-Bold",
        )

        elements.append(Paragraph("<b>EL PRÍNCIPE</b>", styles["Heading1"]))
        elements.append(Paragraph(f"<b>Reporte:</b> {titulo}", styles["Heading2"]))
        elements.append(
            Paragraph(
                f"Fecha de emisión: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 12))

        if kpis:
            elements.append(ReportService._kpi_cards(kpis))
            elements.append(Spacer(1, 16))

        if graficos:
            for grafico in graficos:
                elements.append(grafico)
                elements.append(Spacer(1, 8))
            elements.append(Spacer(1, 8))

        header_row = [Paragraph(str(col), header_style) for col in columnas]
        table_rows = [header_row]

        for fila in filas:
            table_rows.append(
                [
                    Paragraph(str(celda if celda is not None else "—"), cell_style)
                    for celda in fila
                ]
            )

        t = Table(table_rows, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                    ("TOPPADDING", (0, 0), (-1, 0), 5),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F8FAFC")],
                    ),
                ]
            )
        )
        elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        return buffer

    @staticmethod
    def _agregar_hoja_resumen_excel(
        writer,
        headers: List[str],
        filas: List[tuple],
        titulo: str,
        tipo: str = "bar",
        nombre_hoja: str = "Resumen",
    ) -> None:
        wb = writer.book
        ws = wb.create_sheet(nombre_hoja)
        ws.append(headers)
        for celda in ws[1]:
            celda.font = Font(bold=True)
        for fila in filas:
            ws.append(list(fila))

        n_filas = len(filas)
        n_series = len(headers) - 1
        data_ref = Reference(ws, min_col=2, max_col=1 + n_series, min_row=1, max_row=1 + n_filas)
        cat_ref = Reference(ws, min_col=1, min_row=2, max_row=1 + n_filas)

        chart = PieChart() if tipo == "pie" else BarChart()
        if tipo != "pie":
            chart.type = "col"
            chart.style = 10
        chart.title = titulo
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cat_ref)
        chart.height = 8.5
        chart.width = 16
        ws.add_chart(chart, "E2")

    @staticmethod
    def generate_orders_excel(db: Session, desde=None, hasta=None) -> io.BytesIO:
        stmt = select(Pedido).options(selectinload(Pedido.cliente))
        if desde is not None:
            stmt = stmt.where(Pedido.fecha_pedido >= desde)
        if hasta is not None:
            stmt = stmt.where(Pedido.fecha_pedido <= hasta)
        orders = db.scalars(stmt).all()
        data = [
            {
                "Código": o.codigo_pedido,
                "Cliente": (
                    o.cliente.razon_social if o.cliente else f"ID {o.cliente_id}"
                ),
                "RUC/DNI": o.cliente.ruc_dni if o.cliente else "—",
                "Fecha": (
                    o.fecha_pedido.strftime("%Y-%m-%d %H:%M") if o.fecha_pedido else "—"
                ),
                "Fecha Entrega": (
                    o.fecha_entrega.strftime("%Y-%m-%d %H:%M")
                    if o.fecha_entrega
                    else "—"
                ),
                "Forma de Pago": str(o.forma_pago),
                "Estado": str(o.estado),
                "Monto Total (S/)": float(o.monto_total),
                "Observaciones": o.observaciones or "",
            }
            for o in orders
        ]
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Pedidos")

            orden_estados = ["Pendiente", "Aprobado", "Entregado", "Cancelado"]
            conteo = Counter(str(o.estado) for o in orders)
            ReportService._agregar_hoja_resumen_excel(
                writer,
                headers=["Estado", "Cantidad de Pedidos"],
                filas=[(e, conteo.get(e, 0)) for e in orden_estados],
                titulo="Pedidos por Estado",
                tipo="bar",
            )
        output.seek(0)
        return output

    @staticmethod
    def generate_inventory_excel(db: Session) -> io.BytesIO:
        products = db.scalars(select(Producto)).all()
        data = [
            {
                "SKU": p.sku,
                "Nombre": p.nombre,
                "Unidad": p.unidad_medida,
                "Stock Actual": p.stock_actual,
                "Stock Mínimo": p.stock_minimo,
                "Precio Costo (S/)": float(p.precio_costo),
                "Precio Venta (S/)": float(p.precio_unitario),
                "Rotación": str(p.nivel_rotacion),
                "Estado Stock": "Crítico" if p.stock_actual <= p.stock_minimo else "OK",
            }
            for p in products
        ]
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Inventario")

            conteo_rotacion = Counter(str(p.nivel_rotacion or "Sin definir") for p in products)
            ReportService._agregar_hoja_resumen_excel(
                writer,
                headers=["Nivel de Rotación", "Cantidad de Productos"],
                filas=list(conteo_rotacion.items()),
                titulo="Productos por Nivel de Rotación",
                tipo="pie",
            )
        output.seek(0)
        return output

    @staticmethod
    def generate_customers_excel(db: Session) -> io.BytesIO:
        customers = db.scalars(select(Cliente)).all()
        data = [
            {
                "Tipo Doc": "RUC" if c.ruc_dni and len(c.ruc_dni) == 11 else "DNI",
                "N° Documento": c.ruc_dni or "—",
                "Razón Social / Nombre": c.razon_social or "—",
                "Tipo Cliente": str(getattr(c, "tipo_cliente", "") or "—"),
                "Dirección": str(getattr(c, "direccion", "") or ""),
                "Distrito": str(getattr(c, "distrito", "") or ""),
                "Teléfono": str(getattr(c, "telefono", "") or ""),
                "Correo": str(getattr(c, "correo", "") or ""),
                "Estado": str(getattr(c, "estado", "") or "Activo"),
            }
            for c in customers
        ]
        df = pd.DataFrame(
            data
            if data
            else [
                {
                    "Tipo Doc": "—",
                    "N° Documento": "—",
                    "Razón Social / Nombre": "—",
                    "Tipo Cliente": "—",
                    "Dirección": "",
                    "Distrito": "",
                    "Teléfono": "",
                    "Correo": "",
                    "Estado": "—",
                }
            ]
        )
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Clientes")

            if customers:
                conteo_tipo = Counter(str(getattr(c, "tipo_cliente", None) or "Sin definir") for c in customers)
                ReportService._agregar_hoja_resumen_excel(
                    writer,
                    headers=["Tipo de Cliente", "Cantidad"],
                    filas=list(conteo_tipo.items()),
                    titulo="Clientes por Tipo",
                    tipo="pie",
                )
        output.seek(0)
        return output

    @staticmethod
    def generate_order_errors_excel(db: Session, desde=None, hasta=None) -> io.BytesIO:
        stmt = (
            select(DetallePedido)
            .join(Pedido)
            .options(
                selectinload(DetallePedido.pedido).selectinload(Pedido.cliente),
                selectinload(DetallePedido.producto),
            )
            .where(DetallePedido.tiene_error == True)
        )
        if desde is not None:
            stmt = stmt.where(Pedido.fecha_pedido >= desde)
        if hasta is not None:
            stmt = stmt.where(Pedido.fecha_pedido <= hasta)
        detalles_error = db.scalars(stmt).all()
        data = [
            {
                "N° Pedido": d.pedido.codigo_pedido if d.pedido else "—",
                "Cliente": (
                    d.pedido.cliente.razon_social
                    if d.pedido and d.pedido.cliente
                    else "—"
                ),
                "Producto": d.producto.nombre if d.producto else "—",
                "Cantidad": d.cantidad,
                "Tipo de Error": str(d.tipo_error),
                "Detalle / Observación": d.descripcion_error
                or d.pedido.observaciones
                or "",
                "Fecha Pedido": (
                    d.pedido.fecha_pedido.strftime("%Y-%m-%d")
                    if d.pedido and d.pedido.fecha_pedido
                    else "—"
                ),
                "Estado Pedido": str(d.pedido.estado) if d.pedido else "—",
            }
            for d in detalles_error
        ]
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Errores_Pedidos")

            if detalles_error:
                conteo_tipo_error = Counter(str(d.tipo_error) for d in detalles_error)
                ReportService._agregar_hoja_resumen_excel(
                    writer,
                    headers=["Tipo de Error", "Cantidad"],
                    filas=list(conteo_tipo_error.items()),
                    titulo="Distribución por Tipo de Error",
                    tipo="pie",
                )
        output.seek(0)
        return output

    @staticmethod
    def generate_indicators_excel(db: Session) -> io.BytesIO:
        pedidos = list(
            db.scalars(select(Pedido).options(selectinload(Pedido.detalles))).all()
        )
        total_pedidos_items = sum(len(p.detalles) for p in pedidos)
        detalles_con_error = sum(
            1 for p in pedidos for d in p.detalles if d.tiene_error
        )
        nepp = (
            (detalles_con_error / total_pedidos_items)
            if total_pedidos_items > 0
            else 0.0
        )

        indicador = IndicatorService.get_latest(db) or IndicatorService.calculate_and_save(
            db, resumen="Cálculo automático para reporte Excel"
        )
        pfcc = float(indicador.valor_pfcc or 0)
        ntdc = float(indicador.valor_ntdc or 0)

        data = [
            {
                "Sigla": "NEPP",
                "Indicador": "Número de errores en los productos pedidos",
                "Fórmula": "NEPP = TEPP ÷ TPP",
                "Valor Numérico": round(nepp, 4),
                "Formato Presentación": f"{round(nepp * 100, 2)}%",
                "Meta": "< 0.05",
                "Detalle Muestra": f"{detalles_con_error} errores de {total_pedidos_items} ítems registrados",
            },
            {
                "Sigla": "PFCC",
                "Indicador": "Porcentaje de fallas al definir condiciones comerciales",
                "Fórmula": "PFCC = (TCCF ÷ TCCD) × 100",
                "Valor Numérico": round(pfcc / 100, 4),
                "Formato Presentación": f"{round(pfcc, 2)}%",
                "Meta": "< 10%",
                "Detalle Muestra": f"{indicador.total_fallas_condiciones} fallas de {indicador.total_condiciones_pactadas} condiciones registradas",
            },
            {
                "Sigla": "NTDC",
                "Indicador": "Nivel de toma de decisiones comerciales",
                "Fórmula": "NTDC = (TDCE ÷ TDCT) × 100",
                "Valor Numérico": round(ntdc / 100, 4),
                "Formato Presentación": f"{round(ntdc, 2)}%",
                "Meta": "≥ 75%",
                "Detalle Muestra": (
                    f"{indicador.total_decisiones_efectivas} decisiones efectivas de "
                    f"{indicador.total_decisiones_evaluadas} registradas "
                    f"({indicador.total_decisiones_corregidas} corregidas tras incidencia)"
                ),
            },
        ]
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Indicadores")

            ReportService._agregar_hoja_resumen_excel(
                writer,
                headers=["Indicador", "Actual (%)", "Meta (%)"],
                filas=[
                    ("NEPP", round(nepp * 100, 2), 5),
                    ("PFCC", round(pfcc, 2), 10),
                    ("NTDC", round(ntdc, 2), 75),
                ],
                titulo="Indicadores vs. Meta (%)",
                tipo="bar",
            )
        output.seek(0)
        return output

    @staticmethod
    def generate_orders_pdf(db: Session, desde=None, hasta=None) -> io.BytesIO:
        stmt = select(Pedido).options(selectinload(Pedido.cliente))
        if desde is not None:
            stmt = stmt.where(Pedido.fecha_pedido >= desde)
        if hasta is not None:
            stmt = stmt.where(Pedido.fecha_pedido <= hasta)
        orders = db.scalars(stmt).all()
        columnas = ["Código", "Cliente", "Fecha", "Forma Pago", "Estado", "Total (S/)"]
        filas = [
            [
                str(o.codigo_pedido),
                str(o.cliente.razon_social if o.cliente else f"ID {o.cliente_id}"),
                o.fecha_pedido.strftime("%Y-%m-%d") if o.fecha_pedido else "—",
                str(o.forma_pago),
                str(o.estado),
                f"S/ {float(o.monto_total):,.2f}",
            ]
            for o in orders
        ]

        total_pedidos = len(orders)
        monto_total = sum(float(o.monto_total or 0) for o in orders)
        ticket_prom = monto_total / total_pedidos if total_pedidos else 0
        kpis = [
            ("Total Pedidos", str(total_pedidos), "#1E3A8A"),
            ("Monto Total", f"S/ {monto_total:,.2f}", "#16a34a"),
            ("Ticket Promedio", f"S/ {ticket_prom:,.2f}", "#ea580c"),
        ]

        orden_estados = ["Pendiente", "Aprobado", "Entregado", "Cancelado"]
        conteo = Counter(str(o.estado) for o in orders)
        grafico = ReportService._grafico_barras(
            {e: conteo.get(e, 0) for e in orden_estados}, "Pedidos por Estado"
        )

        return ReportService._crear_pdf_base(
            "Reporte de Pedidos", columnas, filas, kpis=kpis, graficos=[grafico]
        )

    @staticmethod
    def generate_inventory_pdf(db: Session) -> io.BytesIO:
        products = db.scalars(select(Producto)).all()
        columnas = [
            "SKU",
            "Producto",
            "Unidad",
            "Stock",
            "Mínimo",
            "Precio (S/)",
            "Rotación",
        ]
        filas = [
            [
                str(p.sku),
                str(p.nombre),
                str(p.unidad_medida),
                str(p.stock_actual),
                str(p.stock_minimo),
                f"S/ {float(p.precio_unitario):.2f}",
                str(p.nivel_rotacion),
            ]
            for p in products
        ]

        total_productos = len(products)
        criticos = sum(1 for p in products if (p.stock_actual or 0) <= (p.stock_minimo or 0))
        valor_inventario = sum(float(p.precio_costo or 0) * (p.stock_actual or 0) for p in products)
        kpis = [
            ("Total Productos", str(total_productos), "#1E3A8A"),
            ("Stock Crítico", str(criticos), "#dc2626"),
            ("Valor Inventario", f"S/ {valor_inventario:,.2f}", "#16a34a"),
        ]

        conteo_rotacion = Counter(str(p.nivel_rotacion or "Sin definir") for p in products)
        graficos = [ReportService._grafico_pie(dict(conteo_rotacion), "Productos por Nivel de Rotación")] if products else []

        return ReportService._crear_pdf_base(
            "Catálogo de Inventario", columnas, filas, kpis=kpis, graficos=graficos
        )

    @staticmethod
    def generate_customers_pdf(db: Session) -> io.BytesIO:
        customers = db.scalars(select(Cliente)).all()
        columnas = ["N° Doc", "Razón Social", "Tipo", "Distrito", "Teléfono", "Estado"]
        filas = [
            [
                str(c.ruc_dni or "—"),
                str(c.razon_social or "—"),
                str(getattr(c, "tipo_cliente", "") or "—"),
                str(getattr(c, "distrito", "") or "—"),
                str(getattr(c, "telefono", "") or "—"),
                str(getattr(c, "estado", "") or "Activo"),
            ]
            for c in customers
        ]
        if not filas:
            filas = [["—", "Sin registros", "—", "—", "—", "—"]]

        kpis = [("Total Clientes", str(len(customers)), "#1E3A8A")]
        graficos = []
        if customers:
            conteo_tipo = Counter(str(getattr(c, "tipo_cliente", None) or "Sin definir") for c in customers)
            graficos.append(ReportService._grafico_pie(dict(conteo_tipo), "Clientes por Tipo"))

        return ReportService._crear_pdf_base(
            "Cartera de Clientes", columnas, filas, kpis=kpis, graficos=graficos
        )

    @staticmethod
    def generate_order_errors_pdf(db: Session, desde=None, hasta=None) -> io.BytesIO:
        stmt = (
            select(DetallePedido)
            .join(Pedido)
            .options(
                selectinload(DetallePedido.pedido).selectinload(Pedido.cliente),
                selectinload(DetallePedido.producto),
            )
            .where(DetallePedido.tiene_error == True)
        )
        if desde is not None:
            stmt = stmt.where(Pedido.fecha_pedido >= desde)
        if hasta is not None:
            stmt = stmt.where(Pedido.fecha_pedido <= hasta)
        detalles_error = db.scalars(stmt).all()
        columnas = ["N° Pedido", "Cliente", "Producto", "Cant.", "Tipo Error", "Fecha"]
        filas = [
            [
                str(d.pedido.codigo_pedido if d.pedido else "—"),
                str(
                    d.pedido.cliente.razon_social
                    if d.pedido and d.pedido.cliente
                    else "—"
                ),
                str(d.producto.nombre if d.producto else "—"),
                str(d.cantidad),
                str(d.tipo_error or "—"),
                (
                    d.pedido.fecha_pedido.strftime("%Y-%m-%d")
                    if d.pedido and d.pedido.fecha_pedido
                    else "—"
                ),
            ]
            for d in detalles_error
        ]

        total_errores = len(detalles_error)
        pedidos_afectados = len({d.pedido_id for d in detalles_error})
        kpis = [
            ("Total Errores", str(total_errores), "#dc2626"),
            ("Pedidos Afectados", str(pedidos_afectados), "#ea580c"),
        ]
        graficos = []
        if detalles_error:
            conteo_tipo_error = Counter(str(d.tipo_error) for d in detalles_error)
            graficos.append(
                ReportService._grafico_pie(
                    dict(conteo_tipo_error),
                    "Distribución por Tipo de Error",
                    colores_lista=["#dc2626", "#ea580c", "#f59e0b", "#b91c1c"],
                )
            )

        return ReportService._crear_pdf_base(
            "Pedidos con Errores Detectados", columnas, filas, kpis=kpis, graficos=graficos
        )

    @staticmethod
    def generate_indicators_pdf(db: Session) -> io.BytesIO:
        pedidos = list(
            db.scalars(select(Pedido).options(selectinload(Pedido.detalles))).all()
        )
        total_pedidos_items = sum(len(p.detalles) for p in pedidos)
        detalles_con_error = sum(
            1 for p in pedidos for d in p.detalles if d.tiene_error
        )
        nepp = (
            (detalles_con_error / total_pedidos_items)
            if total_pedidos_items > 0
            else 0.0
        )

        indicador = IndicatorService.get_latest(db) or IndicatorService.calculate_and_save(
            db, resumen="Cálculo automático para reporte PDF"
        )
        pfcc = float(indicador.valor_pfcc or 0)
        ntdc = float(indicador.valor_ntdc or 0)

        columnas = ["Sigla", "Indicador", "Fórmula", "Valor", "Meta", "Muestra"]
        filas = [
            [
                "NEPP",
                "Errores en productos pedidos",
                "TEPP ÷ TPP",
                f"{round(nepp, 4)} ({round(nepp * 100, 2)}%)",
                "< 0.05",
                f"{detalles_con_error} / {total_pedidos_items}",
            ],
            [
                "PFCC",
                "Fallas en condiciones comerciales",
                "(TCCF ÷ TCCD) × 100",
                f"{round(pfcc, 2)}%",
                "< 10%",
                f"{indicador.total_fallas_condiciones} / {indicador.total_condiciones_pactadas}",
            ],
            [
                "NTDC",
                "Toma de decisiones comerciales",
                "(TDCE ÷ TDCT) × 100",
                f"{round(ntdc, 2)}%",
                "≥ 75%",
                f"{indicador.total_decisiones_efectivas} / {indicador.total_decisiones_evaluadas}",
            ],
        ]

        kpis = [
            ("NEPP", f"{round(nepp * 100, 2)}%", "#dc2626" if nepp > 0.10 else ("#ea580c" if nepp > 0.05 else "#16a34a")),
            ("PFCC", f"{round(pfcc, 2)}%", "#dc2626" if pfcc > 25 else ("#ea580c" if pfcc > 10 else "#16a34a")),
            ("NTDC", f"{round(ntdc, 2)}%", "#16a34a" if ntdc >= 75 else ("#ea580c" if ntdc >= 50 else "#dc2626")),
        ]
        grafico = ReportService._grafico_barras_comparativo(
            ["NEPP", "PFCC", "NTDC"],
            {
                "Actual (%)": [round(nepp * 100, 2), round(pfcc, 2), round(ntdc, 2)],
                "Meta (%)": [5, 10, 75],
            },
            "Indicadores vs. Meta (%)",
        )

        return ReportService._crear_pdf_base(
            "Indicadores Comerciales (NEPP · PFCC · NTDC)",
            columnas,
            filas,
            kpis=kpis,
            graficos=[grafico],
        )