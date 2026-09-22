from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.category import CategoryResponse


class ProductBase(BaseModel):
    categoria_id: int
    sku: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=200)
    descripcion: Optional[str] = None
    unidad_medida: str = Field(..., max_length=100)
    precio_unitario: Decimal = Field(..., ge=0, decimal_places=2)
    precio_costo: Decimal = Field(..., ge=0, decimal_places=2)
    stock_actual: int = Field(default=0, ge=0)
    stock_minimo: int = Field(default=5, ge=0)
    nivel_rotacion: Literal["Alta", "Media", "Baja"] = "Media"
    activo: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    categoria_id: Optional[int] = None
    sku: Optional[str] = Field(None, max_length=50)
    nombre: Optional[str] = Field(None, max_length=200)
    descripcion: Optional[str] = None
    unidad_medida: Optional[str] = Field(None, max_length=100)
    precio_unitario: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    precio_costo: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    stock_actual: Optional[int] = Field(None, ge=0)
    stock_minimo: Optional[int] = Field(None, ge=0)
    nivel_rotacion: Optional[Literal["Alta", "Media", "Baja"]] = None


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creado_en: datetime
    categoria: Optional[CategoryResponse] = None