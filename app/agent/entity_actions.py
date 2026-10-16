import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agent.choices import opciones_de_clientes, respuesta_opciones
from app.agent.customer_actions import es_crear_cliente
from app.agent.edit_draft import responder_edicion
from app.agent.fechas_texto import _sin_acentos
from app.agent.quick_answers import PAT_CODIGO
from app.agent.quote_intent import PALABRAS_SOCIETARIAS, _descuento_pactado
from app.models.customer import Cliente
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.services.customer_service import CustomerService
from app.services.quote_note_service import _token_coincide, normalizar, tokens

PREFIJO_CLIENTE_ACCION = "¿Sobre qué cliente?"
TIPOS = {"mayorista": "Mayorista", "institucional": "Institucional", "minorista": "Minorista"}

V_EDITAR_CLIENTE = r"(?:cambia\w*|actualiza\w*|modifica\w*|corrige\w*|pon(?:le|lo)?|anota\w*|registra\w*|agrega\w*|renombra\w*|edita\w*|haz(?:lo|la)?|marca(?:lo|la)?|convierte\w*|pasa(?:lo|la)?|cambiale|quita\w*)"
V_DESACTIVAR = r"(?:desactiva\w*|deshabilita\w*|inactiva\w*)"
V_ELIMINAR = r"(?:elimina\w*|borra\w*|quita\w*|saca\w*|retira\w*)"
V_REACTIVAR = r"(?:reactiva\w*|activa\w*|habilita\w*)"
ATRIBUTOS_CLIENTE = r"\b(?:telefono|celular|cel|whatsapp|fono|correo|email|mail|direccion|distrito|tipo|vip|regular|ruc|dni|nombre|razon social|renombr\w+)\b"
ATRIBUTOS_SOLO_CLIENTE = r"\b(?:telefono|celular|whatsapp|fono|correo|email|mail|direccion|distrito|vip|ruc|dni|renombr\w+)\b"

PAT_EXCLUIR_CLIENTE = re.compile(r"\b(?:cotizacion|cotizaciones|pedido|pedidos|producto|productos|descuento|credito|condicion|condiciones|stock|grafic\w*)\b")
PAT_TELEFONO = re.compile(r"(?:telefono|celular|cel|whatsapp|fono)\D{0,60}?((?:\+?\d[\d\s\-]{5,15}\d))")
PAT_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PAT_DIRECCION = re.compile(r"(?i)direcci[oó]n\s*(?:(?:a|de|es)\b|:|=)?\s*([^,;]+)")
PAT_DISTRITO = re.compile(r"(?i)distrito\s*(?:(?:a|de|es)\b|:|=)?\s*([^,;]+)")
PAT_NOMBRE_NUEVO = re.compile(r"(?i)(?:renombra\w*|cambia\w*\s+(?:el\s+)?(?:nombre|raz[oó]n social)(?:\s+del\s+cliente)?)\s+(.*?)\s+(?:a|por)\s+(.+)$")
PAT_RUC = re.compile(r"(?:ruc|dni)\D{0,6}(\d{8,11})\b")
PAT_QUITAR_VIP = re.compile(r"\bya no es vip\b|\bquita\w*\s+(?:el\s+)?vip\b|\bsin vip\b|\bregular\b|\bno es vip\b")
PAT_VIP = re.compile(r"\bvip\b")


def _texto(respuesta: str, datos: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"respuesta": respuesta, "datos_estructurados": datos}


def _explicacion(resumen: str, fuentes: List[str]) -> Dict[str, Any]:
    return {"resumen": resumen, "fuentes": fuentes, "formula": None, "periodo": "datos al momento de la consulta"}


def _buscar_cliente_todos(db: Session, prompt: str) -> Tuple[Optional[Cliente], List[Cliente]]:
    palabras = tokens(prompt)
    puntajes: List[Tuple[Tuple[int, float], Cliente]] = []
    for cliente in db.scalars(select(Cliente)).all():
        propios = [t for t in tokens(cliente.razon_social) if t not in PALABRAS_SOCIETARIAS and len(t) >= 3]
        if not propios:
            continue
        coincidentes = sum(1 for t in propios if any(_token_coincide(p, t) for p in palabras))
        if coincidentes:
            puntajes.append(((coincidentes, round(coincidentes / len(propios), 4)), cliente))
    if not puntajes:
        return None, []
    mejor = max(p for p, _ in puntajes)
    finalistas = [c for p, c in puntajes if p == mejor]
    return (finalistas[0], []) if len(finalistas) == 1 else (None, finalistas[:5])


