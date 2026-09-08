from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ConfiguracionSistema(Base):
    __tablename__ = "configuracion_sistema"

    id: Mapped[int] = mapped_column(primary_key=True)
    meta_diaria_ventas: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("6000.00"), server_default="6000.00"
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
