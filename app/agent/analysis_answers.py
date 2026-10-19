import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.fechas_texto import extraer_rangos
from app.agent.quote_intent import _buscar_cliente_en_texto
from app.models.product import Producto
from app.services import analytics_service as an
from app.services.quote_note_service import candidatos, normalizar, tokens

PAT_COMPARAR = re.compile(r"\bcompar\w*\b|\bvs\b|\bversus\b|\bfrente a\b|\bcontra\b")
PAT_GRAFICO = re.compile(r"\bgrafic\w*\b|\bdiagrama\b|\bevolucion\b|\btendencia\b")
PAT_PORQUE = re.compile(
    r"\bpor ?que\b.*\bventas?\b|\bque paso con (?:las )?ventas\b|\bpor ?que (?:bajaron|cayeron|subieron|aumentaron|disminuyeron)\b"
    r"|\bmotivo\b.*\b(?:baja|caida|subida)\b.*\bventas?\b"
)
PAT_REPOSICION = re.compile(
    r"\breponer\b|\breposicion\b|\bcuanto pedir\b|\bcobertura\b|\bdias de stock\b|\bquiebre\b"
    r"|\bse (?:va a |van a )?(?:agotar|agotan)\b|\bcuando se agota\b|\bpedir al? proveedor\b"
    r"|\bque (?:debo |tengo que |deberia )?(?:pedir|comprar) (?:al? )?proveedor\b"
)
PAT_RECOMPRA = re.compile(
    r"\ba quien le toca\b|\bquien(?:es)? (?:le |les )?toca(?:n)? (?:comprar|pedir|recomprar)\b|\brecompra\b"
    r"|\bcuando (?:vuelven|vuelve|volveran) a comprar\b|\bclientes? por (?:recomprar|volver a comprar)\b|\bcadencia\b"
    r"|\bclientes? que (?:ya )?(?:deberian|van a|tienen que) (?:comprar|pedir)\b|\bles toca comprar\b"
)
PAT_PLAN = re.compile(
    r"\bque me recomiendas\b|\brecomendaci\w+\b|\bque (?:hago|debo hacer|deberia hacer) hoy\b"
    r"|\bprioridades\b|\bplan del dia\b|\bpor donde empiezo\b|\bque priorizo\b|\bque hago ahora\b"
)
PAT_RANKING = re.compile(
    r"\b(?:top|ranking|mejores|principales|mas vendid\w+|mas compra\w+|que mas (?:se )?(?:vend\w+|compra\w+)|mayor rotacion|mas rotacion)\b"
)
PAT_VALOR = re.compile(r"\b(?:ventas|ingresos|soles|facturacion|monto|dinero)\b")
PAT_CATEGORIA = re.compile(r"\bcategorias?\b|\brubros?\b")
PAT_TOP = re.compile(r"\bmas vendid\w+\b|\bmayor rotacion\b|\btop\b|\bproductos\b")

PERIODOS_PATRONES: List[Tuple[str, re.Pattern]] = [
    ("semana_pasada", re.compile(r"\bsemana (?:pasada|anterior)\b|\bultima semana\b")),
    ("mes_pasado", re.compile(r"\bmes (?:pasado|anterior)\b|\bultimo mes\b")),
    ("ayer", re.compile(r"\bayer\b")),
    ("hoy", re.compile(r"\bhoy\b")),
    ("semana", re.compile(r"\bsemana\b")),
    ("mes", re.compile(r"\bmes\b")),
]
RUIDO_ENTIDAD = {
    "compara", "comparar", "comparame", "comparacion", "ventas", "venta", "vendio", "vendido", "entre",
    "producto", "productos", "cliente", "clientes", "hoy", "ayer", "semana", "mes", "este", "esta",
    "pasado", "pasada", "grafico", "grafica", "grafique", "muestrame", "dame", "con", "de", "del",
}

SOLES = "S/ "


def _soles(valor: float) -> str:
    return f"S/ {valor:,.2f}"


def _de(nombre: str) -> str:
    etiqueta = an.ETIQUETAS[nombre]
    if etiqueta.startswith("del "):
        return etiqueta
    if etiqueta.startswith("el "):
        return "del " + etiqueta[3:]
    return "de " + etiqueta


def _signo(valor: float) -> str:
    return "+" if valor >= 0 else "−"


def _porcentaje(actual: float, previo: float) -> str:
    if not previo:
        return "—" if not actual else "nuevo"
    return f"{(actual - previo) / previo * 100:+.0f} %"


