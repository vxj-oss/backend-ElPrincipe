from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    nombre_usuario: str = Field(..., max_length=100)
    password: str = Field(..., max_length=200)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    exp: Optional[int] = None


class UserAuthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_usuario: str
    nombre_completo: str
    correo: EmailStr
    rol: str
    esta_activo: bool