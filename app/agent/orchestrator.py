import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.agent.context_builder import ContextBuilder
from app.agent.llm_client import llm_client
from app.agent import respuesta_cache
from app.agent.quick_answers import responder_rapido
from app.agent.quote_intent import (
    clientes_para_llamar,
    es_clientes_para_llamar,
    es_pedido_de_cotizacion,
    es_repetir_cotizacion,
    preparar_borrador,
    repetir_ultima_cotizacion,
)
from app.agent.prompts import (
    DECISION_ASSISTANT_PROMPT,
    SYSTEM_PROMPT,
    build_datetime_context,
    build_identity_context,
)
from app.agent.tools import CommercialTools
from app.core.time import ahora_lima
from app.models.user import Usuario

logger = logging.getLogger("elprincipe.agent.orchestrator")


class AgentOrchestrator:
    """Orquestador central del razonamiento del Agente IA.

    El modelo decide por sí mismo qué herramientas llamar (tool calling) según
    la consulta del usuario, en vez de enrutar por palabras clave fijas.
    """

    @staticmethod
    def handle_query(
        db: Session,
        current_user: Usuario,
        prompt: str,
        session_id: Optional[int] = None,
        contexto: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        directo = None
        if es_repetir_cotizacion(prompt):
            directo = repetir_ultima_cotizacion(db, prompt)
        elif es_pedido_de_cotizacion(prompt):
            directo = preparar_borrador(db, prompt)
        elif es_clientes_para_llamar(prompt):
            directo = clientes_para_llamar(db)
        else:
            texto_rapido = responder_rapido(db, prompt, current_user)
            if texto_rapido:
                directo = {"respuesta": texto_rapido, "datos_estructurados": None}
        if directo:
            return {
                "respuesta": directo["respuesta"],
                "datos_estructurados": directo["datos_estructurados"],
                "modelo_usado": llm_client.model,
            }

        chat_history = ContextBuilder.build_chat_history(db, session_id, prompt)
        previos = ContextBuilder.previous_user_text(db, session_id, prompt)
        formatted_user_prompt = (
            DECISION_ASSISTANT_PROMPT.replace("{chat_history}", chat_history).replace(
                "{user_query}", prompt
            )
        )

        system_prompt = (
            SYSTEM_PROMPT
            + build_datetime_context(ahora_lima())
            + build_identity_context(current_user)
        )
        tools_relevantes = CommercialTools.select_relevant_tools(f"{prompt} {previos}")

        guardada = respuesta_cache.obtener(current_user.id, chat_history, prompt)
        if guardada is not None:
            return {"respuesta": guardada, "modelo_usado": llm_client.model}

        respuesta_texto = llm_client.generate_response(
            system_prompt=system_prompt,
            user_prompt=formatted_user_prompt,
            tools=tools_relevantes,
            tool_dispatcher=lambda name, args: CommercialTools.dispatch(
                db, current_user, name, args
            ),
        )

        respuesta_cache.guardar(current_user.id, chat_history, prompt, respuesta_texto)

        return {
            "respuesta": respuesta_texto,
            "modelo_usado": llm_client.model,
        }
