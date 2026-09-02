from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.decision import DecisionResponse
from app.services.decision_service import DecisionService

router = APIRouter(prefix="/decisions", tags=["Decisiones Comerciales"])


@router.get("/", response_model=List[DecisionResponse], summary="Listar decisiones comerciales registradas")
def list_decisions(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return DecisionService.get_all(db, skip=skip, limit=limit)
