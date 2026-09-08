from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int
    pedido_id: Optional[int] = None
    tipo: str
    cantidad: int
    stock_anterior: int
    stock_nuevo: int
    motivo: Optional[str] = None
    creado_en: datetime
