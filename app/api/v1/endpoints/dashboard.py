from decimal import Decimal
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin, get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.services.config_service import ConfigService
from app.services.dashboard_service import DashboardService
from app.services.history_service import HistoryService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class ConfigResponse(BaseModel):
    meta_diaria_ventas: float


class ConfigUpdate(BaseModel):
    meta_diaria_ventas: Decimal = Field(..., gt=0)


@router.get("/summary", response_model=Dict[str, Any], summary="Resumen global para el dashboard")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return DashboardService.get_summary(db)


@router.get("/config", response_model=ConfigResponse, summary="Configuración comercial de la empresa")
def get_config(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    config = ConfigService.get(db)
    return ConfigResponse(meta_diaria_ventas=float(config.meta_diaria_ventas))


@router.put("/config", response_model=ConfigResponse, summary="Actualizar configuración comercial")
def update_config(
    payload: ConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_admin),
):
    config = ConfigService.update(db, payload.meta_diaria_ventas)
    HistoryService.log(
        db, "ACTUALIZAR", "Configuracion", current_user.id,
        {
            "entidad": "Meta comercial",
            "descripcion": f"Actualizó la meta diaria de ventas a S/ {float(config.meta_diaria_ventas):,.2f}",
        },
        request.client.host if request.client else None,
    )
    return ConfigResponse(meta_diaria_ventas=float(config.meta_diaria_ventas))
