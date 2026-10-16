import re
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.agent.choices import opciones_de_clientes, respuesta_opciones
from app.agent.tools import CommercialTools
from app.core.time import LIMA_TZ, ahora_lima
from app.models.customer import Cliente
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.agent.quote_intent import _buscar_cliente_en_texto
from app.services import analytics_service as an
from app.services.config_service import ConfigService
from app.services.customer_profile_service import obtener_ficha
from app.services.profit_service import productos_mas_vendidos, rango_periodo, resumen_rentabilidad
from app.services.quote_note_service import candidatos, normalizar, tokens

PAT_CRITICO = re.compile(
    r"\bstock (?:critico|bajo|minimo)\b"
    r"|\bproductos? (?:criticos?|por agotarse|agotandose|sin stock|con poco stock|con bajo stock)\b"
    r"|\bque (?:productos? )?(?:se )?(?:estan )?(?:acabando|agotando)\b"
    r"|\bpor agotarse\b"
)
PAT_PENDIENTES = re.compile(
    r"\bpedidos? (?:pendientes?|por confirmar|sin confirmar)\b|\bpendientes? (?:de )?confirmar\b"
)
PAT_COMPRARON_HOY = re.compile(
    r"\bclientes? que compraron hoy\b|\bque clientes? (?:compraron|compro) hoy\b"
    r"|\bquien(?:es)? (?:compro|compraron) hoy\b|\bcompraron hoy\b"
)
PAT_INDICADORES = re.compile(
    r"\bcomo vamos\b|\bindicadores?\b|\bsemaforo\b"
    r"|\bcuantas cotizaciones (?:llevo|llevamos|hay|hicimos|hubo|tenemos|atendimos)\b"
    r"|\bcuantos pedidos (?:llevo|llevamos|hay|hicimos|hubo|tenemos|procesamos)\b"
    r"|\btiempo (?:promedio )?de (?:toma de )?decision\b|\bncca\b|\bnpp\b|\btptd\b"
)
PAT_LEGADO = re.compile(r"\b(?:nepp|pfcc|ntdc)\b")
PAT_SALUDO = re.compile(r"^(?:hola|holi|holaa+|buenas|buenos dias|buenas tardes|buenas noches|hey|que tal)(?: [a-z]+){0,3}$")
PAT_GRACIAS = re.compile(r"^(?:muchas |mil )?gracias(?: [a-z]+){0,3}$|^ok(?:ey)?$|^listo$|^perfecto$|^vale$")
PAT_AYUDA = re.compile(
    r"\bque (?:puedes|sabes|haces)\b|\bayuda\b|\bcomandos?\b|\bque (?:puedo )?(?:preguntarte|pedirte|preguntar)\b"
    r"|\bcomo (?:te )?(?:uso|funcionas)\b|\bpara que sirves\b"
)
PAT_CODIGO = re.compile(r"\b(PED|COT)-([0-9A-Za-z]{3,12})\b", re.IGNORECASE)
PAT_EXPLICAR = re.compile(
    r"\bexplic\w*\b|\bcomo (?:se )?(?:calcula|calcular|mide|medir|funciona)\b|\bque (?:es|significa|son)\b"
    r"|\bformula\b|\bdefinicion\b|\bpor que\b|\bpara que\b"
)
PAT_CLIENTE = re.compile(
    r"\bcuanto\b.*\b(?:compro|comprado|gastado|gastó|gasto)\b|\bcompras? de(?:l)?\b|\bultima compra\b"
    r"|\bcuando (?:fue )?(?:la )?(?:ultima vez )?(?:que )?compro\b|\bque (?:lleva|compra|productos lleva)\b"
    r"|\bsuele (?:llevar|comprar)\b|\bcotizaciones? pendientes? (?:de|del)\b|\btelefono\b|\bcelular\b"
    r"|\bcontacto\b|\bcorreo\b|\bficha\b|\bresumen (?:del? )?cliente\b|\bhistorial de compras\b"
    r"|\bticket promedio\b|\bcondicion(?:es)? (?:comercial(?:es)?|pactadas?) (?:de|del)\b"
    r"|\b(?:detalles?|informacion|datos|perfil|ficha) (?:del? |sobre |de la )?(?:el )?cliente\b"
    r"|\b(?:dime|cuentame|hablame|dame) (?:de|sobre|del) (?:el )?cliente\b"
)
PAT_META = re.compile(r"\bavance\b.*\bmeta\b|\bmeta (?:diaria|comercial|de ventas)\b|\bcuanto (?:me )?falta\b.*\bmeta\b")
PAT_MARGEN = re.compile(r"\bmargen(?:es)?\b|\brentabilidad\b|\bganancias?\b|\butilidad(?:es)?\b")
PAT_TOP = re.compile(
    r"\bmas vendid[oa]s?\b|\bmayor rotacion\b|\bmas rotacion\b|\brotacion\b"
    r"|\bproductos? (?:que )?mas se vend\w*\b|\btop (?:de )?productos\b"
)
PAT_VENTAS = re.compile(
    r"\bcuanto\b.*\b(?:vend\w+|factur\w+)\b|\bventas?\b.*\b(?:hoy|semana|mes|dia)\b"
    r"|\b(?:hoy|semana|mes)\b.*\bventas?\b|\bresumen de ventas\b|\bventas totales\b"
)
PAT_PRODUCTO = re.compile(
    r"\b(?:stock|precio|precios|cuesta|cuestan|vale|valen|tenemos|tienen|tienes|queda|quedan|disponible|disponibles)\b"
    r"|\bcuanto hay\b|\bhay\b"
)
PAT_PRODUCTO_FUERTE = re.compile(
    r"\b(?:stock|precio|precios|cuesta|cuestan|vale|valen|disponible|disponibles|queda|quedan|cuanto hay|unidades)\b"
)
PAT_OTROS = re.compile(
    r"\b(?:cliente|clientes|pedido|pedidos|cotizacion|cotizaciones|venta|ventas|vendi|vendimos|margen|"
    r"rotacion|promedio|compar\w+|historial|movimiento|movimientos|usuario|usuarios)\b"
)

