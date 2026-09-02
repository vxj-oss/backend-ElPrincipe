from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from .base import Base


class SolicitudClienteDetalle(Base):
    __tablename__ = "solicitud_cliente_detalles"

    id = Column(Integer, primary_key=True, index=True)
    solicitud_id = Column(Integer, ForeignKey("solicitudes_cliente.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id", ondelete="SET NULL"), nullable=True)
    nombre_producto_solicitado = Column(String(255), nullable=False)
    cantidad_solicitada = Column(Integer, nullable=False, default=1)
    precio_esperado = Column(Numeric(10, 2), nullable=True)

    solicitud = relationship("SolicitudCliente", back_populates="detalles")
    producto = relationship("Producto")