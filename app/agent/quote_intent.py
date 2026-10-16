import re
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, distinct, func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.agent.choices import opciones_de_clientes, respuesta_opciones
from app.core.time import ahora_lima
from app.models.commercial_term import CondicionComercial
from app.models.customer import Cliente
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.schemas.customer_request import NotaCotizacionRequest
from app.services.quote_note_service import (
    NotaCotizacionService,
    _token_coincide,
    normalizar,
    tokens,
)

VERBOS = (
    r"(?:arm(?:a|ar|e|es)|cre(?:a|ar|e|es)|haz|hacer|hag(?:a|as)|gener(?:a|ar|e|es)|registr(?:a|ar|e|es)"
    r"|prepar(?:a|ar|e|es)|elabor(?:a|ar|e|es)|redact(?:a|ar|e|es))"
)

PATRON_INTENCION = re.compile(
    rf"\b{VERBOS}(?:me|le|nos)?\b[^.\n]{{0,40}}\bcotizacion(?:es)?\b|\bcotiz(?:a|ame|ale|anos)\b"
)
PATRON_REPETIR = re.compile(r"\b(?:lo mismo|igual|repite|repiteme|repetime|repetir)\b")
PATRON_ANTERIOR = re.compile(r"\b(?:ultim[oa]|anterior|pasad[oa]|vez)\b")
PATRON_LLAMAR = re.compile(
    r"\ba quien(?: debo| tengo que| deberia| puedo)? llam"
    r"|\bclientes? (?:inactivos?|sin comprar)\b"
    r"|\bque clientes? no (?:han |ha )?compr"
    r"|\bclientes? que (?:no )?(?:han )?(?:dejaron|dejado) de comprar\b"
)

DIAS_SIN_COMPRAR = 30
MAX_CLIENTES_LLAMAR = 8
MAX_SUGERENCIAS = 3
PALABRAS_SOCIETARIAS = {"sac", "eirl", "srl", "ltda", "sa", "ltd"}


def es_pedido_de_cotizacion(texto: str) -> bool:
    return bool(PATRON_INTENCION.search(normalizar(texto)))


def es_repetir_cotizacion(texto: str) -> bool:
    limpio = normalizar(texto)
    return bool(PATRON_REPETIR.search(limpio) and PATRON_ANTERIOR.search(limpio))


def es_clientes_para_llamar(texto: str) -> bool:
    return bool(PATRON_LLAMAR.search(normalizar(texto)))


def _descuento_pactado(db: Session, cliente_id: int) -> float:
    condicion = db.scalar(
        select(CondicionComercial)
        .where(
            CondicionComercial.cliente_id == cliente_id,
            CondicionComercial.tipo_condicion == "Descuento",
        )
        .order_by(CondicionComercial.id.desc())
    )
    return float(condicion.porcentaje_descuento or 0) if condicion else 0.0


def _sugerencias_cruzadas(db: Session, producto_ids: List[int]) -> List[Dict[str, Any]]:
    if not producto_ids:
        return []
    base = aliased(DetallePedido)
    otro = aliased(DetallePedido)
    stmt = (
        select(otro.producto_id, func.count(distinct(otro.pedido_id)).label("veces"))
        .join(base, base.pedido_id == otro.pedido_id)
        .join(Pedido, Pedido.id == otro.pedido_id)
        .where(
            base.producto_id.in_(producto_ids),
            otro.producto_id.notin_(producto_ids),
            Pedido.estado != "Cancelado",
        )
        .group_by(otro.producto_id)
        .order_by(desc("veces"))
        .limit(MAX_SUGERENCIAS * 3)
    )
    sugeridos: List[Dict[str, Any]] = []
    for producto_id, _ in db.execute(stmt).all():
        producto = db.get(Producto, producto_id)
        if producto and producto.activo and (producto.stock_actual or 0) > 0:
            sugeridos.append(
                {
                    "producto_id": producto.id,
                    "nombre": producto.nombre,
                    "precio": float(producto.precio_unitario),
                    "stock": producto.stock_actual,
                }
            )
        if len(sugeridos) == MAX_SUGERENCIAS:
            break
    return sugeridos


def _armar_borrador(
    db: Session,
    prompt: str,
    cliente: Optional[Dict[str, Any]],
    items: List[Dict[str, Any]],
    advertencias: List[str],
    origen: Optional[str] = None,
) -> Dict[str, Any]:
    total = len(items)
    cierre = f" para {cliente['nombre']}" if cliente else ""
    respuesta = (
        f"Armé un borrador de cotización{cierre} con {total} "
        f"{'producto' if total == 1 else 'productos'}"
        f"{f', basado en {origen}' if origen else ''}. Revísalo y confírmalo aquí abajo."
    )
    if not cliente:
        respuesta += " Falta elegir el cliente."

    ids = [it["producto_id"] for it in items if it["producto_id"]]
    return {
        "respuesta": respuesta,
        "datos_estructurados": {
            "tipo": "borrador_cotizacion",
            "nota": prompt,
            "cliente": cliente,
            "items": items,
            "advertencias": advertencias,
            "descuento_pactado_pct": _descuento_pactado(db, cliente["id"]) if cliente else 0,
            "sugerencias": _sugerencias_cruzadas(db, ids),
            "origen": origen,
            "explicacion": {
                "resumen": "El modelo de IA interpretó tu nota y el sistema buscó cada producto en el catálogo. Los precios siempre salen del catálogo, no del modelo.",
                "fuentes": ["Catálogo de productos activos", "Clientes registrados", "Condición de descuento pactada con el cliente"],
                "formula": None,
                "periodo": "datos al momento de la consulta",
            },
        },
    }