def _periodos(limpio: str, rangos: Optional[List[str]] = None) -> List[str]:
    texto = limpio
    encontrados: List[Tuple[int, str]] = []
    for m in re.finditer(r"\bfecha(\d+)\b", texto):
        indice = int(m.group(1))
        if rangos and indice < len(rangos):
            encontrados.append((m.start(), rangos[indice]))
        texto = texto[: m.start()] + " " * (m.end() - m.start()) + texto[m.end():]
    for nombre, patron in PERIODOS_PATRONES:
        for m in patron.finditer(texto):
            encontrados.append((m.start(), nombre))
            texto = texto[: m.start()] + " " * (m.end() - m.start()) + texto[m.end():]
    encontrados.sort()
    resultado: List[str] = []
    for _, nombre in encontrados:
        if nombre not in resultado:
            resultado.append(nombre)
    return resultado


def _explicacion(resumen: str, fuentes: List[str], formula: Optional[str] = None, periodo: Optional[str] = None) -> Dict[str, Any]:
    return {"resumen": resumen, "fuentes": fuentes, "formula": formula, "periodo": periodo}


def _grafico(
    tipo: str,
    titulo: str,
    etiquetas: List[str],
    series: List[Dict[str, Any]],
    explicacion: Dict[str, Any],
    prefijo: str = SOLES,
    horizontal: bool = False,
) -> Dict[str, Any]:
    return {
        "horizontal": horizontal,
        "tipo": "grafico",
        "grafico": tipo,
        "titulo": titulo,
        "labels": etiquetas,
        "series": series,
        "prefijo": prefijo,
        "explicacion": explicacion,
    }


def _comparar_periodos(db: Session, a: str, b: str) -> Dict[str, Any]:
    ta, tb = an.total_periodo(db, a), an.total_periodo(db, b)
    diferencia = ta["ventas"] - tb["ventas"]
    lineas = [
        f"Ventas {_de(a)} vs {an.ETIQUETAS[b]}:",
        f"• {an.ETIQUETAS[a].capitalize()} ({an.texto_rango(a)}): {_soles(ta['ventas'])} en {_pl(ta['pedidos'], 'pedido', 'pedidos')}.",
        f"• {an.ETIQUETAS[b].capitalize()} ({an.texto_rango(b)}): {_soles(tb['ventas'])} en {_pl(tb['pedidos'], 'pedido', 'pedidos')}.",
        f"Diferencia: {_signo(diferencia)}{_soles(abs(diferencia))} ({_porcentaje(ta['ventas'], tb['ventas'])}).",
    ]
    if "hoy" in (a, b):
        lineas.append("Ojo: hoy el día aún no termina, así que la comparación puede cambiar.")
    pares = {frozenset((a, b))}
    es_semanal = pares == {frozenset(("semana", "semana_pasada"))}
    es_mensual = pares == {frozenset(("mes", "mes_pasado"))}
    dias_a, dias_b = max(1, an.dias_del_rango(a)), max(1, an.dias_del_rango(b))
    if dias_a != dias_b:
        lineas.append(
            f"Los periodos tienen distinta duración ({dias_a} y {dias_b} días); promedio diario: "
            f"{_soles(ta['ventas'] / dias_a)} vs {_soles(tb['ventas'] / dias_b)}."
        )
    if es_semanal or es_mensual:
        lineas.append("Se comparan los mismos días transcurridos de cada periodo.")
        etiquetas, valores_a = an.serie_diaria(db, a)
        _, valores_b = an.serie_diaria(db, b)
        largo = min(len(valores_a), len(valores_b))
        grafico = _grafico(
            "bar" if es_semanal else "line",
            f"Ventas diarias: {an.ETIQUETAS[a]} vs {an.ETIQUETAS[b]}",
            etiquetas[:largo],
            [
                {"nombre": an.ETIQUETAS[a].capitalize(), "valores": valores_a[:largo]},
                {"nombre": an.ETIQUETAS[b].capitalize(), "valores": valores_b[:largo]},
            ],
            _explicacion(
                "Suma de los montos de los pedidos confirmados, día por día, en cada periodo.",
                ["Pedidos con estado Aprobado o Entregado", "Fecha del pedido en hora de Lima"],
                "Ventas del día = Σ monto_total de los pedidos del día",
                f"{an.texto_rango(a)} y {an.texto_rango(b)}",
            ),
        )
    elif an.dias_del_rango(a) == an.dias_del_rango(b) and an.dias_del_rango(a) <= 31:
        _, valores_a = an.serie_diaria(db, a)
        _, valores_b = an.serie_diaria(db, b)
        grafico = _grafico(
            "bar" if len(valores_a) <= 10 else "line",
            f"Ventas diarias: {an.ETIQUETAS[a]} vs {an.ETIQUETAS[b]}",
            [f"Día {i}" for i in range(1, len(valores_a) + 1)],
            [
                {"nombre": an.ETIQUETAS[a].capitalize(), "valores": valores_a},
                {"nombre": an.ETIQUETAS[b].capitalize(), "valores": valores_b},
            ],
            _explicacion(
                "Suma de los montos de los pedidos confirmados, día por día, en cada periodo.",
                ["Pedidos con estado Aprobado o Entregado", "Fecha del pedido en hora de Lima"],
                "Ventas del día = Σ monto_total de los pedidos del día",
                f"{an.texto_rango(a)} y {an.texto_rango(b)}",
            ),
        )
    else:
        grafico = _grafico(
            "bar",
            "Comparación de ventas",
            [an.ETIQUETAS[b].capitalize(), an.ETIQUETAS[a].capitalize()],
            [{"nombre": "Ventas", "valores": [round(tb["ventas"], 2), round(ta["ventas"], 2)]}],
            _explicacion(
                "Suma de los montos de los pedidos confirmados de cada periodo.",
                ["Pedidos con estado Aprobado o Entregado"],
                "Ventas = Σ monto_total",
                f"{an.texto_rango(a)} y {an.texto_rango(b)}",
            ),
        )
    return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}


