import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, aliased

from app.agent import forecast as fc
from app.agent.analysis_answers import _explicacion, _grafico, _resolver_producto
from app.agent.anomalies import detectar_anomalias
from app.agent.dashboard_reading import (
    _punto_indicadores,
    _punto_recompra,
    _punto_por_aprobar,
    _punto_por_convertir,
    _punto_stock,
    _punto_ventas,
)
from app.agent.quote_intent import _buscar_cliente_en_texto
from app.core.time import ahora_lima
from app.models.customer import Cliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.services import analytics_service as an
from app.services.profit_service import ESTADOS_CONFIRMADOS
from app.services.quote_note_service import normalizar, tokens

PAT_INFORME = re.compile(
    r"\b(?:informe|reporte|resumen|balance|cierre|analisis)\s+semanal\b"
    r"|\b(?:informe|reporte|resumen|balance|analisis)\s+de\s+(?:la|esta)\s+semana\b"
    r"|\bcomo (?:me )?(?:fue|va|ha ido|estuvo) (?:la|esta) semana\b|\binforme narrado\b"
)
PAT_INFORME_OTRO = re.compile(
    r"\bexcel\b|\bxlsx\b|\binventario\b|\berrores\b|\bplanilla\b"
    r"|\b(?:reporte|informe) de (?:pedidos|clientes|productos|indicadores)\b"
)
PAT_ANOMALIAS = re.compile(
    r"\banomal\w+|\balgo (?:raro|extrano|inusual|sospechoso)\b|\binusual\w*|\batipic\w*|\bsospechos\w*"
    r"|\bdetecta\w* (?:errores|problemas|irregularidades)\b|\birregularidad\w*|\bcosas raras\b|\bpedidos? (?:raros?|extranos?)\b"
)
PAT_SIMULAR = re.compile(
    r"\bsimul\w+|\bque (?:pasa|pasaria|ocurre|ocurriria|sucede|sucederia|pasara) si\b"
    r"|\b(?:y|que tal|pero) si (?:le |les |me )?(?:subo|aumento|incremento|elevo|bajo|reduzco|rebajo|disminuyo|doy|hago|ofrezco|pongo|aplico|descuento|regalo)\b"
    r"|^si (?:le |les )?(?:subo|aumento|incremento|elevo|bajo|reduzco|rebajo|disminuyo|doy|hago|ofrezco|pongo|aplico)\b"
)
PAT_VENTA_CRUZADA = re.compile(
    r"\bventa cruzada\b|\bque (?:suelen|suele|sueles|acostumbran) (?:comprar|llevar|pedir)\b"
    r"|\b(?:que|cual\w*) (?:productos? )?(?:le )?(?:puedo|podria|debo|deberia) (?:ofrecer|venderle|sugerir|ofrecerle)\b"
    r"|\bque (?:mas )?(?:le )?(?:ofrezco|vendo)\b|\bcomplement\w+\b|\bque (?:se )?(?:lleva|llevan|compra|compran) (?:junto|con|ademas)\b"
    r"|\bque combina con\b|\boportunidades? de venta\b|\bque (?:mas )?(?:podria|puedo) (?:ofrecerle|ofrecer|venderle)\b"
)
PAT_PRONOSTICO = re.compile(
    r"\bpronostic\w*|\bproyecc\w*|\bproyectad\w*|\bprediccion\w*|\bpredecir\b|\bprevision de ventas\b"
    r"|\bcuanto (?:voy a|vamos a|podria|podre|podremos|se va a|va a) vend\w+|\bcuanto vendere\b|\bcuanto venderemos\b"
    r"|\bventas (?:esperadas|estimadas|futuras)\b|\bcierre (?:estimado )?del mes\b|\bcomo cerrare el mes\b"
    r"|\bcomo cerrar\w* (?:el )?mes\b|\bestimacion de ventas\b|\bdemanda (?:esperada|futura|proyectada)\b"
)
PAT_PORCENTAJE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por\s?ciento|porciento)")
PAT_NUMERO_SUELTO = re.compile(
    r"\b(?:subo|aumento|incremento|elevo|bajo|reduzco|rebajo|disminuyo|descuento|doy|hago|ofrezco|aplico)\b(?:\s+\w+){0,4}?\s+(\d+(?:[.,]\d+)?)"
)
PAT_SUBIR = re.compile(r"\b(?:subo|aumento|incremento|elevo|subir|aumentar|incrementar|alza|alzo)\b")
PAT_DESCUENTO = re.compile(r"\bdescuent\w*|\brebaj\w*|\bregalo\b|\bbonific\w*|\bdoy\b")
PAT_HORIZONTE_DIAS = re.compile(r"\b(\d{1,2})\s+dias\b")
PAT_FIN_MES = re.compile(r"\b(?:fin de mes|cierre|cerrare|cerrar\w*|resto del mes|este mes|el mes)\b")
RUIDO = {
    "si", "subo", "aumento", "incremento", "elevo", "bajo", "reduzco", "rebajo", "disminuyo", "doy", "hago", "ofrezco",
    "pongo", "aplico", "descuento", "descuentos", "precio", "precios", "ciento", "por", "porciento", "que", "pasa",
    "pasaria", "ocurre", "sucede", "simula", "simular", "simulame", "simulacion", "cliente", "producto", "productos",
    "ventas", "venta", "vender", "venderia", "vendere", "margen", "pronostico", "pronosticar", "proyeccion", "proyectar",
    "proximo", "proxima", "proximos", "proximas", "dias", "dia", "semana", "semanas", "mes", "cuanto", "voy", "vamos",
    "estimado", "estimacion", "demanda", "esperada", "prediccion", "del", "de", "la", "el", "los", "las", "para", "un",
    "una", "al", "con", "unidades", "unidad", "y", "le", "les", "pero", "tal", "mas", "menos", "a", "en", "se", "va",
    "podria", "podre", "ventas", "cuales", "cual", "suelen", "suele", "comprar", "llevar", "pedir", "junto", "ofrecer",
    "ofrecerle", "venderle", "puedo", "debo", "deberia", "complementa", "complementan", "complementos", "combina",
    "oportunidades", "oportunidad", "lleva", "llevan", "compra", "compran", "ademas", "sugerir", "venta", "cruzada",
    "regalo", "bonifico", "rebaja", "pasaria", "hoy", "ayer", "este", "esta",
}


