from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.customer_request_item import SolicitudClienteDetalle
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.models.stock_movement import MovimientoStock
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.category_service import CategoryService


class ProductService:
    @staticmethod
    def get_by_id(db: Session, product_id: int) -> Optional[Producto]:
        stmt = (
            select(Producto)
            .options(joinedload(Producto.categoria))
            .where(Producto.id == product_id)
        )
        return db.scalar(stmt)

    @staticmethod
    def get_by_sku(db: Session, sku: str) -> Optional[Producto]:
        return db.scalar(select(Producto).where(Producto.sku == sku))

    @staticmethod
    def get_all(
        db: Session,
        category_id: Optional[int] = None,
        incluir_inactivos: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Producto]:
        stmt = select(Producto).options(joinedload(Producto.categoria))
        if category_id:
            stmt = stmt.where(Producto.categoria_id == category_id)
        if not incluir_inactivos:
            stmt = stmt.where(Producto.activo.is_(True))
        stmt = stmt.order_by(Producto.id.desc())
        return list(db.scalars(stmt.offset(skip).limit(limit)).all())

    @staticmethod
    def create(db: Session, prod_in: ProductCreate) -> Producto:
        if not CategoryService.get_by_id(db, prod_in.categoria_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La categoría especificada no existe",
            )
        if ProductService.get_by_sku(db, prod_in.sku):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El SKU '{prod_in.sku}' ya está asignado a otro producto",
            )

        product = Producto(**prod_in.model_dump())
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def update(db: Session, product_id: int, prod_in: ProductUpdate) -> Producto:
        product = ProductService.get_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado",
            )

        update_data = prod_in.model_dump(exclude_unset=True)
        if "categoria_id" in update_data:
            if not CategoryService.get_by_id(db, update_data["categoria_id"]):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="La categoría especificada no existe",
                )

        for key, value in update_data.items():
            setattr(product, key, value)

        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def _tiene_historial(db: Session, product_id: int) -> bool:
        en_pedidos = db.scalar(
            select(func.count(DetallePedido.id)).where(DetallePedido.producto_id == product_id)
        ) or 0
        en_solicitudes = db.scalar(
            select(func.count(SolicitudClienteDetalle.id)).where(
                SolicitudClienteDetalle.producto_id == product_id
            )
        ) or 0
        en_movimientos = db.scalar(
            select(func.count(MovimientoStock.id)).where(MovimientoStock.producto_id == product_id)
        ) or 0
        return (en_pedidos + en_solicitudes + en_movimientos) > 0

    @staticmethod
    def delete(db: Session, product_id: int) -> dict:
        product = ProductService.get_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado",
            )

        if ProductService._tiene_historial(db, product_id):
            if not product.activo:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El producto ya está inactivo.",
                )
            product.activo = False
            db.commit()
            return {
                "message": (
                    "El producto tiene historial de pedidos o movimientos de stock, "
                    "por lo que se marcó como inactivo en lugar de eliminarlo."
                ),
                "soft_delete": True,
            }

        db.delete(product)
        db.commit()
        return {"message": "Producto eliminado exitosamente", "soft_delete": False}

    @staticmethod
    def reactivar(db: Session, product_id: int) -> Producto:
        product = ProductService.get_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado",
            )
        product.activo = True
        db.commit()
        db.refresh(product)
        return product