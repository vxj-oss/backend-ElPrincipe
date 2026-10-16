import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agent.choices import opciones_de_clientes, respuesta_opciones
from app.agent.quick_answers import PAT_CODIGO
from app.agent.quote_intent import _buscar_cliente_en_texto, _descuento_pactado
from app.core.time import LIMA_TZ
from app.models.commercial_term import CondicionComercial
from app.models.customer import Cliente
from app.models.agent_message import MensajeAgente
from app.services.quote_note_service import candidatos, tokens
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.product import Producto
from app.services import analytics_service as an
from app.services.quote_note_service import normalizar

PREFIJO_PEDIDO_PENDIENTE = "¿De qué cliente o cotización quieres hacer el pedido?"
PREFIJO_ESTADO_PENDIENTE = "¿De qué pedido? Dime el código"
PREFIJO_UNIDADES_PENDIENTE = "¿Cuántas unidades repones de "

PAT_VERBO_PEDIDO = re.compile(
    r"\b(?:haz|hazle|hacer|crea|crear|genera|generar|registra|registrar|prepara|preparar|arma|armar|"
    r"procesa|procesar|convierte|convertir|pasa|pasar|transforma|transformar)(?:me|le|lo|la)?\b[^.\n]{0,40}\bpedido\b"
)
PAT_COTIZACION_FUENTE = re.compile(
    r"\b(?:en|a) pedido\b|\bpedido (?:de|desde|a partir de) (?:la |esa |esta )?cotizacion\b"
    r"|\bde (?:la |esa |esta )?cotizacion\b.*\bpedido\b"
)
PAT_ESTADO = re.compile(
    r"\b(?:marca|marcar|pasa|pasar|cambia|cambiar|actualiza|actualizar|aprueba|aprobar|entrega|entregar|"
    r"cancela|cancelar|anula|anular|confirma|confirmar|despacha|despachar)\b[^.\n]{0,40}\bpedido\b"
)
PAT_DESCARGA = re.compile(r"\b(?:pdf|ticket|comprobante|descarga\w*|imprim\w*|bajar|baja|bajame)\b")
PAT_COTIZACION = re.compile(r"\bcotizacion(?:es)?\b")
PAT_REPONER = re.compile(
    r"\brepon\w*\b"
    r"|\b(?:agrega\w*|suma\w*|sube\w*|aumenta\w*|ingresa\w*|incrementa\w*|anade\w*)\b[^.\n]{0,50}\b(?:stock|inventario|existencias)\b"
    r"|\b(?:ingresaron|llegaron|recibimos|entraron)\b"
)
PAT_PREGUNTA_REPOSICION = re.compile(r"\b(?:que|cuales?|cuanto|cuantos|debo|deberia|conviene)\b")
PAT_CANTIDAD_REPOSICION = [
    re.compile(r"\b(?:con|de|por|ingresaron|llegaron|recibimos|entraron|mas|agrega\w*|suma\w*|repon\w*|sube\w*|aumenta\w*)\s+(\d{1,5})\b(?!\.\d)(?!\s*(?:lt|cm|ml|kg|gr|mm|l|x)\b)"),
    re.compile(r"\b(\d{1,5})\s+(?:unidades|unidad|und|u|piezas|cajas|bolsas)\b"),
]
RUIDO_REPOSICION = {
    "repon", "reponer", "reponga", "reponme", "repone", "reponemos", "stock", "inventario", "existencias", "unidades", "unidad",
    "de", "el", "la", "los", "las", "con", "mas", "agrega", "agregar", "agregale", "suma", "sumale", "sube", "aumenta",
    "ingresa", "ingresar", "ingresaron", "llegaron", "recibimos", "entraron", "por", "favor", "al", "a", "en", "quiero",
    "necesito", "puedes", "piezas", "incrementa", "anade", "anadir", "un", "una", "del", "al", "mi", "nuestro",
}

ESTADOS_PALABRAS: List[Tuple[str, re.Pattern]] = [
    ("Cancelado", re.compile(r"\b(?:cancela|cancelar|cancelado|anula|anular|anulado)\b")),
    ("Entregado", re.compile(r"\b(?:entrega|entregar|entregado|despacha|despachar|despachado)\b")),
    ("Aprobado", re.compile(r"\b(?:aprueba|aprobar|aprobado|confirma|confirmar|confirmado)\b")),
    ("Pendiente", re.compile(r"\bpendiente\b")),
]


