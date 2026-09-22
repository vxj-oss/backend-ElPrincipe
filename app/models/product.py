from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .category import Categoria
    from .order_item import DetallePedido


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unidad_medida: Mapped[str] = mapped_column(String(100), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    precio_costo: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    stock_actual: Mapped[int] = mapped_column(nullable=False, default=0)
    stock_minimo: Mapped[int] = mapped_column(nullable=False, default=5)
    nivel_rotacion: Mapped[str] = mapped_column(
        Enum("Alta", "Media", "Baja", name="nivel_rotacion_producto"),
        nullable=False,
        default="Media",
    )
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    categoria: Mapped["Categoria"] = relationship("Categoria", back_populates="productos")
    detalles: Mapped[List["DetallePedido"]] = relationship(
        "DetallePedido", back_populates="producto"
    )