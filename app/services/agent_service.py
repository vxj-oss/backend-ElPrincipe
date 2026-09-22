import time
import logging
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentOrchestrator
from app.models.agent_message import MensajeAgente
from app.models.agent_session import SesionAgente
from app.models.user import Usuario

logger = logging.getLogger("elprincipe.services.agent")


class AgentService:
    @staticmethod
    def get_or_create_session(
        db: Session, user_id: int, session_id: Optional[int] = None, prompt_preview: str = ""
    ) -> SesionAgente:
        """Recupera la sesión existente o crea una nueva asociada al usuario."""
        if session_id:
            ses = db.scalar(
                select(SesionAgente).where(
                    SesionAgente.id == session_id,
                    SesionAgente.usuario_id == user_id,
                )
            )
            if ses:
                return ses

        titulo = (prompt_preview[:50] + "...") if prompt_preview else "Consulta Asistente de Ventas"
        nueva_sesion = SesionAgente(
            usuario_id=user_id,
            titulo_sesion=titulo,
            esta_activa=True,
        )
        db.add(nueva_sesion)
        db.commit()
        db.refresh(nueva_sesion)
        return nueva_sesion

    @staticmethod
    def execute_query(
        db: Session,
        current_user: Usuario,
        prompt: str,
        session_id: Optional[int] = None,
        contexto: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ejecuta el pipeline completo del agente inteligente y persiste el historial."""
        start_time = time.time()
        sesion = AgentService.get_or_create_session(
            db=db, user_id=current_user.id, session_id=session_id, prompt_preview=prompt
        )
        msg_user = MensajeAgente(
            sesion_id=sesion.id,
            rol_emisor="user",
            contenido=prompt,
            datos_estructurados=contexto,
        )
        db.add(msg_user)
        db.commit()
        try:
            agent_result = AgentOrchestrator.handle_query(
                db=db,
                current_user=current_user,
                prompt=prompt,
                session_id=sesion.id,
                contexto=contexto,
            )
            respuesta_texto = agent_result.get("respuesta", "Sin respuesta del modelo.")
            contexto_usado = agent_result.get("contexto_utilizado")
        except Exception as e:
            logger.error(f"Error procesando la consulta del agente: {e}")
            respuesta_texto = f"Error al procesar la solicitud con el Agente Comercial: {str(e)}"
            contexto_usado = None

        elapsed = round(time.time() - start_time, 2)
        msg_assistant = MensajeAgente(
            sesion_id=sesion.id,
            rol_emisor="assistant",
            contenido=respuesta_texto,
            datos_estructurados={"contexto_utilizado": contexto_usado} if contexto_usado else None,
            tiempo_respuesta_segundos=elapsed,
        )
        db.add(msg_assistant)
        db.commit()

        return {
            "sesion_id": sesion.id,
            "respuesta": respuesta_texto,
            "datos_estructurados": msg_assistant.datos_estructurados,
            "tiempo_respuesta": elapsed,
        }