from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .agent_message import MensajeAgente
    from .order import Pedido
    from .user import Usuario


class DecisionComercial(Base):
    __tablename__ = "decisiones_comerciales"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    pedido_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pedidos.id"), nullable=True)
    mensaje_agente_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("mensajes_agente.id"), nullable=True
    )
    tipo_decision: Mapped[str] = mapped_column(
        Enum(
            "Aprobacion_Descuento",
            "Extension_Credito",
            "Sustitucion_Producto",
            "Ajuste_Precio",
            "Confirmacion_Pedido",
            name="tipo_decision_enum",
        ),
        nullable=False,
    )
    recomendacion_ia: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_tomada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    es_efectiva: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    observaciones_impacto: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_decision: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relaciones
    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="decisiones")
    pedido: Mapped[Optional["Pedido"]] = relationship("Pedido", back_populates="decisiones")
    mensaje_agente: Mapped[Optional["MensajeAgente"]] = relationship(
        "MensajeAgente", back_populates="decisiones"
    )