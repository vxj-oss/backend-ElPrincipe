import re
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.tools import CommercialTools
from app.core.metas import METAS_INDICADORES, color_conteo, color_tiempo
from app.core.time import ahora_lima
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.services import analytics_service as an
from app.services.activity_indicator_service import ActivityIndicatorService
from app.services.quote_note_service import normalizar

PAT_INDICADOR = re.compile(
    r"\b(?:ncca|npp|tptd|indicadores?|cotizaciones atendidas|pedidos procesados|"
    r"tiempo (?:promedio )?(?:de )?(?:toma de )?decision)\b"
)
PAT_GRAFICO = re.compile(r"\bgrafic\w*\b|\bevolucion\b|\btendencia\b|\bhistorico\b|\bcomo (?:han|ha) ido\b")
PAT_RECOMENDAR = re.compile(
    r"\b(?:por ?que|que hago|que puedo hacer|como (?:mejoro|mejorar|subo|subir|bajo|bajar|aumento|aumentar|reduzco|reducir|"
    r"salgo|salir)|mejorar|mejora|recomend\w*|que (?:me )?(?:sugieres|aconsejas)|consejos?|estrategias?|"
    r"en rojo|en naranja|no llego|no alcanzo|llegar a la meta)\b"
)
PAT_DIAS = re.compile(r"\b(\d{1,2})\s+dias\b")
MAX_DIAS = 31
DIAS_POR_DEFECTO = 7
COLOR_META = "linea"
SOLO_EXPLICAR = re.compile(r"\b(?:que es|que significa|explic\w*|como se (?:calcula|mide)|formula|definicion)\b")


def _foco(limpio: str) -> Optional[str]:
    if re.search(r"\bncca\b|\bcotizaciones atendidas\b", limpio):
        return "NCCA"
    if re.search(r"\bnpp\b|\bpedidos procesados\b", limpio):
        return "NPP"
    if re.search(r"\btptd\b|\btiempo (?:promedio )?(?:de )?(?:toma de )?decision\b", limpio):
        return "TPTD"
    return None


def _dias(limpio: str) -> int:
    coincidencia = PAT_DIAS.search(limpio)
    if coincidencia:
        return max(2, min(MAX_DIAS, int(coincidencia.group(1))))
    if re.search(r"\bquincena\b", limpio):
        return 15
    if re.search(r"\bmes\b", limpio):
        return 30
    return DIAS_POR_DEFECTO


def _explicacion(resumen: str, fuentes: List[str], formula: Optional[str], periodo: str) -> Dict[str, Any]:
    return {"resumen": resumen, "fuentes": fuentes, "formula": formula, "periodo": periodo}


