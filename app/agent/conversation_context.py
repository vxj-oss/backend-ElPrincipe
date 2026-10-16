import re
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.agent.context_builder import ContextBuilder
from app.agent.customer_actions import PREFIJO_CLIENTE_NOMBRE
from app.agent.entity_actions import PREFIJO_CLIENTE_ACCION
from app.agent.product_actions import PREFIJO_PRODUCTO, resolver_pendiente_producto
from app.agent.term_actions import PREFIJO_CONDICION_CLIENTE
from app.agent.actions import PREFIJO_ESTADO_PENDIENTE, PREFIJO_PEDIDO_PENDIENTE, PREFIJO_UNIDADES_PENDIENTE
from app.agent.quick_answers import (
    PAT_CLIENTE,
    PAT_CODIGO,
    PAT_MARGEN,
    PAT_TOP,
    PAT_VENTAS,
    _consulta_producto,
)
from app.agent.quote_intent import _buscar_cliente_en_texto
from app.services.quote_note_service import normalizar, tokens

PREFIJO_CLIENTE_DUDOSO = "¿A cuál cliente te refieres? Encontré: "
PREFIJO_PRODUCTOS_PENDIENTES = "¿Qué productos le cotizo a "
PREFIJO_CLIENTE_Y_PRODUCTOS = "¿Para qué cliente y qué productos?"

MAX_TOKENS_SEGUIMIENTO = 8
MAX_TOKENS_RESPUESTA = 25

PAT_PERIODO = re.compile(
    r"^(?:y |pero |ahora )?(?:que tal )?(?:en |de |para )?(?:la |el |este |esta |lo de |lo del )?"
    r"(hoy|semana|mes)(?: actual)?$"
)
PAT_Y_DE = re.compile(r"^(?:y|pero|ahora)(?: (?:de|del|el de|la de|los de|las de|lo de|a|para))? (.+)$")
PAT_REFERENCIA_CLIENTE = re.compile(
    r"\bsu (?:telefono|correo|direccion|celular|ficha|historial|ticket)\b"
    r"|\bcuando (?:fue )?(?:la )?(?:ultima vez )?(?:que )?(?:compro|pidio)\b"
    r"|\bcuanto (?:ha )?(?:compro|comprado|gastado|gasto)\b"
    r"|\bque (?:lleva|compra|suele)\b|\bsus (?:compras|pedidos|cotizaciones)\b"
)
PAT_REFERENCIA_CODIGO = re.compile(r"\b(?:ese|esa|dicho|dicha|el mismo|la misma)\s+(?:pedido|cotizacion)\b")
ORDINALES = {
    "1": 0, "uno": 0, "primero": 0, "primer": 0, "primera": 0,
    "2": 1, "dos": 1, "segundo": 1, "segunda": 1,
    "3": 2, "tres": 2, "tercero": 2, "tercer": 2, "tercera": 2,
    "4": 3, "cuatro": 3, "cuarto": 3, "cuarta": 3,
    "5": 4, "cinco": 4, "quinto": 4, "quinta": 4,
}


def _ultimo(mensajes: List[Tuple[str, str]], rol: str) -> Optional[str]:
    for r, contenido in reversed(mensajes):
        if r == rol:
            return contenido
    return None


def _nombres_dudosos(texto_agente: str) -> List[str]:
    cuerpo = texto_agente[len(PREFIJO_CLIENTE_DUDOSO):].strip().rstrip(".")
    return [n.strip() for n in cuerpo.split(", ") if n.strip()]


def _elegir_nombre(respuesta: str, nombres: List[str]) -> Optional[str]:
    palabras = [t for t in normalizar(respuesta).split() if t not in {"el", "la", "los", "las", "del", "de"}]
    if len(palabras) == 1 and palabras[0] in ORDINALES:
        indice = ORDINALES[palabras[0]]
        return nombres[indice] if indice < len(nombres) else None
    buscados = [t for t in palabras if len(t) >= 3]
    if not buscados:
        return None
    coincidentes = [n for n in nombres if all(b in normalizar(n).split() or b in normalizar(n) for b in buscados)]
    return coincidentes[0] if len(coincidentes) == 1 else None


def _resolver_pendiente(
    prompt: str, ultimo_agente: Optional[str], previos_usuario: List[str]
) -> Optional[str]:
    if not ultimo_agente or "?" in prompt or len(tokens(prompt)) > MAX_TOKENS_RESPUESTA:
        return None

    if ultimo_agente.startswith(PREFIJO_CLIENTE_DUDOSO) and previos_usuario:
        elegido = _elegir_nombre(prompt, _nombres_dudosos(ultimo_agente))
        if elegido:
            return f"{previos_usuario[-1]} {elegido}"
        return None

    if ultimo_agente.startswith(PREFIJO_PRODUCTOS_PENDIENTES):
        resto = ultimo_agente[len(PREFIJO_PRODUCTOS_PENDIENTES):]
        cliente = resto.split("?", 1)[0].strip()
        if cliente:
            return f"arma una cotizacion para {cliente} con {prompt}"

    if ultimo_agente.startswith(PREFIJO_CLIENTE_Y_PRODUCTOS):
        return f"arma una cotizacion para {prompt}"

    if ultimo_agente.startswith(PREFIJO_UNIDADES_PENDIENTE):
        nombre = ultimo_agente[len(PREFIJO_UNIDADES_PENDIENTE):].split("?", 1)[0].strip()
        if nombre and re.search(r"\d", prompt):
            return f"repon el stock de {nombre} con {prompt}"
        return None

    pendiente_producto = resolver_pendiente_producto(ultimo_agente, prompt)
    if pendiente_producto:
        return pendiente_producto

    if ultimo_agente.startswith(PREFIJO_PRODUCTO) and previos_usuario:
        return f"{previos_usuario[-1]} {prompt}"

    if ultimo_agente.startswith(PREFIJO_CLIENTE_ACCION) and previos_usuario:
        return f"{previos_usuario[-1]} del cliente {prompt}"

    if ultimo_agente.startswith(PREFIJO_CONDICION_CLIENTE) and previos_usuario:
        return f"{previos_usuario[-1]} para {prompt}"

    if ultimo_agente.startswith(PREFIJO_CLIENTE_NOMBRE) and previos_usuario:
        return f"{previos_usuario[-1]} nombre {prompt}"

    if ultimo_agente.startswith(PREFIJO_PEDIDO_PENDIENTE):
        return f"hazle el pedido a {prompt}"

    if ultimo_agente.startswith(PREFIJO_ESTADO_PENDIENTE) and previos_usuario:
        return f"{previos_usuario[-1]} {prompt}"

    return None


