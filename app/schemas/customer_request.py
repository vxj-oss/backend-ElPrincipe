from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.customer import CustomerResponse
from app.schemas.customer_request_item import (
    SolicitudClienteDetalleCreate,
    SolicitudClienteDetalleResponse,
)
from app.schemas.user import UserResponse


class SolicitudClienteBase(BaseModel):
    cliente_id: int
    canal_recepcion: Optional[str] = Field(default="Presencial", max_length=50)
    observaciones: Optional[str] = None


class SolicitudClienteCreate(SolicitudClienteBase):
    detalles: List[SolicitudClienteDetalleCreate] = Field(..., min_length=1)
    hora_apertura_modal: Optional[datetime] = None


class SolicitudClienteResponse(SolicitudClienteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo_solicitud: str
    usuario_id: int
    fecha_solicitud: datetime
    hora_apertura_modal: Optional[datetime] = None
    estado: str
    auditado_ia: bool = False
    resultado_auditoria: Optional[str] = None
    descripcion_auditoria: Optional[str] = None
    fecha_auditoria: Optional[datetime] = None
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
    ia_disponible: bool = True
    ventas_adicionales: List[str] = []


class NotaCotizacionRequest(BaseModel):
    texto: str = Field(..., min_length=3, max_length=3000)
    cliente_id: Optional[int] = None


class NotaCotizacionOpcion(BaseModel):
    producto_id: int
    nombre: str
    precio: Decimal
    stock: Optional[int] = None


class NotaCotizacionItem(BaseModel):
    producto_id: Optional[int] = None
    nombre: str
    texto_original: str
    cantidad: int = Field(..., gt=0)
    precio_esperado: Optional[Decimal] = None
    stock: Optional[int] = None
    coincidencia: Literal["catalogo", "sin_coincidencia", "ambiguo"]
    opciones: List[NotaCotizacionOpcion] = []


class NotaCotizacionResponse(BaseModel):
    items: List[NotaCotizacionItem] = []
    cliente_sugerido_id: Optional[int] = None
    ia_disponible: bool = True
    advertencias: List[str] = []
