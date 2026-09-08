from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.category import Categoria
from app.models.product import Producto
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    @staticmethod
    def get_by_id(db: Session, category_id: int) -> Optional[Categoria]:
        return db.scalar(select(Categoria).where(Categoria.id == category_id))

    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Categoria]:
        return db.scalar(select(Categoria).where(Categoria.nombre == name))

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[Categoria]:
        return list(db.scalars(select(Categoria).offset(skip).limit(limit)).all())

    @staticmethod
    def create(db: Session, cat_in: CategoryCreate) -> Categoria:
        if CategoryService.get_by_name(db, cat_in.nombre):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una categoría llamada '{cat_in.nombre}'.",
            )
        category = Categoria(**cat_in.model_dump())
        db.add(category)
        db.commit()
        db.refresh(category)
        return category

    @staticmethod
    def update(db: Session, category_id: int, cat_in: CategoryUpdate) -> Categoria:
        category = CategoryService.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada",
            )

        datos = cat_in.model_dump(exclude_unset=True)

        nuevo_nombre = datos.get("nombre")
        if nuevo_nombre and nuevo_nombre != category.nombre:
            existente = CategoryService.get_by_name(db, nuevo_nombre)
            if existente and existente.id != category_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe una categoría llamada '{nuevo_nombre}'.",
                )

        for key, value in datos.items():
            setattr(category, key, value)

        db.commit()
        db.refresh(category)
        return category

    @staticmethod
    def delete(db: Session, category_id: int) -> bool:
        category = CategoryService.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada",
            )

        productos_asociados = db.scalar(
            select(func.count(Producto.id)).where(Producto.categoria_id == category_id)
        ) or 0
        if productos_asociados > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"No se puede eliminar: la categoría tiene {productos_asociados} "
                    "producto(s) asociado(s). Reasígnalos a otra categoría primero."
                ),
            )

        db.delete(category)
        db.commit()
        return True