def _cambio_periodo(limpio: str, previos_usuario: List[str]) -> Optional[str]:
    coincidencia = PAT_PERIODO.match(limpio)
    if not coincidencia:
        return None
    periodo = coincidencia.group(1)
    for previo in reversed(previos_usuario):
        base = normalizar(previo)
        if PAT_MARGEN.search(base):
            return f"margen de {periodo}"
        if PAT_TOP.search(base):
            return f"productos mas vendidos {periodo}"
        if PAT_VENTAS.search(base) or "venta" in base:
            return f"ventas de {periodo}"
    return None


def _plantilla_cliente(base_previa: str, nombre: str) -> str:
    base = normalizar(base_previa)
    if re.search(r"\b(?:telefono|celular|contacto|correo)\b", base):
        return f"telefono de {nombre}"
    if re.search(r"\bultima compra\b|\bcuando (?:fue )?(?:la )?(?:ultima vez )?(?:que )?compro\b", base):
        return f"ultima compra de {nombre}"
    if re.search(r"\bque (?:lleva|compra|productos lleva)\b|\bsuele (?:llevar|comprar)\b", base):
        return f"que lleva {nombre}"
    if re.search(r"\bcotizaciones? pendientes?\b", base):
        return f"cotizaciones pendientes de {nombre}"
    return f"resumen del cliente {nombre}"


def _cambio_cliente_o_producto(
    db: Session, limpio: str, previos_usuario: List[str]
) -> Optional[str]:
    coincidencia = PAT_Y_DE.match(limpio)
    if not coincidencia or not previos_usuario:
        return None
    resto = coincidencia.group(1)
    if len(resto.split()) > 4:
        return None
    previo = previos_usuario[-1]
    base_previa = normalizar(previo)

    if PAT_CLIENTE.search(base_previa):
        cliente, _ = _buscar_cliente_en_texto(db, resto)
        if cliente:
            return _plantilla_cliente(previo, cliente.razon_social)

    if _consulta_producto(base_previa, previo):
        verbo = "precio de" if re.search(r"\b(?:precio|precios|cuesta|cuestan|vale|valen|costo)\b", base_previa) else "stock de"
        return f"{verbo} {resto}"
    return None


def _ultimo_cliente(db: Session, mensajes: List[Tuple[str, str]]):
    for _, contenido in reversed(mensajes):
        cliente, _ = _buscar_cliente_en_texto(db, contenido)
        if cliente:
            return cliente
    return None


def _referencia_cliente(
    db: Session, prompt: str, limpio: str, mensajes: List[Tuple[str, str]]
) -> Optional[str]:
    if not PAT_REFERENCIA_CLIENTE.search(limpio):
        return None
    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    if cliente or dudosos:
        return None
    anterior = _ultimo_cliente(db, mensajes)
    if not anterior:
        return None
    return f"{prompt} de {anterior.razon_social}"


def _referencia_codigo(prompt: str, limpio: str, mensajes: List[Tuple[str, str]]) -> Optional[str]:
    if not PAT_REFERENCIA_CODIGO.search(limpio) or PAT_CODIGO.search(prompt):
        return None
    for _, contenido in reversed(mensajes):
        encontrado = PAT_CODIGO.search(contenido)
        if encontrado:
            return f"{prompt} {encontrado.group(1).upper()}-{encontrado.group(2).upper()}"
    return None


def resolver_seguimiento(db: Session, prompt: str, session_id: Optional[int]) -> str:
    mensajes = ContextBuilder.get_recent_messages(db, session_id, prompt, limit=6)
    if not mensajes:
        return prompt

    previos_usuario = [contenido for rol, contenido in mensajes if rol == "user"]
    pendiente = _resolver_pendiente(prompt, _ultimo(mensajes, "assistant"), previos_usuario)
    if pendiente:
        return pendiente

    limpio = normalizar(prompt)
    if len(limpio.split()) > MAX_TOKENS_SEGUIMIENTO:
        return prompt

    return (
        _cambio_periodo(limpio, previos_usuario)
        or _cambio_cliente_o_producto(db, limpio, previos_usuario)
        or _referencia_cliente(db, prompt, limpio, mensajes)
        or _referencia_codigo(prompt, limpio, mensajes)
        or prompt
    )
