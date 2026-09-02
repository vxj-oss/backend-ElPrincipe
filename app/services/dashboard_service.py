from decimal import Decimal
from typing import Any, Dict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Cliente
from app.models.order import Pedido
from app.models.product import Producto
from app.services.indicator_service import IndicatorService


class DashboardService:
    @staticmethod
    def get_summary(db: Session) -> Dict[str, Any]:
        total_clientes = db.scalar(select(func.count(Cliente.id))) or 0
        total_productos = db.scalar(select(func.count(Producto.id))) or 0
        total_pedidos = db.scalar(select(func.count(Pedido.id))) or 0

        ventas_totales = (
            db.scalar(
                select(func.sum(Pedido.monto_total)).where(Pedido.estado != "Cancelado")
            )
            or Decimal("0.00")
        )

        pedidos_pendientes = (
            db.scalar(select(func.count(Pedido.id)).where(Pedido.estado == "Pendiente")) or 0
        )
        pedidos_aprobados = (
            db.scalar(select(func.count(Pedido.id)).where(Pedido.estado == "Aprobado")) or 0
        )
        pedidos_entregados = (
            db.scalar(select(func.count(Pedido.id)).where(Pedido.estado == "Entregado")) or 0
        )

        indicador_actual = IndicatorService.get_latest(db)

        return {
            "metricas": {
                "total_clientes": total_clientes,
                "total_productos": total_productos,
                "total_pedidos": total_pedidos,
                "ventas_totales": float(ventas_totales),
            },
            "pedidos_por_estado": {
                "pendientes": pedidos_pendientes,
                "aprobados": pedidos_aprobados,
                "entregados": pedidos_entregados,
            },
            "indicadores_kpi": {
                "nepp": float(indicador_actual.valor_nepp) if indicador_actual and indicador_actual.valor_nepp else 0.0,
                "pfcc": float(indicador_actual.valor_pfcc) if indicador_actual and indicador_actual.valor_pfcc else 0.0,
                "ntdc": float(indicador_actual.valor_ntdc) if indicador_actual and indicador_actual.valor_ntdc else 0.0,
            },
        }