def _grafico_pedidos(db: Session, periodo: str) -> Dict[str, Any]:
    pedidos = an.pedidos_del_periodo(db, periodo)
    if not pedidos:
        return {"respuesta": f"No hay pedidos registrados para {an.ETIQUETAS[periodo]}.", "datos_estructurados": None}
    total = sum(p["total"] for p in pedidos)
    mayor = max(pedidos, key=lambda p: p["total"])
    lineas = [f"Pedidos {_de(periodo)} ({an.texto_rango(periodo)}): {len(pedidos)} por {_soles(total)} en total."]
    lineas += [f"• {p['codigo']} — {p['cliente']} — {_soles(p['total'])} ({p['estado']}, {p['hora']})" for p in pedidos]
    lineas.append(f"El mayor es {mayor['codigo']} de {mayor['cliente']} con {_soles(mayor['total'])}.")
    etiquetas = [f"{p['codigo'][-6:]} {' '.join(p['cliente'].split()[:2])}" for p in pedidos]
    grafico = _grafico(
        "bar",
        f"Pedidos {_de(periodo)}",
        etiquetas,
        [{"nombre": "Total del pedido", "valores": [round(p["total"], 2) for p in pedidos]}],
        _explicacion(
            "Un barra por cada pedido no cancelado del periodo, con su monto total.",
            ["Pedidos del periodo en hora de Lima, excepto cancelados"],
            "Total del pedido = Σ subtotal de sus líneas",
            an.texto_rango(periodo),
        ),
    )
    return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}


def _corto(nombre: str, largo: int = 30) -> str:
    return nombre if len(nombre) <= largo else nombre[: largo - 1] + "…"


