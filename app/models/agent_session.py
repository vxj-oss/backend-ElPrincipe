from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .agent_message import MensajeAgente
    from .user import Usuario


class SesionAgente(Base):
    __tablename__ = "sesiones_agente"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    titulo_sesion: Mapped[str] = mapped_column(String(200), nullable=False, default="Nueva sesión")
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    esta_activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="sesiones")
    mensajes: Mapped[List["MensajeAgente"]] = relationship(
        "MensajeAgente", back_populates="sesion", cascade="all, delete-orphan"
    )