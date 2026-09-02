from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin, get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.services.history_service import HistoryService
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Productos"])


@router.get("/", response_model=List[ProductResponse], summary="Listar productos")
def list_products(
    category_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return ProductService.get_all(db, category_id=category_id, skip=skip, limit=limit)


@router.get("/{product_id}", response_model=ProductResponse, summary="Obtener producto por ID")
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return ProductService.get_by_id(db, product_id)


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, summary="Crear producto")
def create_product(
    prod_in: ProductCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_admin),
):
    prod = ProductService.create(db, prod_in)
    HistoryService.log(
        db, "CREAR", "Productos", current_user.id,
        {"entidad": prod.sku, "descripcion": f"Registró nuevo producto {prod.nombre} ({prod.sku})"},
        request.client.host if request.client else None
    )
    return prod


@router.put("/{product_id}", response_model=ProductResponse, summary="Actualizar producto")
def update_product(
    product_id: int,
    prod_in: ProductUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_admin),
):
    prod = ProductService.update(db, product_id, prod_in)
    HistoryService.log(
        db, "ACTUALIZAR", "Productos", current_user.id,
        {"entidad": prod.sku, "descripcion": f"Actualizó datos de {prod.nombre} ({prod.sku})"},
        request.client.host if request.client else None
    )
    return prod


@router.delete("/{product_id}", summary="Eliminar producto")
def delete_product(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_admin),
):
    prod = ProductService.get_by_id(db, product_id)
    sku = prod.sku if prod else f"ID {product_id}"
    ProductService.delete(db, product_id)
    HistoryService.log(
        db, "ELIMINAR", "Productos", current_user.id,
        {"entidad": sku, "descripcion": f"Eliminó el producto {sku}"},
        request.client.host if request.client else None
    )
    return {"message": "Producto eliminado exitosamente"}