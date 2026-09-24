from datetime import date
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel


class ReportFilterRequest(BaseModel):
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    cliente_id: Optional[int] = None
    usuario_id: Optional[int] = None
    formato: Literal["pdf", "excel", "json"] = "json"


class SalesKPIReport(BaseModel):
    ventas_totales: float
    cantidad_pedidos: int
    ticket_promedio: float
    tasa_efectividad: float
    pedidos_por_estado: Dict[str, int]


class IndicatorReportResponse(BaseModel):
    fecha_generacion: str
    periodo_evaluado: str
    indicadores: Dict[str, Any]
    metricas_clave: List[Dict[str, Any]]