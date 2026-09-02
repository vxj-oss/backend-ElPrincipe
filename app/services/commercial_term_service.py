from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.commercial_term import CondicionComercial
from app.schemas.commercial_term import CommercialTermCreate, CommercialTermUpdate
from app.services.indicator_service import IndicatorService


class CommercialTermService:
    @staticmethod
    def get_all(
        db: Session,
        cliente_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[CondicionComercial]:
        stmt = (
            select(CondicionComercial)
            .options(
                selectinload(CondicionComercial.cliente),
            )
        )
        if cliente_id:
            stmt = stmt.where(CondicionComercial.cliente_id == cliente_id)

        stmt = stmt.order_by(CondicionComercial.id.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_by_id(db: Session, term_id: int) -> Optional[CondicionComercial]:
        stmt = (
            select(CondicionComercial)
            .options(
                selectinload(CondicionComercial.cliente),
            )
            .where(CondicionComercial.id == term_id)
        )
        return db.scalar(stmt)

    @staticmethod
    def get_by_client(db: Session, cliente_id: int) -> List[CondicionComercial]:
        stmt = (
            select(CondicionComercial)
            .options(
                selectinload(CondicionComercial.cliente),
            )
            .where(CondicionComercial.cliente_id == cliente_id)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def create(db: Session, term_in: CommercialTermCreate) -> CondicionComercial:
        term = CondicionComercial(**term_in.model_dump())
        db.add(term)
        db.commit()
        db.refresh(term)
        IndicatorService.calculate_and_save(
            db, resumen="Recálculo automático tras registro de condición comercial"
        )
        return CommercialTermService.get_by_id(db, term.id)

    @staticmethod
    def update(
        db: Session, term_id: int, term_in: CommercialTermUpdate
    ) -> CondicionComercial:
        term = CommercialTermService.get_by_id(db, term_id)
        if not term:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Condición comercial no encontrada",
            )
        for key, value in term_in.model_dump(exclude_unset=True).items():
            setattr(term, key, value)
        db.commit()
        db.refresh(term)
        return term