def _soles(valor: float) -> str:
    return f"S/ {float(valor or 0):,.2f}"


def _texto(respuesta: str, datos: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"respuesta": respuesta, "datos_estructurados": datos}


def _explicacion(resumen: str, fuentes: List[str], formula: Optional[str] = None) -> Dict[str, Any]:
    return {"resumen": resumen, "fuentes": fuentes, "formula": formula, "periodo": "datos al momento de la consulta"}


def _valor_pactado(condicion: Optional[CondicionComercial]) -> str:
    if not condicion:
        return "Contado"
    if condicion.tipo_condicion == "Credito":
        return f"Credito {condicion.dias_plazo_pactados or 0}d"
    if condicion.tipo_condicion == "Descuento":
        return f"Descuento {int(condicion.porcentaje_descuento or 0)}%"
    if condicion.tipo_condicion == "Forma_Pago":
        return condicion.forma_pago_pactada or "Contado"
    return "Contado"


def _cliente_o_pregunta(db: Session, prompt: str) -> Tuple[Optional[Cliente], Optional[Dict[str, Any]]]:
    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    if cliente is None and dudosos:
        return None, respuesta_opciones(
            "¿A cuál cliente te refieres? Encontré: " + ", ".join(c.razon_social for c in dudosos) + ".",
            opciones_de_clientes(dudosos, prompt),
        )
    return cliente, None


def _solicitud_por_codigo(db: Session, codigo: str) -> Tuple[Optional[SolicitudCliente], Optional[str]]:
    filas = db.scalars(
        select(SolicitudCliente)
        .options(selectinload(SolicitudCliente.cliente), selectinload(SolicitudCliente.detalles))
        .where(SolicitudCliente.codigo_solicitud.ilike(f"{codigo}%"))
        .limit(5)
    ).all()
    if not filas:
        return None, f"No encontré ninguna cotización con el código {codigo}."
    if len(filas) > 1:
        return None, "Hay varias cotizaciones que empiezan así: " + ", ".join(s.codigo_solicitud for s in filas) + ". Escribe el código completo."
    return filas[0], None


def _pedido_por_codigo(db: Session, codigo: str) -> Tuple[Optional[Pedido], Optional[str]]:
    filas = db.scalars(
        select(Pedido)
        .options(selectinload(Pedido.cliente))
        .where(Pedido.codigo_pedido.ilike(f"{codigo}%"))
        .limit(5)
    ).all()
    if not filas:
        return None, f"No encontré ningún pedido con el código {codigo}."
    if len(filas) > 1:
        return None, "Hay varios pedidos que empiezan así: " + ", ".join(p.codigo_pedido for p in filas) + ". Escribe el código completo."
    return filas[0], None


def _es_de_hoy(solicitud: SolicitudCliente) -> bool:
    inicio, fin = an.rango("hoy")
    return bool(solicitud.fecha_solicitud) and inicio <= solicitud.fecha_solicitud < fin


