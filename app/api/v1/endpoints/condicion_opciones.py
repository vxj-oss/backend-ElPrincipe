from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin, get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.condicion_opcion import (
    OpcionCondicionCreate,
    OpcionCondicionResponse,
    OpcionCondicionUpdate,
)
from app.services.condicion_opcion_service import CondicionOpcionService

router = APIRouter(prefix="/condicion-opciones", tags=["Catálogo de Condiciones Comerciales"])


@router.get("/", response_model=List[OpcionCondicionResponse], summary="Listar opciones del catálogo")
def list_opciones(
    tipo_condicion: Optional[str] = None,
    solo_activas: bool = False,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return CondicionOpcionService.get_all(db, tipo_condicion=tipo_condicion, solo_activas=solo_activas)


@router.post(
    "/",
    response_model=OpcionCondicionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar opción al catálogo (admin)",
)
def create_opcion(
    opcion_in: OpcionCondicionCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return CondicionOpcionService.create(db, opcion_in)


@router.put("/{opcion_id}", response_model=OpcionCondicionResponse, summary="Actualizar opción del catálogo (admin)")
def update_opcion(
    opcion_id: int,
    opcion_in: OpcionCondicionUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return CondicionOpcionService.update(db, opcion_id, opcion_in)


@router.delete("/{opcion_id}", summary="Eliminar opción del catálogo (admin)")
def delete_opcion(
    opcion_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    CondicionOpcionService.delete(db, opcion_id)
    return {"message": "Opción eliminada exitosamente"}