def _ranking(db: Session, limpio: str, periodos: List[str]) -> Dict[str, Any]:
    periodo = periodos[0] if periodos else "mes"
    etiqueta = f"({an.texto_rango(periodo)})"

    if re.search(r"\bclientes?\b", limpio):
        filas = an.top_clientes(db, periodo)
        if not filas:
            return {"respuesta": f"No hay ventas confirmadas para {an.ETIQUETAS[periodo]}.", "datos_estructurados": None}
        lineas = [f"Mejores clientes {_de(periodo)} {etiqueta}:"]
        lineas += [f"{i}. {n} — {_soles(v)} en {_pl(c, 'pedido', 'pedidos')}" for i, (n, c, v) in enumerate(filas, 1)]
        grafico = _grafico(
            "bar",
            f"Mejores clientes — {an.ETIQUETAS[periodo]}",
            [_corto(n) for n, _, _ in filas],
            [{"nombre": "Ventas", "valores": [round(v, 2) for _, _, v in filas]}],
            _explicacion(
                "Sumé los pedidos confirmados de cada cliente y los ordené de mayor a menor.",
                ["Pedidos con estado Aprobado o Entregado", "Agrupados por cliente"],
                "Ventas del cliente = Σ monto_total de sus pedidos",
                an.texto_rango(periodo),
            ),
            horizontal=True,
        )
        return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}

    por_valor = bool(PAT_VALOR.search(limpio))
    filas = an.top_productos(db, periodo)
    if not filas:
        return {"respuesta": f"No hay ventas confirmadas para {an.ETIQUETAS[periodo]}.", "datos_estructurados": None}
    filas.sort(key=lambda f: f[2] if por_valor else f[1], reverse=True)
    filas = filas[:8]
    lineas = [f"Productos más vendidos {_de(periodo)} {etiqueta}, por {'ventas' if por_valor else 'unidades'}:"]
    lineas += [f"{i}. {n} — {int(u)} u. ({_soles(v)})" for i, (n, u, v) in enumerate(filas, 1)]
    grafico = _grafico(
        "bar",
        f"Productos más vendidos — {an.ETIQUETAS[periodo]}",
        [_corto(n) for n, _, _ in filas],
        [{"nombre": "Ventas" if por_valor else "Unidades", "valores": [round(v if por_valor else u, 2) for _, u, v in filas]}],
        _explicacion(
            "Ordené los productos por lo vendido en pedidos confirmados del periodo.",
            ["Detalle de pedidos con estado Aprobado o Entregado", "Agrupado por producto"],
            "Ranking por Σ subtotal" if por_valor else "Ranking por Σ cantidad vendida",
            an.texto_rango(periodo),
        ),
        prefijo=SOLES if por_valor else "",
        horizontal=True,
    )
    return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}


def _separar_entidades(limpio: str) -> List[str]:
    cuerpo = re.sub(r"\bcompar\w*\b", " ", limpio)
    partes = re.split(r"\bcon\b|\bvs\b|\bversus\b|\bcontra\b|\bfrente a\b|\by\b|\be\b", cuerpo)
    limpias = []
    for parte in partes:
        restantes = [t for t in tokens(parte) if t not in RUIDO_ENTIDAD]
        if restantes:
            limpias.append(" ".join(restantes))
    return limpias


def _resolver_producto(productos: List[Tuple[int, str]], texto: str) -> Optional[Tuple[List[int], str]]:
    lista = candidatos(texto, productos, True)
    exactos = [c for c in lista if c[2] >= 1.0]
    if not exactos or len(exactos) > 30:
        return None
    if len(exactos) == 1:
        return [exactos[0][0]], exactos[0][1]
    return [c[0] for c in exactos], f"{texto.capitalize()} ({len(exactos)} productos)"


def _pl(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _comparar_entidades(db: Session, limpio: str, periodo: str) -> Optional[Dict[str, Any]]:
    partes = _separar_entidades(limpio)
    if len(partes) < 2 or len(partes) > 4:
        return None

    clientes = []
    for parte in partes:
        cliente, _ = _buscar_cliente_en_texto(db, parte)
        clientes.append(cliente)
    if all(clientes) and len({c.id for c in clientes}) == len(clientes):
        datos = an.ventas_de_clientes(db, [c.id for c in clientes], periodo)
        etiquetas = [c.razon_social for c in clientes]
        valores = [round(datos.get(c.id, (0, 0.0))[1], 2) for c in clientes]
        lineas = [f"Ventas por cliente — {an.ETIQUETAS[periodo]} ({an.texto_rango(periodo)}):"]
        lineas += [
            f"• {c.razon_social}: {_soles(datos.get(c.id, (0, 0.0))[1])} en {_pl(datos.get(c.id, (0, 0.0))[0], 'pedido', 'pedidos')}"
            for c in clientes
        ]
        grafico = _grafico(
            "bar",
            "Ventas por cliente",
            etiquetas,
            [{"nombre": "Ventas", "valores": valores}],
            _explicacion(
                "Suma de los montos de los pedidos confirmados de cada cliente en el periodo.",
                ["Pedidos con estado Aprobado o Entregado", "Agrupados por cliente"],
                "Ventas del cliente = Σ monto_total de sus pedidos",
                an.texto_rango(periodo),
            ),
        )
        return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}

    catalogo = [(p.id, p.nombre) for p in db.scalars(select(Producto).where(Producto.activo.is_(True))).all()]
    grupos = [_resolver_producto(catalogo, parte) for parte in partes]
    if all(grupos):
        todos = [i for ids, _ in grupos for i in ids]
        datos = an.ventas_de_productos(db, todos, periodo)

        def suma(ids):
            unidades = sum(datos.get(i, (0.0, 0.0))[0] for i in ids)
            ventas = sum(datos.get(i, (0.0, 0.0))[1] for i in ids)
            return unidades, ventas

        etiquetas = [nombre for _, nombre in grupos]
        valores = [round(suma(ids)[1], 2) for ids, _ in grupos]
        lineas = [f"Ventas por producto — {an.ETIQUETAS[periodo]} ({an.texto_rango(periodo)}):"]
        lineas += [f"• {nombre}: {_soles(suma(ids)[1])} ({int(suma(ids)[0])} u.)" for ids, nombre in grupos]
        grafico = _grafico(
            "bar",
            "Ventas por producto",
            etiquetas,
            [{"nombre": "Ventas", "valores": valores}],
            _explicacion(
                "Suma de los subtotales de los productos que coinciden con cada nombre en los pedidos confirmados del periodo.",
                ["Detalle de pedidos con estado Aprobado o Entregado", "Coincidencia aproximada contra el catálogo activo"],
                "Ventas = Σ subtotal de las líneas del producto",
                an.texto_rango(periodo),
            ),
        )
        return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}
    return None