def _crear_pedido(db: Session, prompt: str) -> Dict[str, Any]:
    coincidencia = PAT_CODIGO.search(prompt)
    solicitud: Optional[SolicitudCliente] = None

    if coincidencia and coincidencia.group(1).upper() == "COT":
        solicitud, error = _solicitud_por_codigo(db, f"COT-{coincidencia.group(2).upper()}")
        if error:
            return _texto(error)
    else:
        cliente, pregunta = _cliente_o_pregunta(db, prompt)
        if pregunta:
            return pregunta
        if cliente is None:
            return _texto(
                f"{PREFIJO_PEDIDO_PENDIENTE} Por ejemplo: «hazle el pedido a Lavandería Burbujas» "
                "o «convierte la cotización COT-XXXX en pedido»."
            )
        inicio, fin = an.rango("hoy")
        pendientes = db.scalars(
            select(SolicitudCliente)
            .options(selectinload(SolicitudCliente.cliente), selectinload(SolicitudCliente.detalles))
            .where(
                SolicitudCliente.cliente_id == cliente.id,
                SolicitudCliente.estado == "Pendiente",
                SolicitudCliente.fecha_solicitud >= inicio,
                SolicitudCliente.fecha_solicitud < fin,
            )
            .order_by(SolicitudCliente.fecha_solicitud.desc())
        ).all()
        if not pendientes:
            return _texto(
                f"{cliente.razon_social} no tiene cotizaciones pendientes de hoy. "
                "Primero arma la cotización, por ejemplo: «arma una cotización para "
                f"{cliente.razon_social} con 3 lejías»."
            )
        solicitud = pendientes[0]

    if solicitud.estado != "Pendiente":
        return _texto(f"La cotización {solicitud.codigo_solicitud} ya está {solicitud.estado.lower()}, no se puede convertir en pedido.")
    if not _es_de_hoy(solicitud):
        return _texto(
            f"La cotización {solicitud.codigo_solicitud} no es de hoy. Solo se pueden convertir en pedido las cotizaciones pendientes del día."
        )

    cliente = solicitud.cliente
    descuento = _descuento_pactado(db, solicitud.cliente_id)
    condiciones = db.scalars(
        select(CondicionComercial)
        .where(CondicionComercial.cliente_id == solicitud.cliente_id)
        .order_by(CondicionComercial.id.desc())
    ).all()
    formas = [{"condicion_id": c.id, "valor": _valor_pactado(c)} for c in condiciones] or [
        {"condicion_id": None, "valor": "Contado"}
    ]

    items: List[Dict[str, Any]] = []
    advertencias: List[str] = []
    for det in solicitud.detalles:
        producto = db.get(Producto, det.producto_id) if det.producto_id else None
        if not producto:
            advertencias.append(f"«{det.nombre_producto_solicitado}» no está vinculado al catálogo; corrígelo en la cotización.")
            items.append(
                {
                    "producto_id": None,
                    "nombre": det.nombre_producto_solicitado,
                    "cantidad": det.cantidad_solicitada,
                    "precio_unitario": float(det.precio_esperado or 0),
                    "stock": None,
                }
            )
            continue
        precio = round(float(producto.precio_unitario) * (1 - descuento / 100), 2)
        items.append(
            {
                "producto_id": producto.id,
                "nombre": producto.nombre,
                "cantidad": det.cantidad_solicitada,
                "precio_unitario": precio,
                "stock": producto.stock_actual,
            }
        )

    total = sum(i["cantidad"] * i["precio_unitario"] for i in items)
    texto = (
        f"Armé el pedido de {cliente.razon_social} a partir de la cotización {solicitud.codigo_solicitud}: "
        f"{len(items)} {'producto' if len(items) == 1 else 'productos'}, total {_soles(total)}"
        f"{f' (con {descuento:g} % de descuento pactado)' if descuento else ''}. Revísalo y confírmalo aquí abajo."
    )
    datos = {
        "tipo": "borrador_pedido",
        "solicitud_id": solicitud.id,
        "codigo_solicitud": solicitud.codigo_solicitud,
        "cliente": {"id": cliente.id, "nombre": cliente.razon_social},
        "formas_pago": formas,
        "descuento_pactado_pct": descuento,
        "items": items,
        "advertencias": advertencias,
        "explicacion": _explicacion(
            "Tomé los productos de la cotización y apliqué los precios vigentes del catálogo con el descuento pactado del cliente. Nada se guarda hasta que confirmes.",
            [
                "Cotización pendiente del día",
                "Catálogo de productos: precio y stock actual",
                "Condiciones comerciales pactadas con el cliente",
            ],
            "Precio = precio de lista × (1 − descuento pactado)",
        ),
    }
    return _texto(texto, datos)


def _estado_pedido_nuevo(limpio: str) -> Optional[str]:
    for estado, patron in ESTADOS_PALABRAS:
        if patron.search(limpio):
            return estado
    return None


