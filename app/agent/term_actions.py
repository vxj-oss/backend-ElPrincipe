import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.choices import opciones_de_clientes, respuesta_opciones
from app.agent.customer_actions import es_crear_cliente
from app.agent.fechas_texto import _sin_acentos
from app.agent.quote_intent import _buscar_cliente_en_texto
from app.models.commercial_term import CondicionComercial
from app.models.condicion_opcion import OpcionCondicionComercial
from app.models.customer import Cliente
from app.models.order import Pedido
from app.services.quote_note_service import normalizar

PREFIJO_CONDICION_CLIENTE = "¿A qué cliente le aplico la condición?"

PALABRAS_CONDICION = r"(?:descuento|dcto|rebaja|credito|plazo|forma de pago|condicion(?:es)?(?: comercial(?:es)?)?|contado|tarjeta)"
V_CREAR = r"(?:pon(?:le|er)?|da(?:le|r)?|otorga\w*|pacta\w*|asigna\w*|registra\w*|agrega\w*|crea\w*|configura\w*|establece\w*|autoriza\w*|aplica\w*|habilita\w*)"
V_CAMBIAR = r"(?:cambia\w*|actualiza\w*|modifica\w*|sube\w*|baja\w*|ajusta\w*|aumenta\w*|reduce\w*|corrige\w*)"
V_QUITAR = r"(?:quita\w*|elimina\w*|borra\w*|saca\w*|remueve\w*|retira\w*|anula\w*|suprime\w*|cancela\w*)"

PAT_QUITAR = re.compile(rf"\b{V_QUITAR}\b[^.\n]{{0,40}}\b{PALABRAS_CONDICION}\b")
PAT_CAMBIAR = re.compile(rf"\b{V_CAMBIAR}\b[^.\n]{{0,40}}\b{PALABRAS_CONDICION}\b")
PAT_CREAR = re.compile(rf"\b{V_CREAR}\b[^.\n]{{0,40}}\b{PALABRAS_CONDICION}\b|\bpaga\b[^.\n]{{0,20}}\b(?:contado|tarjeta)\b")
PAT_EXCLUIR = re.compile(r"\b(?:cotizacion|cotizaciones|pedido|pedidos|stock|producto|productos|ventas?|grafic\w*)\b")

PAT_TIPO = [
    ("Descuento", re.compile(r"\b(?:descuento|dcto|rebaja)\b|%|por ?ciento")),
    ("Credito", re.compile(r"\b(?:credito|plazo)\b|\b\d+\s*dias?\b")),
    ("Forma_Pago", re.compile(r"\bforma de pago\b|\bcontado\b|\btarjeta\b")),
]
PAT_PORCENTAJE = re.compile(r"(\d{1,2}(?:[.,]\d+)?)\s*(?:%|por ?ciento)|\bdescuento\s+(?:de\s+|del\s+|al\s+)?(\d{1,2}(?:[.,]\d+)?)\b")
PAT_DIAS = re.compile(r"\b(\d{1,3})\s*dias?\b|\bcredito\s+(?:de\s+|a\s+)?(\d{1,3})\b")
PAT_FORMA = re.compile(r"\b(contado|tarjeta|otro)\b")

ETIQUETA_TIPO = {"Credito": "crédito", "Descuento": "descuento", "Forma_Pago": "forma de pago"}


def _texto(respuesta: str, datos: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"respuesta": respuesta, "datos_estructurados": datos}


def _numero(valor: str) -> str:
    n = float(valor.replace(",", "."))
    return str(int(n)) if n == int(n) else str(n)


def _opciones(db: Session, tipo: str) -> List[Tuple[str, str]]:
    filas = db.scalars(
        select(OpcionCondicionComercial)
        .where(OpcionCondicionComercial.tipo_condicion == tipo, OpcionCondicionComercial.activo.is_(True))
        .order_by(OpcionCondicionComercial.orden)
    ).all()
    return [(f.valor, f.etiqueta) for f in filas]