def _resumen_periodo(db: Session, periodo: str) -> Dict[str, Any]:
    t = an.total_periodo(db, periodo)
    etiqueta = an.ETIQUETAS[periodo]
    texto = (
        f"Ventas {_de(periodo)}{'' if an.es_rango_libre(periodo) else ' (' + an.texto_rango(periodo) + ')'}: {_pl(t['pedidos'], 'venta', 'ventas')} "
        f"(pedidos aprobados y entregados) por {_soles(t['ventas'])}"
    )
    if t["pedidos"]:
        texto += f", con un ticket promedio de {_soles(t['ticket'])}"
    texto += f". Cotizaciones registradas en el periodo: {t['cotizaciones']}."
    datos = {
        "tipo": "analisis",
        "acciones": [{"tipo": "pregunta", "etiqueta": "Ver gráfico diario", "texto": f"gráfico de ventas {etiqueta}"}],
        "explicacion": _explicacion(
            "Conté los pedidos confirmados del periodo y sumé sus montos.",
            ["Pedidos con estado Aprobado o Entregado", "Cotizaciones de clientes del periodo"],
            "Ticket promedio = ventas ÷ número de pedidos",
            an.texto_rango(periodo),
        ),
    }
    return {"respuesta": texto, "datos_estructurados": datos}


def _grafico_ventas(db: Session, limpio: str, periodos: List[str]) -> Dict[str, Any]:
    if PAT_CATEGORIA.search(limpio):
        periodo = periodos[0] if periodos else "mes"
        filas = an.ventas_por_categoria(db, periodo)
        if not filas:
            return {"respuesta": f"No hay ventas confirmadas para {an.ETIQUETAS[periodo]}.", "datos_estructurados": None}
        filas = filas[:8]
        lineas = [f"Ventas por categoría — {an.ETIQUETAS[periodo]} ({an.texto_rango(periodo)}):"]
        lineas += [f"• {n}: {_soles(v)}" for n, v in filas]
        grafico = _grafico(
            "doughnut",
            "Ventas por categoría",
            [n for n, _ in filas],
            [{"nombre": "Ventas", "valores": [round(v, 2) for _, v in filas]}],
            _explicacion(
                "Suma de los subtotales de los productos de cada categoría en los pedidos confirmados.",
                ["Detalle de pedidos con estado Aprobado o Entregado", "Categoría del producto"],
                "Ventas de la categoría = Σ subtotal",
                an.texto_rango(periodo),
            ),
        )
        return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}

    periodo = periodos[0] if periodos else ("mes" if re.search(r"\bevolucion\b|\btendencia\b", limpio) else "semana")
    if periodo in ("hoy", "ayer"):
        periodo = "semana"
    etiquetas, valores = an.serie_diaria(db, periodo)
    total = sum(valores)
    mejor = max(range(len(valores)), key=lambda i: valores[i]) if valores else None
    lineas = [f"Ventas diarias {_de(periodo)} ({an.texto_rango(periodo)}): total {_soles(total)}."]
    if mejor is not None and valores[mejor] > 0:
        lineas.append(f"El mejor día fue {etiquetas[mejor]} con {_soles(valores[mejor])}.")
    grafico = _grafico(
        "bar" if periodo.startswith("semana") else "line",
        f"Ventas diarias — {an.ETIQUETAS[periodo]}",
        etiquetas,
        [{"nombre": "Ventas", "valores": valores}],
        _explicacion(
            "Suma de los montos de los pedidos confirmados de cada día.",
            ["Pedidos con estado Aprobado o Entregado", "Fecha del pedido en hora de Lima"],
            "Ventas del día = Σ monto_total",
            an.texto_rango(periodo),
        ),
    )
    return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}