def _grafico_indicador(db: Session, foco: Optional[str], dias: int) -> Dict[str, Any]:
    serie = ActivityIndicatorService.get_serie_dias(db, dias)
    etiquetas = [d["fecha_completa"][:5] for d in serie]
    rango_texto = f"{serie[0]['fecha_completa']} al {serie[-1]['fecha_completa']}"
    fuentes = ["Cotizaciones atendidas por día", "Pedidos procesados por día", "Tiempo entre abrir el registro y aprobar el pedido"]

    if foco == "TPTD":
        valores = [round(d["tiempo_promedio_decision_segundos"]) if d.get("tiempo_promedio_decision_segundos") is not None else None for d in serie]
        con_dato = [(d["fecha_completa"][:5], v) for d, v in zip(serie, valores) if v is not None]
        meta = METAS_INDICADORES["TPTD"]["verde_antes_de"]
        if not con_dato:
            return {"respuesta": f"No hay pedidos aprobados con tiempo de decisión en los últimos {dias} días.", "datos_estructurados": None}
        promedio = sum(v for _, v in con_dato) / len(con_dato)
        mejor = min(con_dato, key=lambda x: x[1])
        peor = max(con_dato, key=lambda x: x[1])
        verdes = sum(1 for _, v in con_dato if color_tiempo(v) == "verde")
        texto = (
            f"Tiempo promedio de decisión (TPTD) de los últimos {dias} días ({rango_texto}): "
            f"promedio {promedio:.0f} s sobre {len(con_dato)} días con datos. Meta: menos de {meta} s.\n"
            f"Mejor día: {mejor[0]} con {mejor[1]} s. Día más lento: {peor[0]} con {peor[1]} s. "
            f"Días en verde: {verdes} de {len(con_dato)}."
        )
        datos = {
            "tipo": "grafico",
            "grafico": "line",
            "horizontal": False,
            "titulo": f"TPTD por día, en segundos (últimos {dias} días)",
            "labels": etiquetas,
            "series": [
                {"nombre": "TPTD (s)", "valores": valores},
                {"nombre": f"Meta (< {meta} s)", "valores": [meta] * len(etiquetas), "tipo": COLOR_META},
            ],
            "prefijo": "",
            "explicacion": _explicacion(
                "Promedio, por día, del tiempo entre abrir el registro de la cotización y aprobar el pedido, en segundos.",
                fuentes[2:],
                "TPTD del día = Σ (hora de aprobación − hora de apertura) ÷ pedidos aprobados del día",
                rango_texto,
            ),
        }
        return {"respuesta": texto, "datos_estructurados": datos}

    if foco in ("NCCA", "NPP"):
        clave = "solicitudes" if foco == "NCCA" else "pedidos"
        nombre = "Cotizaciones atendidas (NCCA)" if foco == "NCCA" else "Pedidos procesados (NPP)"
        meta = METAS_INDICADORES[foco]["verde_desde"]
        valores = [int(d[clave]) for d in serie]
        colores = [color_conteo(foco, v) for v in valores]
        mejor = max(range(len(valores)), key=lambda i: valores[i])
        texto = (
            f"{nombre} de los últimos {dias} días ({rango_texto}): total {sum(valores)}, promedio {sum(valores) / len(valores):.1f} por día. "
            f"Meta: {meta} o más por día.\n"
            f"Días en verde: {colores.count('verde')}, naranja: {colores.count('naranja')}, rojo: {colores.count('rojo')}. "
            f"Mejor día: {etiquetas[mejor]} con {valores[mejor]}."
        )
        datos = {
            "tipo": "grafico",
            "grafico": "bar",
            "horizontal": False,
            "titulo": f"{nombre} por día (últimos {dias} días)",
            "labels": etiquetas,
            "series": [
                {"nombre": nombre, "valores": valores},
                {"nombre": f"Meta ({meta})", "valores": [meta] * len(etiquetas), "tipo": COLOR_META},
            ],
            "prefijo": "",
            "explicacion": _explicacion(
                "Conteo diario con la meta de la tesis como línea de referencia.",
                [fuentes[0] if foco == "NCCA" else fuentes[1]],
                "NCCA = Σ cotizaciones atendidas del día" if foco == "NCCA" else "NPP = Σ pedidos procesados del día",
                rango_texto,
            ),
        }
        return {"respuesta": texto, "datos_estructurados": datos}

    ncca = [int(d["solicitudes"]) for d in serie]
    npp = [int(d["pedidos"]) for d in serie]
    tiempos = [d["tiempo_promedio_decision_segundos"] for d in serie if d.get("tiempo_promedio_decision_segundos") is not None]
    texto = (
        f"Indicadores de los últimos {dias} días ({rango_texto}):\n"
        f"• NCCA: total {sum(ncca)}, promedio {sum(ncca) / len(ncca):.1f}/día (meta {METAS_INDICADORES['NCCA']['verde_desde']}).\n"
        f"• NPP: total {sum(npp)}, promedio {sum(npp) / len(npp):.1f}/día (meta {METAS_INDICADORES['NPP']['verde_desde']}).\n"
        + (
            f"• TPTD: promedio {sum(tiempos) / len(tiempos):.0f} s en {len(tiempos)} días con datos (meta menos de {METAS_INDICADORES['TPTD']['verde_antes_de']} s)."
            if tiempos
            else "• TPTD: sin pedidos aprobados con tiempo registrado en el periodo."
        )
    )
    datos = {
        "tipo": "grafico",
        "grafico": "bar",
        "horizontal": False,
        "titulo": f"NCCA y NPP por día (últimos {dias} días)",
        "labels": etiquetas,
        "series": [
            {"nombre": "NCCA (cotizaciones)", "valores": ncca},
            {"nombre": "NPP (pedidos)", "valores": npp},
        ],
        "prefijo": "",
        "explicacion": _explicacion(
            "Conteo diario de cotizaciones atendidas y de pedidos procesados.",
            fuentes[:2],
            "NCCA = Σ cotizaciones atendidas; NPP = Σ pedidos procesados",
            rango_texto,
        ),
    }
    return {"respuesta": texto, "datos_estructurados": datos}


def _conteo(db: Session, consulta) -> int:
    return int(db.scalar(consulta) or 0)