def _pedido_objetivo(db: Session, prompt: str, estado_nuevo: str) -> Tuple[Optional[Pedido], Optional[Dict[str, Any]]]:
    coincidencia = PAT_CODIGO.search(prompt)
    if coincidencia and coincidencia.group(1).upper() == "PED":
        pedido, mensaje = _pedido_por_codigo(db, f"PED-{coincidencia.group(2).upper()}")
        return pedido, (_texto(mensaje) if mensaje else None)

    cliente, pregunta = _cliente_o_pregunta(db, prompt)
    if pregunta:
        return None, pregunta
    if cliente is None:
        return None, _texto(f"{PREFIJO_ESTADO_PENDIENTE} (por ejemplo PED-AB12CD34) o el nombre del cliente.")
    origen = {"Aprobado": ("Pendiente",), "Entregado": ("Aprobado", "Pendiente"), "Cancelado": ("Pendiente", "Aprobado")}.get(
        estado_nuevo, ("Pendiente", "Aprobado")
    )
    pedido = db.scalars(
        select(Pedido)
        .options(selectinload(Pedido.cliente))
        .where(Pedido.cliente_id == cliente.id, Pedido.estado.in_(origen))
        .order_by(Pedido.fecha_pedido.desc())
        .limit(1)
    ).first()
    if not pedido:
        return None, _texto(f"{cliente.razon_social} no tiene pedidos que se puedan pasar a {estado_nuevo.lower()}.")
    return pedido, None


def _cambiar_estado(db: Session, prompt: str, estado_nuevo: str) -> Dict[str, Any]:
    pedido, error = _pedido_objetivo(db, prompt, estado_nuevo)
    if error:
        return error
    if pedido.estado == estado_nuevo:
        return _texto(f"El pedido {pedido.codigo_pedido} ya está {estado_nuevo.lower()}.")
    if pedido.estado == "Cancelado":
        return _texto(f"El pedido {pedido.codigo_pedido} está cancelado y ya no se puede cambiar.")
    rango = {"Pendiente": 0, "Aprobado": 1, "Entregado": 2}
    if estado_nuevo == "Cancelado" and pedido.estado == "Entregado":
        return _texto(f"El pedido {pedido.codigo_pedido} ya fue entregado, no se puede cancelar desde aquí.")
    if estado_nuevo != "Cancelado" and rango.get(estado_nuevo, 0) < rango.get(pedido.estado, 0):
        return _texto(
            f"El pedido {pedido.codigo_pedido} está {pedido.estado.lower()}; retroceder su estado hazlo desde el módulo de Pedidos."
        )
    cliente = pedido.cliente.razon_social if pedido.cliente else "Cliente general"
    datos = {
        "tipo": "accion_estado",
        "pedido_id": pedido.id,
        "codigo": pedido.codigo_pedido,
        "cliente": cliente,
        "total": float(pedido.monto_total or 0),
        "estado_actual": pedido.estado,
        "estado_nuevo": estado_nuevo,
        "explicacion": _explicacion(
            "Identifiqué el pedido y preparé el cambio de estado. Se aplica solo cuando confirmas; al aprobar se descuenta el stock y al cancelar se devuelve.",
            ["Pedido por código o último pedido del cliente que admite el cambio"],
            None,
        ),
    }
    return _texto(
        f"¿Paso el pedido {pedido.codigo_pedido} de {cliente} ({_soles(pedido.monto_total)}) de {pedido.estado} a {estado_nuevo}? Confírmalo aquí abajo.",
        datos,
    )


