import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.agent.context_builder import ContextBuilder
from app.agent.actions import responder_accion
from app.agent.analysis_answers import responder_analisis
from app.agent.insight_answers import responder_insights
from app.agent.order_phrasing import normalizar_orden
from app.agent.planner import clasificar_restantes, es_escritura, separar_pasos
from app.agent.conversation_context import resolver_seguimiento
from app.agent.customer_actions import es_crear_cliente, responder_crear_cliente
from app.agent.pantalla_context import aplicar_pantalla
from app.agent.product_actions import responder_producto
from app.agent.term_actions import responder_condicion
from app.agent.ui_actions import responder_navegacion
from app.agent.edit_draft import es_edicion, responder_edicion
from app.agent.entity_actions import responder_cliente_accion, responder_cotizacion_accion, responder_pedido_items
from app.agent.report_actions import responder_reporte
from app.agent.indicator_answers import responder_indicadores
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
from app.agent import sql_tool
from app.agent.tools import CommercialTools
from app.core.time import ahora_lima
from app.models.user import Usuario

logger = logging.getLogger("elprincipe.agent.orchestrator")

ETIQUETAS_HERRAMIENTAS = {
    "listar_condiciones_comerciales": "Condiciones comerciales pactadas",
    "listar_clientes": "Cartera de clientes",
    "listar_pedidos": "Pedidos registrados",
    "buscar_producto_stock_precio": "Catálogo de productos: precio y stock",
    "listar_productos_stock_critico": "Productos con stock crítico",
    "buscar_pedido_por_codigo": "Detalle de un pedido por código",
    "historial_productos_comprados": "Historial de productos comprados",
    "clientes_que_compraron_hoy": "Pedidos de hoy por cliente",
    "obtener_indicadores_comerciales": "Indicadores NCCA, NPP y TPTD",
    "productos_mayor_rotacion": "Productos de mayor rotación",
    "buscar_cliente_detalle": "Ficha del cliente",
    "listar_solicitudes_clientes": "Cotizaciones de clientes",
    "buscar_solicitud_por_codigo": "Detalle de una cotización por código",
    "listar_movimientos_stock": "Movimientos de stock",
    "listar_categorias": "Categorías de productos",
    "consultar_historial_auditoria": "Historial de auditoría",
    "obtener_mi_perfil": "Perfil del usuario",
    "buscar_informacion_trabajador": "Información de trabajadores",
    "listar_trabajadores": "Trabajadores",
    "mis_pedidos_registrados": "Pedidos registrados por el usuario",
    "analizar_reposicion": "Cobertura de stock según ritmo de venta de 30 días",
    "analizar_recompra_clientes": "Cadencia de compra de cada cliente",
    "diagnostico_ventas": "Comparación de ventas contra el periodo anterior",
    "consultar_base_datos": "Consulta directa a la base de datos (solo lectura)",
}



