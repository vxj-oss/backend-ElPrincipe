from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class OpcionCondicionBase(BaseModel):
    tipo_condicion: Literal["Credito", "Descuento", "Forma_Pago"]
    valor: str = Field(..., max_length=50)
    etiqueta: str = Field(..., max_length=100)
    orden: int = 0
    activo: bool = True


class OpcionCondicionCreate(OpcionCondicionBase):
    pass


class OpcionCondicionUpdate(BaseModel):
    valor: Optional[str] = Field(None, max_length=50)
    etiqueta: Optional[str] = Field(None, max_length=100)
    orden: Optional[int] = None
    activo: Optional[bool] = None


class OpcionCondicionResponse(OpcionCondicionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creado_en: datetime
