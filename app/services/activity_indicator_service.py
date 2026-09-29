from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import LIMA_TZ, ahora_lima
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido


class ActivityIndicatorService:
    @staticmethod
    def _rango_dia_para(momento: datetime) -> Tuple[datetime, datetime, str]:
        dia = momento.astimezone(LIMA_TZ).date()
        inicio = datetime.combine(dia, time(0, 0), tzinfo=LIMA_TZ)
        fin = inicio + timedelta(days=1)
        etiqueta = dia.strftime("%d/%m")
        return inicio, fin, etiqueta

    @staticmethod
    def _dia_anterior_de(inicio_dia: datetime) -> Tuple[datetime, datetime, str]:
        momento_anterior = inicio_dia - timedelta(seconds=1)
        return ActivityIndicatorService._rango_dia_para(momento_anterior)

    @staticmethod
    def _contar_solicitudes(
        db: Session, inicio: datetime, fin: datetime, resultado: Optional[str] = None
    ) -> int:
        stmt = select(func.count(SolicitudCliente.id)).where(
            SolicitudCliente.fecha_solicitud >= inicio,
            SolicitudCliente.fecha_solicitud < fin,
            SolicitudCliente.estado == "Atendida",
            SolicitudCliente.auditado_ia.is_(True),
        )
        if resultado:
            stmt = stmt.where(SolicitudCliente.resultado_auditoria == resultado)
        return db.scalar(stmt) or 0

    @staticmethod
    def _contar_pedidos(
        db: Session, inicio: datetime, fin: datetime, resultado: Optional[str] = None
    ) -> int:
        stmt = select(func.count(Pedido.id)).where(
            Pedido.fecha_aprobacion >= inicio,
            Pedido.fecha_aprobacion < fin,
            Pedido.estado.in_(("Aprobado", "Entregado")),
            Pedido.auditado_ia.is_(True),
        )
        if resultado:
            stmt = stmt.where(Pedido.resultado_auditoria == resultado)
        return db.scalar(stmt) or 0

    @staticmethod
    def _tiempo_promedio_decision_minutos(
        db: Session, inicio: Optional[datetime] = None, fin: Optional[datetime] = None
    ) -> Optional[Decimal]:
        inicio_decision = func.coalesce(
            SolicitudCliente.hora_apertura_modal, SolicitudCliente.fecha_solicitud
        )
        stmt = (
            select(
                func.avg(
                    func.extract("epoch", Pedido.fecha_aprobacion)
                    - func.extract("epoch", inicio_decision)
                )
            )
            .select_from(Pedido)
            .join(SolicitudCliente, SolicitudCliente.id == Pedido.solicitud_id)
            .where(Pedido.fecha_aprobacion.isnot(None))
        )
        if inicio is not None and fin is not None:
            stmt = stmt.where(Pedido.fecha_aprobacion >= inicio, Pedido.fecha_aprobacion < fin)

        segundos = db.scalar(stmt)
        if segundos is None:
            return None
        return (Decimal(str(segundos)) / Decimal(60)).quantize(Decimal("0.01"))

    @staticmethod
    def _variacion_pct(actual: int, anterior: int) -> Decimal:
        if anterior == 0:
            return Decimal("100.00") if actual > 0 else Decimal("0.00")
        return (Decimal(actual - anterior) / Decimal(anterior) * 100).quantize(Decimal("0.01"))

    @staticmethod
    def calcular_resumen(db: Session) -> dict:
        ahora = ahora_lima()
        inicio_actual, fin_actual, etiqueta_actual = ActivityIndicatorService._rango_dia_para(ahora)
        inicio_anterior, fin_anterior, etiqueta_anterior = ActivityIndicatorService._dia_anterior_de(
            inicio_actual
        )

        solicitudes_actual = ActivityIndicatorService._contar_solicitudes(db, inicio_actual, fin_actual)
        solicitudes_anterior = ActivityIndicatorService._contar_solicitudes(db, inicio_anterior, fin_anterior)
        pedidos_actual = ActivityIndicatorService._contar_pedidos(db, inicio_actual, fin_actual)
        pedidos_anterior = ActivityIndicatorService._contar_pedidos(db, inicio_anterior, fin_anterior)

        tpd_dia_actual = ActivityIndicatorService._tiempo_promedio_decision_minutos(
            db, inicio_actual, fin_actual
        )
        tpd_general = ActivityIndicatorService._tiempo_promedio_decision_minutos(db)

        return {
            "dia_actual": etiqueta_actual,
            "dia_anterior": etiqueta_anterior,
            "solicitudes_dia_actual": solicitudes_actual,
            "solicitudes_dia_anterior": solicitudes_anterior,
            "variacion_solicitudes_pct": ActivityIndicatorService._variacion_pct(
                solicitudes_actual, solicitudes_anterior
            ),
            "pedidos_dia_actual": pedidos_actual,
            "pedidos_dia_anterior": pedidos_anterior,
            "variacion_pedidos_pct": ActivityIndicatorService._variacion_pct(pedidos_actual, pedidos_anterior),
            "solicitudes_conformes_dia_actual": ActivityIndicatorService._contar_solicitudes(
                db, inicio_actual, fin_actual, "Conforme"
            ),
            "solicitudes_con_observaciones_dia_actual": ActivityIndicatorService._contar_solicitudes(
                db, inicio_actual, fin_actual, "Con_Observaciones"
            ),
            "pedidos_conformes_dia_actual": ActivityIndicatorService._contar_pedidos(
                db, inicio_actual, fin_actual, "Conforme"
            ),
            "pedidos_con_observaciones_dia_actual": ActivityIndicatorService._contar_pedidos(
                db, inicio_actual, fin_actual, "Con_Observaciones"
            ),
            "tiempo_promedio_decision_minutos": tpd_dia_actual,
            "tiempo_promedio_decision_minutos_general": tpd_general,
        }

    @staticmethod
    def get_serie_dias(db: Session, cantidad_dias: int = 15) -> List[dict]:
        ahora = ahora_lima()
        inicio, fin, etiqueta = ActivityIndicatorService._rango_dia_para(ahora)

        dias = []
        for _ in range(cantidad_dias):
            solicitudes = ActivityIndicatorService._contar_solicitudes(db, inicio, fin)
            pedidos = ActivityIndicatorService._contar_pedidos(db, inicio, fin)
            tpd = ActivityIndicatorService._tiempo_promedio_decision_minutos(db, inicio, fin)
            dias.append(
                {
                    "label": etiqueta,
                    "solicitudes": solicitudes,
                    "pedidos": pedidos,
                    "tiempo_promedio_decision_minutos": float(tpd) if tpd is not None else None,
                }
            )
            inicio, fin, etiqueta = ActivityIndicatorService._dia_anterior_de(inicio)

        dias.reverse()

        primer_dia_con_actividad = next(
            (i for i, d in enumerate(dias) if d["solicitudes"] > 0 or d["pedidos"] > 0),
            len(dias) - 1,
        )
        return dias[primer_dia_con_actividad:]
