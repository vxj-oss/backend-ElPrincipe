from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _validar_ruc_dni(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    limpio = v.strip()
    if not limpio.isdigit():
        raise ValueError("El RUC/DNI debe contener solo dígitos")
    if len(limpio) not in (8, 11):
        raise ValueError("El DNI debe tener 8 dígitos y el RUC 11 dígitos")
    return limpio


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
    _v_ruc = field_validator("ruc_dni")(_validar_ruc_dni)


class CustomerUpdate(BaseModel):
    ruc_dni: Optional[str] = Field(None, min_length=8, max_length=11)

    _v_ruc = field_validator("ruc_dni")(_validar_ruc_dni)
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