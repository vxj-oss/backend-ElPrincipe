import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.agent.context_builder import ContextBuilder
from app.agent.llm_client import llm_client
from app.agent.prompts import DECISION_ASSISTANT_PROMPT, SYSTEM_PROMPT, build_identity_context
from app.agent.tools import CommercialTools
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
        chat_history = ContextBuilder.build_chat_history(db, session_id)
        formatted_user_prompt = (
            DECISION_ASSISTANT_PROMPT.replace("{chat_history}", chat_history).replace(
                "{user_query}", prompt
            )
        )

        system_prompt = SYSTEM_PROMPT + build_identity_context(current_user)
        tools_relevantes = CommercialTools.select_relevant_tools(prompt)

        respuesta_texto = llm_client.generate_response(
            system_prompt=system_prompt,
            user_prompt=formatted_user_prompt,
            tools=tools_relevantes,
            tool_dispatcher=lambda name, args: CommercialTools.dispatch(
                db, current_user, name, args
            ),
        )

        return {
            "respuesta": respuesta_texto,
            "modelo_usado": llm_client.model,
        }
