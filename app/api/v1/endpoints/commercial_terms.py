from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.commercial_term import (
    CommercialTermCreate,
    CommercialTermResponse,
    CommercialTermUpdate,
)
from app.services.commercial_term_service import CommercialTermService
from app.services.history_service import HistoryService

router = APIRouter(prefix="/commercial-terms", tags=["Condiciones Comerciales"])


@router.get(
    "/",
    response_model=List[CommercialTermResponse],
    summary="Listar todas las condiciones comerciales pactadas",
)
def list_terms(
    cliente_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return CommercialTermService.get_all(
        db, cliente_id=cliente_id, skip=skip, limit=limit
    )


@router.get(
    "/client/{cliente_id}",
    response_model=List[CommercialTermResponse],
    summary="Listar condiciones de un cliente",
)
def get_terms_by_client(
    cliente_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return CommercialTermService.get_by_client(db, cliente_id)


@router.get(
    "/{term_id}",
    response_model=CommercialTermResponse,
    summary="Obtener condición por ID",
)
def get_term(
    term_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    term = CommercialTermService.get_by_id(db, term_id)
    if not term:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Condición comercial no encontrada",
        )
    return term


@router.post(
    "/",
    response_model=CommercialTermResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Pactar condición para cliente",
)
def create_term(
    term_in: CommercialTermCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    term = CommercialTermService.create(db, term_in)
    HistoryService.log(
        db, "CREAR", "Condiciones", current_user.id,
        {
            "entidad": f"Cliente {term.cliente_id}",
            "descripcion": (
                f"Pactó condición {term.tipo_condicion} para el cliente "
                f"{term.cliente.razon_social if term.cliente else term.cliente_id}"
            ),
        },
        request.client.host if request.client else None,
    )
    return term


@router.put(
    "/{term_id}",
    response_model=CommercialTermResponse,
    summary="Actualizar condición comercial",
)
def update_term(
    term_id: int,
    term_in: CommercialTermUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    term = CommercialTermService.update(db, term_id, term_in)
    HistoryService.log(
        db, "ACTUALIZAR", "Condiciones", current_user.id,
        {
            "entidad": f"Condición {term_id}",
            "descripcion": (
                f"Actualizó la condición {term.tipo_condicion} del cliente "
                f"{term.cliente.razon_social if term.cliente else term.cliente_id}"
            ),
        },
        request.client.host if request.client else None,
    )
    return term