PALABRAS_PREGUNTA = {
    "stock", "precio", "precios", "cuanto", "cuanta", "cuantos", "cuantas", "cuesta", "cuestan",
    "vale", "valen", "hay", "tenemos", "tienen", "tienes", "tiene", "queda", "quedan", "disponible",
    "disponibles", "unidades", "unidad", "cual", "cuales", "que", "dame", "dime", "favor", "me",
    "puedes", "saber", "hoy", "ahora", "costo", "aun", "todavia", "actual", "actualmente",
    "muestrame", "muestra", "ensename", "mostrar", "ver", "quiero", "necesito", "veme", "abre", "llevame",
    "producto", "productos", "tendremos", "tengo", "algun", "alguna", "existe", "existen", "unos", "unas",
}

MAX_LINEAS = 8
MAX_DIRECTO = 3
MAX_PEDIDOS = 10
MAX_PRODUCTOS_CRITICOS = 10


def _rango_hoy():
    hoy = ahora_lima().date()
    inicio = datetime.combine(hoy, time(0, 0), tzinfo=LIMA_TZ)
    return inicio, inicio + timedelta(days=1)


def _soles(valor) -> str:
    return f"S/ {float(valor or 0):,.2f}"


def _stock_critico(db: Session) -> str:
    base = select(Producto).where(Producto.activo.is_(True), Producto.stock_actual <= Producto.stock_minimo)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    if not total:
        return "Ningún producto está en stock crítico por ahora."
    productos = db.scalars(base.order_by(Producto.stock_actual.asc()).limit(MAX_PRODUCTOS_CRITICOS)).all()
    lineas = [
        f"Hay {total} {'producto' if total == 1 else 'productos'} en stock crítico"
        + (f" (los {len(productos)} más bajos):" if total > len(productos) else ":")
    ]
    lineas += [
        f"• {p.nombre} — stock {p.stock_actual} (mínimo {p.stock_minimo})" for p in productos
    ]
    return "\n".join(lineas)


def _pedidos_pendientes(db: Session) -> str:
    total = db.scalar(select(func.count(Pedido.id)).where(Pedido.estado == "Pendiente")) or 0
    if not total:
        return "No hay pedidos pendientes de confirmar."
    pedidos = db.scalars(
        select(Pedido)
        .options(selectinload(Pedido.cliente))
        .where(Pedido.estado == "Pendiente")
        .order_by(Pedido.id.desc())
        .limit(MAX_PEDIDOS)
    ).all()
    lineas = [
        f"Hay {total} {'pedido pendiente' if total == 1 else 'pedidos pendientes'} de confirmar"
        + (f" (los {len(pedidos)} más recientes):" if total > len(pedidos) else ":")
    ]
    for p in pedidos:
        cliente = p.cliente.razon_social if p.cliente else "Cliente general"
        fecha = p.fecha_pedido.astimezone(LIMA_TZ).strftime("%d/%m/%Y") if p.fecha_pedido else "—"
        lineas.append(f"• {p.codigo_pedido} — {cliente} — {_soles(p.monto_total)} — {fecha}")
    return "\n".join(lineas)


