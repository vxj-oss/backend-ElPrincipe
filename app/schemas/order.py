from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.commercial_term_failure import (
    CommercialTermFailureCreate,
    CommercialTermFailureResponse,
)
from app.schemas.customer import CustomerResponse
from app.schemas.order_item import OrderItemCreate, OrderItemResponse
from app.schemas.user import UserResponse


class OrderBase(BaseModel):
    cliente_id: int
    usuario_id: Optional[int] = None
    solicitud_id: Optional[int] = None
    codigo_pedido: Optional[str] = Field(default=None, max_length=30)
    fecha_pedido: Optional[datetime] = None
    fecha_entrega: Optional[datetime] = None
    forma_pago: str = "Contado"
    estado: str = "Pendiente"
    monto_total: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    observaciones: Optional[str] = None


class OrderCreate(BaseModel):
    cliente_id: int
    solicitud_id: Optional[int] = None
    condicion_comercial_id: Optional[int] = None
    codigo_pedido: Optional[str] = None
    fecha_pedido: Optional[datetime] = None
    fecha_entrega: Optional[datetime] = None
    forma_pago: str = "Contado"
    estado: Optional[str] = "Pendiente"
    observaciones: Optional[str] = None
    items: List[OrderItemCreate] = []
    auditoria_condicion: Optional[CommercialTermFailureCreate] = None


class OrderUpdate(BaseModel):
    cliente_id: Optional[int] = None
    solicitud_id: Optional[int] = None
    condicion_comercial_id: Optional[int] = None
    fecha_pedido: Optional[datetime] = None
    fecha_entrega: Optional[datetime] = None
    forma_pago: Optional[str] = None
    estado: Optional[str] = None
    monto_total: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    observaciones: Optional[str] = None
    items: Optional[List[OrderItemCreate]] = None
    auditoria_condicion: Optional[CommercialTermFailureCreate] = None


class StockAlertItem(BaseModel):
    producto_id: int
    nombre: str
    stock_actual: int
    stock_minimo: int
    agotado: bool = False


class OrderResponse(OrderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creado_en: Optional[datetime] = None
    stock_descontado: bool = False
    cliente: Optional[CustomerResponse] = None
    usuario: Optional[UserResponse] = None
    detalles: List[OrderItemResponse] = []
    auditoria_condicion: Optional[CommercialTermFailureResponse] = None
    alertas_stock: List[StockAlertItem] = []