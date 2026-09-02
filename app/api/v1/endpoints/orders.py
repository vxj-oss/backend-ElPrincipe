from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.order import OrderCreate, OrderResponse, OrderUpdate
from app.services.history_service import HistoryService
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Pedidos"])


@router.get("/", response_model=List[OrderResponse], summary="Listar pedidos")
def list_orders(
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    con_error: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return OrderService.get_all(
        db,
        cliente_id=cliente_id,
        estado=estado,
        con_error=con_error,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{order_id}", response_model=OrderResponse, summary="Obtener pedido por ID"
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    order = OrderService.get_by_id(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido no encontrado",
        )
    return order


@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear pedido con evaluación automática",
)
def create_order(
    order_in: OrderCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    order = OrderService.create(db, user_id=current_user.id, order_in=order_in)

    # Detalle de auditoría desde FallaCondicionComercial
    desc_audit = (
        f"Creó pedido {order.codigo_pedido} por S/ {float(order.monto_total):,.2f}"
    )
    if order.auditoria_condicion and order.auditoria_condicion.tiene_falla:
        desc_audit += (
            f" (Falla en condición comercial: {order.auditoria_condicion.motivo_falla})"
        )

    HistoryService.log(
        db,
        "CREAR",
        "Pedidos",
        current_user.id,
        {
            "entidad": order.codigo_pedido,
            "descripcion": desc_audit,
        },
        request.client.host if request.client else None,
    )
    return order


@router.put("/{order_id}", response_model=OrderResponse, summary="Actualizar pedido")
def update_order(
    order_id: int,
    order_in: OrderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    order = OrderService.update(db, order_id, order_in, usuario_id=current_user.id)
    HistoryService.log(
        db,
        "ACTUALIZAR",
        "Pedidos",
        current_user.id,
        {
            "entidad": order.codigo_pedido,
            "descripcion": f"Actualizó pedido {order.codigo_pedido}",
        },
        request.client.host if request.client else None,
    )
    return order


@router.delete("/{order_id}", summary="Eliminar pedido")
def delete_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    order = OrderService.get_by_id(db, order_id)
    codigo = order.codigo_pedido if order else f"ID {order_id}"
    OrderService.delete(db, order_id)
    HistoryService.log(
        db,
        "ELIMINAR",
        "Pedidos",
        current_user.id,
        {
            "entidad": codigo,
            "descripcion": f"Eliminó el pedido {codigo}",
        },
        request.client.host if request.client else None,
    )
    return {"message": "Pedido eliminado exitosamente"}


@router.patch(
    "/{order_id}/error",
    response_model=OrderResponse,
    summary="Registrar error en pedido",
)
def register_order_error(
    order_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    tipo_error = payload.get("tipo_error", "Error_No_Especificado")
    descripcion = payload.get("descripcion", "")
    return OrderService.marcar_error(db, order_id, tipo_error, descripcion)


@router.patch(
    "/{order_id}/limpiar-error",
    response_model=OrderResponse,
    summary="Limpiar error en pedido",
)
def clear_order_error(
    order_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return OrderService.limpiar_error(db, order_id)