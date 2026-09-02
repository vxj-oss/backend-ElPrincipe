from datetime import datetime
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class AuditHistoryBase(BaseModel):
    usuario_id: Optional[int] = None
    accion: Literal["CREAR", "ACTUALIZAR", "ELIMINAR", "CONSULTA_IA"]
    modulo_afectado: str = Field(..., max_length=100)
    detalle_cambio: Optional[Dict[str, Any]] = None


class AuditHistoryCreate(AuditHistoryBase):
    pass


class AuditHistoryResponse(AuditHistoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_nombre: Optional[str] = "Sistema / Asesor"
    usuario_iniciales: Optional[str] = "EP"
    fecha_hora: datetime