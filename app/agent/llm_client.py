import json
import httpx
import logging
from typing import Any, Callable, Dict, List, Optional
from app.core.config import settings

logger = logging.getLogger("elprincipe.agent.llm")

MAX_TOOL_ROUNDS = 4


class LLMClient:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.timeout = httpx.Timeout(300.0, connect=30.0)

        self.base_url = settings.GROQ_BASE_URL.rstrip("/")
        self.model = settings.GROQ_MODEL

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_dispatcher: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> str:
        return self._generate_groq(system_prompt, user_prompt, tools, tool_dispatcher)


    def _generate_groq(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_dispatcher: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> str:
        if not settings.GROQ_API_KEY:
            logger.error("GROQ_API_KEY no está configurada en el .env.")
            return "El servicio de Inteligencia Artificial en la nube no está configurado."

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            with httpx.Client(timeout=self.timeout) as client:
                for _ in range(MAX_TOOL_ROUNDS if tools else 1):
                    payload = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.1,
                        "top_p": 0.8,
                        "max_tokens": 600,
                        "reasoning_effort": "low",
                    }
                    if tools:
                        payload["tools"] = tools
                        payload["tool_choice"] = "auto"

                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    message = response.json()["choices"][0]["message"]

                    tool_calls = message.get("tool_calls")
                    if not tool_calls or not tool_dispatcher:
                        return (message.get("content") or "").strip()

                    messages.append({
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": tool_calls,
                    })
                    for call in tool_calls:
                        nombre = call["function"]["name"]
                        try:
                            args = json.loads(call["function"].get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        try:
                            resultado = tool_dispatcher(nombre, args)
                        except Exception as e:
                            logger.error(f"Error ejecutando herramienta '{nombre}': {e}")
                            resultado = {"error": f"No se pudo ejecutar '{nombre}': {e}"}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(resultado, ensure_ascii=False, default=str),
                        })

            logger.error("Se alcanzó el máximo de rondas de herramientas sin respuesta final.")
            return "No pude completar la consulta tras revisar varias fuentes de datos. Por favor, reformula tu pregunta."
        except httpx.HTTPStatusError as e:
            logger.error(f"Groq respondió con error {e.response.status_code}: {e.response.text}")
            if e.response.status_code == 401:
                return "La clave de API de Groq no es válida. Verifica tu configuración."
            return "El servicio de Inteligencia Artificial en la nube devolvió un error."
        except httpx.ConnectError:
            logger.error("No se pudo conectar con la API de Groq.")
            return "No se pudo conectar con el servicio de Inteligencia Artificial en la nube."
        except httpx.TimeoutException:
            logger.error(f"Timeout al esperar respuesta de Groq ({self.model}).")
            return "El modelo tardó más del tiempo esperado en responder. Por favor, reintenta tu consulta."
        except Exception as e:
            logger.error(f"Error inesperado en LLM (Groq): {e}")
            return f"Ocurrió un error al procesar la respuesta: {str(e)}"


llm_client = LLMClient()