def _resolver_cliente(db: Session, prompt: str) -> Tuple[Optional[Cliente], Optional[Dict[str, Any]]]:
    cliente, dudosos = _buscar_cliente_todos(db, prompt)
    if cliente is None and dudosos:
        return None, respuesta_opciones(
            "¿A cuál cliente te refieres? Encontré: " + ", ".join(c.razon_social for c in dudosos) + ".",
            opciones_de_clientes(dudosos, prompt),
        )
    if cliente is None:
        return None, _texto(f"{PREFIJO_CLIENTE_ACCION} Dime el nombre del cliente, por ejemplo: «Hotel Rosas».")
    return cliente, None


def _cortar_cliente(valor: str) -> str:
    return re.split(r"(?i)\s+(?:al|del|a la|de la|a|de)\s+cliente\b", valor)[0].strip(" .")


def _campos_cliente(prompt: str) -> Tuple[Dict[str, Any], Optional[str]]:
    texto = _sin_acentos(prompt)
    cambios: Dict[str, Any] = {}
    nombre_cliente_texto: Optional[str] = None

    renombrado = PAT_NOMBRE_NUEVO.search(prompt)
    if renombrado:
        nombre_cliente_texto = renombrado.group(1)
        cambios["razon_social"] = renombrado.group(2).strip(" .\"'«»")[:200]

    tel = PAT_TELEFONO.search(texto)
    if tel:
        cambios["telefono"] = re.sub(r"[\s\-]", "", tel.group(1))[:20]
    correo = PAT_CORREO.search(texto)
    if correo:
        cambios["correo"] = correo.group(0)
    direccion = PAT_DIRECCION.search(prompt)
    if direccion:
        cambios["direccion"] = _cortar_cliente(direccion.group(1))[:300]
    distrito = PAT_DISTRITO.search(prompt)
    if distrito:
        cambios["distrito"] = _cortar_cliente(distrito.group(1))[:100]
    ruc = PAT_RUC.search(texto)
    if ruc and len(ruc.group(1)) in (8, 11):
        cambios["ruc_dni"] = ruc.group(1)
    for clave, valor in TIPOS.items():
        if re.search(rf"\b{clave}\b", texto) and re.search(r"\b(?:tipo|ahora es|pasalo a|cambialo a|conviertelo en|es)\b", texto):
            cambios["tipo_cliente"] = valor
            break
    if PAT_QUITAR_VIP.search(texto):
        cambios["clasificacion"] = "Regular"
    elif PAT_VIP.search(texto):
        cambios["clasificacion"] = "VIP"
    return cambios, nombre_cliente_texto


ETIQUETAS_CLIENTE = {
    "razon_social": "Nombre",
    "telefono": "Teléfono",
    "correo": "Correo",
    "direccion": "Dirección",
    "distrito": "Distrito",
    "ruc_dni": "RUC / DNI",
    "tipo_cliente": "Tipo",
    "clasificacion": "Clasificación",
}


