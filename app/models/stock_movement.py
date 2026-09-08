from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .order import Pedido
    from .product import Producto


class MovimientoStock(Base):
    __tablename__ = "movimientos_stock"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    producto_id: Mapped[int] = mapped_column(
        ForeignKey("productos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pedido_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pedidos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tipo: Mapped[str] = mapped_column(
        Enum("Salida", "Entrada", "Ajuste", name="tipo_movimiento_stock_enum"),
        nullable=False,
    )
    cantidad: Mapped[int] = mapped_column(nullable=False)
    stock_anterior: Mapped[int] = mapped_column(nullable=False)
    stock_nuevo: Mapped[int] = mapped_column(nullable=False)
    motivo: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    producto: Mapped["Producto"] = relationship("Producto")
    pedido: Mapped[Optional["Pedido"]] = relationship("Pedido")
