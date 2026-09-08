from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate
from app.services.customer_service import CustomerService
from app.services.history_service import HistoryService

router = APIRouter(prefix="/customers", tags=["Clientes"])


@router.get("/", response_model=List[CustomerResponse], summary="Listar clientes")
def list_customers(
    estado: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return CustomerService.get_all(
        db, estado=estado, search=search, skip=skip, limit=limit
    )


@router.get("/{customer_id}", response_model=CustomerResponse, summary="Obtener cliente por ID")
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    customer = CustomerService.get_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    return customer


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, summary="Crear cliente")
def create_customer(
    cust_in: CustomerCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    customer = CustomerService.create(db, cust_in)
    HistoryService.log(
        db, "CREAR", "Clientes", current_user.id,
        {"entidad": customer.ruc_dni, "descripcion": f"Registró nuevo cliente {customer.razon_social} ({customer.ruc_dni})"},
        request.client.host if request.client else None
    )
    return customer


@router.put("/{customer_id}", response_model=CustomerResponse, summary="Actualizar cliente")
def update_customer(
    customer_id: int,
    cust_in: CustomerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    customer = CustomerService.update(db, customer_id, cust_in)
    HistoryService.log(
        db, "ACTUALIZAR", "Clientes", current_user.id,
        {"entidad": customer.ruc_dni, "descripcion": f"Actualizó datos de {customer.razon_social}"},
        request.client.host if request.client else None
    )
    return customer


@router.delete("/{customer_id}", summary="Eliminar o desactivar cliente")
def delete_customer(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    customer = CustomerService.get_by_id(db, customer_id)
    entidad = customer.ruc_dni if customer else f"ID {customer_id}"
    razon = customer.razon_social if customer else entidad
    resultado = CustomerService.delete(db, customer_id)
    accion_txt = "Desactivó" if resultado.get("soft_delete") else "Eliminó"
    HistoryService.log(
        db, "ELIMINAR", "Clientes", current_user.id,
        {"entidad": entidad, "descripcion": f"{accion_txt} al cliente {razon}"},
        request.client.host if request.client else None
    )
    return resultado