def responder_cliente_accion(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    if PAT_EXCLUIR_CLIENTE.search(limpio) or es_crear_cliente(prompt):
        return None
    menciona_cliente = bool(re.search(r"\bcliente\b", limpio))
    if not menciona_cliente:
        if re.search(rf"\b{V_EDITAR_CLIENTE}\b", limpio) and re.search(ATRIBUTOS_SOLO_CLIENTE, limpio):
            cliente_directo, _ = _buscar_cliente_todos(db, _sin_valores(prompt))
            if cliente_directo is None:
                return None
            return _editar_cliente(db, prompt)
        return None

    if re.search(rf"\b{V_REACTIVAR}\b", limpio) and not re.search(rf"\b{V_DESACTIVAR}\b", limpio):
        return _cambiar_estado_cliente(db, prompt, "reactivar")
    if re.search(rf"\b{V_DESACTIVAR}\b", limpio):
        return _cambiar_estado_cliente(db, prompt, "desactivar")
    if re.search(rf"\b{V_ELIMINAR}\b", limpio) and not re.search(ATRIBUTOS_CLIENTE, limpio):
        return _cambiar_estado_cliente(db, prompt, "eliminar")

    if re.search(rf"\b{V_EDITAR_CLIENTE}\b", limpio) and re.search(ATRIBUTOS_CLIENTE, limpio):
        return _editar_cliente(db, prompt)
    return None


def _cambiar_estado_cliente(db: Session, prompt: str, accion: str) -> Dict[str, Any]:
    cliente, pregunta = _resolver_cliente(db, prompt)
    if pregunta:
        return pregunta
    if accion == "reactivar" and cliente.estado == "Activo":
        return _texto(f"«{cliente.razon_social}» ya está activo.")
    if accion == "desactivar" and cliente.estado == "Inactivo":
        return _texto(f"«{cliente.razon_social}» ya está inactivo.")

    historial = CustomerService._tiene_historial(db, cliente.id)
    advertencias: List[str] = []
    if accion == "eliminar":
        advertencias.append(
            "Tiene historial de pedidos o cotizaciones: no se borrará, se marcará como inactivo."
            if historial
            else "No tiene historial: se eliminará definitivamente."
        )
    elif accion == "desactivar":
        advertencias.append("Dejará de aparecer para nuevas cotizaciones y pedidos; su historial se conserva.")
    else:
        advertencias.append("Volverá a estar disponible para cotizaciones y pedidos.")
    datos = {
        "tipo": "accion_cliente",
        "accion": accion,
        "cliente": {"id": cliente.id, "nombre": cliente.razon_social},
        "tiene_historial": historial,
        "advertencias": advertencias,
        "explicacion": _explicacion(
            "Identifiqué el cliente y preparé el cambio. Se aplica solo al confirmar y queda en el historial de auditoría.",
            ["Clientes registrados", "Pedidos y cotizaciones del cliente (para saber si se puede eliminar)"],
        ),
    }
    verbo = {"reactivar": "Reactivo", "desactivar": "Desactivo", "eliminar": "Desactivo" if historial else "Elimino"}[accion]
    return _texto(f"¿{verbo} al cliente «{cliente.razon_social}»? {advertencias[0]} Confírmalo aquí abajo.", datos)


def _editar_cliente(db: Session, prompt: str) -> Dict[str, Any]:
    cambios_nuevos, texto_cliente = _campos_cliente(prompt)
    if not cambios_nuevos:
        return _texto("No identifiqué qué dato cambiar. Puedes decir, por ejemplo: «cambia el teléfono de Hotel Rosas a 987654321».")
    cliente, pregunta = _resolver_cliente(db, texto_cliente or _sin_valores(prompt))
    if pregunta:
        return pregunta

    cambios: List[Dict[str, Any]] = []
    payload: Dict[str, Any] = {}
    for campo, nuevo in cambios_nuevos.items():
        actual = getattr(cliente, campo) or ""
        if str(actual) == str(nuevo):
            continue
        payload[campo] = nuevo
        cambios.append({"campo": campo, "etiqueta": ETIQUETAS_CLIENTE[campo], "actual": actual or "—", "nuevo": nuevo})
    if not cambios:
        return _texto(f"«{cliente.razon_social}» ya tiene esos datos. No hay nada que cambiar.")

    datos = {
        "tipo": "accion_cliente",
        "accion": "editar",
        "cliente": {"id": cliente.id, "nombre": cliente.razon_social},
        "cambios": cambios,
        "payload": payload,
        "advertencias": [],
        "explicacion": _explicacion(
            "Separé del mensaje los datos a cambiar y los comparé con los actuales. Se aplica solo al confirmar.",
            ["Tu mensaje", "Ficha actual del cliente"],
        ),
    }
    resumen = "; ".join(f"{c['etiqueta'].lower()}: {c['actual']} → {c['nuevo']}" for c in cambios)
    return _texto(f"¿Actualizo a «{cliente.razon_social}»? {resumen}. Confírmalo aquí abajo.", datos)


def _sin_valores(prompt: str) -> str:
    tras_cliente = re.search(r"(?i)\b(?:al|del|de la|de|a la|a)\s+(?:el\s+)?cliente\s+(.+)$", prompt)
    if tras_cliente:
        return tras_cliente.group(1)
    texto = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", " ", prompt)
    texto = re.sub(r"\d[\d\s\-+]{4,}\d", " ", texto)
    return texto


def responder_cotizacion_accion(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    codigo = PAT_CODIGO.search(prompt)
    habla_cotizacion = bool(re.search(r"\bcotizacion(?:es)?\b", limpio)) or bool(codigo and codigo.group(1).upper() == "COT")
    if not habla_cotizacion or not re.search(r"\b(?:elimina\w*|borra\w*|cancela\w*|anula\w*|descarta\w*|quita\w*)\b", limpio):
        return None
    if re.search(r"\b(?:pedido|pedidos)\b", limpio) and not (codigo and codigo.group(1).upper() == "COT"):
        return None

    solicitud: Optional[SolicitudCliente] = None
    opciones = None
    if codigo and codigo.group(1).upper() == "COT":
        filas = db.scalars(
            select(SolicitudCliente)
            .options(selectinload(SolicitudCliente.cliente), selectinload(SolicitudCliente.detalles))
            .where(SolicitudCliente.codigo_solicitud.ilike(f"COT-{codigo.group(2).upper()}%"))
            .limit(5)
        ).all()
        if not filas:
            return _texto(f"No encontré ninguna cotización con el código COT-{codigo.group(2).upper()}.")
        if len(filas) > 1:
            return _texto("Hay varias cotizaciones que empiezan así: " + ", ".join(s.codigo_solicitud for s in filas) + ". Escribe el código completo.")
        solicitud = filas[0]
    else:
        cliente, pregunta = _resolver_cliente(db, prompt)
        if pregunta:
            return pregunta
        filas = db.scalars(
            select(SolicitudCliente)
            .options(selectinload(SolicitudCliente.cliente), selectinload(SolicitudCliente.detalles))
            .where(SolicitudCliente.cliente_id == cliente.id, SolicitudCliente.estado == "Pendiente")
            .order_by(SolicitudCliente.fecha_solicitud.desc())
            .limit(6)
        ).all()
        if not filas:
            return _texto(f"{cliente.razon_social} no tiene cotizaciones pendientes para eliminar.")
        if len(filas) > 1:
            opciones = [(f"{s.codigo_solicitud} · {len(s.detalles)} ítems", f"elimina la cotización {s.codigo_solicitud}") for s in filas]
            return respuesta_opciones(f"{cliente.razon_social} tiene {len(filas)} cotizaciones pendientes. ¿Cuál elimino?", opciones)
        solicitud = filas[0]

    if solicitud.estado == "Atendida":
        return _texto(
            f"La cotización {solicitud.codigo_solicitud} ya se convirtió en pedido, así que no se puede eliminar sin romper ese pedido."
        )
    cliente_nombre = solicitud.cliente.razon_social if solicitud.cliente else f"#{solicitud.cliente_id}"
    datos = {
        "tipo": "accion_cotizacion",
        "accion": "eliminar",
        "solicitud_id": solicitud.id,
        "codigo": solicitud.codigo_solicitud,
        "cliente": cliente_nombre,
        "items": len(solicitud.detalles),
        "estado": solicitud.estado,
        "explicacion": _explicacion(
            "Ubiqué la cotización por código o por el cliente y preparé su eliminación. Se aplica solo al confirmar y queda en el historial de auditoría.",
            ["Cotizaciones de clientes"],
        ),
    }
    return _texto(f"¿Elimino la cotización {solicitud.codigo_solicitud} de {cliente_nombre} ({len(solicitud.detalles)} ítems)? Confírmalo aquí abajo.", datos)


PAT_VERBO_ITEMS = re.compile(
    r"\b(?:cambia\w*|quita\w*|agrega\w*|anade\w*|suma\w*|sube\w*|baja\w*|pon(?:le)?|elimina\w*|saca\w*|retira\w*|modifica\w*|ajusta\w*|aumenta\w*|reduce\w*)\b"
)
PAT_ESTADO_O_DESCARGA = re.compile(
    r"\b(?:aprobado|aprobar|aprueba\w*|entregado|entregar|entrega\w*|cancelado|cancelar|cancela\w*|pendiente|estado|pasalo|marcalo|pdf|ticket|descarga\w*|detalle)\b"
)


def responder_pedido_items(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    codigo = PAT_CODIGO.search(prompt)
    if not codigo or codigo.group(1).upper() != "PED":
        return None
    if not PAT_VERBO_ITEMS.search(limpio) or PAT_ESTADO_O_DESCARGA.search(limpio):
        return None

    codigo_texto = f"PED-{codigo.group(2).upper()}"
    pedidos = db.scalars(
        select(Pedido)
        .options(selectinload(Pedido.cliente), selectinload(Pedido.detalles))
        .where(Pedido.codigo_pedido.ilike(f"{codigo_texto}%"))
        .limit(5)
    ).all()
    if not pedidos:
        return _texto(f"No encontré ningún pedido con el código {codigo_texto}.")
    if len(pedidos) > 1:
        return _texto("Hay varios pedidos que empiezan así: " + ", ".join(p.codigo_pedido for p in pedidos) + ". Escribe el código completo.")
    pedido = pedidos[0]
    if pedido.estado in ("Entregado", "Cancelado"):
        return _texto(f"El pedido {pedido.codigo_pedido} está {pedido.estado.lower()}; ya no se pueden cambiar sus productos.")

    instruccion = re.sub(r"(?i)\b(?:en|al|del|de|a)?\s*(?:el\s+)?pedido\s+PED-[0-9A-Za-z]{3,12}", " ", prompt)
    instruccion = re.sub(r"(?i)\bPED-[0-9A-Za-z]{3,12}\b", " ", instruccion)
    instruccion = re.sub(r"\s+", " ", instruccion).strip()

    items = [
        {
            "producto_id": d.producto_id,
            "nombre": d.producto.nombre if d.producto else f"Producto #{d.producto_id}",
            "cantidad": d.cantidad,
            "precio_unitario": float(d.precio_unitario),
            "stock": d.producto.stock_actual if d.producto else None,
        }
        for d in pedido.detalles
    ]
    resultado = responder_edicion(
        db,
        instruccion,
        {
            "tipo": "pedido",
            "mensaje_id": "pedido",
            "descuento_pct": _descuento_pactado(db, pedido.cliente_id),
            "cliente": {"id": pedido.cliente_id},
            "items": items,
        },
    )
    if resultado is None:
        return _texto(
            "No entendí qué cambiar. Dime, por ejemplo: «en el pedido "
            f"{pedido.codigo_pedido} cambia las lejías a 5 y quita las papeleras»."
        )
    datos_edicion = resultado["datos_estructurados"]
    if not datos_edicion["aplicado"]:
        return _texto(resultado["respuesta"])

    nuevos = datos_edicion["items"]
    if not nuevos:
        return _texto("Con ese cambio el pedido quedaría sin productos. Si quieres cancelarlo, dime «cancela el pedido " + pedido.codigo_pedido + "».")

    antes = {i["producto_id"]: i for i in items}
    despues = {i["producto_id"]: i for i in nuevos}
    lineas: List[Dict[str, Any]] = []
    for pid in list(antes) + [p for p in despues if p not in antes]:
        a, d = antes.get(pid), despues.get(pid)
        if a and d and a["cantidad"] == d["cantidad"]:
            continue
        lineas.append(
            {
                "nombre": (d or a)["nombre"],
                "antes": a["cantidad"] if a else 0,
                "despues": d["cantidad"] if d else 0,
            }
        )
    if not lineas:
        return _texto(f"El pedido {pedido.codigo_pedido} ya tiene esas cantidades. No hay nada que cambiar.")
    total_antes = sum(i["cantidad"] * i["precio_unitario"] for i in items)
    total_despues = sum(i["cantidad"] * i["precio_unitario"] for i in nuevos)
    advertencias = []
    if pedido.estado == "Aprobado":
        advertencias.append("El pedido está aprobado: el stock se reajustará con el cambio.")
    datos = {
        "tipo": "accion_pedido_items",
        "pedido_id": pedido.id,
        "codigo": pedido.codigo_pedido,
        "cliente": pedido.cliente.razon_social if pedido.cliente else "Cliente",
        "estado": pedido.estado,
        "lineas": lineas,
        "total_antes": round(total_antes, 2),
        "total_despues": round(total_despues, 2),
        "items_payload": [
            {"producto_id": i["producto_id"], "cantidad": i["cantidad"], "precio_unitario": i["precio_unitario"]} for i in nuevos
        ],
        "advertencias": advertencias,
        "explicacion": _explicacion(
            "Apliqué tu cambio sobre los productos actuales del pedido. Se guarda solo al confirmar; el sistema vuelve a evaluar el pedido contra la cotización y el stock.",
            ["Productos y cantidades actuales del pedido", "Precios vigentes con el descuento pactado del cliente"],
        ),
    }
    return _texto(
        f"Así quedaría el pedido {pedido.codigo_pedido}: total S/ {total_antes:,.2f} → S/ {total_despues:,.2f}. Revísalo y confírmalo aquí abajo.",
        datos,
    )
