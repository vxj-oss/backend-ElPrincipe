import re
from typing import Any, Dict, List, Optional

from app.agent.order_phrasing import SIN_ACENTOS, normalizar_orden

CONECTORES = re.compile(
    r"(?:[,;.]\s*|\s+)(?:y\s+)?(?:luego|despues|a continuacion|acto seguido|posteriormente|enseguida|por ultimo|finalmente|y de ahi)\b[,\s]*"
    r"|\s+y\s+(?=(?:haz|hazla|hazlo|conviert|pasa|aprueb|descarg|imprim|entreg|despach|mand|envi)\w*(?:la|lo|las|los|le|me)\b)",
    re.IGNORECASE,
)
ARRANQUE_PASO = re.compile(
    r"^(?:arm|haz|hag|hac|cre|gener|registr|prepar|elabor|cotiz|conviert|pas|aprueb|confirm|cancel|anul|entreg|despach"
    r"|descarg|imprim|mand|envi|repon|cambi|actualiz|elimin|borr|agreg|quit|muestr|dame|dime|cuant|que |cual|ver |graf"
    r"|compar|report|marc|dale|anot|ingres|levant|sac)",
    re.IGNORECASE,
)
PAT_PEDIDO = re.compile(r"\bpedido\b")
PAT_TICKET = re.compile(r"\bticket\b")
PAT_PDF = re.compile(r"\bpdf\b|\bdescarg\w*|\bimprim\w*|\bcomprobante\b")
PAT_APROBAR = re.compile(r"\baprueb\w*|\bconfirm\w*")
PAT_ENTREGAR = re.compile(r"\bentreg\w*|\bdespach\w*")
CODIGO = re.compile(r"\b(?:ped|cot)-\w+", re.IGNORECASE)
MAX_PASOS = 4


def separar_pasos(prompt: str) -> List[str]:
    plano = prompt.translate(SIN_ACENTOS)
    cortes = [(m.start(), m.end()) for m in CONECTORES.finditer(plano)]
    if not cortes:
        return [prompt]
    pasos: List[str] = []
    inicio = 0
    for desde, hasta in cortes:
        pasos.append(prompt[inicio:desde])
        inicio = hasta
    pasos.append(prompt[inicio:])
    pasos = [p.strip(" ,;.") for p in pasos if p.strip(" ,;.")]
    if len(pasos) < 2 or len(pasos) > MAX_PASOS:
        return [prompt]
    if len(pasos[0].split()) < 3:
        return [prompt]
    for paso in pasos[1:]:
        if not ARRANQUE_PASO.match(paso.translate(SIN_ACENTOS).strip()):
            return [prompt]
    return pasos


def es_escritura(datos: Optional[Dict[str, Any]]) -> bool:
    tipo = (datos or {}).get("tipo") or ""
    return tipo.startswith("borrador_") or tipo.startswith("accion_")


def _corto(texto: str) -> str:
    texto = texto.strip()
    return (texto[:1].upper() + texto[1:])[:48]


def clasificar_restantes(pasos: List[str], datos: Dict[str, Any]) -> List[Dict[str, Any]]:
    tipo = datos.get("tipo")
    resultado: List[Dict[str, Any]] = []
    for paso in pasos:
        clasificado = clasificar_paso(paso, {"tipo": tipo})
        resultado.append(clasificado)
        if clasificado["etiqueta"] == "Convertir en pedido":
            tipo = "borrador_pedido"
    return resultado


def clasificar_paso(paso: str, datos_previos: Dict[str, Any]) -> Dict[str, Any]:
    limpio = paso.translate(SIN_ACENTOS).lower()
    tipo = datos_previos.get("tipo")
    tiene_codigo = bool(CODIGO.search(limpio))
    if tipo == "borrador_cotizacion" and not tiene_codigo:
        if PAT_PEDIDO.search(limpio):
            return {"texto": "Hazle el pedido de la cotización {codigo}", "etiqueta": "Convertir en pedido", "espera": "cotizacion"}
        if PAT_PDF.search(limpio):
            return {"texto": "descarga el pdf de la cotización {codigo}", "etiqueta": "Descargar PDF", "espera": "cotizacion"}
    if tipo == "borrador_pedido" and not tiene_codigo:
        if PAT_TICKET.search(limpio):
            return {"texto": "descarga el ticket del pedido {codigo}", "etiqueta": "Descargar ticket", "espera": "pedido"}
        if PAT_PDF.search(limpio):
            return {"texto": "descarga el pdf del pedido {codigo}", "etiqueta": "Descargar PDF", "espera": "pedido"}
        if PAT_ENTREGAR.search(limpio):
            return {"texto": "marca el pedido {codigo} como entregado", "etiqueta": "Marcar como entregado", "espera": "pedido"}
        if PAT_APROBAR.search(limpio):
            return {"texto": "aprueba el pedido {codigo}", "etiqueta": "Aprobar pedido", "espera": "pedido"}
    return {"texto": normalizar_orden(paso), "etiqueta": _corto(paso), "espera": None}