def _descargar(db: Session, prompt: str, limpio: str) -> Dict[str, Any]:
    coincidencia = PAT_CODIGO.search(prompt)
    quiere_ticket = bool(re.search(r"\bticket\b", limpio))
    acciones: List[Dict[str, Any]] = []

    if coincidencia and coincidencia.group(1).upper() == "COT":
        solicitud, error = _solicitud_por_codigo(db, f"COT-{coincidencia.group(2).upper()}")
        if error:
            return _texto(error)
        acciones.append({"tipo": "descarga", "etiqueta": "Descargar PDF", "ruta": f"/customer-requests/{solicitud.id}/pdf", "nombre": f"{solicitud.codigo_solicitud}.pdf"})
        codigo = solicitud.codigo_solicitud
    elif coincidencia:
        pedido, error = _pedido_por_codigo(db, f"PED-{coincidencia.group(2).upper()}")
        if error:
            return _texto(error)
        codigo = pedido.codigo_pedido
        pdf = {"tipo": "descarga", "etiqueta": "Descargar PDF", "ruta": f"/orders/{pedido.id}/pdf", "nombre": f"{codigo}.pdf"}
        ticket = {"tipo": "descarga", "etiqueta": "Descargar ticket", "ruta": f"/orders/{pedido.id}/ticket", "nombre": f"{codigo}-ticket.pdf"}
        acciones += [ticket, pdf] if quiere_ticket else [pdf, ticket]
    else:
        cliente, pregunta = _cliente_o_pregunta(db, prompt)
        if pregunta:
            return pregunta
        if cliente is None:
            return _texto("¿De qué documento? Dime el código (por ejemplo PED-AB12CD34 o COT-AB12CD34) o el nombre del cliente.")
        if PAT_COTIZACION.search(limpio):
            solicitud = db.scalars(
                select(SolicitudCliente).where(SolicitudCliente.cliente_id == cliente.id).order_by(SolicitudCliente.fecha_solicitud.desc()).limit(1)
            ).first()
            if not solicitud:
                return _texto(f"{cliente.razon_social} no tiene cotizaciones registradas.")
            codigo = solicitud.codigo_solicitud
            acciones.append({"tipo": "descarga", "etiqueta": "Descargar PDF", "ruta": f"/customer-requests/{solicitud.id}/pdf", "nombre": f"{codigo}.pdf"})
        else:
            pedido = db.scalars(
                select(Pedido).where(Pedido.cliente_id == cliente.id).order_by(Pedido.fecha_pedido.desc()).limit(1)
            ).first()
            if not pedido:
                return _texto(f"{cliente.razon_social} no tiene pedidos registrados.")
            codigo = pedido.codigo_pedido
            pdf = {"tipo": "descarga", "etiqueta": "Descargar PDF", "ruta": f"/orders/{pedido.id}/pdf", "nombre": f"{codigo}.pdf"}
            ticket = {"tipo": "descarga", "etiqueta": "Descargar ticket", "ruta": f"/orders/{pedido.id}/ticket", "nombre": f"{codigo}-ticket.pdf"}
            acciones += [ticket, pdf] if quiere_ticket else [pdf, ticket]

    datos = {
        "tipo": "analisis",
        "acciones": acciones,
        "explicacion": _explicacion(
            "Ubiqué el documento por su código o por el último registro del cliente y preparé la descarga.",
            ["Pedidos y cotizaciones registrados"],
            None,
        ),
    }
    return _texto(f"Listo, aquí tienes los documentos de {codigo}.", datos)


PAT_GRAFICO_REF = re.compile(r"\b(?:grafic[oa]s?|diagrama|ese grafico|esa grafica|la grafica|el grafico)\b")