def _diagnostico(db: Session, periodos: List[str]) -> Dict[str, Any]:
    nombre = periodos[0] if periodos else "semana"
    if nombre not in ("hoy", "semana", "mes") and not an.es_rango_libre(nombre):
        nombre = {"ayer": "hoy", "semana_pasada": "semana", "mes_pasado": "mes"}.get(nombre, "semana")
    d = an.diagnostico(db, nombre)
    actual, previo = d["actual"], d["anterior"]
    diferencia = actual["ventas"] - previo["ventas"]
    sube = diferencia >= 0
    a, b = an.ETIQUETAS[nombre], an.ETIQUETAS[d["previo"]]
    a_de, b_de = _de(nombre), _de(d["previo"])
    lineas = [
        f"Ventas {a_de}: {_soles(actual['ventas'])} en {actual['pedidos']} pedidos, frente a "
        f"{_soles(previo['ventas'])} en {previo['pedidos']} pedidos {b_de} "
        f"({_signo(diferencia)}{_soles(abs(diferencia))}, {_porcentaje(actual['ventas'], previo['ventas'])}).",
    ]
    if previo["pedidos"] or actual["pedidos"]:
        lineas.append(
            f"Ticket promedio: {_soles(actual['ticket'])} vs {_soles(previo['ticket'])}. "
            f"Cotizaciones: {actual['cotizaciones']} vs {previo['cotizaciones']}."
        )
    clave_prod = d["subidas_producto"] if sube else d["caidas_producto"]
    clave_cli = d["subidas_cliente"] if sube else d["caidas_cliente"]
    if clave_prod:
        lineas.append("Productos que más explican el cambio:")
        lineas += [f"• {n}: {_signo(dif)}{_soles(abs(dif))} ({_soles(act)} vs {_soles(pre)})" for n, dif, act, pre in clave_prod]
    if clave_cli:
        lineas.append("Clientes que más explican el cambio:")
        lineas += [f"• {n}: {_signo(dif)}{_soles(abs(dif))} ({_soles(act)} vs {_soles(pre)})" for n, dif, act, pre in clave_cli]
    if not sube:
        if d["productos_caidos_con_poco_stock"]:
            lineas.append(
                "Ojo: estos productos bajaron y están en stock crítico, puede ser falta de inventario: "
                + ", ".join(d["productos_caidos_con_poco_stock"]) + "."
            )
        if actual["cotizaciones"] < previo["cotizaciones"]:
            lineas.append("También hubo menos cotizaciones, así que entró menos demanda al embudo.")
        if d["caidas_cliente"]:
            lineas.append(f"Sugerencia: contacta a {d['caidas_cliente'][0][0]}, que dejó de comprar al ritmo anterior.")
    elif previo["ventas"] == 0 and actual["ventas"] == 0:
        lineas = ["No hay ventas confirmadas en ninguno de los dos periodos para comparar."]

    grafico = _comparar_periodos(db, nombre, d["previo"])["datos_estructurados"]
    grafico["explicacion"] = _explicacion(
        "Comparé las ventas confirmadas del periodo con el periodo anterior y descompuse la diferencia por producto y por cliente.",
        [
            "Pedidos con estado Aprobado o Entregado",
            "Detalle de pedidos agrupado por producto y por cliente",
            "Cotizaciones registradas en cada periodo",
            "Stock actual de los productos que bajaron",
        ],
        "Diferencia = ventas del periodo − ventas del periodo anterior (mismos días transcurridos)",
        f"{an.texto_rango(nombre)} vs {an.texto_rango(d['previo'])}",
    )
    return {"respuesta": "\n".join(lineas), "datos_estructurados": grafico}


