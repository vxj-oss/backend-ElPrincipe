import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.agent.analysis_answers import _periodos
from app.agent.fechas_texto import extraer_rangos
from app.agent.quick_answers import PAT_CODIGO
from app.agent.quote_intent import _buscar_cliente_en_texto
from app.agent.choices import opciones_de_clientes, respuesta_opciones
from app.services import analytics_service as an
from app.services.quote_note_service import normalizar

PAT_PALABRA_REPORTE = re.compile(
    r"\b(?:reporte|reportes|informe|informes|excel|exporta\w*|planilla|hoja de calculo)\b|\bcierre (?:del dia|de caja)\b"
)
PAT_PDF_PLURAL = re.compile(r"\bpdf\b.*\b(?:pedidos|clientes|productos|inventario|indicadores|errores)\b|\b(?:pedidos|clientes|productos|inventario|indicadores)\b.*\bpdf\b")
PAT_FORMATO_EXCEL = re.compile(r"\bexcel\b|\bxlsx\b|\bhoja de calculo\b|\bplanilla\b")
PAT_FORMATO_PDF = re.compile(r"\bpdf\b")
PAT_HISTORIAL_CLIENTE = re.compile(r"\bhistorial\b|\bestado de cuenta\b")
PAT_ORDEN_DESCARGA = re.compile(r"\b(?:descarga\w*|baja\w*|reporte|informe|excel|pdf|exporta\w*|dame|genera\w*|pasame|mandame|quiero|necesito)\b")
PAT_EXCLUIR = re.compile(r"\bgrafic\w*\b|\bese pedido\b|\beste pedido\b|\bticket\b")


def _accion(etiqueta: str, ruta: str, nombre: str) -> Dict[str, Any]:
    return {"tipo": "descarga", "etiqueta": etiqueta, "ruta": ruta, "nombre": nombre}


def _explicacion(texto: str) -> Dict[str, Any]:
    return {
        "resumen": texto,
        "fuentes": ["Los mismos reportes del módulo de Reportes, generados con los datos actuales"],
        "formula": None,
        "periodo": "datos al momento de la consulta",
    }


def _respuesta(texto: str, acciones: List[Dict[str, Any]], explicacion: str) -> Dict[str, Any]:
    return {
        "respuesta": texto,
        "datos_estructurados": {"tipo": "analisis", "acciones": acciones, "explicacion": _explicacion(explicacion)},
    }


def _periodo_en_texto(prompt: str, limpio: str) -> Optional[str]:
    rangos, sin_fechas = extraer_rangos(prompt)
    periodos = _periodos(normalizar(sin_fechas), rangos)
    return periodos[0] if periodos else None


def _desde_hasta(nombre: str) -> Tuple[str, str]:
    from datetime import timedelta

    inicio, fin = an.rango(nombre)
    return inicio.date().isoformat(), (fin.date() - timedelta(days=1)).isoformat()


def _historial_de_cliente(db: Session, prompt: str, limpio: str) -> Optional[Dict[str, Any]]:
    if not (PAT_HISTORIAL_CLIENTE.search(limpio) and PAT_ORDEN_DESCARGA.search(limpio)):
        return None
    cliente, dudosos = _buscar_cliente_en_texto(db, prompt)
    if cliente is None and dudosos:
        nombres = ", ".join(c.razon_social for c in dudosos)
        return respuesta_opciones(
            f"¿El historial de cuál cliente? Encontré: {nombres}.",
            opciones_de_clientes(dudosos, prompt),
        )
    if cliente is None:
        return None
    quiere_excel = bool(PAT_FORMATO_EXCEL.search(limpio))
    quiere_pdf = bool(PAT_FORMATO_PDF.search(limpio))
    ambos = not (quiere_excel ^ quiere_pdf)
    base = f"historial_{re.sub(r'[^a-z0-9]+', '_', normalizar(cliente.razon_social)).strip('_')}"
    acciones: List[Dict[str, Any]] = []
    if quiere_excel or ambos:
        acciones.append(_accion("Descargar Excel", f"/reports/customer-history/excel?cliente_id={cliente.id}", f"{base}.xlsx"))
    if quiere_pdf or ambos:
        acciones.append(_accion("Descargar PDF", f"/reports/customer-history/pdf?cliente_id={cliente.id}", f"{base}.pdf"))
    return _respuesta(
        f"Listo, aquí está el historial de {cliente.razon_social}: pedidos, productos más comprados y cotizaciones.",
        acciones,
        "Es el mismo reporte «Historial por Cliente» del módulo de Reportes.",
    )