class AgentOrchestrator:
    """Orquestador central del razonamiento del Agente IA.

    El modelo decide por sí mismo qué herramientas llamar (tool calling) según
    la consulta del usuario, en vez de enrutar por palabras clave fijas.
    """

    @staticmethod
    def _directo(
        db: Session,
        current_user: Usuario,
        prompt: str,
        session_id: Optional[int],
        contexto: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        es_admin = getattr(current_user, "rol", None) == "administrador"
        directo = None
        borrador = contexto.get("borrador") if isinstance(contexto, dict) else None
        if borrador and es_edicion(prompt) and not es_crear_cliente(prompt):
            directo = responder_edicion(db, prompt, borrador)
        if directo is None:
            directo = responder_navegacion(db, prompt, es_admin)
        if directo is None:
            directo = responder_insights(db, prompt)
        if directo is None:
            directo = responder_condicion(db, prompt)
        if directo is None:
            directo = responder_producto(db, prompt, es_admin)
        if directo is None:
            directo = responder_cliente_accion(db, prompt)
        if directo is None:
            directo = responder_cotizacion_accion(db, prompt)
        if directo is None:
            directo = responder_pedido_items(db, prompt)
        if directo is None:
            directo = responder_reporte(db, prompt)
        if directo is None:
            directo = responder_crear_cliente(db, prompt)
        if directo is None:
            directo = responder_accion(db, prompt, session_id, current_user)
        if directo is None:
            if es_repetir_cotizacion(prompt):
                directo = repetir_ultima_cotizacion(db, prompt)
            elif es_pedido_de_cotizacion(prompt):
                directo = preparar_borrador(db, prompt)
            elif es_clientes_para_llamar(prompt):
                directo = clientes_para_llamar(db)
            else:
                directo = (
                    responder_indicadores(db, prompt)
                    or responder_analisis(db, prompt)
                    or responder_rapido(db, prompt, current_user)
                )
        return directo

    @staticmethod
    def _ejecutar_plan(
        db: Session,
        current_user: Usuario,
        pasos: list,
        session_id: Optional[int],
        contexto: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        pantalla = contexto.get("pantalla") if isinstance(contexto, dict) else None
        textos: list = []
        ultimos_datos = None
        for i, paso in enumerate(pasos):
            texto = normalizar_orden(paso)
            if i == 0:
                texto = resolver_seguimiento(db, texto, session_id)
                texto = aplicar_pantalla(texto, pantalla)
            directo = AgentOrchestrator._directo(db, current_user, texto, session_id, contexto if i == 0 else None)
            if directo is None:
                if i == 0:
                    return None
                restantes = [{"texto": normalizar_orden(p), "etiqueta": p.strip()[:48], "espera": None} for p in pasos[i:]]
                return AgentOrchestrator._respuesta_plan(textos, ultimos_datos, restantes)
            textos.append(directo["respuesta"])
            datos = directo["datos_estructurados"]
            if es_escritura(datos):
                restantes = clasificar_restantes(pasos[i + 1 :], datos)
                return AgentOrchestrator._respuesta_plan(textos, datos, restantes)
            if datos:
                ultimos_datos = datos
        return AgentOrchestrator._respuesta_plan(textos, ultimos_datos, [])

    @staticmethod
    def _respuesta_plan(textos: list, datos: Optional[Dict[str, Any]], pendientes: list) -> Dict[str, Any]:
        if pendientes:
            datos = dict(datos or {"tipo": "texto"})
            datos["plan"] = {"pendientes": pendientes}
        return {
            "respuesta": "\n\n".join(textos),
            "datos_estructurados": datos,
            "modelo_usado": llm_client.model,
        }

    @staticmethod
    def handle_query(
        db: Session,
        current_user: Usuario,
        prompt: str,
        session_id: Optional[int] = None,
        contexto: Optional[Dict[str, Any]] = None,
        on_delta: Optional[Any] = None,
    ) -> Dict[str, Any]:
        pasos = separar_pasos(prompt)
        if len(pasos) > 1:
            plan = AgentOrchestrator._ejecutar_plan(db, current_user, pasos, session_id, contexto)
            if plan:
                return plan
        prompt = normalizar_orden(prompt)
        prompt = resolver_seguimiento(db, prompt, session_id)
        pantalla = contexto.get("pantalla") if isinstance(contexto, dict) else None
        prompt = aplicar_pantalla(prompt, pantalla)
        directo = AgentOrchestrator._directo(db, current_user, prompt, session_id, contexto)
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
            + sql_tool.contexto_sql(getattr(current_user, "rol", None) == "administrador")
        )
        tools_relevantes = CommercialTools.select_relevant_tools(f"{prompt} {previos}")

        guardada = respuesta_cache.obtener(current_user.id, chat_history, prompt)
        if guardada is not None:
            return {"respuesta": guardada, "modelo_usado": llm_client.model}

        herramientas_usadas: list = []
        consultas_sql: list = []

        def despachar(name: str, args: Dict[str, Any]):
            if name not in herramientas_usadas:
                herramientas_usadas.append(name)
            if name == "consultar_base_datos" and args.get("sql"):
                consultas_sql.append(str(args["sql"])[:400])
            return CommercialTools.dispatch(db, current_user, name, args)

        respuesta_texto = llm_client.generate_response(
            system_prompt=system_prompt,
            user_prompt=formatted_user_prompt,
            tools=tools_relevantes,
            tool_dispatcher=despachar,
            on_delta=on_delta,
        )

        respuesta_texto = respuesta_texto.replace("**", "").replace("__", "")
        respuesta_cache.guardar(current_user.id, chat_history, prompt, respuesta_texto)

        datos = None
        if herramientas_usadas:
            datos = {
                "tipo": "texto",
                "explicacion": {
                    "resumen": "Esta respuesta la redactó el modelo de IA a partir de datos que consultó en el sistema.",
                    "fuentes": [ETIQUETAS_HERRAMIENTAS.get(n, n) for n in herramientas_usadas]
                    + [f"Consulta SQL de solo lectura: {c}" for c in consultas_sql[-2:]],
                    "formula": None,
                    "periodo": "datos al momento de la consulta",
                },
            }

        return {
            "respuesta": respuesta_texto,
            "datos_estructurados": datos,
            "modelo_usado": llm_client.model,
        }
