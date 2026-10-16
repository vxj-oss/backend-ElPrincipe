import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.agent.choices import opciones_de_clientes, respuesta_opciones
from app.agent.quick_answers import PAT_CODIGO
from app.agent.quote_intent import _buscar_cliente_en_texto
from app.services.quote_note_service import normalizar

PAT_VERBO_NAV = re.compile(
    r"\b(?:llevame|lleva|llevarme|ir|ve|vamos|abre|abrir|abreme|muestrame|mostrar|ensename|navega|dirigeme|"
    r"quiero ver|quiero ir|vete|salta|cambiar a|cambia a)\b"
)
PAT_EXCLUIR = re.compile(
    r"\b(?:ventas|vendid\w+|grafic\w*|compar\w*|ranking|top|rotacion|por que|stock de|precio|cuanto|margen|"
    r"hoy|ayer|semana|mes|pdf|ticket|descarg\w*|crea(?:r)?|registr\w+|elimin\w+|borra\w*)\b"
)
PAT_FORMULARIO = re.compile(r"\b(?:formulario|pantalla|ventana|modal)\b.*\bnuev[oa]\b|\bnuev[oa]\b.*\b(?:formulario|pantalla|ventana)\b")

MODULOS: List[Tuple[str, List[str], str, bool]] = [
    ("Dashboard", [r"dashboard", r"inicio", r"panel principal", r"tablero"], "/dashboard", False),
    ("Productos", [r"productos?", r"inventario", r"catalogo"], "/productos", False),
    ("Clientes", [r"clientes?", r"cartera"], "/clientes", False),
    ("Cotizaciones", [r"cotizaciones", r"cotizacion", r"solicitudes"], "/solicitudes", False),
    ("Pedidos", [r"pedidos?"], "/pedidos", False),
    ("Condiciones comerciales", [r"condiciones(?: comerciales)?"], "/condiciones", False),
    ("Indicadores", [r"indicadores?"], "/indicadores", False),
    ("Reportes", [r"reportes?", r"informes?"], "/reportes", False),
    ("Historial", [r"historial", r"auditoria", r"bitacora"], "/historial", True),
    ("Usuarios", [r"usuarios", r"trabajadores", r"asesores"], "/usuarios", True),
    ("Mi perfil", [r"mi perfil", r"perfil"], "/perfil", False),
    ("Configuración", [r"configuracion", r"ajustes"], "/configuracion", False),
    ("Agente IA", [r"agente (?:ia|completo)", r"chat completo", r"pantalla del agente"], "/agente", False),
]

ESTADOS_PEDIDO = [
    ("Pendiente", r"pendientes?"), ("Aprobado", r"aprobad[oa]s?"), ("Entregado", r"entregad[oa]s?"),
    ("Cancelado", r"cancelad[oa]s?"),
]
ESTADOS_COTIZACION = [("Pendiente", r"pendientes?"), ("Atendida", r"atendid[oa]s?"), ("Cancelada", r"cancelad[oa]s?")]
STOCK = [("critico", r"critico|agotando|agotad[oa]s?"), ("bajo", r"bajo"), ("ok", r"normal(?:es)?|ok|suficiente")]
TIPOS_CLIENTE = [("Mayorista", r"mayoristas?"), ("Minorista", r"minoristas?"), ("Institucional", r"institucionales?")]


def _respuesta(texto: str, ruta: str, etiqueta: str) -> Dict[str, Any]:
    return {
        "respuesta": texto,
        "datos_estructurados": {"tipo": "navegacion", "ruta": ruta, "etiqueta": etiqueta, "auto": True},
    }


def _filtro(limpio: str, opciones: List[Tuple[str, str]]) -> Optional[str]:
    for valor, patron in opciones:
        if re.search(rf"\b(?:{patron})\b", limpio):
            return valor
    return None


