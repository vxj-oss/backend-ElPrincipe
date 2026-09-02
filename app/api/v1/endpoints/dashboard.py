from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=Dict[str, Any], summary="Resumen global para el dashboard")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return DashboardService.get_summary(db)