def _reposicion(db: Session) -> Dict[str, Any]:
    filas = an.cobertura_stock(db)
    if not filas:
        return {
            "respuesta": "Por ahora ningún producto está en riesgo de agotarse en los próximos "
            f"{an.UMBRAL_COBERTURA_DIAS} días según su ritmo de venta.",
            "datos_estructurados": None,
        }
    lineas = [f"Estos productos se agotarían pronto según su ritmo de venta de los últimos {an.DIAS_VENTANA_ROTACION} días:"]
    for f in filas:
        cobertura = f"{f['dias_cobertura']} días" if f["dias_cobertura"] is not None else "sin ventas recientes"
        lineas.append(
            f"• {f['nombre']} — stock {f['stock']} ({cobertura} de cobertura, vende {f['ritmo_diario']}/día) → pedir {f['sugerido']} u."
        )
    lineas.append(f"La sugerencia busca cubrir {an.DIAS_OBJETIVO_STOCK} días de venta.")
    con_cobertura = [f for f in filas if f["dias_cobertura"] is not None]
    datos: Dict[str, Any] = {
        "tipo": "analisis",
        "acciones": [
            {"tipo": "descarga", "etiqueta": "Lista de reposición (Excel)", "ruta": "/reports/reposicion/excel", "nombre": "lista_reposicion.xlsx"}
        ],
        "explicacion": _explicacion(
            "Divido el stock actual entre las unidades que se venden por día y sugiero pedir lo necesario para cubrir 15 días.",
            [
                f"Ventas de los últimos {an.DIAS_VENTANA_ROTACION} días (pedidos Aprobados o Entregados)",
                "Stock actual y stock mínimo del producto",
            ],
            f"Días de cobertura = stock ÷ (unidades vendidas en {an.DIAS_VENTANA_ROTACION} días ÷ {an.DIAS_VENTANA_ROTACION}); sugerido = ritmo diario × {an.DIAS_OBJETIVO_STOCK} − stock",
            f"últimos {an.DIAS_VENTANA_ROTACION} días",
        ),
    }
    if con_cobertura:
        datos = _grafico(
            "bar",
            "Días de stock restantes",
            [f["nombre"] for f in con_cobertura],
            [{"nombre": "Días de cobertura", "valores": [f["dias_cobertura"] for f in con_cobertura]}],
            datos["explicacion"],
            prefijo="",
        )
        datos["acciones"] = [
            {"tipo": "descarga", "etiqueta": "Lista de reposición (Excel)", "ruta": "/reports/reposicion/excel", "nombre": "lista_reposicion.xlsx"}
        ]
    return {"respuesta": "\n".join(lineas), "datos_estructurados": datos}


def _mensaje_recompra(nombre: str, habituales: List[str]) -> str:
    primero = nombre.split()[0].capitalize()
    habitual = f" Podemos prepararte tu pedido habitual de {' y '.join(habituales)}." if habituales else ""
    return f"Hola {primero}, ¿cómo estás? Te escribimos de EL PRÍNCIPE para saber si necesitas reponer tus productos.{habitual} ¿Te armamos una cotización?"


def _recompra(db: Session) -> Dict[str, Any]:
    filas = an.cadencia_clientes(db, limite=6)
    if not filas:
        return {
            "respuesta": "Por ahora ningún cliente con historial suficiente está por recomprar. "
            f"Necesito al menos {an.MIN_PEDIDOS_CADENCIA} compras de un cliente para estimar cada cuánto compra.",
            "datos_estructurados": None,
        }
    lineas = ["Estos clientes ya están en su momento habitual de recompra:"]
    tarjetas = []
    for f in filas:
        estado = "atrasado" if f["atrasado"] else "toca pronto"
        lineas.append(
            f"• {f['nombre']} — suele comprar cada {f['intervalo_dias']} días y lleva {f['dias_sin_comprar']} sin comprar ({estado})."
        )
        habituales = an.productos_habituales(db, f["id"])
        tarjetas.append(
            {
                "titulo": f["nombre"],
                "detalle": f"Cada {f['intervalo_dias']} días · {f['dias_sin_comprar']} sin comprar"
                + (f" · Lleva: {', '.join(habituales)}" if habituales else ""),
                "mensaje": _mensaje_recompra(f["nombre"], habituales),
                "consulta": f"Arma una cotización para {f['nombre']}",
            }
        )
    datos = {
        "tipo": "analisis",
        "filas": tarjetas,
        "explicacion": _explicacion(
            "Calculo cada cuántos días compra cada cliente (mediana entre sus compras) y marco a los que ya llegaron al 80 % de ese intervalo.",
            ["Fechas de todos los pedidos no cancelados del cliente", "Solo clientes activos con al menos 3 compras en días distintos"],
            "Intervalo habitual = mediana de días entre compras; toca cuando días sin comprar ≥ 0,8 × intervalo",
            "historial completo del cliente",
        ),
    }
    return {"respuesta": "\n".join(lineas), "datos_estructurados": datos}


