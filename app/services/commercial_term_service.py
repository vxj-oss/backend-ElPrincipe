from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.commercial_term import CondicionComercial
from app.models.order import Pedido
from app.schemas.commercial_term import CommercialTermCreate, CommercialTermUpdate
from app.services.condicion_opcion_service import CondicionOpcionService
from app.services.indicator_service import IndicatorService

ESTADOS_NO_CONFIRMADOS = ("Pendiente",)

CAMPO_POR_TIPO = {
    "Credito": "dias_plazo_pactados",
    "Descuento": "porcentaje_descuento",
    "Forma_Pago": "forma_pago_pactada",
}


def _valores_coinciden(valor, opcion_catalogo: str) -> bool:
    a, b = str(valor).strip(), opcion_catalogo.strip()
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


class CommercialTermService:
    @staticmethod
    def _validar_valor_en_catalogo(db: Session, tipo_condicion: str, valor) -> None:
        if valor is None:
            return
        valores_validos = CondicionOpcionService.valores_activos(db, tipo_condicion)
        if not valores_validos:
            return
        if not any(_valores_coinciden(valor, v) for v in valores_validos):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"'{valor}' no es una opción vigente del catálogo para {tipo_condicion}. "
                    f"Opciones válidas: {', '.join(valores_validos)}."
                ),
            )

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
    def _reauditar_pedidos_cliente(db: Session, cliente_id: int) -> None:
        from app.services.order_service import OrderService

        stmt = (
            select(Pedido)
            .options(selectinload(Pedido.auditoria_condicion))
            .where(
                Pedido.cliente_id == cliente_id,
                Pedido.estado.in_(ESTADOS_NO_CONFIRMADOS),
            )
        )
        for pedido in db.scalars(stmt).all():
            evaluacion = OrderService._auditar_condicion_comercial_pedido(
                db=db,
                pedido_id=pedido.id,
                cliente_id=cliente_id,
                forma_pago=pedido.forma_pago,
                monto_total=pedido.monto_total,
            )
            if pedido.auditoria_condicion:
                pedido.auditoria_condicion.condicion_comercial_id = evaluacion.condicion_comercial_id
                pedido.auditoria_condicion.tiene_falla = evaluacion.tiene_falla
                pedido.auditoria_condicion.motivo_falla = evaluacion.motivo_falla
                pedido.auditoria_condicion.fecha_evaluacion = datetime.now(timezone.utc)
            else:
                db.add(evaluacion)

    @staticmethod
    def create(db: Session, term_in: CommercialTermCreate) -> CondicionComercial:
        datos = term_in.model_dump()
        CommercialTermService._validar_valor_en_catalogo(
            db, datos["tipo_condicion"], datos.get(CAMPO_POR_TIPO[datos["tipo_condicion"]])
        )
        existente = db.scalar(
            select(CondicionComercial).where(
                CondicionComercial.cliente_id == datos["cliente_id"],
                CondicionComercial.tipo_condicion == datos["tipo_condicion"],
            )
        )
        if existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "El cliente ya tiene una condición de este tipo. "
                    "Edita la existente en lugar de crear otra."
                ),
            )

        term = CondicionComercial(**datos)
        db.add(term)
        db.flush()
        CommercialTermService._reauditar_pedidos_cliente(db, term.cliente_id)
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
        datos = term_in.model_dump(exclude_unset=True)
        tipo_resultante = datos.get("tipo_condicion", term.tipo_condicion)
        campo_valor = CAMPO_POR_TIPO.get(tipo_resultante)
        if campo_valor and campo_valor in datos:
            CommercialTermService._validar_valor_en_catalogo(db, tipo_resultante, datos[campo_valor])

        for key, value in datos.items():
            setattr(term, key, value)
        db.flush()
        CommercialTermService._reauditar_pedidos_cliente(db, term.cliente_id)
        db.commit()
        db.refresh(term)
        IndicatorService.calculate_and_save(
            db, resumen="Recálculo automático tras actualización de condición comercial"
        )
        return CommercialTermService.get_by_id(db, term_id)

    @staticmethod
    def delete(db: Session, term_id: int) -> Dict[str, Any]:
        term = CommercialTermService.get_by_id(db, term_id)
        if not term:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Condición comercial no encontrada",
            )
        cliente_id = term.cliente_id
        cliente_nombre = term.cliente.razon_social if term.cliente else str(cliente_id)
        tipo_condicion = term.tipo_condicion

        db.delete(term)
        db.commit()
        CommercialTermService._reauditar_pedidos_cliente(db, cliente_id)
        db.commit()
        IndicatorService.calculate_and_save(
            db, resumen="Recálculo automático tras eliminación de condición comercial"
        )
        return {"cliente_nombre": cliente_nombre, "tipo_condicion": tipo_condicion}