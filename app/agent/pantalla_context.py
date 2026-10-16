import re
from typing import Any, Dict, Optional

from app.services.quote_note_service import normalizar

PAT_DEICTICO_CLIENTE = re.compile(r"(?i)\b(?:este|ese|dicho|actual)\s+cliente\b|\bel cliente (?:actual|abierto|seleccionado)\b")
PAT_DEICTICO_PEDIDO = re.compile(r"(?i)\b(?:este|ese|dicho|actual)\s+pedido\b|\bel pedido (?:actual|abierto|seleccionado)\b")
PAT_DEICTICO_PRODUCTO = re.compile(r"(?i)\b(?:este|ese|dicho|actual)\s+producto\b")

PAT_CLIENTE_IMPLICITO = re.compile(
    r"\bsu (?:telefono|correo|direccion|celular|ficha|historial|ticket)\b"
    r"|\bcuando (?:fue )?(?:la )?(?:ultima vez )?(?:que )?(?:compro|pidio)\b|\bultima compra\b"
    r"|\bcuanto (?:ha |me )?(?:compro|comprado|gastado|compra)\b|\bque (?:lleva|compra|suele)\b"
    r"|\bresumen\b|\bficha\b|\bcotizaciones? pendientes?\b|\bsus (?:compras|pedidos|cotizaciones)\b"
    r"|\bcomo (?:viene|va|esta)\b|\bticket promedio\b|\bcondicion(?:es)?\b|\bsuele\b"
)
PAT_COTIZAR_IMPLICITO = re.compile(
    r"\bhazle\b|\bcotizale\b|\barmale\b|\b(?:arma|crea|haz|genera|prepara)\w*\b[^.\n]{0,25}\bcotizacion\b"
    r"|\bcotiza\b|\blo mismo\b|\brepite\b|\brepiteme\b"
)
PAT_ACCION_CLIENTE = re.compile(
    r"\b(?:desactiv\w+|reactiv\w+|deshabilit\w+|elimin\w+|borra\w*|renombr\w+|corrige\w*)\b"
    r"|\b(?:telefono|celular|correo|email|direccion|distrito|vip|ruc|dni)\b"
)
PAT_CONDICION_IMPLICITA = re.compile(
    r"\b(?:ponle|dale|quitale|eliminale|cambiale|pactale|asignale|otorgale|sacale)\b"
    r"|\b(?:descuento|credito|forma de pago|condicion(?:es)?)\b"
)
PAT_PEDIDO_IMPLICITO = re.compile(
    r"\b(?:pdf|ticket|comprobante|descarga\w*|imprim\w*|estado|detalle|total|cuanto|entregado|aprobado|cancel\w*|"
    r"pasalo|marcalo|aprobalo|entregalo|cancelalo|anulalo|confirmalo|cual es|que tiene|que lleva|quien|"
    r"cambiale|quitale|agregale|sumale|subele|bajale|ponle|cambia\w*|quita\w*|agrega\w*|suma\w*|sube\w*|baja\w*)\b"
)
PAT_PRODUCTO_IMPLICITO = re.compile(r"\b(?:stock|precio|cuesta|vale|cuanto (?:queda|hay)|disponible|repon\w*|queda)\b")

CLITICOS = {
    "pasalo": "pasa", "marcalo": "marca", "aprobalo": "aprueba", "entregalo": "entrega",
    "cancelalo": "cancela", "anulalo": "anula", "confirmalo": "confirma",
}


def _incluye_nombre(limpio: str, nombre: str) -> bool:
    palabras = [t for t in normalizar(nombre).split() if len(t) >= 4]
    return bool(palabras) and sum(1 for t in palabras if t in limpio.split()) >= max(1, len(palabras) // 2)


def aplicar_pantalla(prompt: str, pantalla: Optional[Dict[str, Any]]) -> str:
    if not isinstance(pantalla, dict):
        return prompt
    entidad = pantalla.get("entidad")
    if not isinstance(entidad, dict):
        return prompt
    tipo = entidad.get("tipo")
    limpio = normalizar(prompt)

    if tipo == "cliente" and entidad.get("nombre"):
        nombre = str(entidad["nombre"])
        reemplazado, cambios = PAT_DEICTICO_CLIENTE.subn(nombre, prompt)
        if cambios:
            return reemplazado
        if _incluye_nombre(limpio, nombre):
            return prompt
        if PAT_ACCION_CLIENTE.search(limpio) and not re.search(r"\b(?:descuento|credito|condicion)\b", limpio):
            return f"{prompt} del cliente {nombre}"
        if PAT_COTIZAR_IMPLICITO.search(limpio) or PAT_CONDICION_IMPLICITA.search(limpio):
            return f"{prompt} para {nombre}"
        if PAT_CLIENTE_IMPLICITO.search(limpio):
            return f"{prompt} de {nombre}"
        return prompt

    if tipo == "pedido" and entidad.get("codigo"):
        codigo = str(entidad["codigo"])
        if re.search(r"(?i)\bPED-[0-9A-Za-z]{3,12}\b", prompt):
            return prompt
        reemplazado, cambios = PAT_DEICTICO_PEDIDO.subn(f"pedido {codigo}", prompt)
        if cambios:
            return reemplazado
        if PAT_PEDIDO_IMPLICITO.search(limpio) and not re.search(r"\bcliente\b", limpio):
            texto = limpio if any(re.search(rf"\b{c}\b", limpio) for c in CLITICOS) else prompt
            for clitico, verbo in CLITICOS.items():
                texto = re.sub(rf"\b{clitico}\b", verbo, texto)
            return f"{texto} pedido {codigo}"
        return prompt

    if tipo == "producto" and entidad.get("nombre"):
        nombre = str(entidad["nombre"])
        reemplazado, cambios = PAT_DEICTICO_PRODUCTO.subn(nombre, prompt)
        if cambios:
            return reemplazado
        if PAT_PRODUCTO_IMPLICITO.search(limpio) and not _incluye_nombre(limpio, nombre):
            return f"{prompt} de {nombre}"
    return prompt