def _clientes_hoy(db: Session) -> str:
    inicio, fin = _rango_hoy()
    filas = db.execute(
        select(Cliente.razon_social, func.count(Pedido.id), func.sum(Pedido.monto_total))
        .join(Cliente, Cliente.id == Pedido.cliente_id)
        .where(
            Pedido.fecha_pedido >= inicio,
            Pedido.fecha_pedido < fin,
            Pedido.estado != "Cancelado",
        )
        .group_by(Cliente.razon_social)
        .order_by(func.sum(Pedido.monto_total).desc())
    ).all()
    if not filas:
        return "Hoy aún no hay compras registradas."
    lineas = [f"Hoy compraron {len(filas)} {'cliente' if len(filas) == 1 else 'clientes'}:"]
    for nombre, cantidad, monto in filas[:MAX_PEDIDOS]:
        lineas.append(
            f"• {nombre} — {cantidad} {'pedido' if cantidad == 1 else 'pedidos'} — {_soles(monto)}"
        )
    return "\n".join(lineas)


def _indicadores(db: Session) -> str:
    datos = CommercialTools.get_indicadores_actividad(db)
    ncca, npp, tptd = datos["NCCA"], datos["NPP"], datos["TPTD"]
    lineas = [
        f"Así vamos hoy ({datos['dia_actual']}):",
        f"• Cotizaciones atendidas (NCCA): {ncca['valor_hoy']} — semáforo {ncca['color_semaforo']} "
        f"(meta: {ncca['meta']}). Ayer: {ncca['valor_dia_anterior']}.",
        f"• Pedidos procesados (NPP): {npp['valor_hoy']} — semáforo {npp['color_semaforo']} "
        f"(meta: {npp['meta']}). Ayer: {npp['valor_dia_anterior']}.",
    ]
    if tptd["valor_hoy_segundos"] is None:
        historico = tptd["promedio_historico_segundos"]
        extra = f" El promedio histórico es {historico} s." if historico is not None else ""
        lineas.append(f"• Tiempo promedio de decisión (TPTD): aún sin pedidos aprobados hoy.{extra}")
    else:
        lineas.append(
            f"• Tiempo promedio de decisión (TPTD): {tptd['valor_hoy_segundos']} s — semáforo "
            f"{tptd['color_semaforo']} (meta: {tptd['meta']}), con {tptd['pedidos_considerados_hoy']} pedidos."
        )
    previos = datos["ultimos_dias"][:-1][-3:]
    if previos:
        lineas.append("Días anteriores:")
        for d in previos:
            tiempo = f"{d['tiempo_promedio_decision_segundos']} s" if d["tiempo_promedio_decision_segundos"] is not None else "sin tiempo"
            lineas.append(f"  {d['fecha']}: {d['cotizaciones']} cotizaciones, {d['pedidos']} pedidos, {tiempo}")
    return "\n".join(lineas)


def _periodo_en_texto(limpio: str) -> Optional[str]:
    if re.search(r"\bhoy\b", limpio):
        return "hoy"
    if re.search(r"\bsemana\b", limpio):
        return "semana"
    if re.search(r"\bmes\b", limpio):
        return "mes"
    return None


ETIQUETAS_PERIODO = {"hoy": "Hoy", "semana": "Esta semana", "mes": "Este mes"}


def _ventas(db: Session, limpio: str) -> str:
    periodos = [_periodo_en_texto(limpio)] if _periodo_en_texto(limpio) else ["hoy", "semana", "mes"]
    lineas = ["Ventas confirmadas (pedidos aprobados y entregados):"]
    for periodo in periodos:
        datos = resumen_rentabilidad(db, *rango_periodo(periodo))
        lineas.append(
            f"• {ETIQUETAS_PERIODO[periodo]}: {_soles(datos['ventas'])} en "
            f"{datos['pedidos']} {'pedido' if datos['pedidos'] == 1 else 'pedidos'}"
        )
    return "\n".join(lineas)


