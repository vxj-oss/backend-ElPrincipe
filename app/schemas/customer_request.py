from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.customer import CustomerResponse
from app.schemas.customer_request_item import (
    SolicitudClienteDetalleCreate,
    SolicitudClienteDetalleResponse,
)
from app.schemas.user import UserResponse


class SolicitudClienteBase(BaseModel):
    cliente_id: int
    canal_recepcion: Optional[str] = Field(default="WhatsApp", max_length=50)
    observaciones: Optional[str] = None


class SolicitudClienteCreate(SolicitudClienteBase):
    detalles: List[SolicitudClienteDetalleCreate] = Field(..., min_length=1)


class SolicitudClienteResponse(SolicitudClienteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo_solicitud: str
    usuario_id: int
    fecha_solicitud: datetime
    estado: str
    creado_en: datetime
    cliente: Optional[CustomerResponse] = None
    usuario: Optional[UserResponse] = None
    detalles: List[SolicitudClienteDetalleResponse] = []


class ComparacionPedidoItem(BaseModel):
    producto_id: int
    sku: Optional[str] = None
    nombre: str
    cantidad: int
    precio_unitario: Decimal


class ComparacionPedidoRequest(BaseModel):
    solicitud_id: Optional[int] = None
    cliente_id: int
    forma_pago: Optional[str] = "Contado"
    items_pedido: List[ComparacionPedidoItem]


class ComparacionPedidoResponse(BaseModel):
    hay_discrepancia: bool
    tipo_error: Optional[str] = None
    descripcion_discrepancia: str
    analisis_ia: str
    sugerencias_correccion: List[str] = []