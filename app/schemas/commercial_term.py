from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.customer import CustomerResponse


class CommercialTermBase(BaseModel):
    cliente_id: int
    tipo_condicion: Literal[
        "Plazo_Credito",
        "Descuento_Volumen",
        "Limite_Credito",
        "Forma_Pago",
    ]
    dias_plazo_pactados: Optional[int] = 0
    porcentaje_descuento: Optional[Decimal] = Field(
        default=Decimal("0.00"), ge=0, le=100, decimal_places=2
    )
    limite_credito_asignado: Optional[Decimal] = Field(
        default=Decimal("0.00"), ge=0, decimal_places=2
    )


class CommercialTermCreate(CommercialTermBase):
    @field_validator("dias_plazo_pactados")
    @classmethod
    def validar_dias_estandar(cls, v):
        if v is not None and int(v) not in [0, 15, 30]:
            raise ValueError("Los días de plazo solo pueden ser 0 (Contado), 15 o 30.")
        return v


class CommercialTermUpdate(BaseModel):
    cliente_id: Optional[int] = None
    tipo_condicion: Optional[
        Literal[
            "Plazo_Credito",
            "Descuento_Volumen",
            "Limite_Credito",
            "Forma_Pago",
        ]
    ] = None
    dias_plazo_pactados: Optional[int] = None
    porcentaje_descuento: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    limite_credito_asignado: Optional[Decimal] = Field(None, ge=0, decimal_places=2)

    @field_validator("dias_plazo_pactados")
    @classmethod
    def validar_dias_estandar(cls, v):
        if v is not None and int(v) not in [0, 15, 30]:
            raise ValueError("Los días de plazo solo pueden ser 0 (Contado), 15 o 30.")
        return v


class CommercialTermResponse(CommercialTermBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_registro: datetime
    cliente: Optional[CustomerResponse] = None