def _margen(db: Session, limpio: str, usuario=None) -> str:
    if usuario is not None and getattr(usuario, 'rol', None) != 'administrador':
        return 'El margen y los costos solo están disponibles para administradores.'
    periodos = [_periodo_en_texto(limpio)] if _periodo_en_texto(limpio) else ["hoy", "semana", "mes"]
    lineas = ["Margen = ventas confirmadas − costo de los productos vendidos:"]
    for periodo in periodos:
        datos = resumen_rentabilidad(db, *rango_periodo(periodo))
        if datos["ventas"] == 0:
            lineas.append(f"• {ETIQUETAS_PERIODO[periodo]}: sin ventas.")
        else:
            lineas.append(
                f"• {ETIQUETAS_PERIODO[periodo]}: {_soles(datos['margen'])} "
                f"({datos['margen_pct']:.1f} % de {_soles(datos['ventas'])})"
            )
    lineas.append("Se calcula con el costo actual registrado de cada producto.")
    return "\n".join(lineas)


def _mas_vendidos(db: Session, limpio: str) -> str:
    periodo = _periodo_en_texto(limpio) or "mes"
    filas = productos_mas_vendidos(db, *rango_periodo(periodo))
    if not filas:
        return f"No hay ventas confirmadas para {ETIQUETAS_PERIODO[periodo].lower()}."
    lineas = [f"Productos más vendidos — {ETIQUETAS_PERIODO[periodo].lower()}:"]
    for posicion, (nombre, unidades, ventas) in enumerate(filas, start=1):
        lineas.append(f"{posicion}. {nombre} — {int(unidades)} u. ({_soles(ventas)})")
    return "\n".join(lineas)


def _avance_meta(db: Session) -> str:
    meta = float(ConfigService.get(db).meta_diaria_ventas)
    ventas = resumen_rentabilidad(db, *rango_periodo("hoy"))["ventas"]
    porcentaje = ventas / meta * 100 if meta else 0
    faltante = max(0.0, meta - ventas)
    texto = f"Hoy llevas {_soles(ventas)} de la meta diaria de {_soles(meta)} ({porcentaje:.0f} %)."
    if faltante:
        texto += f" Te faltan {_soles(faltante)}."
    else:
        texto += " Ya cumpliste la meta del día."
    return texto


def _ayuda() -> str:
    return "\n".join(
        [
            "Esto es lo que puedo hacer por ti:",
            "• Indicadores: «¿cómo vamos hoy?», «gráfico del TPTD de los últimos 7 días», «¿cómo mejoro el NPP?»",
            "• Ventas y meta: «ventas del mes», «margen de la semana», «avance de meta»",
            "• Gráficos: «gráfico de ventas del 1 al 10 de octubre», «productos más vendidos de septiembre en gráfico», «mejores clientes del mes», «compara este mes con el mes pasado»",
            "• Productos: «stock de papeleras», «productos más vendidos del mes», «stock crítico»",
            "• Clientes: «¿cuánto ha comprado Burbujas?», «¿qué lleva Hotel Rosas?», «teléfono de Juan», «¿a quién debo llamar hoy?»",
            "• Pedidos y cotizaciones: «pedidos pendientes», «estado del pedido PED-XXXX», «detalle de COT-XXXX»",
            "• Clientes y cotizaciones: «cambia el teléfono de Hotel Rosas a 987654321», «desactiva al cliente Pamela», «elimina la cotización COT-XXXX»",
            "• Pedidos: «en el pedido PED-XXXX cambia las lejías a 5 y quita las papeleras»",
            "• Reportes: «reporte de pedidos del mes en Excel», «inventario en PDF», «el cierre del día», «lista de reposición», «TPTD por día»",
            "• Productos (administrador): «crea el producto Jabón líquido 1 lt, precio 12, costo 8, categoría Limpieza», «cámbiale el precio a la lejía a 13», «súbele el costo a las escobas en 10 %», «elimina el producto escoba de paja», «reactiva el producto …»",
            "• Condiciones comerciales: «ponle a Hotel Rosas un descuento del 10 %», «dale crédito de 15 días a Pamela», «quítale el descuento a Maria»",
            "• Clientes nuevos: «crea el cliente Lavandería El Sol, RUC 20123456789, teléfono 987654321, mayorista»",
            "• Cotizar: «arma una cotización para … con 3 lejías» o «hazle a … lo mismo que la última vez»",
            "• Predicción: «pronóstico de ventas de la próxima semana», «¿cómo cerraré el mes?», «pronóstico de la escoba»",
            "• Simulador: «¿qué pasa si subo 5 % el precio de la lejía?», «¿y si le doy 10 % de descuento a Hotel Rosas?»",
            "• Venta cruzada: «¿qué suelen comprar con la lejía?», «¿qué le puedo ofrecer a Hotel Rosas?»",
            "• Informe e inusuales: «informe semanal» (con PDF), «¿hay algo raro en mis ventas?»",
            "• Cualquier otra pregunta sobre tus datos: la analizo directamente en la base de datos (solo lectura), por ejemplo «¿qué día de la semana vendemos más?»",
            "Tip: escribe «/» para ver todos los comandos.",
        ]
    )


