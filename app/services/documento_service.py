from typing import Any, Dict

import httpx

from app.core.config import settings

URL_BASE = "https://api.decolecta.com/v1"
TIMEOUT = 8.0


class ErrorConsultaDocumento(Exception):
    def __init__(self, mensaje: str, estado: int = 502) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado


def consultar_documento(numero: str) -> Dict[str, Any]:
    numero = (numero or "").strip()
    if not numero.isdigit() or len(numero) not in (8, 11):
        raise ErrorConsultaDocumento("Escribe un DNI de 8 dígitos o un RUC de 11 dígitos.", 400)
    token = settings.DECOLECTA_API_TOKEN
    if not token:
        raise ErrorConsultaDocumento("La consulta de RUC/DNI no está configurada en el servidor.", 503)

    es_ruc = len(numero) == 11
    ruta = "/sunat/ruc" if es_ruc else "/reniec/dni"
    try:
        respuesta = httpx.get(
            f"{URL_BASE}{ruta}",
            params={"numero": numero},
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        raise ErrorConsultaDocumento("No se pudo conectar con el servicio de consulta. Intenta de nuevo.")

    if respuesta.status_code in (400, 404, 422):
        raise ErrorConsultaDocumento("No se encontraron datos para ese número.", 404)
    if respuesta.status_code in (401, 403):
        raise ErrorConsultaDocumento("El servicio de consulta rechazó las credenciales del servidor.", 502)
    if respuesta.status_code == 429:
        raise ErrorConsultaDocumento("Se alcanzó el límite de consultas. Intenta más tarde.", 429)
    if respuesta.status_code != 200:
        raise ErrorConsultaDocumento("El servicio de consulta no respondió correctamente.")

    datos = respuesta.json()
    if es_ruc:
        return {
            "tipo": "RUC",
            "numero": numero,
            "nombre": (datos.get("razon_social") or "").strip(),
            "direccion": (datos.get("direccion") or "").strip(),
            "distrito": (datos.get("distrito") or "").strip(),
            "estado": datos.get("estado"),
            "condicion": datos.get("condicion"),
        }
    return {
        "tipo": "DNI",
        "numero": numero,
        "nombre": (datos.get("full_name") or "").strip(),
        "direccion": "",
        "distrito": "",
        "estado": None,
        "condicion": None,
    }
