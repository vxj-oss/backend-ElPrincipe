import re
import unicodedata
from datetime import date, timedelta
from typing import List, Optional, Tuple

from app.core.time import ahora_lima

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
NOMBRES_MES = "|".join(MESES)
MAX_DIAS_RANGO = 366

PAT_NUMERICO = re.compile(
    r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*(?:al|a|hasta|-)\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?"
)
PAT_DEL_AL_MES = re.compile(
    rf"\b(?:del|desde el|desde)\s+(\d{{1,2}})(?:\s+de\s+({NOMBRES_MES}))?\s+(?:al|hasta el|hasta|a)\s+(?:el\s+)?(\d{{1,2}})\s+de\s+({NOMBRES_MES})(?:\s+(?:de|del)\s+(\d{{4}}))?"
)
PAT_ENTRE = re.compile(
    rf"\bentre\s+el\s+(\d{{1,2}})\s+y\s+el\s+(\d{{1,2}})\s+de\s+({NOMBRES_MES})(?:\s+(?:de|del)\s+(\d{{4}}))?"
)
PAT_DIA_MES = re.compile(rf"\b(?:el\s+(?:dia\s+)?)?(\d{{1,2}})\s+de\s+({NOMBRES_MES})(?:\s+(?:de|del)\s+(\d{{4}}))?")
PAT_DIA_NUMERICO = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
PAT_MES_SOLO = re.compile(rf"\b(?:(?:el\s+)?mes\s+(?:de\s+)?)?({NOMBRES_MES})(?:\s+(?:de|del)\s+(\d{{4}}))?\b")


def _sin_acentos(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in base if not unicodedata.combining(c)).lower()


def _anio(valor: Optional[str], hoy: date) -> int:
    if not valor:
        return hoy.year
    n = int(valor)
    return 2000 + n if n < 100 else n


def _fecha(anio: int, mes: int, dia: int) -> Optional[date]:
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def nombre_rango(inicio: date, fin: date) -> str:
    return f"rango:{inicio.isoformat()}:{fin.isoformat()}"


def _validar(inicio: Optional[date], fin: Optional[date], hoy: date) -> Optional[str]:
    if not inicio or not fin:
        return None
    if inicio > fin:
        inicio, fin = fin, inicio
    if inicio > hoy:
        return None
    fin = min(fin, hoy)
    if (fin - inicio).days + 1 > MAX_DIAS_RANGO:
        return None
    return nombre_rango(inicio, fin)


def _mes_completo(mes: int, anio: Optional[str], hoy: date) -> Optional[str]:
    if anio:
        año = _anio(anio, hoy)
    else:
        año = hoy.year if mes <= hoy.month else hoy.year - 1
    inicio = date(año, mes, 1)
    siguiente = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    return _validar(inicio, siguiente - timedelta(days=1), hoy)


def extraer_rangos(prompt: str) -> Tuple[List[str], str]:
    hoy = ahora_lima().date()
    texto = _sin_acentos(prompt)
    rangos: List[str] = []

    def reservar(coincidencia: "re.Match[str]", nombre: Optional[str]) -> None:
        nonlocal texto
        if nombre is None:
            return
        marcador = f" fecha{len(rangos)} "
        rangos.append(nombre)
        texto = texto[: coincidencia.start()] + marcador + " " * max(0, len(coincidencia.group(0)) - len(marcador)) + texto[coincidencia.end():]

    for patron in (PAT_NUMERICO, PAT_DEL_AL_MES, PAT_ENTRE):
        while True:
            m = patron.search(texto)
            if not m:
                break
            if patron is PAT_NUMERICO:
                d1, m1, a1, d2, m2, a2 = m.groups()
                inicio = _fecha(_anio(a1 or a2, hoy), int(m1), int(d1))
                fin = _fecha(_anio(a2 or a1, hoy), int(m2), int(d2))
            elif patron is PAT_DEL_AL_MES:
                d1, mes1, d2, mes2, anio = m.groups()
                mes_fin = MESES[mes2]
                mes_ini = MESES[mes1] if mes1 else mes_fin
                año_fin = _anio(anio, hoy) if anio else (hoy.year if mes_fin <= hoy.month else hoy.year - 1)
                año_ini = año_fin - 1 if mes_ini > mes_fin else año_fin
                inicio = _fecha(año_ini, mes_ini, int(d1))
                fin = _fecha(año_fin, mes_fin, int(d2))
            else:
                d1, d2, mes, anio = m.groups()
                año = _anio(anio, hoy) if anio else (hoy.year if MESES[mes] <= hoy.month else hoy.year - 1)
                inicio = _fecha(año, MESES[mes], int(d1))
                fin = _fecha(año, MESES[mes], int(d2))
            nombre = _validar(inicio, fin, hoy)
            if nombre is None:
                texto = texto[: m.start()] + " " * (m.end() - m.start()) + texto[m.end():]
                continue
            reservar(m, nombre)

    for patron in (PAT_DIA_MES, PAT_DIA_NUMERICO):
        while True:
            m = patron.search(texto)
            if not m:
                break
            if patron is PAT_DIA_MES:
                dia, mes, anio = m.groups()
                año = _anio(anio, hoy) if anio else (hoy.year if MESES[mes] <= hoy.month else hoy.year - 1)
                fecha = _fecha(año, MESES[mes], int(dia))
            else:
                dia, mes, anio = m.groups()
                fecha = _fecha(_anio(anio, hoy), int(mes), int(dia))
            nombre = _validar(fecha, fecha, hoy)
            if nombre is None:
                texto = texto[: m.start()] + " " * (m.end() - m.start()) + texto[m.end():]
                continue
            reservar(m, nombre)

    while True:
        m = PAT_MES_SOLO.search(texto)
        if not m:
            break
        nombre = _mes_completo(MESES[m.group(1)], m.group(2), hoy)
        if nombre is None:
            texto = texto[: m.start()] + " " * (m.end() - m.start()) + texto[m.end():]
            continue
        reservar(m, nombre)

    return rangos, texto
