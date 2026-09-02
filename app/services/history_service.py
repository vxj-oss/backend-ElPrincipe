from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.history import HistorialAuditoria
from app.models.user import Usuario


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
    def get_all(
        db: Session,
        modulo: Optional[str] = None,
        usuario_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(HistorialAuditoria, Usuario)
            .outerjoin(Usuario, HistorialAuditoria.usuario_id == Usuario.id)
            .order_by(HistorialAuditoria.fecha_hora.desc())
        )
        if modulo:
            stmt = stmt.where(HistorialAuditoria.modulo_afectado == modulo)
        if usuario_id:
            stmt = stmt.where(HistorialAuditoria.usuario_id == usuario_id)

        stmt = stmt.offset(skip).limit(limit)
        results = db.execute(stmt).all()

        registros = []
        for hist, user in results:
            nombre = "Sistema / Asesor"
            ini = "EP"
            if user: 
                nombre_val = (
                    getattr(user, "nombre_completo", None)
                    or getattr(user, "nombres", None)
                    or getattr(user, "nombre", None)
                    or getattr(user, "username", None)
                    or ""
                )
                apellido_val = getattr(user, "apellidos", None) or getattr(user, "apellido", None) or ""

                if nombre_val and apellido_val:
                    nombre = f"{nombre_val} {apellido_val}".strip()
                elif nombre_val:
                    nombre = nombre_val.strip()
                else:
                    nombre = getattr(user, "email", "Usuario")

                partes = nombre.split()
                if len(partes) >= 2:
                    ini = f"{partes[0][0]}{partes[1][0]}".upper()
                elif len(partes) == 1:
                    ini = partes[0][:2].upper()

            registros.append({
                "id": hist.id,
                "usuario_id": hist.usuario_id,
                "usuario_nombre": nombre,
                "usuario_iniciales": ini,
                "accion": hist.accion,
                "modulo_afectado": hist.modulo_afectado,
                "detalle_cambio": hist.detalle_cambio,
                "fecha_hora": hist.fecha_hora,
            })

        return registros