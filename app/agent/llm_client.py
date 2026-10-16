import json
import re
import time
import httpx
import logging
from typing import Any, Callable, Dict, List, Optional
from app.core.config import settings

logger = logging.getLogger("elprincipe.agent.llm")

MAX_TOOL_ROUNDS = 4
ESPERA_MAXIMA_SEGUNDOS = 25
PAT_ESPERA = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s")


class LLMClient:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.timeout = httpx.Timeout(300.0, connect=30.0)

        self.base_url = settings.GROQ_BASE_URL.rstrip("/")
        self.model = settings.GROQ_MODEL
        self.modelos_respaldo = [m.strip() for m in settings.GROQ_FALLBACK_MODELS.split(",") if m.strip()]
        self._bloqueados: Dict[str, float] = {}

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_dispatcher: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        max_tokens: int = 600,
        on_delta: Optional[Callable[[Optional[str]], None]] = None,
    ) -> str:
        return self._generate_groq(system_prompt, user_prompt, tools, tool_dispatcher, max_tokens, on_delta)


    @staticmethod
    def _espera_sugerida(response: httpx.Response) -> Optional[float]:
        encabezado = response.headers.get("retry-after")
        if encabezado:
            try:
                return float(encabezado)
            except ValueError:
                pass
        coincidencia = PAT_ESPERA.search(response.text or "")
        if not coincidencia:
            return None
        minutos = float(coincidencia.group(1) or 0)
        return minutos * 60 + float(coincidencia.group(2))

    def _modelo_disponible(self, excluir: Optional[str] = None) -> Optional[str]:
        ahora = time.monotonic()
        for modelo in [self.model, *self.modelos_respaldo]:
            if modelo != excluir and self._bloqueados.get(modelo, 0) <= ahora:
                return modelo
        return None

    def _con_reintento(self, solicitud: Callable[[], Any], payload: Dict[str, Any]) -> Any:
        for intento in range(2 + len(self.modelos_respaldo)):
            try:
                return solicitud()
            except httpx.HTTPStatusError as error:
                if error.response.status_code != 429:
                    raise
                espera = self._espera_sugerida(error.response)
                self._bloqueados[payload["model"]] = time.monotonic() + (espera if espera is not None else 20)
                alterno = self._modelo_disponible(excluir=payload["model"])
                if alterno:
                    logger.warning(f"Límite de tokens en {payload['model']}; cambio a {alterno}.")
                    payload["model"] = alterno
                    continue
                if espera is None or espera > ESPERA_MAXIMA_SEGUNDOS or intento >= 1 + len(self.modelos_respaldo):
                    raise
                logger.warning(f"Límite de tokens alcanzado en todos los modelos; reintento en {espera:.1f}s.")
                time.sleep(espera + 0.5)

    @staticmethod
    def _leer_stream(
        client: httpx.Client,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        on_delta: Callable[[Optional[str]], None],
    ) -> Dict[str, Any]:
        contenido: List[str] = []
        llamadas: Dict[int, Dict[str, Any]] = {}
        with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code >= 400:
                response.read()
                response.raise_for_status()
            for linea in response.iter_lines():
                if not linea or not linea.startswith("data:"):
                    continue
                dato = linea[5:].strip()
                if dato == "[DONE]":
                    break
                try:
                    delta = json.loads(dato)["choices"][0].get("delta", {})
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                texto = delta.get("content")
                if texto:
                    contenido.append(texto)
                    on_delta(texto)
                for llamada in delta.get("tool_calls") or []:
                    indice = llamada.get("index", 0)
                    acumulada = llamadas.setdefault(
                        indice, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                    )
                    if llamada.get("id"):
                        acumulada["id"] = llamada["id"]
                    funcion = llamada.get("function") or {}
                    if funcion.get("name"):
                        acumulada["function"]["name"] += funcion["name"]
                    if funcion.get("arguments"):
                        acumulada["function"]["arguments"] += funcion["arguments"]
        mensaje: Dict[str, Any] = {"content": "".join(contenido)}
        if llamadas:
            mensaje["tool_calls"] = [llamadas[i] for i in sorted(llamadas)]
            if contenido:
                on_delta(None)
        return mensaje

    def _generate_groq(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_dispatcher: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        max_tokens: int = 600,
        on_delta: Optional[Callable[[Optional[str]], None]] = None,
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
                        "model": self._modelo_disponible() or self.model,
                        "messages": messages,
                        "temperature": 0.1,
                        "top_p": 0.8,
                        "max_tokens": max_tokens,
                        "reasoning_effort": "low",
                    }
                    if tools:
                        payload["tools"] = tools
                        payload["tool_choice"] = "auto"

                    if on_delta:
                        payload["stream"] = True
                        message = self._con_reintento(
                            lambda: self._leer_stream(client, url, headers, payload, on_delta), payload
                        )
                    else:
                        def pedir():
                            respuesta = client.post(url, headers=headers, json=payload)
                            respuesta.raise_for_status()
                            return respuesta.json()["choices"][0]["message"]

                        message = self._con_reintento(pedir, payload)

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
            if e.response.status_code == 429:
                return "El servicio de IA está saturado por el límite de uso por minuto. Espera unos segundos y vuelve a preguntar."
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