def responder_reporte(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    if PAT_EXCLUIR.search(limpio) or PAT_CODIGO.search(prompt):
        return None
    historial = _historial_de_cliente(db, prompt, limpio)
    if historial:
        return historial
    if not (PAT_PALABRA_REPORTE.search(limpio) or PAT_PDF_PLURAL.search(limpio)):
        return None

    quiere_excel = bool(PAT_FORMATO_EXCEL.search(limpio))
    quiere_pdf = bool(PAT_FORMATO_PDF.search(limpio))
    ambos = not (quiere_excel ^ quiere_pdf)
    periodo = _periodo_en_texto(prompt, limpio)

    if re.search(r"\bcierre (?:del dia|de caja)\b", limpio) or (re.search(r"\bcierre\b", limpio) and re.search(r"\bdia\b", limpio)):
        return _respuesta(
            "Listo, aquí está el cierre del día en PDF (ventas, pedidos, indicadores y pendientes de hoy).",
            [_accion("Descargar cierre del día (PDF)", "/reports/cierre-dia/pdf", "cierre_del_dia.pdf")],
            "El cierre del día resume lo vendido hoy, los pedidos y cotizaciones, los indicadores y los pendientes.",
        )

    if re.search(r"\breposicion\b|\breponer\b|\blista de compras\b", limpio):
        return _respuesta(
            "Listo, aquí está la lista de reposición en Excel, con los productos por reponer y la cantidad sugerida.",
            [_accion("Descargar lista de reposición (Excel)", "/reports/reposicion/excel", "lista_reposicion.xlsx")],
            "La lista usa el ritmo de venta de los últimos 30 días para sugerir cuánto reponer.",
        )

    indicador = re.search(r"\b(ncca|npp|tptd)\b", limpio)
    if indicador and re.search(r"\b(?:por dia|diario|dia por dia|por dias)\b", limpio):
        sigla = indicador.group(1).upper()
        dias = re.search(r"\b(\d{1,2})\s+dias\b", limpio)
        suf = f"&dias={int(dias.group(1))}" if dias else ""
        return _respuesta(
            f"Listo, aquí está el {sigla} por día en Excel.",
            [_accion(f"Descargar {sigla} por día (Excel)", f"/reports/indicators/actividad/excel?indicador={sigla}{suf}", f"{sigla.lower()}_por_dia.xlsx")],
            "Serie diaria del indicador con su semáforo según las metas configuradas.",
        )
    if re.search(r"\b(?:tptd|tiempo (?:promedio )?de (?:toma de )?decision)\b", limpio) and re.search(r"\bpor pedido\b", limpio):
        return _respuesta(
            "Listo, aquí está el tiempo de decisión por pedido en Excel.",
            [_accion("Descargar TPTD por pedido (Excel)", "/reports/indicators/tpd/por-pedido/excel", "tpd_por_pedido.xlsx")],
            "Tiempo entre abrir la cotización y aprobar cada pedido.",
        )

    objetos: List[Tuple[str, str, str, bool]] = [
        ("pedidos con errores", r"\berrores?\b|\bcon error\b", "errors", True),
        ("indicadores", r"\bindicadores?\b", "indicators", False),
        ("pedidos", r"\bpedidos?\b|\bventas?\b", "orders", True),
        ("inventario", r"\binventario\b|\bstock\b|\bproductos?\b", "inventory", False),
        ("clientes", r"\bclientes?\b|\bcartera\b", "customers", False),
    ]
    for nombre, patron, ruta, admite_periodo in objetos:
        if not re.search(patron, limpio):
            continue
        consulta = ""
        sufijo_nombre = ""
        cuando = ""
        if admite_periodo and periodo:
            desde, hasta = _desde_hasta(periodo)
            consulta = f"?desde={desde}&hasta={hasta}"
            sufijo_nombre = f"_{desde}_{hasta}"
            cuando = f" de {an.ETIQUETAS[periodo]} ({an.texto_rango(periodo)})".replace("de del ", "del ").replace("de el ", "del ")
        acciones: List[Dict[str, Any]] = []
        base = nombre.replace(" ", "_")
        if quiere_excel or ambos:
            acciones.append(_accion("Descargar Excel", f"/reports/{ruta}/excel{consulta}", f"{base}{sufijo_nombre}.xlsx"))
        if quiere_pdf or ambos:
            acciones.append(_accion("Descargar PDF", f"/reports/{ruta}/pdf{consulta}", f"{base}{sufijo_nombre}.pdf"))
        return _respuesta(
            f"Listo, aquí está el reporte de {nombre}{cuando}.",
            acciones,
            "Es el mismo reporte del módulo de Reportes" + (", filtrado por el periodo que pediste." if consulta else "."),
        )

    return _respuesta(
        "¿De qué reporte? Tengo pedidos, pedidos con errores, inventario, clientes, indicadores, reposición y el cierre del día.",
        [
            {"tipo": "pregunta", "etiqueta": "Pedidos del mes", "texto": "reporte de pedidos del mes"},
            {"tipo": "pregunta", "etiqueta": "Inventario", "texto": "reporte de inventario"},
            {"tipo": "pregunta", "etiqueta": "Cierre del día", "texto": "cierre del día"},
        ],
        "Lista de reportes disponibles.",
    )