def _saludo(usuario) -> str:
    nombre = (getattr(usuario, "nombre_completo", "") or "").split()
    base = f"¡Hola, {nombre[0]}!" if nombre else "¡Hola!"
    return f"{base} Soy tu asistente comercial. Pregúntame por ventas, stock, clientes o pedidos, o escribe «/» para ver los comandos."


def _fecha(iso: Optional[str]) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def _hace(dias: Optional[int]) -> str:
    if dias is None:
        return "sin compras"
    if dias == 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    return f"hace {dias} días"


def _cliente(db: Session, prompt: str, limpio: str) -> Optional[str]:
    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    if cliente is None and dudosos:
        return "¿A cuál cliente te refieres? Encontré: " + ", ".join(c.razon_social for c in dudosos) + "."
    if cliente is None:
        return None

    ficha = obtener_ficha(db, cliente.id)
    resumen = ficha["resumen"]
    nombre = cliente.razon_social

    if re.search(r"\b(?:telefono|celular|contacto|correo)\b", limpio):
        datos = []
        if cliente.telefono:
            datos.append(f"Teléfono: {cliente.telefono}")
        if cliente.correo:
            datos.append(f"Correo: {cliente.correo}")
        if cliente.direccion:
            datos.append(f"Dirección: {cliente.direccion}")
        if not datos:
            return f"{nombre} no tiene teléfono, correo ni dirección registrados."
        return f"{nombre}\n" + "\n".join(f"• {d}" for d in datos)

    if re.search(r"\bultima compra\b|\bcuando (?:fue )?(?:la )?(?:ultima vez )?(?:que )?compro\b", limpio):
        if not ficha["ultimos_pedidos"] or resumen["ultima_compra"] is None:
            return f"{nombre} aún no tiene compras registradas."
        ultimo = ficha["ultimos_pedidos"][0]
        return (
            f"La última compra de {nombre} fue el {_fecha(resumen['ultima_compra'])} "
            f"({_hace(resumen['dias_sin_comprar'])}): {ultimo['codigo']} por {_soles(ultimo['total'])}."
        )

    if re.search(r"\bque (?:lleva|compra|productos lleva)\b|\bsuele (?:llevar|comprar)\b", limpio):
        if not ficha["productos_frecuentes"]:
            return f"{nombre} aún no tiene compras registradas."
        lineas = [f"Lo que más lleva {nombre}:"]
        lineas += [f"• {p['nombre']} — {p['unidades']} u." for p in ficha["productos_frecuentes"]]
        return "\n".join(lineas)

    if re.search(r"\bcotizaciones? pendientes?\b", limpio):
        pendientes = ficha["cotizaciones_pendientes"]
        if not pendientes["items"]:
            return f"{nombre} no tiene cotizaciones pendientes."
        lineas = [f"Cotizaciones pendientes de {nombre} ({pendientes['total']}):"]
        lineas += [
            f"• {c['codigo']} — {_fecha(c['fecha'])} — {c['items']} {'ítem' if c['items'] == 1 else 'ítems'}"
            for c in pendientes["items"]
        ]
        return "\n".join(lineas)

    lineas = [
        f"{nombre}:",
        f"• Total comprado: {_soles(resumen['total_comprado'])} en {resumen['pedidos']} "
        f"{'pedido' if resumen['pedidos'] == 1 else 'pedidos'} (ticket promedio {_soles(resumen['ticket_promedio'])}).",
        f"• Última compra: {_hace(resumen['dias_sin_comprar'])}"
        + (f" ({_fecha(resumen['ultima_compra'])})." if resumen["ultima_compra"] else "."),
    ]
    if ficha["condiciones"]:
        lineas.append("• Condición pactada: " + ", ".join(ficha["condiciones"]) + ".")
    if ficha["productos_frecuentes"]:
        lineas.append("• Lleva más: " + ", ".join(p["nombre"] for p in ficha["productos_frecuentes"][:3]) + ".")
    pendientes = ficha["cotizaciones_pendientes"]["total"]
    if pendientes:
        lineas.append(f"• Cotizaciones pendientes: {pendientes}.")
    if cliente.telefono:
        lineas.append(f"• Teléfono: {cliente.telefono}.")
    return "\n".join(lineas)