def _valor_de(cond: CondicionComercial) -> str:
    if cond.tipo_condicion == "Credito":
        return str(cond.dias_plazo_pactados)
    if cond.tipo_condicion == "Descuento":
        return _numero(str(cond.porcentaje_descuento))
    return cond.forma_pago_pactada or ""


def _etiqueta(tipo: str, valor: str, opciones: List[Tuple[str, str]]) -> str:
    for v, etiqueta in opciones:
        if v == valor or (v.replace(".", "").isdigit() and valor.replace(".", "").isdigit() and float(v) == float(valor)):
            return etiqueta
    return {"Credito": f"Crédito {valor}d", "Descuento": f"Descuento {valor}%"}.get(tipo, valor)


def _frase(tipo: str, valor: str, cliente: str) -> str:
    if tipo == "Descuento":
        return f"ponle a {cliente} un descuento del {valor}%"
    if tipo == "Credito":
        return f"dale a {cliente} crédito de {valor} días"
    return f"{cliente} paga {valor.lower()}"


def _tipo_en_texto(texto: str) -> Optional[str]:
    for tipo, patron in PAT_TIPO:
        if patron.search(texto):
            return tipo
    return None


def _valor_en_texto(tipo: str, texto: str) -> Optional[str]:
    if tipo == "Descuento":
        m = PAT_PORCENTAJE.search(texto)
        return _numero(m.group(1) or m.group(2)) if m else None
    if tipo == "Credito":
        m = PAT_DIAS.search(texto)
        return str(int(m.group(1) or m.group(2))) if m else None
    m = PAT_FORMA.search(texto)
    return m.group(1).capitalize() if m else None


def _pendientes(db: Session, cliente_id: int) -> int:
    return int(db.scalar(select(func.count(Pedido.id)).where(Pedido.cliente_id == cliente_id, Pedido.estado == "Pendiente")) or 0)


def _explicacion(accion: str) -> Dict[str, Any]:
    verbo = {"crear": "pactar", "actualizar": "cambiar", "eliminar": "eliminar"}[accion]
    return {
        "resumen": f"Identifiqué el cliente, el tipo de condición y el valor, y preparé la acción de {verbo}. Se aplica solo cuando confirmas y queda en el historial de auditoría.",
        "fuentes": ["Tu mensaje", "Condiciones comerciales actuales del cliente", "Catálogo de opciones vigentes (créditos, descuentos y formas de pago)"],
        "formula": None,
        "periodo": "datos al momento de la consulta",
    }


