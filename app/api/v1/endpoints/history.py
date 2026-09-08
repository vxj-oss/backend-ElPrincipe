from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.history import AuditHistoryPage
from app.services.history_service import HistoryService

router = APIRouter(prefix="/history", tags=["Auditoría / Historial"])


@router.get("/stats", response_model=Dict[str, Any], summary="Estadísticas del historial de auditoría")
def get_audit_stats(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return HistoryService.get_stats(db)


@router.get("/", response_model=AuditHistoryPage, summary="Consultar historial de auditoría")
def get_audit_history(
    modulo: Optional[str] = None,
    usuario_id: Optional[int] = None,
    accion: Optional[str] = None,
    rango: Optional[str] = None,
    busqueda: Optional[str] = None,
    pagina: int = 1,
    por_pagina: int = 20,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return HistoryService.get_all(
        db,
        modulo=modulo,
        usuario_id=usuario_id,
        accion=accion,
        rango=rango,
        busqueda=busqueda,
        pagina=pagina,
        por_pagina=por_pagina,
    )
