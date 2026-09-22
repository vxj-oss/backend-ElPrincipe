from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.customer_request import (
    ComparacionPedidoRequest,
    ComparacionPedidoResponse,
    SolicitudClienteCreate,
    SolicitudClienteResponse,
)
from app.services.customer_request_service import SolicitudClienteService
from app.services.history_service import HistoryService

router = APIRouter(prefix="/customer-requests", tags=["Solicitudes de Clientes"])


@router.post(
    "/",
    response_model=SolicitudClienteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una nueva solicitud de cliente",
)
def create_customer_request(
    payload: SolicitudClienteCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    solicitud = SolicitudClienteService.create_request(
        db=db, user_id=current_user.id, payload=payload
    )
    HistoryService.log(
        db, "CREAR", "Solicitudes", current_user.id,
        {
            "entidad": solicitud.codigo_solicitud,
            "descripcion": (
                f"Registró la solicitud {solicitud.codigo_solicitud} "
                f"({len(solicitud.detalles)} ítem(s)) por canal {solicitud.canal_recepcion}"
            ),
        },
        request.client.host if request.client else None,
    )
    return solicitud


@router.get(
    "/",
    response_model=List[SolicitudClienteResponse],
    summary="Listar solicitudes de cliente",
)
def list_customer_requests(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    return SolicitudClienteService.get_all(db=db, skip=skip, limit=limit)


@router.get(
    "/{request_id}",
    response_model=SolicitudClienteResponse,
    summary="Obtener detalle de una solicitud",
)
def get_customer_request_detail(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    req = SolicitudClienteService.get_by_id(db=db, request_id=request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitud de cliente no encontrada.",
        )
    return req


@router.delete(
    "/{request_id}",
    summary="Eliminar una solicitud de cliente",
)
def delete_customer_request(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    info = SolicitudClienteService.delete(db, request_id)
    HistoryService.log(
        db, "ELIMINAR", "Solicitudes", current_user.id,
        {
            "entidad": info["codigo_solicitud"],
            "descripcion": f"Eliminó la solicitud {info['codigo_solicitud']} de {info['cliente_nombre']}",
        },
        request.client.host if request.client else None,
    )
    return {"message": "Solicitud eliminada correctamente."}


@router.post(
    "/validate-order",
    response_model=ComparacionPedidoResponse,
    summary="Validar pedido contra solicitud usando IA",
)
def validate_order_against_request(
    payload: ComparacionPedidoRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    return SolicitudClienteService.audit_order_against_request(db=db, payload=payload)