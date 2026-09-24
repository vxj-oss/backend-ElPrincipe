from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RegistroIndicador(Base):
    __tablename__ = "registros_indicador"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    fecha_calculo: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
    total_pedidos_evaluados: Mapped[int] = mapped_column(nullable=False, default=0)
    total_items_pedidos: Mapped[int] = mapped_column(nullable=False, default=0)
    total_errores_productos: Mapped[int] = mapped_column(nullable=False, default=0)
    valor_nepp: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    total_condiciones_pactadas: Mapped[int] = mapped_column(nullable=False, default=0)
    total_fallas_condiciones: Mapped[int] = mapped_column(nullable=False, default=0)
    valor_pfcc: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    total_decisiones_evaluadas: Mapped[int] = mapped_column(nullable=False, default=0)
    total_decisiones_efectivas: Mapped[int] = mapped_column(nullable=False, default=0)
    total_decisiones_corregidas: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    valor_ntdc: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    resumen_operativo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)