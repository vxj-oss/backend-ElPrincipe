from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .commercial_term import CondicionComercial
    from .customer_request import SolicitudCliente
    from .order import Pedido


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ruc_dni: Mapped[str] = mapped_column(
        String(11), unique=True, nullable=False, index=True
    )
    razon_social: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_cliente: Mapped[str] = mapped_column(
        Enum("Mayorista", "Institucional", "Minorista", name="tipo_cliente_enum"),
        nullable=False,
    )
    direccion: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    distrito: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    correo: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    clasificacion: Mapped[str] = mapped_column(
        Enum("Regular", "VIP", name="clasificacion_cliente_enum"),
        nullable=False,
        default="Regular",
    )
    estado: Mapped[str] = mapped_column(
        Enum("Activo", "Inactivo", name="estado_cliente_enum"),
        nullable=False,
        default="Activo",
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pedidos: Mapped[List["Pedido"]] = relationship("Pedido", back_populates="cliente")
    solicitudes: Mapped[List["SolicitudCliente"]] = relationship("SolicitudCliente", back_populates="cliente")
    condiciones: Mapped[List["CondicionComercial"]] = relationship(
        "CondicionComercial", back_populates="cliente", cascade="all, delete-orphan"
    )