def responder_condicion(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    if PAT_EXCLUIR.search(limpio) or es_crear_cliente(prompt):
        return None

    if PAT_QUITAR.search(limpio):
        accion = "eliminar"
    elif PAT_CAMBIAR.search(limpio):
        accion = "actualizar"
    elif PAT_CREAR.search(limpio):
        accion = "crear"
    else:
        return None

    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    if cliente is None and dudosos:
        return respuesta_opciones(
            "¿A cuál cliente te refieres? Encontré: " + ", ".join(c.razon_social for c in dudosos) + ".",
            opciones_de_clientes(dudosos, prompt),
        )
    if cliente is None:
        return _texto(f"{PREFIJO_CONDICION_CLIENTE} Dime el nombre del cliente, por ejemplo: «Hotel Rosas».")

    texto = _sin_acentos(prompt)
    tipo = _tipo_en_texto(texto)
    existentes: List[CondicionComercial] = list(
        db.scalars(select(CondicionComercial).where(CondicionComercial.cliente_id == cliente.id).order_by(CondicionComercial.id.desc())).all()
    )

    if accion == "eliminar":
        if not existentes:
            return _texto(f"{cliente.razon_social} no tiene condiciones comerciales pactadas.")
        candidatas = [c for c in existentes if tipo is None or c.tipo_condicion == tipo]
        if not candidatas:
            return _texto(f"{cliente.razon_social} no tiene una condición de {ETIQUETA_TIPO[tipo]}.")
        if len(candidatas) > 1:
            return respuesta_opciones(
                f"{cliente.razon_social} tiene {len(candidatas)} condiciones. ¿Cuál elimino?",
                [
                    (_etiqueta(c.tipo_condicion, _valor_de(c), _opciones(db, c.tipo_condicion)), f"elimina el {ETIQUETA_TIPO[c.tipo_condicion]} de {cliente.razon_social}")
                    for c in candidatas
                ],
            )
        cond = candidatas[0]
        etiqueta = _etiqueta(cond.tipo_condicion, _valor_de(cond), _opciones(db, cond.tipo_condicion))
        datos = {
            "tipo": "accion_condicion",
            "accion": "eliminar",
            "cliente": {"id": cliente.id, "nombre": cliente.razon_social},
            "condicion_id": cond.id,
            "tipo_condicion": cond.tipo_condicion,
            "etiqueta_actual": etiqueta,
            "pedidos_pendientes": _pendientes(db, cliente.id),
            "explicacion": _explicacion("eliminar"),
        }
        return _texto(f"¿Elimino la condición «{etiqueta}» de {cliente.razon_social}? Confírmalo aquí abajo.", datos)

    if tipo is None:
        return respuesta_opciones(
            f"¿Qué condición quieres {'pactar' if accion == 'crear' else 'cambiar'} para {cliente.razon_social}?",
            [("Descuento", f"ponle a {cliente.razon_social} un descuento"), ("Crédito", f"dale a {cliente.razon_social} crédito"), ("Forma de pago", f"cambia la forma de pago de {cliente.razon_social}")],
        )

    opciones = _opciones(db, tipo)
    valor = _valor_en_texto(tipo, texto)
    if valor is None or (opciones and not any(v == valor or _mismo_numero(v, valor) for v, _ in opciones)):
        encabezado = (
            f"{'«' + valor + '» no es una opción vigente. ' if valor else ''}¿Qué {ETIQUETA_TIPO[tipo]} le pacto a {cliente.razon_social}?"
        )
        return respuesta_opciones(encabezado, [(etiqueta, _frase(tipo, v, cliente.razon_social)) for v, etiqueta in opciones])

    existente = next((c for c in existentes if c.tipo_condicion == tipo), None)
    etiqueta_nueva = _etiqueta(tipo, valor, opciones)
    if existente:
        actual = _valor_de(existente)
        etiqueta_actual = _etiqueta(tipo, actual, opciones)
        if actual == valor or _mismo_numero(actual, valor):
            return _texto(f"{cliente.razon_social} ya tiene «{etiqueta_actual}». No hay nada que cambiar.")
        datos = {
            "tipo": "accion_condicion",
            "accion": "actualizar",
            "cliente": {"id": cliente.id, "nombre": cliente.razon_social},
            "condicion_id": existente.id,
            "tipo_condicion": tipo,
            "valor": valor,
            "etiqueta_nueva": etiqueta_nueva,
            "etiqueta_actual": etiqueta_actual,
            "pedidos_pendientes": _pendientes(db, cliente.id),
            "explicacion": _explicacion("actualizar"),
        }
        return _texto(
            f"{cliente.razon_social} ya tiene «{etiqueta_actual}». ¿Lo cambio a «{etiqueta_nueva}»? Confírmalo aquí abajo.", datos
        )

    datos = {
        "tipo": "accion_condicion",
        "accion": "crear",
        "cliente": {"id": cliente.id, "nombre": cliente.razon_social},
        "tipo_condicion": tipo,
        "valor": valor,
        "etiqueta_nueva": etiqueta_nueva,
        "pedidos_pendientes": _pendientes(db, cliente.id),
        "explicacion": _explicacion("crear"),
    }
    return _texto(f"¿Pacto «{etiqueta_nueva}» con {cliente.razon_social}? Confírmalo aquí abajo.", datos)


def _mismo_numero(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except ValueError:
        return False
