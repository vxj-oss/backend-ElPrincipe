import re
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"\d")
_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def _validate_password_complexity(password: str) -> str:
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if not _UPPER.search(password):
        raise ValueError("La contraseña debe incluir al menos una letra mayúscula")
    if not _LOWER.search(password):
        raise ValueError("La contraseña debe incluir al menos una letra minúscula")
    if not _DIGIT.search(password):
        raise ValueError("La contraseña debe incluir al menos un número")
    if not _SPECIAL.search(password):
        raise ValueError("La contraseña debe incluir al menos un símbolo (ej: !@#$%^&*)")
    return password


class UserBase(BaseModel):
    nombre_usuario: str = Field(..., max_length=50)
    nombre_completo: str = Field(..., max_length=150)
    correo: EmailStr
    rol: Literal["administrador", "asesor_comercial"] = "asesor_comercial"
    esta_activo: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class UserUpdate(BaseModel):
    nombre_usuario: Optional[str] = Field(None, max_length=50)
    nombre_completo: Optional[str] = Field(None, max_length=150)
    correo: Optional[EmailStr] = None
    rol: Optional[Literal["administrador", "asesor_comercial"]] = None
    esta_activo: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: Optional[str]) -> Optional[str]:
        return _validate_password_complexity(v) if v is not None else v


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creado_en: datetime
