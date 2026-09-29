from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.condicion_opcion import OpcionCondicionComercial
from app.schemas.condicion_opcion import OpcionCondicionCreate, OpcionCondicionUpdate


class CondicionOpcionService:
    @staticmethod
    def get_by_id(db: Session, opcion_id: int) -> Optional[OpcionCondicionComercial]:
        return db.scalar(select(OpcionCondicionComercial).where(OpcionCondicionComercial.id == opcion_id))

    @staticmethod
    def get_all(
        db: Session, tipo_condicion: Optional[str] = None, solo_activas: bool = False
    ) -> List[OpcionCondicionComercial]:
        stmt = select(OpcionCondicionComercial)
        if tipo_condicion:
            stmt = stmt.where(OpcionCondicionComercial.tipo_condicion == tipo_condicion)
        if solo_activas:
            stmt = stmt.where(OpcionCondicionComercial.activo.is_(True))
        stmt = stmt.order_by(OpcionCondicionComercial.tipo_condicion, OpcionCondicionComercial.orden)
        return list(db.scalars(stmt).all())

    @staticmethod
    def valores_activos(db: Session, tipo_condicion: str) -> List[str]:
        opciones = CondicionOpcionService.get_all(db, tipo_condicion=tipo_condicion, solo_activas=True)
        return [o.valor for o in opciones]

    @staticmethod
    def _en_uso_por_condiciones(db: Session, opcion: OpcionCondicionComercial) -> bool:
        from app.models.commercial_term import CondicionComercial
        from app.services.commercial_term_service import CAMPO_POR_TIPO, _valores_coinciden

        campo = CAMPO_POR_TIPO.get(opcion.tipo_condicion)
        if not campo:
            return False
        columna = getattr(CondicionComercial, campo)
        stmt = select(CondicionComercial).where(
            CondicionComercial.tipo_condicion == opcion.tipo_condicion,
            columna.is_not(None),
        )
        condiciones = db.scalars(stmt).all()
        return any(_valores_coinciden(getattr(c, campo), opcion.valor) for c in condiciones)

    @staticmethod
    def create(db: Session, opcion_in: OpcionCondicionCreate) -> OpcionCondicionComercial:
        existente = db.scalar(
            select(OpcionCondicionComercial).where(
                OpcionCondicionComercial.tipo_condicion == opcion_in.tipo_condicion,
                OpcionCondicionComercial.valor == opcion_in.valor,
            )
        )
        if existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe la opción '{opcion_in.valor}' para el tipo {opcion_in.tipo_condicion}.",
            )
        opcion = OpcionCondicionComercial(**opcion_in.model_dump())
        db.add(opcion)
        db.commit()
        db.refresh(opcion)
        return opcion

    @staticmethod
    def update(db: Session, opcion_id: int, opcion_in: OpcionCondicionUpdate) -> OpcionCondicionComercial:
        opcion = CondicionOpcionService.get_by_id(db, opcion_id)
        if not opcion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opción no encontrada")

        datos = opcion_in.model_dump(exclude_unset=True)
        if datos.get("activo") is False and opcion.activo:
            if CondicionOpcionService._en_uso_por_condiciones(db, opcion):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"No se puede desactivar '{opcion.etiqueta}': hay condiciones "
                        "comerciales pactadas que usan este valor."
                    ),
                )

        for key, value in datos.items():
            setattr(opcion, key, value)

        db.commit()
        db.refresh(opcion)
        return opcion

    @staticmethod
    def delete(db: Session, opcion_id: int) -> bool:
        opcion = CondicionOpcionService.get_by_id(db, opcion_id)
        if not opcion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opción no encontrada")
        if CondicionOpcionService._en_uso_por_condiciones(db, opcion):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"No se puede eliminar '{opcion.etiqueta}': hay condiciones comerciales "
                    "pactadas que usan este valor. Desactívala en su lugar."
                ),
            )
        db.delete(opcion)
        db.commit()
        return True
