from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.schemas.commercial_term import CommercialTermResponse


class CommercialTermFailureBase(BaseModel):
    pedido_id: int
    condicion_comercial_id: Optional[int] = None
    tiene_falla: bool = False
    motivo_falla: Optional[str] = None


class CommercialTermFailureCreate(CommercialTermFailureBase):
    pass


class CommercialTermFailureUpdate(BaseModel):
    condicion_comercial_id: Optional[int] = None
    tiene_falla: Optional[bool] = None
    motivo_falla: Optional[str] = None


class CommercialTermFailureResponse(CommercialTermFailureBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_evaluacion: datetime
    condicion_comercial: Optional[CommercialTermResponse] = None