def _plan_del_dia(db: Session) -> Dict[str, Any]:
    lineas = ["Esto es lo que priorizaría hoy:"]
    acciones: List[Dict[str, Any]] = []
    cobertura = an.cobertura_stock(db, limite=3)
    if cobertura:
        lineas.append("1. Reponer stock:")
        lineas += [
            f"   • {f['nombre']} — queda para {f['dias_cobertura']} días, pedir {f['sugerido']} u."
            if f["dias_cobertura"] is not None
            else f"   • {f['nombre']} — bajo el mínimo, pedir {f['sugerido']} u."
            for f in cobertura
        ]
        acciones.append({"tipo": "pregunta", "etiqueta": "Ver reposición completa", "texto": "¿Qué debo reponer?"})
    clientes = an.cadencia_clientes(db, limite=3)
    if clientes:
        lineas.append("2. Llamar a quienes ya les toca comprar:")
        lineas += [f"   • {c['nombre']} — compra cada {c['intervalo_dias']} días, lleva {c['dias_sin_comprar']} sin comprar." for c in clientes]
        acciones.append({"tipo": "pregunta", "etiqueta": "Ver clientes por recomprar", "texto": "¿A quién le toca comprar?"})
    seguimiento = an.cotizaciones_sin_seguimiento(db)
    if seguimiento:
        lineas.append(f"3. Dar seguimiento a {seguimiento} {'cotización' if seguimiento == 1 else 'cotizaciones'} sin respuesta.")
        acciones.append({"tipo": "enlace", "etiqueta": "Abrir cotizaciones", "ruta": "/solicitudes"})
    if len(lineas) == 1:
        lineas = ["Hoy no veo urgencias: stock cubierto, sin clientes atrasados y sin cotizaciones sin respuesta."]
    datos = {
        "tipo": "analisis",
        "acciones": acciones,
        "explicacion": _explicacion(
            "Junté tres revisiones: cobertura de stock, clientes en su momento de recompra y cotizaciones sin seguimiento.",
            [
                "Ventas de los últimos 30 días y stock actual",
                "Historial de compras de cada cliente",
                "Cotizaciones pendientes con más de 24 horas",
            ],
            None,
            "datos al momento de la consulta",
        ),
    }
    return {"respuesta": "\n".join(lineas), "datos_estructurados": datos}


def responder_analisis(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    rangos, sin_fechas = extraer_rangos(prompt)
    limpio = normalizar(sin_fechas)
    periodos = _periodos(limpio, rangos)

    if PAT_PORQUE.search(limpio):
        return _diagnostico(db, periodos)

    if (
        re.search(r"\bpedidos?\b", limpio)
        and (PAT_GRAFICO.search(limpio) or PAT_COMPARAR.search(limpio))
        and not re.search(r"\bventas?\b|\bvs\b|\bversus\b|\bcontra\b", limpio)
        and len(periodos) <= 1
    ):
        cliente_en_texto, _ = _buscar_cliente_en_texto(db, prompt)
        if cliente_en_texto is None:
            return _grafico_pedidos(db, periodos[0] if periodos else "hoy")

    if PAT_COMPARAR.search(limpio):
        periodo_entidad = periodos[0] if periodos else "mes"
        entidades = _comparar_entidades(db, limpio, periodo_entidad)
        if entidades:
            return entidades
        if re.search(r"\bventas?\b|\bvend\w+\b|\bingresos?\b", limpio) or periodos:
            if len(periodos) >= 2:
                return _comparar_periodos(db, periodos[0], periodos[1])
            base = periodos[0] if periodos else "semana"
            return _comparar_periodos(db, base, an.ANTERIOR[base])

    if PAT_RANKING.search(limpio) and PAT_GRAFICO.search(limpio):
        return _ranking(db, limpio, periodos)
    if rangos and re.search(r"\bpedidos?\b", limpio) and not re.search(r"\bventas?\b", limpio) and len(periodos) == 1:
        cliente_pedido, _ = _buscar_cliente_en_texto(db, prompt)
        if cliente_pedido is None:
            return _grafico_pedidos(db, periodos[0])
    if rangos and re.search(r"\bventas?\b|\bvend\w+\b", limpio) and not PAT_REPOSICION.search(limpio):
        if not PAT_GRAFICO.search(limpio):
            return _resumen_periodo(db, periodos[0])
        return _grafico_ventas(db, limpio, periodos)

    if PAT_REPOSICION.search(limpio):
        return _reposicion(db)
    if PAT_RECOMPRA.search(limpio):
        return _recompra(db)
    if PAT_PLAN.search(limpio):
        return _plan_del_dia(db)
    if PAT_GRAFICO.search(limpio):
        return _grafico_ventas(db, limpio, periodos)
    return None
