from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OpcionCondicionComercial(Base):
    __tablename__ = "opciones_condicion_comercial"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tipo_condicion: Mapped[str] = mapped_column(
        Enum("Credito", "Descuento", "Forma_Pago", name="tipo_condicion_enum"),
        nullable=False,
        index=True,
    )
    valor: Mapped[str] = mapped_column(String(50), nullable=False)
    etiqueta: Mapped[str] = mapped_column(String(100), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
