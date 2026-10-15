from typing import Dict

METAS_INDICADORES = {
    "NCCA": {"verde_desde": 13, "naranja_desde": 7},
    "NPP": {"verde_desde": 12, "naranja_desde": 7},
    "TPTD": {"verde_antes_de": 180, "naranja_hasta": 360},
}


def color_conteo(sigla: str, valor: float) -> str:
    metas = METAS_INDICADORES[sigla]
    if valor >= metas["verde_desde"]:
        return "verde"
    if valor >= metas["naranja_desde"]:
        return "naranja"
    return "rojo"


def color_tiempo(segundos: float) -> str:
    metas = METAS_INDICADORES["TPTD"]
    if segundos < metas["verde_antes_de"]:
        return "verde"
    if segundos <= metas["naranja_hasta"]:
        return "naranja"
    return "rojo"


def descripcion_conteo(sigla: str, unidad: str) -> Dict[str, str]:
    metas = METAS_INDICADORES[sigla]
    verde = metas["verde_desde"]
    naranja = metas["naranja_desde"]
    return {
        "meta": f"{verde} o más {unidad} por día",
        "rangos": f"verde: {verde} o más; naranja: de {naranja} a {verde - 1}; rojo: menos de {naranja}",
    }


def descripcion_tiempo() -> Dict[str, str]:
    metas = METAS_INDICADORES["TPTD"]
    verde = metas["verde_antes_de"]
    naranja = metas["naranja_hasta"]
    return {
        "meta": f"menos de {verde} segundos",
        "rangos": f"verde: menos de {verde} s; naranja: de {verde} a {naranja} s; rojo: más de {naranja} s",
    }
