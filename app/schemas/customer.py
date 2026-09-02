from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerBase(BaseModel):
    ruc_dni: str = Field(..., min_length=8, max_length=11)
    razon_social: str = Field(..., max_length=200)
    tipo_cliente: Literal["Mayorista", "Institucional", "Minorista"]
    direccion: Optional[str] = Field(None, max_length=300)
    distrito: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    correo: Optional[EmailStr] = None
    clasificacion: Optional[Literal["Regular", "VIP"]] = "Regular"
    estado: Literal["Activo", "Inactivo"] = "Activo"


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    ruc_dni: Optional[str] = Field(None, min_length=8, max_length=11)
    razon_social: Optional[str] = Field(None, max_length=200)
    tipo_cliente: Optional[Literal["Mayorista", "Institucional", "Minorista"]] = None
    direccion: Optional[str] = Field(None, max_length=300)
    distrito: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    correo: Optional[EmailStr] = None
    clasificacion: Optional[Literal["Regular", "VIP"]] = None
    estado: Optional[Literal["Activo", "Inactivo"]] = None


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creado_en: datetime