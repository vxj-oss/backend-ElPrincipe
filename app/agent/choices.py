from typing import Any, Dict, List, Optional, Tuple

MAX_OPCIONES = 8


def datos_opciones(
    opciones: List[Tuple[str, str]], explicacion: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    datos: Dict[str, Any] = {
        "tipo": "opciones",
        "opciones": [{"etiqueta": etiqueta, "consulta": consulta} for etiqueta, consulta in opciones[:MAX_OPCIONES]],
    }
    if explicacion:
        datos["explicacion"] = explicacion
    return datos


def respuesta_opciones(
    texto: str, opciones: List[Tuple[str, str]], explicacion: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return {"respuesta": texto, "datos_estructurados": datos_opciones(opciones, explicacion)}


def opciones_de_clientes(dudosos, consulta_base: str) -> List[Tuple[str, str]]:
    return [(c.razon_social, f"{consulta_base} {c.razon_social}") for c in dudosos]
