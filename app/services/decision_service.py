from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.decision import DecisionComercial
from app.models.order import Pedido


class DecisionService:
    @staticmethod
    def registrar_confirmacion_pedido(
        db: Session, pedido: Pedido, usuario_id: int
    ) -> Optional[DecisionComercial]:
        ya_existe = db.scalar(
            select(DecisionComercial).where(
                DecisionComercial.pedido_id == pedido.id,
                DecisionComercial.tipo_decision == "Confirmacion_Pedido",
            )
        )
        if ya_existe:
            return None

        tiene_error_items = any(d.tiene_error for d in pedido.detalles)
        tiene_falla_cc = bool(pedido.auditoria_condicion and pedido.auditoria_condicion.tiene_falla)
        tiene_incidencia = tiene_error_items or tiene_falla_cc

        motivos = []
        if tiene_error_items:
            motivos.append("ítems con error detectado")
        if tiene_falla_cc:
            motivos.append("falla en condición comercial")

        decision = DecisionComercial(
            usuario_id=usuario_id,
            pedido_id=pedido.id,
            tipo_decision="Confirmacion_Pedido",
            recomendacion_ia=(
                f"Se detectaron incidencias antes de confirmar: {', '.join(motivos)}."
                if tiene_incidencia
                else "Sin incidencias detectadas al momento de confirmar el pedido."
            ),
            decision_tomada=(
                f"Confirmó el pedido {pedido.codigo_pedido} a pesar de la(s) incidencia(s) detectada(s)."
                if tiene_incidencia
                else f"Confirmó el pedido {pedido.codigo_pedido} sin incidencias registradas."
            ),
            es_efectiva=not tiene_incidencia,
            observaciones_impacto=", ".join(motivos) if motivos else None,
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)
        return decision

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[dict]:
        stmt = (
            select(DecisionComercial)
            .options(
                selectinload(DecisionComercial.pedido).selectinload(Pedido.cliente),
                selectinload(DecisionComercial.usuario),
            )
            .order_by(DecisionComercial.fecha_decision.desc())
            .offset(skip)
            .limit(limit)
        )
        registros = db.scalars(stmt).all()

        return [
            {
                "id": d.id,
                "pedido_id": d.pedido_id,
                "pedido_codigo": d.pedido.codigo_pedido if d.pedido else None,
                "cliente_nombre": d.pedido.cliente.razon_social if d.pedido and d.pedido.cliente else None,
                "usuario_nombre": d.usuario.nombre_completo if d.usuario else None,
                "tipo_decision": d.tipo_decision,
                "decision_tomada": d.decision_tomada,
                "recomendacion_ia": d.recomendacion_ia,
                "es_efectiva": d.es_efectiva,
                "observaciones_impacto": d.observaciones_impacto,
                "fecha_decision": d.fecha_decision,
            }
            for d in registros
        ]
