from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .customer import Cliente
    from .customer_request_item import SolicitudClienteDetalle
    from .user import Usuario


class SolicitudCliente(Base):
    __tablename__ = "solicitudes_cliente"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    codigo_solicitud: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False
    )
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    fecha_solicitud: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    hora_apertura_modal: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estado: Mapped[str] = mapped_column(
        String(50), default="Pendiente", nullable=False
    )
    auditado_ia: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    resultado_auditoria: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    descripcion_auditoria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_auditoria: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    canal_recepcion: Mapped[Optional[str]] = mapped_column(
        String(50), default="WhatsApp", nullable=True
    )
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="solicitudes")
    usuario: Mapped["Usuario"] = relationship("Usuario")
    detalles: Mapped[List["SolicitudClienteDetalle"]] = relationship(
        "SolicitudClienteDetalle",
        back_populates="solicitud",
        cascade="all, delete-orphan",
    )