def _detalle_codigo(db: Session, prompt: str) -> Optional[str]:
    coincidencia = PAT_CODIGO.search(prompt)
    if not coincidencia:
        return None
    tipo = coincidencia.group(1).upper()
    codigo = f"{tipo}-{coincidencia.group(2).upper()}"

    if tipo == "PED":
        pedidos = db.scalars(
            select(Pedido)
            .options(selectinload(Pedido.cliente), selectinload(Pedido.detalles).selectinload(DetallePedido.producto))
            .where(Pedido.codigo_pedido.ilike(f"{codigo}%"))
            .limit(5)
        ).all()
        if not pedidos:
            return f"No encontré ningún pedido con el código {codigo}."
        if len(pedidos) > 1:
            return "Hay varios pedidos que empiezan así: " + ", ".join(p.codigo_pedido for p in pedidos) + ". Escribe el código completo."
        p = pedidos[0]
        fecha = p.fecha_pedido.astimezone(LIMA_TZ).strftime("%d/%m/%Y") if p.fecha_pedido else "—"
        lineas = [
            f"Pedido {p.codigo_pedido} — {p.estado}",
            f"Cliente: {p.cliente.razon_social if p.cliente else 'Cliente general'} · Fecha: {fecha} · Pago: {p.forma_pago}",
        ]
        lineas += [
            f"• {d.cantidad} × {d.producto.nombre if d.producto else 'Producto'} — {_soles(d.subtotal)}"
            for d in p.detalles
        ]
        lineas.append(f"Total: {_soles(p.monto_total)}")
        if p.resultado_auditoria:
            lineas.append(f"Auditoría IA: {p.resultado_auditoria.replace('_', ' ')}" + (f" — {p.descripcion_auditoria}" if p.descripcion_auditoria and p.descripcion_auditoria != "Conforme." else ""))
        return "\n".join(lineas)

    solicitudes = db.scalars(
        select(SolicitudCliente)
        .options(selectinload(SolicitudCliente.cliente), selectinload(SolicitudCliente.detalles))
        .where(SolicitudCliente.codigo_solicitud.ilike(f"{codigo}%"))
        .limit(5)
    ).all()
    if not solicitudes:
        return f"No encontré ninguna cotización con el código {codigo}."
    if len(solicitudes) > 1:
        return "Hay varias cotizaciones que empiezan así: " + ", ".join(s.codigo_solicitud for s in solicitudes) + ". Escribe el código completo."
    s = solicitudes[0]
    fecha = s.fecha_solicitud.astimezone(LIMA_TZ).strftime("%d/%m/%Y %H:%M")
    lineas = [
        f"Cotización {s.codigo_solicitud} — {s.estado}",
        f"Cliente: {s.cliente.razon_social if s.cliente else f'#{s.cliente_id}'} · Canal: {s.canal_recepcion} · Fecha: {fecha}",
    ]
    for d in s.detalles:
        precio = f" ({_soles(d.precio_esperado)} c/u)" if d.precio_esperado is not None else ""
        lineas.append(f"• {d.cantidad_solicitada} × {d.nombre_producto_solicitado}{precio}")
    if s.resultado_auditoria:
        lineas.append(f"Auditoría IA: {s.resultado_auditoria.replace('_', ' ')}" + (f" — {s.descripcion_auditoria}" if s.descripcion_auditoria and s.descripcion_auditoria != "Conforme." else ""))
    return "\n".join(lineas)