def _soles(valor: float) -> str:
    return f"S/ {valor:,.2f}"


def _delta(valor: float) -> str:
    return f"{'+' if valor >= 0 else '−'}S/ {abs(valor):,.2f}"


def _pl(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _resultado(texto: str, datos: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {"respuesta": texto, "datos_estructurados": datos}


def _productos_activos(db: Session) -> List[Tuple[int, str]]:
    return [(p.id, p.nombre) for p in db.scalars(select(Producto).where(Producto.activo.is_(True))).all()]


def _extraer_producto(db: Session, limpio: str) -> Optional[Tuple[List[int], str]]:
    restos = [t for t in tokens(limpio) if t not in RUIDO and not t.replace(".", "").isdigit()]
    if not restos:
        return None
    catalogo = _productos_activos(db)
    completo = _resolver_producto(catalogo, " ".join(restos))
    if completo:
        return completo
    for palabra in sorted(set(restos), key=len, reverse=True):
        if len(palabra) < 4:
            continue
        encontrado = _resolver_producto(catalogo, palabra)
        if encontrado:
            return encontrado
    return None


def _horizonte(limpio: str) -> Tuple[int, bool]:
    if re.search(r"\bquincena\b", limpio):
        return 15, False
    dias = PAT_HORIZONTE_DIAS.search(limpio)
    if dias:
        return max(1, min(int(dias.group(1)), 31)), False
    if PAT_FIN_MES.search(limpio) and not re.search(r"\bsemana\b", limpio):
        return 0, True
    return 7, False


def _etiqueta_dia(dia, largo: bool) -> str:
    return f"{an.DIAS_SEMANA[dia.weekday()]} {dia.day}" if largo else dia.strftime("%d/%m")


def _pronostico_general(db: Session, limpio: str) -> Dict[str, Any]:
    dias, fin_de_mes = _horizonte(limpio)
    p = fc.proyectar_ventas(db, dias, fin_de_mes)
    if not p["futuro"]:
        return _resultado("El mes ya terminó; no quedan días por proyectar.", None)
    futuro = p["futuro"]
    historia = p["historia"][-7:]
    etiquetas = [_etiqueta_dia(d, len(futuro) <= 10) for d, _ in historia] + [_etiqueta_dia(d, len(futuro) <= 10) for d, _ in futuro]
    reales = [round(v, 2) for _, v in historia] + [None] * len(futuro)
    esperados = [None] * len(historia) + [v for _, v in futuro]
    inicio, fin = futuro[0][0], futuro[-1][0]
    rango = f"{inicio.strftime('%d/%m')} al {fin.strftime('%d/%m')}"
    cuando = "lo que resta del mes" if fin_de_mes else f"los próximos {p['horizonte']} días"

    lineas = [f"Pronóstico de ventas para {cuando} ({rango}):"]
    lineas.append(f"• Esperado: {_soles(p['total'])} (rango razonable: {_soles(p['bajo'])} a {_soles(p['alto'])}).")
    if p["comparable"] and 0.2 <= p["total"] / p["comparable"] <= 5:
        cambio = (p["total"] - p["comparable"]) / p["comparable"] * 100
        lineas.append(f"• Frente a los {p['horizonte']} días anteriores ({_soles(p['comparable'])}): {cambio:+.0f} %.")
    mejor = max(futuro, key=lambda f: f[1])
    if mejor[1] > 0:
        lineas.append(f"• Mejor día esperado: {an.DIAS_SEMANA[mejor[0].weekday()]} {mejor[0].strftime('%d/%m')} con {_soles(mejor[1])}.")
    if p["meta_diaria"]:
        diferencia = p["promedio_diario"] - p["meta_diaria"]
        estado = "por encima de" if diferencia >= 0 else "por debajo de"
        lineas.append(
            f"• Promedio diario esperado {_soles(p['promedio_diario'])}, {estado} tu meta de {_soles(p['meta_diaria'])}"
            + (f" (faltarían {_soles(-diferencia)} por día)." if diferencia < 0 else ".")
        )
    if fin_de_mes:
        llevado = fc.ventas_del_mes_hasta_hoy(db)
        lineas.append(f"• Llevas {_soles(llevado)} este mes; con el pronóstico cerrarías cerca de {_soles(llevado + p['total'])}.")

    acciones: List[Dict[str, Any]] = []
    if p["frenado"]:
        lineas.append(
            f"• Ojo: tus ventas de los últimos 7 días están muy por debajo del ritmo de las últimas 4 semanas. "
            f"Si todo sigue igual que esta semana, serían unos {_soles(p['si_sigue_igual'])}; el pronóstico supone que recuperas parte del ritmo anterior."
        )
        lineas.append("Sugerencia: reactiva primero a los clientes que ya les toca comprar y da seguimiento a las cotizaciones pendientes.")
        acciones.append({"tipo": "pregunta", "etiqueta": "Ver clientes por recomprar", "texto": "¿A quién le toca comprar?"})
        acciones.append({"tipo": "pregunta", "etiqueta": "Plan del día", "texto": "¿Qué me recomiendas hacer hoy?"})
    elif p["tendencia"] <= -0.1:
        lineas.append("Sugerencia: la tendencia reciente es a la baja; conviene contactar a los clientes que ya les toca comprar y revisar el stock de lo más vendido.")
        acciones.append({"tipo": "pregunta", "etiqueta": "Ver clientes por recomprar", "texto": "¿A quién le toca comprar?"})
    elif p["meta_diaria"] and p["promedio_diario"] < p["meta_diaria"]:
        lineas.append("Sugerencia: a este ritmo no llegarías a la meta diaria; apóyate en las cotizaciones pendientes y en los clientes por recomprar.")
        acciones.append({"tipo": "pregunta", "etiqueta": "Plan del día", "texto": "¿Qué me recomiendas hacer hoy?"})
    else:
        lineas.append("Sugerencia: el ritmo es sano; asegúrate de tener stock de los productos de mayor rotación.")
        acciones.append({"tipo": "pregunta", "etiqueta": "¿Qué debo reponer?", "texto": "¿Qué debo reponer?"})
    if p["pocos_datos"]:
        lineas.append(f"Ojo: solo hay {p['dias_activos']} días con ventas en los últimos {fc.DIAS_HISTORIA}; tómalo como referencia.")

    grafico = _grafico(
        "bar",
        f"Pronóstico de ventas — {cuando}",
        etiquetas,
        [{"nombre": "Ventas reales", "valores": reales}, {"nombre": "Pronóstico", "valores": esperados}],
        _explicacion(
            "Estimé el ritmo diario con las ventas de las últimas 4 semanas, ajusté por la tendencia reciente y por el día de la semana (qué días vendes más).",
            [
                f"Pedidos Aprobados o Entregados de los últimos {fc.DIAS_HISTORIA} días",
                "Meta diaria configurada",
            ],
            "Pronóstico del día = ritmo de 28 días × (1 + tendencia/2) × factor del día de la semana",
            f"{rango} (proyección)",
        ),
    )
    datos = dict(grafico)
    datos["acciones"] = acciones
    return _resultado("\n".join(lineas), datos)


def _pronostico_producto(db: Session, ids: List[int], nombre: str, limpio: str) -> Dict[str, Any]:
    dias, _ = _horizonte(limpio)
    dias = dias or 7
    d = fc.demanda_producto(db, ids)
    if d["unidades_30d"] <= 0:
        return _resultado(
            f"{nombre} no registra ventas en los últimos {fc.DIAS_DEMANDA_PRODUCTO} días, así que no tengo base para proyectar su demanda. Stock actual: {d['stock']} u.",
            None,
        )
    esperado = d["ritmo_diario"] * dias
    ultimos = sum(d["serie"][-dias:]) if dias <= len(d["serie"]) else d["unidades_30d"]
    cobertura = d["stock"] / d["ritmo_diario"] if d["ritmo_diario"] else None
    lineas = [f"Demanda de {nombre} para los próximos {dias} días:"]
    lineas.append(f"• Estimado: {esperado:.0f} u. (ritmo de {d['ritmo_diario']:.1f} u. por día, según los últimos {fc.DIAS_DEMANDA_PRODUCTO} días).")
    lineas.append(f"• Stock actual: {d['stock']} u.; alcanza para unos {cobertura:.0f} días.")
    acciones: List[Dict[str, Any]] = []
    if d["stock"] < esperado:
        faltante = int(round(esperado * 1.15 - d["stock"]))
        lineas.append(f"Sugerencia: el stock no cubre la demanda esperada; conviene pedir al menos {max(faltante, 1)} u.")
        if len(ids) == 1:
            acciones.append({"tipo": "pregunta", "etiqueta": "Reponer", "texto": f"repon el stock de {nombre}"})
    else:
        lineas.append("Sugerencia: el stock cubre la demanda esperada; no necesitas reponer todavía.")
    grafico = _grafico(
        "bar",
        f"Demanda de {nombre}",
        [f"Vendidas (últimos {dias} días)", f"Estimadas (próximos {dias} días)", "Stock actual"],
        [{"nombre": "Unidades", "valores": [round(ultimos, 1), round(esperado, 1), d["stock"]]}],
        _explicacion(
            "Proyecté la demanda con el ritmo de ventas de los últimos 30 días y la comparé con el stock actual.",
            ["Detalle de pedidos Aprobados o Entregados", "Stock actual del producto"],
            "Demanda esperada = unidades vendidas en 30 días ÷ 30 × días proyectados",
            f"últimos {fc.DIAS_DEMANDA_PRODUCTO} días",
        ),
        prefijo="",
        horizontal=True,
    )
    datos = dict(grafico)
    datos["acciones"] = acciones
    return _resultado("\n".join(lineas), datos)


def _responder_pronostico(db: Session, prompt: str, limpio: str) -> Dict[str, Any]:
    producto = _extraer_producto(db, limpio)
    if producto:
        return _pronostico_producto(db, producto[0], producto[1], limpio)
    return _pronostico_general(db, limpio)


def _porcentaje(prompt: str, limpio: str) -> Optional[float]:
    m = PAT_PORCENTAJE.search(prompt.lower()) or PAT_NUMERO_SUELTO.search(limpio)
    if not m:
        return None
    valor = float(m.group(1).replace(",", "."))
    return valor if 0 < valor < 100 else None


def _ventas_producto_ventana(db: Session, ids: List[int], dias: int) -> Tuple[float, float, float]:
    hoy = ahora_lima().date()
    desde, hasta = an.rango(f"{an.PREFIJO_RANGO}{(hoy - timedelta(days=dias - 1)).isoformat()}:{hoy.isoformat()}")
    filas = db.execute(
        select(DetallePedido.cantidad, DetallePedido.subtotal, Producto.precio_costo)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .join(Producto, Producto.id == DetallePedido.producto_id)
        .where(
            DetallePedido.producto_id.in_(ids),
            Pedido.estado.in_(ESTADOS_CONFIRMADOS),
            Pedido.fecha_pedido >= desde,
            Pedido.fecha_pedido < hasta,
        )
    ).all()
    unidades = sum(float(c) for c, _, _ in filas)
    ingreso = sum(float(s) for _, s, _ in filas)
    costo = sum(float(c) * float(k) for c, _, k in filas)
    return unidades, ingreso, costo


def _simular_producto(db: Session, ids: List[int], nombre: str, pct: float, subir: bool) -> Dict[str, Any]:
    ventana = 30
    unidades, ingreso, costo = _ventas_producto_ventana(db, ids, ventana)
    if unidades <= 0:
        ventana = 90
        unidades, ingreso, costo = _ventas_producto_ventana(db, ids, ventana)
    if unidades <= 0:
        return _resultado(f"{nombre} no tiene ventas en los últimos 90 días, así que no puedo estimar el efecto de cambiar su precio.", None)

    escala = 30 / ventana
    precio = ingreso / unidades
    costo_u = costo / unidades
    delta = pct / 100 * (1 if subir else -1)
    nuevo_precio = precio * (1 + delta)
    margen_u, margen_nuevo_u = precio - costo_u, nuevo_precio - costo_u
    actual = unidades * margen_u * escala

    escenarios = [("Sin perder clientes", 0.0), ("Esperado", -1.0), ("Sensible", -2.0)]
    resultados: List[Tuple[str, float, float]] = []
    for etiqueta, elasticidad in escenarios:
        q = max(0.0, unidades * (1 + elasticidad * delta))
        resultados.append((etiqueta, q * escala, q * margen_nuevo_u * escala))

    verbo = "subes" if subir else "bajas"
    lineas = [f"Si {verbo} {pct:g} % el precio de {nombre} (de {_soles(precio)} a {_soles(nuevo_precio)}), esto es lo que estimo para 30 días:"]
    lineas.append(f"• Hoy: {_soles(actual)} de margen con unas {unidades * escala:.0f} u. vendidas.")
    for etiqueta, q, margen in resultados:
        lineas.append(f"• {etiqueta}: {q:.0f} u. → {_soles(margen)} de margen ({_delta(margen - actual)} frente a hoy).")
    esperado = resultados[1][2]

    if margen_nuevo_u <= 0:
        lineas.append("Sugerencia: con ese precio ya no cubres el costo del producto; no lo recomiendo.")
    elif subir and margen_nuevo_u > margen_u:
        tolerable = (1 - margen_u / margen_nuevo_u) * 100
        lineas.append(
            f"Sugerencia: {'conviene probarlo' if esperado >= actual else 'ten cuidado'}; ganarías lo mismo aunque pierdas hasta {tolerable:.0f} % de las unidades. "
            "Pruébalo primero con unos clientes."
        )
    elif not subir:
        necesario = (margen_u / margen_nuevo_u - 1) * 100
        lineas.append(
            f"Sugerencia: para no perder margen tendrías que vender {necesario:.0f} % más unidades; "
            f"{'solo vale la pena si buscas rotar stock o ganar clientes' if necesario > 20 else 'es un esfuerzo razonable'}."
        )
    lineas.append("Es una estimación: supone que por cada 1 % de cambio de precio la demanda se mueve 1 % (esperado) o 2 % (sensible).")

    grafico = _grafico(
        "bar",
        f"Margen estimado a 30 días — {nombre}",
        ["Hoy"] + [e for e, _, _ in resultados],
        [{"nombre": "Margen", "valores": [round(actual, 2)] + [round(m, 2) for _, _, m in resultados]}],
        _explicacion(
            f"Tomé lo vendido en los últimos {ventana} días y recalculé el margen con el precio nuevo bajo tres supuestos de reacción de los clientes.",
            ["Detalle de pedidos Aprobados o Entregados", "Costo actual del producto"],
            "Margen = unidades × (precio − costo); unidades nuevas = unidades × (1 + elasticidad × cambio de precio)",
            f"últimos {ventana} días",
        ),
    )
    datos = dict(grafico)
    if len(ids) == 1:
        datos["acciones"] = [{
            "tipo": "pregunta",
            "etiqueta": "Aplicar el cambio de precio",
            "texto": f"{'súbele' if subir else 'bájale'} el precio a {nombre} en {pct:g} %",
        }]
    return _resultado("\n".join(lineas), datos)


def _simular_descuento_cliente(db: Session, cliente: Cliente, pct: float) -> Dict[str, Any]:
    dias = 90
    hoy = ahora_lima().date()
    desde, hasta = an.rango(f"{an.PREFIJO_RANGO}{(hoy - timedelta(days=dias - 1)).isoformat()}:{hoy.isoformat()}")
    filas = db.execute(
        select(DetallePedido.cantidad, DetallePedido.subtotal, Producto.precio_costo, Pedido.id)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .join(Producto, Producto.id == DetallePedido.producto_id)
        .where(
            Pedido.cliente_id == cliente.id,
            Pedido.estado.in_(ESTADOS_CONFIRMADOS),
            Pedido.fecha_pedido >= desde,
            Pedido.fecha_pedido < hasta,
        )
    ).all()
    if not filas:
        return _resultado(f"{cliente.razon_social} no tiene compras confirmadas en los últimos {dias} días, no puedo estimar el efecto de un descuento.", None)
    ingreso = sum(float(s) for _, s, _, _ in filas)
    costo = sum(float(c) * float(k) for c, _, k, _ in filas)
    pedidos = len({p for _, _, _, p in filas})
    margen = ingreso - costo
    d = pct / 100
    margen_nuevo = ingreso * (1 - d) - costo

    lineas = [f"Si le das {pct:g} % de descuento a {cliente.razon_social} (últimos {dias} días: {_pl(pedidos, 'pedido', 'pedidos')}, {_soles(ingreso)} vendidos):"]
    lineas.append(f"• Margen hoy con este cliente: {_soles(margen)}.")
    lineas.append(f"• Con el descuento y el mismo volumen: {_soles(margen_nuevo)} ({_delta(margen_nuevo - margen)}).")
    acciones = [{"tipo": "pregunta", "etiqueta": f"Aplicar {pct:g} % de descuento", "texto": f"ponle a {cliente.razon_social} un descuento del {pct:g} %"}]
    if margen_nuevo <= 0:
        lineas.append("Sugerencia: con ese descuento este cliente dejaría de dejarte margen; no lo recomiendo.")
        acciones = []
    else:
        necesario = (margen / margen_nuevo - 1) * 100
        extra = ingreso * (1 + necesario / 100)
        lineas.append(f"• Para no perder margen tendría que comprar {necesario:.0f} % más (unos {_soles(extra)} en {dias} días).")
        lineas.append(
            "Sugerencia: "
            + (
                "ofrécelo condicionado a un volumen mínimo; el esfuerzo que le pides es alto."
                if necesario > 25
                else "es un descuento razonable si se compromete a comprar más."
            )
        )
    grafico = _grafico(
        "bar",
        f"Margen con {cliente.razon_social} — {dias} días",
        ["Hoy", f"Con {pct:g} % de descuento"],
        [{"nombre": "Margen", "valores": [round(margen, 2), round(margen_nuevo, 2)]}],
        _explicacion(
            "Recalculé el margen de las compras de este cliente restando el descuento al precio y manteniendo el costo.",
            ["Detalle de pedidos Aprobados o Entregados del cliente", "Costo actual de los productos"],
            "Margen = ventas × (1 − descuento) − costo",
            f"últimos {dias} días",
        ),
    )
    datos = dict(grafico)
    datos["acciones"] = acciones
    return _resultado("\n".join(lineas), datos)


def _responder_simulacion(db: Session, prompt: str, limpio: str) -> Dict[str, Any]:
    pct = _porcentaje(prompt, limpio)
    if pct is None:
        return _resultado("¿De cuánto porcentaje quieres la simulación? Por ejemplo: «¿qué pasa si subo 5 % el precio de la lejía?» o «¿y si le doy 10 % de descuento a Hotel Rosas?».", None)
    subir = bool(PAT_SUBIR.search(limpio))
    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    producto = _extraer_producto(db, limpio)
    if PAT_DESCUENTO.search(limpio) and cliente is not None and not subir:
        return _simular_descuento_cliente(db, cliente, pct)
    if producto:
        return _simular_producto(db, producto[0], producto[1], pct, subir)
    if cliente is not None and not subir:
        return _simular_descuento_cliente(db, cliente, pct)
    if dudosos:
        return _resultado("Hay varios clientes que coinciden; dime el nombre completo para simular el descuento.", None)
    return _resultado("¿Sobre qué producto o cliente quieres simularlo? Por ejemplo: «¿qué pasa si subo 5 % el precio de la lejía?» o «¿y si le doy 10 % de descuento a Hotel Rosas?».", None)


def _combinaciones_producto(db: Session, ids: List[int]) -> Tuple[int, List[Tuple[int, int]]]:
    base = db.scalar(
        select(func.count(distinct(DetallePedido.pedido_id)))
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(DetallePedido.producto_id.in_(ids), Pedido.estado != "Cancelado")
    ) or 0
    a = aliased(DetallePedido)
    b = aliased(DetallePedido)
    filas = db.execute(
        select(b.producto_id, func.count(distinct(b.pedido_id)).label("veces"))
        .join(a, a.pedido_id == b.pedido_id)
        .join(Pedido, Pedido.id == b.pedido_id)
        .where(a.producto_id.in_(ids), b.producto_id.notin_(ids), Pedido.estado != "Cancelado")
        .group_by(b.producto_id)
        .order_by(func.count(distinct(b.pedido_id)).desc())
        .limit(12)
    ).all()
    return int(base), [(int(pid), int(v)) for pid, v in filas]


def _fila_producto(db: Session, producto_id: int, detalle_extra: str, consulta: str) -> Optional[Dict[str, Any]]:
    producto = db.get(Producto, producto_id)
    if not producto or not producto.activo or (producto.stock_actual or 0) <= 0:
        return None
    return {
        "titulo": producto.nombre,
        "detalle": f"{detalle_extra} · {_soles(float(producto.precio_unitario))} · stock {producto.stock_actual}",
        "consulta": consulta.replace("{producto}", producto.nombre),
    }


def _venta_cruzada_producto(db: Session, ids: List[int], nombre: str, cliente: Optional[Cliente]) -> Dict[str, Any]:
    base, pares = _combinaciones_producto(db, ids)
    if not base:
        return _resultado(f"{nombre} aún no aparece en pedidos, así que no tengo combinaciones que sugerir.", None)
    filas: List[Dict[str, Any]] = []
    para = f" para {cliente.razon_social}" if cliente else ""
    for producto_id, veces in pares:
        fila = _fila_producto(
            db,
            producto_id,
            f"Va en {veces} de {base} pedidos ({veces / base * 100:.0f} %)",
            f"Arma una cotización{para} con 1 {{producto}}" if cliente else "Arma una cotización con 1 {producto}",
        )
        if fila:
            filas.append(fila)
        if len(filas) == 4:
            break
    if not filas:
        return _resultado(f"Los pedidos con {nombre} no traen otros productos con stock para sugerir.", None)
    texto = (
        f"Quienes compran {nombre} suelen llevar también esto (según {_pl(base, 'pedido', 'pedidos')} anteriores). "
        "Ofrécelo al cotizar:"
    )
    datos = {
        "tipo": "analisis",
        "filas": filas,
        "explicacion": _explicacion(
            "Conté en cuántos pedidos aparece cada producto junto con el que consultas.",
            ["Detalle de pedidos no cancelados", "Stock y precio actual del catálogo"],
            "Porcentaje = pedidos con ambos productos ÷ pedidos con el producto consultado",
            "todo el historial de pedidos",
        ),
    }
    return _resultado(texto, datos)


def _venta_cruzada_cliente(db: Session, cliente: Cliente) -> Dict[str, Any]:
    propios = [
        pid
        for (pid,) in db.execute(
            select(distinct(DetallePedido.producto_id))
            .join(Pedido, Pedido.id == DetallePedido.pedido_id)
            .where(Pedido.cliente_id == cliente.id, Pedido.estado != "Cancelado")
        ).all()
    ]
    if not propios:
        return _resultado(f"{cliente.razon_social} todavía no tiene compras; sin historial no puedo sugerir qué ofrecerle.", None)
    a = aliased(DetallePedido)
    b = aliased(DetallePedido)
    pa = aliased(Pedido)
    pb = aliased(Pedido)
    filas_db = db.execute(
        select(b.producto_id, func.count(distinct(pb.cliente_id)).label("clientes"))
        .join(pb, pb.id == b.pedido_id)
        .join(pa, pa.cliente_id == pb.cliente_id)
        .join(a, a.pedido_id == pa.id)
        .where(
            a.producto_id.in_(propios),
            b.producto_id.notin_(propios),
            pb.cliente_id != cliente.id,
            pa.estado != "Cancelado",
            pb.estado != "Cancelado",
        )
        .group_by(b.producto_id)
        .order_by(func.count(distinct(pb.cliente_id)).desc())
        .limit(12)
    ).all()
    filas: List[Dict[str, Any]] = []
    for producto_id, clientes in filas_db:
        fila = _fila_producto(
            db,
            int(producto_id),
            f"Lo compran {_pl(int(clientes), 'cliente', 'clientes')} con compras parecidas",
            f"Arma una cotización para {cliente.razon_social} con 1 {{producto}}",
        )
        if fila:
            filas.append(fila)
        if len(filas) == 4:
            break
    if not filas:
        return _resultado(f"{cliente.razon_social} ya compra casi todo lo que compran clientes parecidos; no veo oportunidades nuevas.", None)
    datos = {
        "tipo": "analisis",
        "filas": filas,
        "explicacion": _explicacion(
            "Busqué clientes que compran los mismos productos que este cliente y miré qué otros productos llevan que él aún no compra.",
            ["Detalle de pedidos no cancelados de todos los clientes", "Stock y precio actual del catálogo"],
            None,
            "todo el historial de pedidos",
        ),
    }
    return _resultado(f"Oportunidades para {cliente.razon_social}: productos que compran clientes parecidos y que él aún no lleva.", datos)


def _responder_venta_cruzada(db: Session, prompt: str, limpio: str) -> Dict[str, Any]:
    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    producto = _extraer_producto(db, limpio)
    if producto:
        return _venta_cruzada_producto(db, producto[0], producto[1], cliente)
    if cliente is not None:
        return _venta_cruzada_cliente(db, cliente)
    if dudosos:
        return _resultado("Hay varios clientes que coinciden; dime el nombre completo.", None)
    return _resultado("¿Con qué producto o para qué cliente? Por ejemplo: «¿qué suelen comprar con la lejía?» o «¿qué le puedo ofrecer a Hotel Rosas?».", None)


def _responder_anomalias(db: Session) -> Dict[str, Any]:
    hallazgos = detectar_anomalias(db)
    explicacion = _explicacion(
        "Comparé los últimos 14 días contra el comportamiento habitual de los 90 días anteriores: montos de pedidos, precios contra el catálogo y cantidades.",
        ["Pedidos y su detalle", "Precios del catálogo"],
        "Un dato es inusual si se aleja mucho de lo habitual (montos: más de 2.5 desviaciones o 3 veces la mediana; precios: ±30 % del catálogo; cantidades: 5 veces lo normal)",
        "últimos 14 días",
    )
    if not hallazgos:
        return _resultado(
            "Todo en orden: en los últimos 14 días los montos, precios y cantidades de tus pedidos están dentro de lo habitual.",
            {"tipo": "texto", "explicacion": explicacion},
        )
    lineas = [f"Conviene verificar {_pl(len(hallazgos), 'dato', 'datos')} de tus pedidos:"]
    acciones: List[Dict[str, Any]] = []
    vistas = set()
    for h in hallazgos:
        lineas.append(f"• {h['titulo']}. {h['detalle']}")
        accion = h.get("accion")
        if accion and (accion["etiqueta"], accion["texto"]) not in vistas:
            vistas.add((accion["etiqueta"], accion["texto"]))
            acciones.append(accion)
    lineas.append("Sugerencia: confirma que se digitaron bien; si hubo un error, corrígelo desde el pedido.")
    return _resultado("\n".join(lineas), {"tipo": "analisis", "acciones": acciones[:4], "explicacion": explicacion})


def _informe_semanal(db: Session) -> Dict[str, Any]:
    ventas = _punto_ventas(db, "semana", "esta semana")
    total = an.total_periodo(db, "semana")
    secciones: List[Dict[str, Any]] = []
    lineas: List[str] = []

    if ventas:
        resultado = [ventas["texto"], f"Hubo {_pl(total['pedidos'], 'pedido confirmado', 'pedidos confirmados')}, ticket promedio {_soles(total['ticket'])} y {_pl(total['cotizaciones'], 'cotización', 'cotizaciones')} emitidas."]
    else:
        resultado = ["Todavía no hay ventas confirmadas esta semana ni la anterior para comparar."]
    secciones.append({"titulo": "Resultado de la semana", "lineas": resultado})
    lineas.append("Resultado de la semana")
    lineas += [f"• {r}" for r in resultado]

    if ventas and ventas["detalle"]:
        causas = [d["texto"] for d in ventas["detalle"]]
        secciones.append({"titulo": "Qué lo explica", "lineas": causas})
        lineas.append("Qué lo explica")
        lineas += [f"• {c}" for c in causas]

    top_p = sorted(an.top_productos(db, "semana"), key=lambda f: -f[2])[:1]
    top_c = an.top_clientes(db, "semana", 1)
    destacados = []
    if top_p:
        destacados.append(f"Producto estrella: {top_p[0][0]} con {_soles(top_p[0][2])} ({top_p[0][1]:.0f} u.).")
    if top_c:
        destacados.append(f"Mejor cliente: {top_c[0][0]} con {_soles(top_c[0][2])} en {_pl(top_c[0][1], 'pedido', 'pedidos')}.")
    if destacados:
        secciones.append({"titulo": "Lo que destaca", "lineas": destacados})
        lineas.append("Lo que destaca")
        lineas += [f"• {d}" for d in destacados]

    atencion: List[str] = []
    sugerencias: List[str] = []
    for generador in (_punto_indicadores, _punto_stock, _punto_por_aprobar, _punto_por_convertir, _punto_recompra):
        punto = generador(db)
        if not punto:
            continue
        if punto["nivel"] in ("alta", "media"):
            atencion.append(punto["texto"])
        if punto["nivel"] != "ok":
            sugerencias.append(punto["sugerencia"])
    anomalias = detectar_anomalias(db)
    if anomalias:
        atencion.append(f"{_pl(len(anomalias), 'dato de pedido', 'datos de pedidos')} por verificar (monto, precio o cantidad).")
        sugerencias.append("Verifica los datos de pedidos señalados para mantener el registro limpio.")
    if ventas and ventas["sugerencia"] not in ("Registra más ventas en el periodo para poder comparar.",):
        sugerencias.insert(0, ventas["sugerencia"])
    if atencion:
        secciones.append({"titulo": "Requiere atención", "lineas": atencion})
        lineas.append("Requiere atención")
        lineas += [f"• {a}" for a in atencion]
    else:
        lineas.append("Requiere atención")
        lineas.append("• Nada urgente: indicadores en verde, stock cubierto y sin cotizaciones atrasadas.")

    p = fc.proyectar_ventas(db, 7)
    proyeccion = [f"Esperado para los próximos 7 días: {_soles(p['total'])} (rango {_soles(p['bajo'])} a {_soles(p['alto'])})."]
    if p["meta_diaria"]:
        estado = "por encima" if p["promedio_diario"] >= p["meta_diaria"] else "por debajo"
        proyeccion.append(f"Promedio diario esperado {_soles(p['promedio_diario'])}, {estado} de tu meta de {_soles(p['meta_diaria'])}.")
    secciones.append({"titulo": "Proyección", "lineas": proyeccion})
    lineas.append("Proyección")
    lineas += [f"• {x}" for x in proyeccion]

    if sugerencias:
        recomendadas = [f"{i + 1}. {s}" for i, s in enumerate(sugerencias[:4])]
        secciones.append({"titulo": "Qué haría la próxima semana", "lineas": recomendadas})
        lineas.append("Qué haría la próxima semana")
        lineas += recomendadas

    etiquetas, valores = an.serie_diaria(db, "semana")
    grafico = _grafico(
        "bar",
        "Ventas diarias de la semana",
        etiquetas,
        [{"nombre": "Ventas", "valores": valores}],
        _explicacion("Ventas confirmadas de cada día de la semana en curso.", ["Pedidos Aprobados o Entregados"], "Ventas del día = Σ monto_total", an.texto_rango("semana")),
    )
    informe = {
        "titulo": f"Informe semanal — {an.texto_rango('semana')}",
        "secciones": secciones,
        "grafico": {k: grafico[k] for k in ("grafico", "titulo", "labels", "series", "prefijo", "horizontal")},
    }
    inicio, fin = an.rango("semana")
    desde, hasta = inicio.date().isoformat(), (fin.date() - timedelta(days=1)).isoformat()
    acciones = [
        {"tipo": "pdf_informe", "etiqueta": "Descargar informe (PDF)", "informe": informe},
        {"tipo": "descarga", "etiqueta": "Pedidos de la semana (Excel)", "ruta": f"/reports/orders/excel?desde={desde}&hasta={hasta}", "nombre": f"pedidos_{desde}_{hasta}.xlsx"},
    ]
    datos = {
        "tipo": "analisis",
        "acciones": acciones,
        "explicacion": _explicacion(
            "Armé el informe juntando las mismas revisiones del dashboard: ventas contra la semana pasada, causas, indicadores, stock, recompra, seguimiento, datos inusuales y la proyección.",
            ["Pedidos y cotizaciones de la semana", "Indicadores NCCA, NPP y TPTD", "Stock y ritmo de venta de 30 días", "Historial de compras de clientes"],
            None,
            an.texto_rango("semana"),
        ),
    }
    return _resultado("\n".join(lineas), datos)


def responder_insights(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    if PAT_INFORME.search(limpio) and not PAT_INFORME_OTRO.search(limpio):
        return _informe_semanal(db)
    if PAT_ANOMALIAS.search(limpio):
        return _responder_anomalias(db)
    if PAT_SIMULAR.search(limpio):
        return _responder_simulacion(db, prompt, limpio)
    if PAT_VENTA_CRUZADA.search(limpio):
        return _responder_venta_cruzada(db, prompt, limpio)
    if PAT_PRONOSTICO.search(limpio):
        return _responder_pronostico(db, prompt, limpio)
    return None
