import re
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _vacio_a_none(v):
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _validar_ruc_dni(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    limpio = v.strip()
    if not limpio.isdigit():
        raise ValueError("El RUC/DNI debe contener solo dígitos")
    if len(limpio) not in (8, 11):
        raise ValueError("El DNI debe tener 8 dígitos y el RUC 11 dígitos")
    if len(limpio) == 11 and not _ruc_valido(limpio):
        raise ValueError("El RUC no es válido: revisa los dígitos")
    return limpio


_PREFIJOS_RUC = ("10", "15", "16", "17", "20")
_FACTORES_RUC = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_TELEFONO = re.compile(r"^[0-9+\-()/ ]+$")


def _ruc_valido(ruc: str) -> bool:
    if ruc[:2] not in _PREFIJOS_RUC:
        return False
    suma = sum(int(d) * f for d, f in zip(ruc[:10], _FACTORES_RUC))
    verificador = 11 - (suma % 11)
    if verificador >= 10:
        verificador -= 10
    return verificador == int(ruc[10])


def _validar_telefono(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    limpio = v.strip()
    if not limpio:
        return None
    if not _TELEFONO.match(limpio) or sum(c.isdigit() for c in limpio) < 6:
        raise ValueError("El teléfono solo puede tener números, espacios y + - ( ) /, con al menos 6 dígitos")
    return limpio


def _validar_texto_requerido(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    limpio = " ".join(v.split())
    if len(limpio) < 2:
        raise ValueError("Debe tener al menos 2 caracteres")
    return limpio


class CustomerBase(BaseModel):
    ruc_dni: Optional[str] = Field(None, max_length=11)
    razon_social: str = Field(..., max_length=200)
    tipo_cliente: Literal["Mayorista", "Institucional", "Minorista"]
    direccion: Optional[str] = Field(None, max_length=300)
    distrito: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    correo: Optional[EmailStr] = None
    clasificacion: Optional[Literal["Regular", "VIP"]] = "Regular"
    estado: Literal["Activo", "Inactivo"] = "Activo"


class CustomerCreate(CustomerBase):
    _v_razon = field_validator("razon_social")(_validar_texto_requerido)
    _v_tel_vacio = field_validator("telefono", mode="before")(_vacio_a_none)
    _v_tel = field_validator("telefono")(_validar_telefono)
    _v_correo_vacio = field_validator("correo", mode="before")(_vacio_a_none)
    _v_vacio = field_validator("ruc_dni", mode="before")(_vacio_a_none)
    _v_ruc = field_validator("ruc_dni")(_validar_ruc_dni)


class CustomerUpdate(BaseModel):
    ruc_dni: Optional[str] = Field(None, max_length=11)

    _v_vacio = field_validator("ruc_dni", mode="before")(_vacio_a_none)
    _v_ruc = field_validator("ruc_dni")(_validar_ruc_dni)
    razon_social: Optional[str] = Field(None, max_length=200)
    tipo_cliente: Optional[Literal["Mayorista", "Institucional", "Minorista"]] = None
    direccion: Optional[str] = Field(None, max_length=300)
    distrito: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    correo: Optional[EmailStr] = None
    clasificacion: Optional[Literal["Regular", "VIP"]] = None

    _v_razon = field_validator("razon_social")(_validar_texto_requerido)
    _v_tel_vacio = field_validator("telefono", mode="before")(_vacio_a_none)
    _v_tel = field_validator("telefono")(_validar_telefono)
    _v_correo_vacio = field_validator("correo", mode="before")(_vacio_a_none)
    estado: Optional[Literal["Activo", "Inactivo"]] = None


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creado_en: datetime