from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DecisionResponse(BaseModel):
    id: int
    pedido_id: Optional[int] = None
    pedido_codigo: Optional[str] = None
    cliente_nombre: Optional[str] = None
    usuario_nombre: Optional[str] = None
    tipo_decision: str
    decision_tomada: Optional[str] = None
    recomendacion_ia: Optional[str] = None
    es_efectiva: Optional[bool] = None
    observaciones_impacto: Optional[str] = None
    fecha_decision: datetime
