from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.history import AuditHistoryResponse
from app.services.history_service import HistoryService

router = APIRouter(prefix="/history", tags=["Auditoría / Historial"])


@router.get("/", response_model=List[AuditHistoryResponse], summary="Consultar historial de auditoría")
def get_audit_history(
    modulo: Optional[str] = None,
    usuario_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return HistoryService.get_all(
        db, modulo=modulo, usuario_id=usuario_id, skip=skip, limit=limit
    )