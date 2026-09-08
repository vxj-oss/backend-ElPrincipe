from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.decision import DecisionComercial
from app.models.order import Pedido

ESTADOS_SIN_DECISION = ("Cancelado",)


class DecisionService:
    @staticmethod
    def _incidencia_pedido(pedido: Pedido) -> tuple[bool, bool]:
        tiene_error_items = any(d.tiene_error for d in pedido.detalles)
        tiene_falla_cc = bool(
            pedido.auditoria_condicion and pedido.auditoria_condicion.tiene_falla
        )
        return tiene_error_items, tiene_falla_cc

    @staticmethod
    def _buscar_decision(db: Session, pedido_id: int) -> Optional[DecisionComercial]:
        return db.scalar(
            select(DecisionComercial).where(
                DecisionComercial.pedido_id == pedido_id,
                DecisionComercial.tipo_decision == "Confirmacion_Pedido",
            )
        )

    @staticmethod
    def sincronizar_pedido(db: Session, pedido: Pedido) -> Optional[DecisionComercial]:
        if pedido.estado in ESTADOS_SIN_DECISION:
            return None

        tiene_error_items, tiene_falla_cc = DecisionService._incidencia_pedido(pedido)
        tiene_incidencia = tiene_error_items or tiene_falla_cc

        motivos = []
        if tiene_error_items:
            motivos.append("ítems con error detectado")
        if tiene_falla_cc:
            motivos.append("falla en condición comercial")
        detalle_motivos = ", ".join(motivos)

        decision = DecisionService._buscar_decision(db, pedido.id)

        if decision is None:
            decision = DecisionComercial(
                usuario_id=pedido.usuario_id,
                pedido_id=pedido.id,
                tipo_decision="Confirmacion_Pedido",
                recomendacion_ia=(
                    f"Al registrar el pedido se detectaron incidencias: {detalle_motivos}."
                    if tiene_incidencia
                    else "Al registrar el pedido no se detectaron incidencias."
                ),
                decision_tomada=(
                    f"Registró el pedido {pedido.codigo_pedido} con incidencias pendientes de resolver."
                    if tiene_incidencia
                    else f"Registró el pedido {pedido.codigo_pedido} sin incidencias."
                ),
                es_efectiva=not tiene_incidencia,
                requirio_correccion=False,
                observaciones_impacto=detalle_motivos or None,
            )
            db.add(decision)
            return decision

        if decision.es_efectiva is False and not tiene_incidencia:
            decision.requirio_correccion = True
        decision.es_efectiva = not tiene_incidencia
        if tiene_incidencia:
            decision.observaciones_impacto = detalle_motivos
        return decision

    @staticmethod
    def sincronizar_pedidos(db: Session) -> None:
        stmt = (
            select(Pedido)
            .options(
                selectinload(Pedido.detalles),
                selectinload(Pedido.auditoria_condicion),
            )
            .where(Pedido.estado.notin_(ESTADOS_SIN_DECISION))
        )
        for pedido in db.scalars(stmt).all():
            DecisionService.sincronizar_pedido(db, pedido)

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
                "requirio_correccion": d.requirio_correccion,
                "observaciones_impacto": d.observaciones_impacto,
                "fecha_decision": d.fecha_decision,
            }
            for d in registros
        ]
