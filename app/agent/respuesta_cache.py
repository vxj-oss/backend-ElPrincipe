import hashlib
import time
from typing import Dict, Optional, Tuple

VIGENCIA_SEGUNDOS = 300
MAX_ENTRADAS = 200

PREFIJOS_NO_CACHEABLES = (
    "El servicio",
    "La clave",
    "No se pudo",
    "El modelo tardó",
    "Ocurrió un error",
    "No pude completar",
    "Error al procesar",
)

_cache: Dict[str, Tuple[float, str]] = {}


def _clave(usuario_id: int, historial: str, prompt: str) -> str:
    base = f"{usuario_id}|{historial}|{' '.join(prompt.lower().split())}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def obtener(usuario_id: int, historial: str, prompt: str) -> Optional[str]:
    clave = _clave(usuario_id, historial, prompt)
    entrada = _cache.get(clave)
    if not entrada:
        return None
    momento, respuesta = entrada
    if time.time() - momento > VIGENCIA_SEGUNDOS:
        _cache.pop(clave, None)
        return None
    return respuesta


def guardar(usuario_id: int, historial: str, prompt: str, respuesta: str) -> None:
    if not respuesta or respuesta.startswith(PREFIJOS_NO_CACHEABLES):
        return
    if len(_cache) >= MAX_ENTRADAS:
        vencidas = [k for k, (m, _) in _cache.items() if time.time() - m > VIGENCIA_SEGUNDOS]
        for clave in vencidas or list(_cache)[: MAX_ENTRADAS // 4]:
            _cache.pop(clave, None)
    _cache[_clave(usuario_id, historial, prompt)] = (time.time(), respuesta)
