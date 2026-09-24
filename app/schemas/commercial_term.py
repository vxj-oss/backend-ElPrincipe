from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.customer import CustomerResponse


class CommercialTermBase(BaseModel):
    cliente_id: int
    tipo_condicion: Literal["Credito", "Descuento", "Forma_Pago"]
    dias_plazo_pactados: Optional[int] = None
    porcentaje_descuento: Optional[Decimal] = None
    forma_pago_pactada: Optional[str] = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validar_valor_segun_tipo(self):
        if self.tipo_condicion == "Credito" and self.dias_plazo_pactados is None:
            raise ValueError("Selecciona los días de plazo para una condición de Crédito.")
        if self.tipo_condicion == "Descuento" and self.porcentaje_descuento is None:
            raise ValueError("Selecciona el porcentaje de descuento para una condición de Descuento.")
        if self.tipo_condicion == "Forma_Pago" and self.forma_pago_pactada is None:
            raise ValueError("Selecciona la forma de pago pactada.")
        return self


class CommercialTermCreate(CommercialTermBase):
    pass


class CommercialTermUpdate(BaseModel):
    cliente_id: Optional[int] = None
    tipo_condicion: Optional[Literal["Credito", "Descuento", "Forma_Pago"]] = None
    dias_plazo_pactados: Optional[int] = None
    porcentaje_descuento: Optional[Decimal] = None
    forma_pago_pactada: Optional[str] = Field(default=None, max_length=50)


class CommercialTermResponse(CommercialTermBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_registro: datetime
    cliente: Optional[CustomerResponse] = None
