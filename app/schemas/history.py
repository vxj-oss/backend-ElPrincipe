from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

AccionAuditoria = Literal[
    "CREAR",
    "ACTUALIZAR",
    "ELIMINAR",
    "CONSULTA_IA",
    "INICIAR_SESION",
    "CERRAR_SESION",
    "EXPORTAR",
    "ERROR",
]


class AuditHistoryBase(BaseModel):
    usuario_id: Optional[int] = None
    accion: AccionAuditoria
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


class AuditHistoryPage(BaseModel):
    items: List[AuditHistoryResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int