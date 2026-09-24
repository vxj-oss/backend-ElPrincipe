from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .agent_session import SesionAgente
    from .decision import DecisionComercial


class MensajeAgente(Base):
    __tablename__ = "mensajes_agente"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    sesion_id: Mapped[int] = mapped_column(ForeignKey("sesiones_agente.id"), nullable=False)
    rol_emisor: Mapped[str] = mapped_column(
        Enum("user", "assistant", "system", name="rol_emisor_enum"),
        nullable=False,
    )
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    datos_estructurados: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    tiempo_respuesta_segundos: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    sesion: Mapped["SesionAgente"] = relationship("SesionAgente", back_populates="mensajes")
    decisiones: Mapped[List["DecisionComercial"]] = relationship(
        "DecisionComercial", back_populates="mensaje_agente"
    )