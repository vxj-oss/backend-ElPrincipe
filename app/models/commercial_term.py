from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .commercial_term_failure import FallaCondicionComercial
    from .customer import Cliente


class CondicionComercial(Base):
    __tablename__ = "condiciones_comerciales"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    tipo_condicion: Mapped[str] = mapped_column(
        Enum(
            "Credito",
            "Descuento",
            "Forma_Pago",
            name="tipo_condicion_enum",
        ),
        nullable=False,
    )
    dias_plazo_pactados: Mapped[Optional[int]] = mapped_column(nullable=True, default=None)
    porcentaje_descuento: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True, default=None
    )
    forma_pago_pactada: Mapped[Optional[str]] = mapped_column(
        Enum("Contado", "Tarjeta", "Otro", name="forma_pago_pactada_enum"),
        nullable=True,
        default=None,
    )
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="condiciones")
    auditorias: Mapped[List["FallaCondicionComercial"]] = relationship(
        "FallaCondicionComercial", back_populates="condicion_comercial"
    )