PALABRAS_ORDEN = {
    "arma", "armar", "arme", "armes", "crea", "crear", "cree", "crees", "haz", "hacer", "haga", "hagas",
    "genera", "generar", "genere", "generes", "registra", "registrar", "prepara", "preparar",
    "elabora", "elaborar", "redacta", "redactar", "cotiza", "cotizame", "cotizale", "cotizanos",
    "me", "le", "nos", "una", "un", "cotizacion", "cotizaciones", "para", "por", "favor", "puedes",
    "quiero", "necesito", "nueva", "nuevo", "cliente",
}


def _pedir_lo_que_falta(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    if re.search(r"\d", prompt):
        return None
    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    if dudosos:
        return None
    propios = set(tokens(cliente.razon_social)) if cliente else set()
    sobrantes = [
        t for t in tokens(prompt)
        if normalizar(t) not in PALABRAS_ORDEN and t not in propios
        and not any(_token_coincide(t, p) for p in propios)
    ]
    if sobrantes:
        return None
    if cliente:
        texto = (
            f"¿Qué productos le cotizo a {cliente.razon_social}? "
            "Dime las cantidades, por ejemplo: «3 lejías y 2 papeleras»."
        )
    else:
        texto = (
            "¿Para qué cliente y qué productos? "
            "Por ejemplo: «Lavandería Burbujas con 3 lejías y 2 papeleras»."
        )
    return {"respuesta": texto, "datos_estructurados": None}


def preparar_borrador(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    faltante = _pedir_lo_que_falta(db, prompt)
    if faltante:
        return faltante
    resultado = NotaCotizacionService.interpretar(
        db, NotaCotizacionRequest(texto=prompt[:3000])
    )

    if not resultado.ia_disponible:
        return {
            "respuesta": "No pude interpretar tu pedido en este momento. Intenta de nuevo en unos segundos o arma la cotización desde el módulo de Cotizaciones.",
            "datos_estructurados": None,
        }
    if not resultado.items:
        return {
            "respuesta": "No identifiqué productos en tu mensaje. Escríbelo así, por ejemplo: «arma una cotización para Lavandería Burbujas con 3 lejías y 2 papeleras».",
            "datos_estructurados": None,
        }

    cliente = None
    if resultado.cliente_sugerido_id:
        encontrado = db.get(Cliente, resultado.cliente_sugerido_id)
        if encontrado:
            cliente = {"id": encontrado.id, "nombre": encontrado.razon_social}

    items = [
        {
            "producto_id": it.producto_id,
            "nombre": it.nombre,
            "texto_original": it.texto_original,
            "cantidad": it.cantidad,
            "precio_esperado": float(it.precio_esperado) if it.precio_esperado is not None else None,
            "stock": it.stock,
            "coincidencia": it.coincidencia,
            "opciones": [
                {
                    "producto_id": o.producto_id,
                    "nombre": o.nombre,
                    "precio": float(o.precio),
                    "stock": o.stock,
                }
                for o in it.opciones
            ],
        }
        for it in resultado.items
    ]
    return _armar_borrador(db, prompt, cliente, items, resultado.advertencias)


def _buscar_cliente_en_texto(
    db: Session, prompt: str
) -> Tuple[Optional[Cliente], List[Cliente]]:
    palabras = tokens(prompt)
    clientes = list(db.scalars(select(Cliente).where(Cliente.estado == "Activo")).all())
    puntajes: List[Tuple[Tuple[int, float], Cliente]] = []
    for cliente in clientes:
        propios = [t for t in tokens(cliente.razon_social) if t not in PALABRAS_SOCIETARIAS and len(t) >= 3]
        coincidentes = sum(1 for t in propios if any(_token_coincide(p, t) for p in palabras))
        if coincidentes:
            puntajes.append(((coincidentes, round(coincidentes / len(propios), 4)), cliente))
    if not puntajes:
        return None, []
    mejor = max(p for p, _ in puntajes)
    finalistas = [c for p, c in puntajes if p == mejor]
    if len(finalistas) == 1:
        return finalistas[0], []
    return None, finalistas[:5]


def repetir_ultima_cotizacion(db: Session, prompt: str) -> Dict[str, Any]:
    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    if cliente is None and dudosos:
        nombres = ", ".join(c.razon_social for c in dudosos)
        return respuesta_opciones(
            f"¿A cuál cliente te refieres? Encontré: {nombres}.",
            opciones_de_clientes(dudosos, prompt),
        )
    if cliente is None:
        return {
            "respuesta": "¿Para qué cliente quieres repetir la última cotización? Menciónalo, por ejemplo: «hazle a Lavandería Burbujas lo mismo que la última vez».",
            "datos_estructurados": None,
        }

    ultima = db.scalar(
        select(SolicitudCliente)
        .options(selectinload(SolicitudCliente.detalles))
        .where(SolicitudCliente.cliente_id == cliente.id)
        .order_by(SolicitudCliente.id.desc())
        .limit(1)
    )
    if not ultima or not ultima.detalles:
        return {
            "respuesta": f"{cliente.razon_social} no tiene cotizaciones anteriores registradas.",
            "datos_estructurados": None,
        }

    items: List[Dict[str, Any]] = []
    for det in ultima.detalles:
        producto = db.get(Producto, det.producto_id) if det.producto_id else None
        if producto and producto.activo:
            items.append(
                {
                    "producto_id": producto.id,
                    "nombre": producto.nombre,
                    "texto_original": det.nombre_producto_solicitado,
                    "cantidad": det.cantidad_solicitada,
                    "precio_esperado": float(producto.precio_unitario),
                    "stock": producto.stock_actual,
                    "coincidencia": "catalogo",
                    "opciones": [],
                }
            )
        else:
            items.append(
                {
                    "producto_id": None,
                    "nombre": det.nombre_producto_solicitado,
                    "texto_original": det.nombre_producto_solicitado,
                    "cantidad": det.cantidad_solicitada,
                    "precio_esperado": float(det.precio_esperado) if det.precio_esperado is not None else None,
                    "stock": None,
                    "coincidencia": "sin_coincidencia",
                    "opciones": [],
                }
            )

    fecha = ultima.fecha_solicitud.astimezone(ahora_lima().tzinfo).strftime("%d/%m/%Y")
    advertencias = [
        "Los precios se actualizaron al catálogo vigente."
    ]
    if any(it["coincidencia"] == "sin_coincidencia" for it in items):
        advertencias.append("Algunos productos ya no están disponibles en el catálogo; revísalos.")

    return _armar_borrador(
        db,
        prompt,
        {"id": cliente.id, "nombre": cliente.razon_social},
        items,
        advertencias,
        origen=f"la cotización {ultima.codigo_solicitud} del {fecha}",
    )


def clientes_para_llamar(db: Session) -> Dict[str, Any]:
    ahora = ahora_lima()
    limite = ahora - timedelta(days=DIAS_SIN_COMPRAR)
    ultimas = (
        select(Pedido.cliente_id, func.max(Pedido.fecha_pedido).label("ultima"))
        .where(Pedido.estado != "Cancelado")
        .group_by(Pedido.cliente_id)
        .subquery()
    )
    filas = db.execute(
        select(Cliente, ultimas.c.ultima)
        .join(ultimas, ultimas.c.cliente_id == Cliente.id)
        .where(Cliente.estado == "Activo", ultimas.c.ultima < limite)
        .order_by(ultimas.c.ultima.asc())
        .limit(MAX_CLIENTES_LLAMAR)
    ).all()

    if not filas:
        return {
            "respuesta": f"No hay clientes activos con más de {DIAS_SIN_COMPRAR} días sin comprar.",
            "datos_estructurados": None,
        }

    lineas = [
        f"Clientes con más de {DIAS_SIN_COMPRAR} días sin comprar (los {len(filas)} con más tiempo):"
    ]
    for cliente, ultima in filas:
        dias = (ahora - ultima).days
        habitual = db.scalar(
            select(Producto.nombre)
            .join(DetallePedido, DetallePedido.producto_id == Producto.id)
            .join(Pedido, Pedido.id == DetallePedido.pedido_id)
            .where(Pedido.cliente_id == cliente.id, Pedido.estado != "Cancelado")
            .group_by(Producto.id, Producto.nombre)
            .order_by(desc(func.sum(DetallePedido.cantidad)))
            .limit(1)
        )
        detalle = f"último pedido {ultima.astimezone(ahora.tzinfo).strftime('%d/%m/%Y')} (hace {dias} días)"
        if habitual:
            detalle += f"; suele llevar: {habitual}"
        if cliente.telefono:
            detalle += f"; tel. {cliente.telefono}"
        lineas.append(f"• {cliente.razon_social} — {detalle}")
    return {
        "respuesta": "\n".join(lineas),
        "datos_estructurados": {
            "tipo": "texto",
            "explicacion": {
                "resumen": f"Listé los clientes activos cuya última compra fue hace más de {DIAS_SIN_COMPRAR} días.",
                "fuentes": ["Pedidos no cancelados de cada cliente", "Productos más comprados por el cliente"],
                "formula": f"Días sin comprar = hoy − fecha de la última compra (umbral: {DIAS_SIN_COMPRAR} días)",
                "periodo": "historial completo",
            },
        },
    }
