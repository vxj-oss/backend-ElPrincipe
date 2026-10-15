from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_message import MensajeAgente

MAX_CARACTERES_MENSAJE = 500


class ContextBuilder:
    @staticmethod
    def get_recent_messages(
        db: Session,
        session_id: Optional[int],
        prompt: Optional[str] = None,
        limit: int = 6,
    ) -> List[Tuple[str, str]]:
        if not session_id:
            return []
        stmt = (
            select(MensajeAgente.rol_emisor, MensajeAgente.contenido)
            .where(
                MensajeAgente.sesion_id == session_id,
                MensajeAgente.rol_emisor.in_(("user", "assistant")),
            )
            .order_by(MensajeAgente.id.desc())
            .limit(limit + 1)
        )
        filas = [(rol, contenido) for rol, contenido in db.execute(stmt).all()]
        if filas and filas[0][0] == "user" and (prompt is None or filas[0][1] == prompt):
            filas = filas[1:]
        filas = [
            (rol, contenido)
            for rol, contenido in filas
            if not (rol == "assistant" and contenido.startswith("Error al procesar"))
        ]
        return list(reversed(filas[:limit]))

    @staticmethod
    def build_chat_history(
        db: Session,
        session_id: Optional[int],
        prompt: Optional[str] = None,
        limit: int = 6,
    ) -> str:
        mensajes = ContextBuilder.get_recent_messages(db, session_id, prompt, limit)
        if not mensajes:
            return "Conversación nueva (sin mensajes previos)."
        lineas = []
        for rol, contenido in mensajes:
            texto = " ".join(contenido.split())
            if len(texto) > MAX_CARACTERES_MENSAJE:
                texto = texto[:MAX_CARACTERES_MENSAJE] + "…"
            lineas.append(f"{'Usuario' if rol == 'user' else 'Asistente'}: {texto}")
        return "\n".join(lineas)

    @staticmethod
    def previous_user_text(
        db: Session, session_id: Optional[int], prompt: Optional[str] = None, cantidad: int = 2
    ) -> str:
        mensajes = ContextBuilder.get_recent_messages(db, session_id, prompt, limit=6)
        usuario = [contenido for rol, contenido in mensajes if rol == "user"]
        return " ".join(usuario[-cantidad:])
