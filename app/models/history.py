from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import Usuario


class HistorialAuditoria(Base):
    __tablename__ = "historial_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    accion: Mapped[str] = mapped_column(
        Enum(
            "CREAR",
            "ACTUALIZAR",
            "ELIMINAR",
            "CONSULTA_IA",
            "INICIAR_SESION",
            "CERRAR_SESION",
            "EXPORTAR",
            "ERROR",
            name="accion_auditoria_enum",
        ),
        nullable=False,
    )
    modulo_afectado: Mapped[str] = mapped_column(String(100), nullable=False)
    detalle_cambio: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    direccion_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    usuario: Mapped[Optional["Usuario"]] = relationship("Usuario", back_populates="auditoria")