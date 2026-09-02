from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SolicitudClienteDetalleBase(BaseModel):
    producto_id: Optional[int] = None
    nombre_producto_solicitado: str = Field(..., min_length=1, max_length=255)
    cantidad_solicitada: int = Field(..., gt=0)
    precio_esperado: Optional[Decimal] = Field(default=None, ge=0)


class SolicitudClienteDetalleCreate(SolicitudClienteDetalleBase):
    pass


class SolicitudClienteDetalleResponse(SolicitudClienteDetalleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int