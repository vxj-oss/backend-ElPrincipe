from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin, get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services.category_service import CategoryService

router = APIRouter(prefix="/categories", tags=["Categorías"])


@router.get("/", response_model=List[CategoryResponse], summary="Listar categorías")
def list_categories(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return CategoryService.get_all(db, skip=skip, limit=limit)


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED, summary="Crear categoría")
def create_category(
    cat_in: CategoryCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return CategoryService.create(db, cat_in)


@router.put("/{category_id}", response_model=CategoryResponse, summary="Actualizar categoría")
def update_category(
    category_id: int,
    cat_in: CategoryUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return CategoryService.update(db, category_id, cat_in)


@router.delete("/{category_id}", summary="Eliminar categoría")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    CategoryService.delete(db, category_id)
    return {"message": "Categoría eliminada exitosamente"}