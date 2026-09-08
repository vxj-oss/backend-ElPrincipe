from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import List, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.commercial_term_failure import FallaCondicionComercial
from app.models.decision import DecisionComercial
from app.models.indicator_log import RegistroIndicador
from app.models.order import Pedido
from app.models.order_item import DetallePedido

LIMA_TZ = ZoneInfo("America/Lima")


class IndicatorService:
    @staticmethod
    def calcular_actual(db: Session) -> dict:
        """Cálculo global en vivo de NEPP, PFCC y NTDC sobre todos los registros
        no cancelados, con el mismo criterio que las series por rango."""
        total_items = (
            db.scalar(
                select(func.count(DetallePedido.id))
                .join(Pedido, Pedido.id == DetallePedido.pedido_id)
                .where(Pedido.estado != "Cancelado")
            )
            or 0
        )
        total_errores_prod = (
            db.scalar(
                select(func.count(DetallePedido.id))
                .join(Pedido, Pedido.id == DetallePedido.pedido_id)
                .where(Pedido.estado != "Cancelado", DetallePedido.tiene_error.is_(True))
            )
            or 0
        )
        total_pedidos = (
            db.scalar(select(func.count(Pedido.id)).where(Pedido.estado != "Cancelado")) or 0
        )
        val_nepp = (
            Decimal(str(round(total_errores_prod / total_items, 4)))
            if total_items > 0
            else Decimal("0.0000")
        )

        cc_evaluadas = (
            db.scalar(
                select(func.count(FallaCondicionComercial.id))
                .join(Pedido, Pedido.id == FallaCondicionComercial.pedido_id)
                .where(Pedido.estado != "Cancelado")
            )
            or 0
        )
        cc_falladas = (
            db.scalar(
                select(func.count(FallaCondicionComercial.id))
                .join(Pedido, Pedido.id == FallaCondicionComercial.pedido_id)
                .where(
                    Pedido.estado != "Cancelado",
                    FallaCondicionComercial.tiene_falla.is_(True),
                )
            )
            or 0
        )
        val_pfcc = (
            Decimal(str(round((cc_falladas / cc_evaluadas) * 100, 4)))
            if cc_evaluadas > 0
            else Decimal("0.0000")
        )

        def _contar_decisiones(*filtros) -> int:
            return (
                db.scalar(
                    select(func.count(DecisionComercial.id))
                    .join(Pedido, Pedido.id == DecisionComercial.pedido_id)
                    .where(
                        DecisionComercial.pedido_id.isnot(None),
                        Pedido.estado != "Cancelado",
                        *filtros,
                    )
                )
                or 0
            )

        total_decisiones = _contar_decisiones()
        total_efectivas = _contar_decisiones(DecisionComercial.es_efectiva.is_(True))
        total_corregidas = _contar_decisiones(DecisionComercial.requirio_correccion.is_(True))
        val_ntdc = (
            Decimal(str(round((total_efectivas / total_decisiones) * 100, 4)))
            if total_decisiones > 0
            else Decimal("0.0000")
        )

        return {
            "total_pedidos_evaluados": total_pedidos,
            "total_items_pedidos": total_items,
            "total_errores_productos": total_errores_prod,
            "valor_nepp": val_nepp,
            "total_condiciones_pactadas": cc_evaluadas,
            "total_fallas_condiciones": cc_falladas,
            "valor_pfcc": val_pfcc,
            "total_decisiones_evaluadas": total_decisiones,
            "total_decisiones_efectivas": total_efectivas,
            "total_decisiones_corregidas": total_corregidas,
            "valor_ntdc": val_ntdc,
        }

    @staticmethod
    def calculate_and_save(db: Session, resumen: Optional[str] = None) -> RegistroIndicador:
        from app.services.decision_service import DecisionService

        DecisionService.sincronizar_pedidos(db)
        db.flush()
        m = IndicatorService.calcular_actual(db)

        hoy_lima = datetime.now(LIMA_TZ).date()
        inicio = datetime.combine(hoy_lima, time.min, tzinfo=LIMA_TZ)
        fin = datetime.combine(hoy_lima, time.max, tzinfo=LIMA_TZ)
        log = db.scalar(
            select(RegistroIndicador)
            .where(RegistroIndicador.fecha_calculo >= inicio, RegistroIndicador.fecha_calculo <= fin)
            .order_by(RegistroIndicador.id.desc())
        )

        if log is None:
            log = RegistroIndicador()
            db.add(log)

        log.total_pedidos_evaluados = m["total_pedidos_evaluados"]
        log.total_items_pedidos = m["total_items_pedidos"]
        log.total_errores_productos = m["total_errores_productos"]
        log.valor_nepp = m["valor_nepp"]
        log.total_condiciones_pactadas = m["total_condiciones_pactadas"]
        log.total_fallas_condiciones = m["total_fallas_condiciones"]
        log.valor_pfcc = m["valor_pfcc"]
        log.total_decisiones_evaluadas = m["total_decisiones_evaluadas"]
        log.total_decisiones_efectivas = m["total_decisiones_efectivas"]
        log.total_decisiones_corregidas = m["total_decisiones_corregidas"]
        log.valor_ntdc = m["valor_ntdc"]
        log.resumen_operativo = resumen or "Cálculo global de indicadores de desempeño"

        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_latest(db: Session) -> RegistroIndicador:
        return IndicatorService.calculate_and_save(
            db, resumen="Cálculo automático de indicadores"
        )

    @staticmethod
    def get_all(db: Session, limit: int = 30) -> List[RegistroIndicador]:
        stmt = (
            select(RegistroIndicador)
            .order_by(RegistroIndicador.fecha_calculo.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def _calcular_para_rango(db: Session, inicio: datetime, fin: datetime) -> dict:
        """Calcula NEPP/PFCC/NTDC usando solo los registros reales (con fecha)
        que caen dentro de [inicio, fin] — sin depender de los snapshots
        guardados por calculate_and_save."""
        total_items = (
            db.scalar(
                select(func.count(DetallePedido.id))
                .join(Pedido, Pedido.id == DetallePedido.pedido_id)
                .where(
                    Pedido.fecha_pedido >= inicio,
                    Pedido.fecha_pedido <= fin,
                    Pedido.estado != "Cancelado",
                )
            )
            or 0
        )
        errores_items = (
            db.scalar(
                select(func.count(DetallePedido.id))
                .join(Pedido, Pedido.id == DetallePedido.pedido_id)
                .where(
                    Pedido.fecha_pedido >= inicio,
                    Pedido.fecha_pedido <= fin,
                    Pedido.estado != "Cancelado",
                    DetallePedido.tiene_error.is_(True),
                )
            )
            or 0
        )
        val_nepp = (
            Decimal(str(round(errores_items / total_items, 4))) if total_items > 0 else Decimal("0.0000")
        )

        cc_evaluadas = (
            db.scalar(
                select(func.count(FallaCondicionComercial.id))
                .join(Pedido, Pedido.id == FallaCondicionComercial.pedido_id)
                .where(
                    Pedido.fecha_pedido >= inicio,
                    Pedido.fecha_pedido <= fin,
                    Pedido.estado != "Cancelado",
                )
            )
            or 0
        )
        cc_falladas = (
            db.scalar(
                select(func.count(FallaCondicionComercial.id))
                .join(Pedido, Pedido.id == FallaCondicionComercial.pedido_id)
                .where(
                    Pedido.fecha_pedido >= inicio,
                    Pedido.fecha_pedido <= fin,
                    Pedido.estado != "Cancelado",
                    FallaCondicionComercial.tiene_falla.is_(True),
                )
            )
            or 0
        )
        val_pfcc = (
            Decimal(str(round((cc_falladas / cc_evaluadas) * 100, 4))) if cc_evaluadas > 0 else Decimal("0.0000")
        )

        total_decisiones = (
            db.scalar(
                select(func.count(DecisionComercial.id))
                .join(Pedido, Pedido.id == DecisionComercial.pedido_id)
                .where(
                    Pedido.fecha_pedido >= inicio,
                    Pedido.fecha_pedido <= fin,
                    DecisionComercial.pedido_id.isnot(None),
                    Pedido.estado != "Cancelado",
                )
            )
            or 0
        )
        decisiones_efectivas = (
            db.scalar(
                select(func.count(DecisionComercial.id))
                .join(Pedido, Pedido.id == DecisionComercial.pedido_id)
                .where(
                    Pedido.fecha_pedido >= inicio,
                    Pedido.fecha_pedido <= fin,
                    DecisionComercial.pedido_id.isnot(None),
                    Pedido.estado != "Cancelado",
                    DecisionComercial.es_efectiva.is_(True),
                )
            )
            or 0
        )
        val_ntdc = (
            Decimal(str(round((decisiones_efectivas / total_decisiones) * 100, 4)))
            if total_decisiones > 0
            else Decimal("0.0000")
        )

        return {"valor_nepp": val_nepp, "valor_pfcc": val_pfcc, "valor_ntdc": val_ntdc}

    @staticmethod
    def get_daily_series(db: Session) -> List[dict]:
        """Evolución diaria (Lun-Dom de la semana actual), con datos reales."""
        hoy_lima = datetime.now(LIMA_TZ).date()
        inicio_semana = hoy_lima - timedelta(days=hoy_lima.weekday())

        resultado = []
        for i in range(7):
            dia = inicio_semana + timedelta(days=i)
            inicio = datetime.combine(dia, time.min, tzinfo=LIMA_TZ)
            fin = datetime.combine(dia, time.max, tzinfo=LIMA_TZ)
            valores = IndicatorService._calcular_para_rango(db, inicio, fin)
            resultado.append({"label": dia.isoformat(), **valores})
        return resultado

    @staticmethod
    def get_weekly_series(db: Session) -> List[dict]:
        """Comparación semanal (Sem 1-4 del mes actual), con datos reales.
        La última semana se extiende hasta el fin de mes para no dejar
        fuera los días 29-31."""
        hoy_lima = datetime.now(LIMA_TZ).date()
        inicio_mes = hoy_lima.replace(day=1)
        if inicio_mes.month == 12:
            fin_mes = inicio_mes.replace(year=inicio_mes.year + 1, month=1) - timedelta(days=1)
        else:
            fin_mes = inicio_mes.replace(month=inicio_mes.month + 1) - timedelta(days=1)

        resultado = []
        for i in range(4):
            dia_inicio = inicio_mes + timedelta(days=i * 7)
            dia_fin = fin_mes if i == 3 else dia_inicio + timedelta(days=6)
            inicio = datetime.combine(dia_inicio, time.min, tzinfo=LIMA_TZ)
            fin = datetime.combine(dia_fin, time.max, tzinfo=LIMA_TZ)
            valores = IndicatorService._calcular_para_rango(db, inicio, fin)
            resultado.append({"label": f"Sem {i + 1}", **valores})
        return resultado

    @staticmethod
    def get_monthly_series(db: Session) -> List[dict]:
        """Evolución mensual (mes anterior vs. mes actual), con datos reales."""
        hoy_lima = datetime.now(LIMA_TZ).date()
        inicio_mes_actual = hoy_lima.replace(day=1)
        fin_mes_anterior = inicio_mes_actual - timedelta(days=1)
        inicio_mes_anterior = fin_mes_anterior.replace(day=1)

        rango_anterior = (
            datetime.combine(inicio_mes_anterior, time.min, tzinfo=LIMA_TZ),
            datetime.combine(fin_mes_anterior, time.max, tzinfo=LIMA_TZ),
        )
        rango_actual = (
            datetime.combine(inicio_mes_actual, time.min, tzinfo=LIMA_TZ),
            datetime.combine(hoy_lima, time.max, tzinfo=LIMA_TZ),
        )

        return [
            {"label": "Mes Ant.", **IndicatorService._calcular_para_rango(db, *rango_anterior)},
            {"label": "Mes Act.", **IndicatorService._calcular_para_rango(db, *rango_actual)},
        ]