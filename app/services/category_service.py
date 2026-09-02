from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Categoria
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
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La categoría '{cat_in.nombre}' ya existe",
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

        for key, value in cat_in.model_dump(exclude_unset=True).items():
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
        db.delete(category)
        db.commit()
        return True