def _consulta_producto(limpio: str, prompt: str) -> Optional[str]:
    if not PAT_PRODUCTO.search(limpio) or PAT_OTROS.search(limpio):
        return None
    restantes = [t for t in tokens(prompt) if t not in PALABRAS_PREGUNTA]
    if not restantes or len(restantes) > 5 or len(tokens(prompt)) > 12:
        return None
    return " ".join(restantes)


def _stock_precio(db: Session, consulta: str, estricto: bool = True) -> Tuple[Optional[str], Optional[List[Tuple[str, str]]]]:
    productos = list(db.scalars(select(Producto).where(Producto.activo.is_(True))).all())
    por_id = {p.id: p for p in productos}
    lista = candidatos(consulta, [(p.id, p.nombre) for p in productos])
    exactos = [c for c in lista if c[2] >= 1.0]

    if not exactos:
        if not lista and not estricto:
            return None, None
        if lista:
            parecidos = ", ".join(c[1] for c in lista[:3])
            return f"No encontré «{consulta}» en el catálogo. ¿Quizás buscas: {parecidos}?", None
        return f"No encontré productos que coincidan con «{consulta}».", None

    ordenados = sorted((por_id[c[0]] for c in exactos), key=lambda p: p.nombre)
    objetivo = normalizar(consulta)
    iguales = [p for p in ordenados if normalizar(p.nombre) == objetivo]
    if iguales:
        ordenados = iguales[:1]

    if len(ordenados) > MAX_DIRECTO:
        opciones = [(p.nombre, f"stock de {p.nombre}") for p in ordenados[:MAX_LINEAS]]
        extra = f" Te muestro los {MAX_LINEAS} primeros." if len(ordenados) > MAX_LINEAS else ""
        return f"Encontré {len(ordenados)} productos para «{consulta}». ¿Cuál te interesa?{extra}", opciones

    lineas = [
        f"Encontré {len(ordenados)} {'producto' if len(ordenados) == 1 else 'productos'} para «{consulta}»:"
    ]
    for p in ordenados:
        aviso = f" (bajo el mínimo de {p.stock_minimo})" if (p.stock_actual or 0) <= (p.stock_minimo or 0) else ""
        lineas.append(f"• {p.nombre} — {_soles(p.precio_unitario)} — stock {p.stock_actual or 0}{aviso}")
    return "\n".join(lineas), None


def _resp(texto: str, resumen: Optional[str] = None, fuentes: Optional[List[str]] = None, formula: Optional[str] = None, periodo: Optional[str] = None) -> Dict[str, Any]:
    datos = None
    if resumen:
        datos = {
            "tipo": "texto",
            "explicacion": {"resumen": resumen, "fuentes": fuentes or [], "formula": formula, "periodo": periodo},
        }
    return {"respuesta": texto, "datos_estructurados": datos}


def _periodo_texto(limpio: str) -> str:
    periodo = _periodo_en_texto(limpio)
    if periodo:
        return an.texto_rango(periodo)
    return f"hoy ({an.texto_rango('hoy')}), semana ({an.texto_rango('semana')}) y mes ({an.texto_rango('mes')})"


