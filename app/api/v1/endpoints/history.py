from datetime import datetime, time
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.history import AuditHistoryPage
from app.services.history_service import HistoryService

LIMA_TZ = ZoneInfo("America/Lima")

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


@router.delete(
    "/",
    summary="Eliminar eventos de auditoría en un rango de fechas",
)
def delete_audit_history(
    desde: str,
    hasta: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_admin),
):
    try:
        fecha_desde = datetime.combine(
            datetime.strptime(desde, "%Y-%m-%d").date(), time.min, tzinfo=LIMA_TZ
        )
        fecha_hasta = datetime.combine(
            datetime.strptime(hasta, "%Y-%m-%d").date(), time.max, tzinfo=LIMA_TZ
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de fecha inválido. Usa YYYY-MM-DD.",
        )
    if fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha 'desde' no puede ser posterior a 'hasta'.",
        )

    total = HistoryService.delete_by_range(db, fecha_desde, fecha_hasta)
    HistoryService.log(
        db, "ELIMINAR", "Auditoria", current_user.id,
        {
            "entidad": f"{desde} a {hasta}",
            "descripcion": f"Eliminó {total} evento(s) de auditoría entre {desde} y {hasta}",
        },
        request.client.host if request.client else None,
    )
    return {"message": f"Se eliminaron {total} evento(s) de auditoría.", "total_eliminados": total}