def _ultimo_grafico(db: Session, session_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    filas = db.scalars(
        select(MensajeAgente.datos_estructurados)
        .where(MensajeAgente.sesion_id == session_id, MensajeAgente.rol_emisor == "assistant")
        .order_by(MensajeAgente.id.desc())
        .limit(12)
    ).all()
    for datos in filas:
        if isinstance(datos, dict) and datos.get("tipo") == "grafico":
            return datos
    return None


def _pdf_grafico(db: Session, session_id: Optional[int]) -> Dict[str, Any]:
    grafico = _ultimo_grafico(db, session_id)
    if not grafico:
        return _texto(
            "Aún no hay ningún gráfico en esta conversación. Pídeme uno, por ejemplo: "
            "«gráfico de ventas de la semana» o «compara las ventas de esta semana con la anterior», y luego te lo paso a PDF."
        )
    datos = {
        "tipo": "analisis",
        "acciones": [{"tipo": "pdf_grafico", "etiqueta": "Descargar PDF del gráfico", "grafico": grafico}],
        "explicacion": _explicacion(
            "Tomé el último gráfico de la conversación y lo convertí en un PDF con la imagen, la tabla de datos y cómo se calculó.",
            ["Último gráfico generado en esta conversación"],
            None,
        ),
    }
    return _texto(f"Listo, aquí tienes el PDF de «{grafico.get('titulo', 'tu gráfico')}».", datos)


def _cantidad_reposicion(limpio: str) -> Optional[int]:
    for patron in PAT_CANTIDAD_REPOSICION:
        coincidencia = patron.search(limpio)
        if coincidencia:
            return int(coincidencia.group(1))
    return None


def _reponer_stock(db: Session, prompt: str, limpio: str, usuario) -> Optional[Dict[str, Any]]:
    cantidad = _cantidad_reposicion(limpio)
    if PAT_PREGUNTA_REPOSICION.search(limpio) and cantidad is None:
        return None

    restantes = [t for t in tokens(prompt) if t not in RUIDO_REPOSICION and not (cantidad is not None and t == str(cantidad))]
    if not restantes:
        return None

    catalogo = [(p.id, p.nombre) for p in db.scalars(select(Producto).where(Producto.activo.is_(True))).all()]
    consulta = " ".join(restantes)
    exactos = [c for c in candidatos(consulta, catalogo) if c[2] >= 1.0]
    objetivo = normalizar(consulta)
    iguales = [c for c in exactos if normalizar(c[1]) == objetivo]
    if iguales:
        exactos = iguales[:1]

    if not exactos:
        return _texto(f"No encontré «{consulta}» en el catálogo para reponer stock.")

    if getattr(usuario, "rol", None) != "administrador":
        return _texto("Solo un administrador puede registrar reposiciones de stock.")

    if len(exactos) > 1:
        sufijo = f" con {cantidad}" if cantidad else ""
        return respuesta_opciones(
            f"Encontré {len(exactos)} productos para «{consulta}». ¿A cuál le repongo stock?",
            [(c[1], f"repon el stock de {c[1]}{sufijo}") for c in sorted(exactos, key=lambda c: c[1])],
        )

    producto = db.get(Producto, exactos[0][0])
    if cantidad is None:
        return _texto(f"{PREFIJO_UNIDADES_PENDIENTE}{producto.nombre}? (hoy tiene {producto.stock_actual or 0} u.)")
    if cantidad > 100000:
        return _texto("Esa cantidad es demasiado grande; confírmala e inténtalo de nuevo.")

    actual = producto.stock_actual or 0
    datos = {
        "tipo": "accion_stock",
        "producto_id": producto.id,
        "nombre": producto.nombre,
        "stock_actual": actual,
        "cantidad": cantidad,
        "stock_nuevo": actual + cantidad,
        "explicacion": _explicacion(
            "Identifiqué el producto y calculé el stock resultante. Se registra como un ingreso en los movimientos de stock solo cuando confirmas.",
            ["Catálogo de productos activos: stock actual", "Movimientos de stock (se agrega una entrada)"],
            "Stock nuevo = stock actual + unidades repuestas",
        ),
    }
    return _texto(
        f"¿Registro la entrada de {cantidad} u. de {producto.nombre}? El stock pasaría de {actual} a {actual + cantidad}. Confírmalo aquí abajo.",
        datos,
    )


def responder_accion(
    db: Session, prompt: str, session_id: Optional[int] = None, usuario=None
) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    tiene_codigo = bool(PAT_CODIGO.search(prompt))
    estado_nuevo = _estado_pedido_nuevo(limpio)

    if PAT_REPONER.search(limpio) and not tiene_codigo:
        repuesto = _reponer_stock(db, prompt, limpio, usuario)
        if repuesto:
            return repuesto

    if (
        PAT_DESCARGA.search(limpio)
        and PAT_GRAFICO_REF.search(limpio)
        and not tiene_codigo
        and not re.search(r"\b(?:pedido|cotizacion)\b", limpio)
    ):
        return _pdf_grafico(db, session_id)

    if PAT_DESCARGA.search(limpio) and (tiene_codigo or "pedido" in limpio or PAT_COTIZACION.search(limpio)):
        if not re.search(r"\b(?:arma|armar|crea|crear|haz|hacer)\b", limpio):
            return _descargar(db, prompt, limpio)

    if estado_nuevo and PAT_ESTADO.search(limpio) and not PAT_COTIZACION_FUENTE.search(limpio):
        codigo_ped = PAT_CODIGO.search(prompt)
        if PAT_COTIZACION.search(limpio) and not (codigo_ped and codigo_ped.group(1).upper() == "PED"):
            return None
        return _cambiar_estado(db, prompt, estado_nuevo)

    if PAT_VERBO_PEDIDO.search(limpio):
        habla_de_cotizacion = bool(PAT_COTIZACION.search(limpio))
        codigo = PAT_CODIGO.search(prompt)
        tiene_cot = bool(codigo and codigo.group(1).upper() == "COT")
        if not habla_de_cotizacion or tiene_cot or PAT_COTIZACION_FUENTE.search(limpio):
            return _crear_pedido(db, prompt)
    return None
