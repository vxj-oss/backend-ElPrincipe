from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .order import Pedido
    from .product import Producto


class DetallePedido(Base):
    __tablename__ = "detalles_pedido"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), nullable=False)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    cantidad: Mapped[int] = mapped_column(nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tiene_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tipo_error: Mapped[str] = mapped_column(
        Enum(
            "Ninguno",
            "SKU_Incorrecto",
            "Precio_Desactualizado",
            "Stock_Insuficiente",
            "Cantidad_Erronea",
            name="tipo_error_detalle_enum",
        ),
        nullable=False,
        default="Ninguno",
    )
    descripcion_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relaciones
    pedido: Mapped["Pedido"] = relationship("Pedido", back_populates="detalles")
    producto: Mapped["Producto"] = relationship("Producto", back_populates="detalles")