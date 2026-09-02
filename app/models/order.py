from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .commercial_term_failure import FallaCondicionComercial
    from .customer import Cliente
    from .decision import DecisionComercial
    from .order_item import DetallePedido
    from .user import Usuario


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    codigo_pedido: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    fecha_pedido: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_entrega: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    forma_pago: Mapped[str] = mapped_column(
        Enum("Contado", "Credito 15d", "Credito 30d", name="forma_pago_enum"),
        nullable=False,
    )
    estado: Mapped[str] = mapped_column(
        Enum("Pendiente", "Aprobado", "Entregado", "Cancelado", name="estado_pedido_enum"),
        nullable=False,
        default="Pendiente",
    )
    monto_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="pedidos")
    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="pedidos")
    detalles: Mapped[List["DetallePedido"]] = relationship(
        "DetallePedido", back_populates="pedido", cascade="all, delete-orphan"
    )
    auditoria_condicion: Mapped[Optional["FallaCondicionComercial"]] = relationship(
        "FallaCondicionComercial", back_populates="pedido", uselist=False, cascade="all, delete-orphan"
    )
    decisiones: Mapped[List["DecisionComercial"]] = relationship(
        "DecisionComercial", back_populates="pedido"
    )