def _recomendaciones(db: Session, foco: Optional[str]) -> Dict[str, Any]:
    datos = CommercialTools.get_indicadores_actividad(db)
    ncca, npp, tptd = datos["NCCA"], datos["NPP"], datos["TPTD"]
    inicio, fin = an.rango("hoy")
    pendientes_confirmar = _conteo(db, select(func.count(Pedido.id)).where(Pedido.estado == "Pendiente"))
    cotizaciones_hoy_pendientes = _conteo(
        db,
        select(func.count(SolicitudCliente.id)).where(
            SolicitudCliente.estado == "Pendiente",
            SolicitudCliente.fecha_solicitud >= inicio,
            SolicitudCliente.fecha_solicitud < fin,
        ),
    )
    sin_seguimiento = an.cotizaciones_sin_seguimiento(db)
    por_recomprar = len(an.cadencia_clientes(db, limite=30))

    lineas: List[str] = []
    acciones: List[Dict[str, Any]] = []

    if foco in (None, "NCCA"):
        meta = METAS_INDICADORES["NCCA"]["verde_desde"]
        if ncca["color_semaforo"] == "verde":
            lineas.append(f"• NCCA: {ncca['valor_hoy']} cotizaciones, en verde. Mantén el ritmo.")
        else:
            faltan = max(0, meta - ncca["valor_hoy"])
            lineas.append(
                f"• NCCA ({ncca['color_semaforo']}): llevas {ncca['valor_hoy']} y la meta es {meta}; te faltan {faltan}. "
                f"Hay {por_recomprar} clientes que ya están en su momento de recompra y {sin_seguimiento} cotizaciones sin seguimiento: "
                "ahí están las oportunidades más rápidas."
            )
            acciones.append({"tipo": "pregunta", "etiqueta": "Clientes por recomprar", "texto": "¿A quién le toca comprar?"})
            acciones.append({"tipo": "enlace", "etiqueta": "Abrir cotizaciones", "ruta": "/solicitudes?estado=Pendiente"})

    if foco in (None, "NPP"):
        meta = METAS_INDICADORES["NPP"]["verde_desde"]
        if npp["color_semaforo"] == "verde":
            lineas.append(f"• NPP: {npp['valor_hoy']} pedidos, en verde.")
        else:
            faltan = max(0, meta - npp["valor_hoy"])
            lineas.append(
                f"• NPP ({npp['color_semaforo']}): llevas {npp['valor_hoy']} y la meta es {meta}; te faltan {faltan}. "
                f"Tienes {cotizaciones_hoy_pendientes} cotizaciones pendientes de hoy para convertir en pedido y "
                f"{pendientes_confirmar} pedidos por confirmar."
            )
            acciones.append({"tipo": "pregunta", "etiqueta": "Pedidos por confirmar", "texto": "¿Qué pedidos están pendientes de confirmar?"})
            acciones.append({"tipo": "enlace", "etiqueta": "Abrir pedidos", "ruta": "/pedidos?estado=Pendiente"})

    if foco in (None, "TPTD"):
        meta = METAS_INDICADORES["TPTD"]["verde_antes_de"]
        valor = tptd["valor_hoy_segundos"]
        historico = tptd["promedio_historico_segundos"]
        if valor is None:
            lineas.append("• TPTD: hoy aún no hay pedidos aprobados, así que no hay tiempo del día para evaluar.")
        elif tptd["color_semaforo"] == "verde":
            lineas.append(f"• TPTD: {valor} s, en verde (meta: menos de {meta} s).")
        else:
            exceso = valor - meta
            comparacion = f" El promedio histórico es {historico} s." if historico is not None else ""
            lineas.append(
                f"• TPTD ({tptd['color_semaforo']}): {valor} s, {exceso} s por encima de la meta de {meta} s.{comparacion} "
                "Para bajarlo: arma las cotizaciones desde una nota o por el chat, usa «hazle lo mismo que la última vez» con clientes "
                "recurrentes y aprueba los pedidos apenas el cliente confirme."
            )
            acciones.append({"tipo": "pregunta", "etiqueta": "Ver gráfico del TPTD", "texto": "gráfico del TPTD de los últimos 7 días"})

    if all("en verde" in l or "no hay" in l for l in lineas):
        lineas.append("Hoy no veo indicadores en alerta. Si quieres, te muestro cómo evolucionaron estos días.")
    acciones.append({"tipo": "pregunta", "etiqueta": "Ver gráfico de indicadores", "texto": "gráfico de los indicadores de los últimos 7 días"})

    texto = "Así lo veo hoy y esto es lo que haría:\n" + "\n".join(lineas)
    return {
        "respuesta": texto,
        "datos_estructurados": {
            "tipo": "analisis",
            "acciones": acciones,
            "explicacion": _explicacion(
                "Comparé cada indicador de hoy con la meta de la tesis y revisé qué oportunidades hay abiertas: clientes por recomprar, cotizaciones sin seguimiento y pedidos pendientes.",
                [
                    "Indicadores NCCA, NPP y TPTD de hoy",
                    "Cadencia de compra de cada cliente",
                    "Cotizaciones pendientes y pedidos por confirmar",
                ],
                "Semáforo según las metas configuradas (NCCA ≥ 13, NPP ≥ 12, TPTD < 180 s)",
                f"hoy, {ahora_lima().strftime('%d/%m/%Y')}",
            ),
        },
    }


def responder_indicadores(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    if not PAT_INDICADOR.search(limpio):
        return None
    if SOLO_EXPLICAR.search(limpio) and not PAT_GRAFICO.search(limpio):
        return None
    foco = _foco(limpio)
    if PAT_GRAFICO.search(limpio):
        return _grafico_indicador(db, foco, _dias(limpio))
    if PAT_RECOMENDAR.search(limpio):
        return _recomendaciones(db, foco)
    return None
