import io
from datetime import datetime
from typing import Any, Dict
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
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
    def _crear_pdf_base(titulo: str, columnas: list, filas: list) -> io.BytesIO:
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
        return ReportService._crear_pdf_base("Reporte de Pedidos", columnas, filas)

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
        return ReportService._crear_pdf_base("Catálogo de Inventario", columnas, filas)

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
        return ReportService._crear_pdf_base("Cartera de Clientes", columnas, filas)

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
        return ReportService._crear_pdf_base(
            "Pedidos con Errores Detectados", columnas, filas
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
        return ReportService._crear_pdf_base(
            "Indicadores Comerciales (NEPP · PFCC · NTDC)", columnas, filas
        )