def responder_rapido(db: Session, prompt: str, usuario=None) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    if PAT_SALUDO.match(limpio):
        return _resp(_saludo(usuario))
    if PAT_GRACIAS.match(limpio):
        return _resp("¡Con gusto! Si necesitas algo más, aquí estoy.")
    if PAT_AYUDA.search(limpio):
        return _resp(_ayuda())
    detalle = _detalle_codigo(db, prompt)
    if detalle:
        return _resp(
            detalle,
            "Busqué el código exacto en los pedidos o cotizaciones registrados.",
            ["Tabla de pedidos o de cotizaciones de clientes", "Detalle de productos del documento"],
            None,
            None,
        )
    if PAT_EXPLICAR.search(limpio):
        return None
    if PAT_CRITICO.search(limpio):
        return _resp(
            _stock_critico(db),
            "Listé los productos activos cuyo stock actual llegó al mínimo definido.",
            ["Catálogo de productos activos"],
            "Stock crítico = stock actual ≤ stock mínimo",
            "stock al momento de la consulta",
        )
    if PAT_PENDIENTES.search(limpio):
        return _resp(
            _pedidos_pendientes(db),
            "Listé los pedidos que todavía no se confirmaron.",
            ["Pedidos con estado Pendiente"],
            None,
            "todos los pendientes",
        )
    if PAT_COMPRARON_HOY.search(limpio):
        return _resp(
            _clientes_hoy(db),
            "Agrupé por cliente los pedidos de hoy que no fueron cancelados.",
            ["Pedidos del día en hora de Lima, excepto cancelados"],
            "Total del cliente = Σ monto_total de sus pedidos de hoy",
            an.texto_rango("hoy"),
        )
    if PAT_INDICADORES.search(limpio) and not PAT_LEGADO.search(limpio):
        respuesta_indicadores = _resp(
            _indicadores(db),
            "Mostré los tres indicadores de la tesis con su semáforo según las metas configuradas.",
            [
                "NCCA: cotizaciones atendidas en el día",
                "NPP: pedidos procesados en el día",
                "TPTD: tiempo entre abrir el pedido y aprobarlo",
            ],
            "TPTD = Σ (hora de aprobación − hora de apertura) ÷ pedidos aprobados",
            an.texto_rango("hoy"),
        )
        respuesta_indicadores["datos_estructurados"]["tipo"] = "analisis"
        respuesta_indicadores["datos_estructurados"]["acciones"] = [
            {"tipo": "pregunta", "etiqueta": "¿Cómo mejoro los indicadores?", "texto": "¿Cómo mejoro los indicadores?"},
            {"tipo": "pregunta", "etiqueta": "Ver gráfico", "texto": "gráfico de los indicadores de los últimos 7 días"},
        ]
        return respuesta_indicadores
    if PAT_META.search(limpio):
        return _resp(
            _avance_meta(db),
            "Comparé las ventas confirmadas de hoy con la meta diaria configurada.",
            ["Pedidos Aprobados o Entregados de hoy", "Meta diaria en Configuración"],
            "Avance = ventas de hoy ÷ meta diaria × 100",
            an.texto_rango("hoy"),
        )
    if PAT_MARGEN.search(limpio):
        texto = _margen(db, limpio, usuario)
        if texto.startswith("El margen y los costos solo"):
            return _resp(texto)
        return _resp(
            texto,
            "Resté el costo de los productos vendidos a las ventas confirmadas.",
            ["Detalle de pedidos Aprobados o Entregados", "Costo registrado de cada producto"],
            "Margen = Σ subtotal − Σ (costo del producto × cantidad)",
            _periodo_texto(limpio),
        )
    if PAT_TOP.search(limpio):
        return _resp(
            _mas_vendidos(db, limpio),
            "Ordené los productos por unidades vendidas en pedidos confirmados.",
            ["Detalle de pedidos Aprobados o Entregados"],
            "Ranking por Σ cantidad vendida",
            an.texto_rango(_periodo_en_texto(limpio) or "mes"),
        )
    if PAT_VENTAS.search(limpio):
        return _resp(
            _ventas(db, limpio),
            "Sumé los pedidos confirmados de cada periodo.",
            ["Detalle de pedidos Aprobados o Entregados"],
            "Ventas = Σ subtotal de los pedidos confirmados",
            _periodo_texto(limpio),
        )
    if PAT_CLIENTE.search(limpio):
        cliente_unico, dudosos = _buscar_cliente_en_texto(db, prompt)
        if cliente_unico is None and dudosos:
            return respuesta_opciones(
                "¿A cuál cliente te refieres? Encontré: " + ", ".join(c.razon_social for c in dudosos) + ".",
                opciones_de_clientes(dudosos, prompt),
            )
        respuesta_cliente = _cliente(db, prompt, limpio)
        if respuesta_cliente:
            return _resp(
                respuesta_cliente,
                "Armé la ficha del cliente con su historial de pedidos y cotizaciones.",
                ["Pedidos no cancelados del cliente", "Cotizaciones pendientes", "Datos de contacto registrados"],
                "Ticket promedio = total comprado ÷ número de pedidos",
                "historial completo",
            )
    consulta = _consulta_producto(limpio, prompt)
    if consulta:
        texto_stock, opciones_stock = _stock_precio(db, consulta, bool(PAT_PRODUCTO_FUERTE.search(limpio)))
        if texto_stock is None:
            return None
        if opciones_stock:
            return respuesta_opciones(texto_stock, opciones_stock)
        return _resp(
            texto_stock,
            "Busqué el nombre en el catálogo activo, tolerando plurales y errores de tipeo.",
            ["Catálogo de productos activos: precio y stock actual"],
            None,
            "stock al momento de la consulta",
        )
    return None
