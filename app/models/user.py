from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .agent_session import SesionAgente
    from .decision import DecisionComercial
    from .history import HistorialAuditoria
    from .order import Pedido


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre_usuario: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    clave_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    correo: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    rol: Mapped[str] = mapped_column(
        Enum("administrador", "asesor_comercial", name="rol_usuario"),
        nullable=False,
        default="asesor_comercial",
    )
    esta_activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    bloqueado_hasta: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    preferencias: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    pedidos: Mapped[List["Pedido"]] = relationship("Pedido", back_populates="usuario")
    sesiones: Mapped[List["SesionAgente"]] = relationship("SesionAgente", back_populates="usuario")
    decisiones: Mapped[List["DecisionComercial"]] = relationship(
        "DecisionComercial", back_populates="usuario"
    )
    auditoria: Mapped[List["HistorialAuditoria"]] = relationship(
        "HistorialAuditoria", back_populates="usuario"
    )