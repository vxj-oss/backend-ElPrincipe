from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.history import HistorialAuditoria
from app.models.user import Usuario

LIMA_TZ = ZoneInfo("America/Lima")


class HistoryService:
    @staticmethod
    def log(
        db: Session,
        accion: str,
        modulo: str,
        usuario_id: Optional[int] = None,
        detalle: Optional[Dict[str, Any]] = None,
        ip: Optional[str] = None,
    ) -> HistorialAuditoria:
        record = HistorialAuditoria(
            usuario_id=usuario_id,
            accion=accion,
            modulo_afectado=modulo,
            detalle_cambio=detalle,
            direccion_ip=ip,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def _rango_fechas(rango: Optional[str]):
        if not rango:
            return None
        ahora = datetime.now(LIMA_TZ)
        hoy = ahora.date()
        if rango == "hoy":
            inicio = datetime.combine(hoy, time.min, tzinfo=LIMA_TZ)
        elif rango == "semana":
            inicio = datetime.combine(hoy - timedelta(days=hoy.weekday()), time.min, tzinfo=LIMA_TZ)
        elif rango == "mes":
            inicio = datetime.combine(hoy.replace(day=1), time.min, tzinfo=LIMA_TZ)
        else:
            return None
        return inicio, ahora

    @staticmethod
    def get_all(
        db: Session,
        modulo: Optional[str] = None,
        usuario_id: Optional[int] = None,
        accion: Optional[str] = None,
        rango: Optional[str] = None,
        busqueda: Optional[str] = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> Dict[str, Any]:
        base = (
            select(HistorialAuditoria, Usuario)
            .outerjoin(Usuario, HistorialAuditoria.usuario_id == Usuario.id)
        )

        if modulo:
            base = base.where(HistorialAuditoria.modulo_afectado == modulo)
        if usuario_id:
            base = base.where(HistorialAuditoria.usuario_id == usuario_id)
        if accion:
            base = base.where(HistorialAuditoria.accion == accion)

        limites = HistoryService._rango_fechas(rango)
        if limites:
            base = base.where(
                HistorialAuditoria.fecha_hora >= limites[0],
                HistorialAuditoria.fecha_hora <= limites[1],
            )

        if busqueda:
            q = f"%{busqueda.strip()}%"
            base = base.where(
                or_(
                    HistorialAuditoria.modulo_afectado.ilike(q),
                    HistorialAuditoria.detalle_cambio["descripcion"].astext.ilike(q),
                    HistorialAuditoria.detalle_cambio["entidad"].astext.ilike(q),
                    Usuario.nombre_completo.ilike(q),
                )
            )

        total = db.scalar(
            select(func.count()).select_from(base.subquery())
        ) or 0

        pagina = max(1, pagina)
        por_pagina = max(1, min(por_pagina, 200))
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

        stmt = (
            base.order_by(HistorialAuditoria.fecha_hora.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        results = db.execute(stmt).all()

        items = []
        for hist, user in results:
            nombre = "Sistema / Asesor"
            ini = "EP"
            if user:
                nombre_val = getattr(user, "nombre_completo", None) or getattr(
                    user, "nombre_usuario", None
                ) or ""
                if nombre_val:
                    nombre = nombre_val.strip()
                partes = nombre.split()
                if len(partes) >= 2:
                    ini = f"{partes[0][0]}{partes[1][0]}".upper()
                elif len(partes) == 1:
                    ini = partes[0][:2].upper()

            items.append(
                {
                    "id": hist.id,
                    "usuario_id": hist.usuario_id,
                    "usuario_nombre": nombre,
                    "usuario_iniciales": ini,
                    "accion": hist.accion,
                    "modulo_afectado": hist.modulo_afectado,
                    "detalle_cambio": hist.detalle_cambio,
                    "fecha_hora": hist.fecha_hora,
                }
            )

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": total_paginas,
        }

    @staticmethod
    def delete_by_range(db: Session, desde: datetime, hasta: datetime) -> int:
        stmt = sa_delete(HistorialAuditoria).where(
            HistorialAuditoria.fecha_hora >= desde,
            HistorialAuditoria.fecha_hora <= hasta,
        )
        resultado = db.execute(stmt)
        db.commit()
        return resultado.rowcount or 0

    @staticmethod
    def get_stats(db: Session) -> Dict[str, Any]:
        ahora = datetime.now(LIMA_TZ)
        hoy = ahora.date()
        inicio_hoy = datetime.combine(hoy, time.min, tzinfo=LIMA_TZ)
        inicio_mes = datetime.combine(hoy.replace(day=1), time.min, tzinfo=LIMA_TZ)

        eventos_hoy = db.scalar(
            select(func.count(HistorialAuditoria.id)).where(
                HistorialAuditoria.fecha_hora >= inicio_hoy
            )
        ) or 0
        eventos_mes = db.scalar(
            select(func.count(HistorialAuditoria.id)).where(
                HistorialAuditoria.fecha_hora >= inicio_mes
            )
        ) or 0
        con_error = db.scalar(
            select(func.count(HistorialAuditoria.id)).where(
                HistorialAuditoria.accion == "ERROR"
            )
        ) or 0
        modulo_row = db.execute(
            select(HistorialAuditoria.modulo_afectado, func.count(HistorialAuditoria.id).label("n"))
            .group_by(HistorialAuditoria.modulo_afectado)
            .order_by(func.count(HistorialAuditoria.id).desc())
            .limit(1)
        ).first()

        return {
            "eventos_hoy": eventos_hoy,
            "eventos_mes": eventos_mes,
            "con_error": con_error,
            "modulo_activo": modulo_row[0] if modulo_row else "—",
        }
