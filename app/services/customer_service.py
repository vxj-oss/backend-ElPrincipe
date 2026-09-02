from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Cliente
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerService:
    @staticmethod
    def get_by_id(db: Session, customer_id: int) -> Optional[Cliente]:
        return db.scalar(select(Cliente).where(Cliente.id == customer_id))

    @staticmethod
    def get_by_ruc_dni(db: Session, ruc_dni: str) -> Optional[Cliente]:
        return db.scalar(select(Cliente).where(Cliente.ruc_dni == ruc_dni))

    @staticmethod
    def get_all(
        db: Session,
        estado: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Cliente]:
        stmt = select(Cliente)
        if estado:
            stmt = stmt.where(Cliente.estado == estado)
        if search:
            filtro = f"%{search}%"
            stmt = stmt.where(
                (Cliente.razon_social.ilike(filtro)) | (Cliente.ruc_dni.ilike(filtro))
            )
        stmt = stmt.order_by(Cliente.id.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def create(db: Session, cust_in: CustomerCreate) -> Cliente:
        if CustomerService.get_by_ruc_dni(db, cust_in.ruc_dni):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe un cliente con el RUC/DNI '{cust_in.ruc_dni}'",
            )
        customer = Cliente(**cust_in.model_dump())
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer

    @staticmethod
    def update(db: Session, customer_id: int, cust_in: CustomerUpdate) -> Cliente:
        customer = CustomerService.get_by_id(db, customer_id)
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente no encontrado",
            )

        datos = cust_in.model_dump(exclude_unset=True)
        if "ruc_dni" in datos and datos["ruc_dni"] != customer.ruc_dni:
            existente = CustomerService.get_by_ruc_dni(db, datos["ruc_dni"])
            if existente:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ya existe otro cliente con el RUC/DNI '{datos['ruc_dni']}'",
                )

        for key, value in datos.items():
            setattr(customer, key, value)

        db.commit()
        db.refresh(customer)
        return customer

    @staticmethod
    def delete(db: Session, customer_id: int) -> bool:
        customer = CustomerService.get_by_id(db, customer_id)
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente no encontrado",
            )
        db.delete(customer)
        db.commit()
        return True