def _modulo_mencionado(limpio: str) -> Optional[Tuple[str, str, bool]]:
    mejor: Optional[Tuple[int, Tuple[str, str, bool]]] = None
    for nombre, patrones, ruta, solo_admin in MODULOS:
        for patron in patrones:
            m = re.search(rf"\b{patron}\b", limpio)
            if m and (mejor is None or len(m.group(0)) > mejor[0]):
                mejor = (len(m.group(0)), (nombre, ruta, solo_admin))
    return mejor[1] if mejor else None


def responder_navegacion(db: Session, prompt: str, es_admin: bool) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    if not PAT_VERBO_NAV.search(limpio):
        return None

    codigo = PAT_CODIGO.search(prompt)
    if codigo:
        tipo, resto = codigo.group(1).upper(), codigo.group(2).upper()
        if tipo == "PED":
            return _respuesta(f"Abro el pedido PED-{resto}.", f"/pedidos?detalle=PED-{resto}", f"Pedido PED-{resto}")
        return _respuesta(f"Busco la cotización COT-{resto}.", f"/solicitudes?q=COT-{resto}", f"Cotización COT-{resto}")

    if PAT_EXCLUIR.search(limpio):
        return None

    if PAT_FORMULARIO.search(limpio):
        formularios = [
            (r"\bpedido\b", "Nuevo pedido", "/pedidos?nuevo=1"),
            (r"\bcotizacion\b", "Nueva cotización", "/solicitudes?nueva=1"),
            (r"\bproducto\b", "Nuevo producto", "/productos?nuevo=1"),
            (r"\bcliente\b", "Nuevo cliente", "/clientes?nuevo=1"),
        ]
        for patron, etiqueta, ruta in formularios:
            if re.search(patron, limpio):
                if etiqueta == "Nueva cotización":
                    cliente, _ = _buscar_cliente_en_texto(db, prompt)
                    if cliente:
                        ruta += f"&cliente={cliente.id}"
                        etiqueta = f"Nueva cotización para {cliente.razon_social}"
                return _respuesta(f"Abro el formulario de {etiqueta[0].lower() + etiqueta[1:]}.", ruta, etiqueta)

    if re.search(r"\bcliente\b", limpio) and not re.search(r"\bclientes\b", limpio):
        cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
        if cliente is None and dudosos:
            return respuesta_opciones(
                "¿A cuál cliente te refieres? Encontré: " + ", ".join(c.razon_social for c in dudosos) + ".",
                opciones_de_clientes(dudosos, prompt),
            )
        if cliente:
            return _respuesta(
                f"Abro la ficha de {cliente.razon_social}.",
                f"/clientes?q={quote(cliente.razon_social)}&detalle={cliente.id}",
                cliente.razon_social,
            )

    modulo = _modulo_mencionado(limpio)
    if not modulo:
        return None
    nombre, ruta, solo_admin = modulo
    if solo_admin and not es_admin:
        return {"respuesta": f"La sección «{nombre}» es solo para administradores.", "datos_estructurados": None}

    if ruta == "/pedidos":
        estado = _filtro(limpio, ESTADOS_PEDIDO)
        if estado:
            ruta, nombre = f"/pedidos?estado={estado}", f"Pedidos {estado.lower()}s"
    elif ruta == "/productos":
        stock = _filtro(limpio, STOCK)
        if stock and re.search(r"\bstock\b|\bcritico|\bagotad|\bagotando", limpio):
            etiquetas = {"critico": "stock crítico", "bajo": "stock bajo", "ok": "stock normal"}
            ruta, nombre = f"/productos?stock={stock}", f"Productos con {etiquetas[stock]}"
    elif ruta == "/clientes":
        tipo = _filtro(limpio, TIPOS_CLIENTE)
        if tipo:
            ruta, nombre = f"/clientes?tipo={tipo}", f"Clientes {tipo.lower()}s"
    elif ruta == "/solicitudes":
        estado = _filtro(limpio, ESTADOS_COTIZACION)
        if estado:
            ruta, nombre = f"/solicitudes?estado={estado}", f"Cotizaciones {estado.lower()}s"

    return _respuesta(f"Te llevo a {nombre}.", ruta, nombre)
