from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ActivityIndicatorSummary(BaseModel):
    dia_actual: str
    dia_anterior: str
    solicitudes_dia_actual: int
    solicitudes_dia_anterior: int
    variacion_solicitudes_pct: Decimal
    pedidos_dia_actual: int
    pedidos_dia_anterior: int
    variacion_pedidos_pct: Decimal
    solicitudes_conformes_dia_actual: int = 0
    solicitudes_con_observaciones_dia_actual: int = 0
    pedidos_conformes_dia_actual: int = 0
    pedidos_con_observaciones_dia_actual: int = 0
    tiempo_promedio_decision_minutos: Optional[Decimal] = None
    tiempo_promedio_decision_minutos_general: Optional[Decimal] = None


class DiaPoint(BaseModel):
    label: str
    solicitudes: int
    pedidos: int
    tiempo_promedio_decision_minutos: Optional[float] = None
