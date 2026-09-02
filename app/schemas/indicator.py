from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class IndicatorLogBase(BaseModel):
    total_pedidos_evaluados: int = 0
    total_items_pedidos: int = 0
    total_errores_productos: int = 0
    valor_nepp: Optional[Decimal] = Field(None, decimal_places=4)
    total_condiciones_pactadas: int = 0
    total_fallas_condiciones: int = 0
    valor_pfcc: Optional[Decimal] = Field(None, decimal_places=4)
    total_decisiones_evaluadas: int = 0
    total_decisiones_efectivas: int = 0
    valor_ntdc: Optional[Decimal] = Field(None, decimal_places=4)
    resumen_operativo: Optional[str] = None


class IndicatorLogCreate(IndicatorLogBase):
    pass


class IndicatorLogResponse(IndicatorLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_calculo: datetime


class IndicatorPeriodPoint(BaseModel):
    label: str
    valor_nepp: Decimal = Field(..., decimal_places=4)
    valor_pfcc: Decimal = Field(..., decimal_places=4)
    valor_ntdc: Decimal = Field(..., decimal_places=4)


class IndicatorSummaryResponse(BaseModel):
    periodo: str
    nepp: Decimal = Field(..., description="Número de Errores en Productos Pedidos")
    pfcc: Decimal = Field(..., description="Porcentaje de Fallas en Condiciones Comerciales")
    ntdc: Decimal = Field(..., description="Nivel de Toma de Decisiones Comerciales")
    total_pedidos: int
    total_fallas: int
    total_decisiones: int