from decimal import Decimal
from typing import Any, Dict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Cliente
from app.models.order import Pedido
from app.models.product import Producto
from app.services.config_service import ConfigService
from app.services.indicator_service import IndicatorService

ESTADOS_CONFIRMADOS = ("Aprobado", "Entregado")


class DashboardService:
    @staticmethod
    def get_summary(db: Session) -> Dict[str, Any]:
        total_clientes = db.scalar(select(func.count(Cliente.id))) or 0
        total_productos = db.scalar(
            select(func.count(Producto.id)).where(Producto.activo.is_(True))
        ) or 0
        total_pedidos = db.scalar(select(func.count(Pedido.id))) or 0

        ventas_totales = (
            db.scalar(
                select(func.sum(Pedido.monto_total)).where(
                    Pedido.estado.in_(ESTADOS_CONFIRMADOS)
                )
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

        m = IndicatorService.calcular_actual(db)
        meta_diaria = ConfigService.get(db).meta_diaria_ventas

        return {
            "metricas": {
                "total_clientes": total_clientes,
                "total_productos": total_productos,
                "total_pedidos": total_pedidos,
                "ventas_totales": float(ventas_totales),
                "meta_diaria_ventas": float(meta_diaria),
            },
            "pedidos_por_estado": {
                "pendientes": pedidos_pendientes,
                "aprobados": pedidos_aprobados,
                "entregados": pedidos_entregados,
            },
            "indicadores_kpi": {
                "nepp": float(m["valor_nepp"]),
                "pfcc": float(m["valor_pfcc"]),
                "ntdc": float(m["valor_ntdc"]),
            },
        }