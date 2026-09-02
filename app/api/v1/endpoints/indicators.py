from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.indicator import IndicatorLogResponse, IndicatorPeriodPoint
from app.services.indicator_service import IndicatorService

router = APIRouter(prefix="/indicators", tags=["Indicadores / KPIs"])


@router.get("/daily", response_model=List[IndicatorPeriodPoint], summary="Evolución diaria real (Lun-Dom de la semana actual)")
def get_daily_indicators(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return IndicatorService.get_daily_series(db)


@router.get("/weekly", response_model=List[IndicatorPeriodPoint], summary="Comparación semanal real (Sem 1-4 del mes actual)")
def get_weekly_indicators(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return IndicatorService.get_weekly_series(db)


@router.get("/monthly", response_model=List[IndicatorPeriodPoint], summary="Evolución mensual real (mes anterior vs. actual)")
def get_monthly_indicators(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return IndicatorService.get_monthly_series(db)


@router.get("/latest", response_model=IndicatorLogResponse, summary="Obtener última medición de indicadores")
def get_latest_indicators(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return IndicatorService.get_latest(db)


@router.get("/history", response_model=List[IndicatorLogResponse], summary="Historial de mediciones de indicadores")
def get_indicator_history(
    limit: int = 30,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return IndicatorService.get_all(db, limit=limit)


@router.post("/calculate", response_model=IndicatorLogResponse, status_code=status.HTTP_201_CREATED, summary="Calcular indicadores")
def calculate_indicators(
    resumen: str = "Cálculo manual ejecutado desde el panel",
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return IndicatorService.calculate_and_save(db, resumen=resumen)