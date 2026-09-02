from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class OrderItemBase(BaseModel):
    producto_id: int
    cantidad: int = Field(default=1, gt=0)
    precio_unitario: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    subtotal: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    tiene_error: bool = False
    tipo_error: str = "Ninguno"
    descripcion_error: Optional[str] = None


class OrderItemCreate(BaseModel):
    producto_id: int
    cantidad: int = Field(default=1, gt=0)
    precio_unitario: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    subtotal: Optional[Decimal] = None
    tiene_error: bool = False
    tipo_error: Optional[str] = "Ninguno"
    descripcion_error: Optional[str] = None


class OrderItemUpdate(BaseModel):
    cantidad: Optional[int] = Field(None, gt=0)
    precio_unitario: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    subtotal: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    tiene_error: Optional[bool] = None
    tipo_error: Optional[str] = None
    descripcion_error: Optional[str] = None


class OrderItemResponse(OrderItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pedido_id: int