from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .commercial_term import CondicionComercial
    from .order import Pedido


class FallaCondicionComercial(Base):
    __tablename__ = "fallas_condiciones_comerciales"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedidos.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    condicion_comercial_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("condiciones_comerciales.id", ondelete="SET NULL"), nullable=True
    )
    tiene_falla: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    motivo_falla: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_evaluacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pedido: Mapped["Pedido"] = relationship("Pedido", back_populates="auditoria_condicion")
    condicion_comercial: Mapped[Optional["CondicionComercial"]] = relationship(
        "CondicionComercial", back_populates="auditorias"
    )