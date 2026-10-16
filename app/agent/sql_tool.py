import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Set

from sqlalchemy import Boolean, Date, DateTime, Enum, Integer, Numeric, String, Text
from sqlalchemy.exc import DBAPIError

from app.core.database import engine
from app.models.base import Base
import app.models  # noqa: F401

MAX_FILAS = 50
TIMEOUT_MS = 4000
MAX_LARGO_SQL = 2500

TABLAS_NUNCA = {"mensajes_agente", "sesiones_agente", "decisiones_comerciales"}
TABLAS_FUERA_DEL_ESQUEMA = {"opciones_condicion_comercial", "fallas_condiciones_comerciales", "configuracion_sistema", "registros_indicador"}
COLUMNAS_OMITIDAS_EN_ESQUEMA = {"creado_en", "actualizado_en", "descripcion"}
TABLAS_SOLO_ADMIN = {"usuarios", "historial_auditoria"}
COLUMNAS_NUNCA = {"clave_hash"}
COLUMNAS_SOLO_ADMIN = {"precio_costo"}

PAT_PROHIBIDAS = re.compile(
    r"\b(?:insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|execute|vacuum|analyze|"
    r"reindex|cluster|listen|notify|lock|refresh|merge|into|set_config|current_setting|information_schema|"
    r"pg_[a-z_]+|lo_[a-z_]+|dblink|nextval|setval|txid_[a-z_]+)\b"
)
PAT_FOR_UPDATE = re.compile(r"\bfor\s+(?:update|share|no\s+key|key\s+share)\b")
PAT_INICIO = re.compile(r"^\s*(?:select|with)\b")
PAT_ASTERISCO = re.compile(r"\bselect\s+(?:distinct\s+)?\*|,\s*\*|\b\w+\.\*")
PAT_COUNT_ASTERISCO = re.compile(r"count\s*\(\s*\*\s*\)")


class ErrorConsulta(Exception):
    pass


def _tablas_visibles(es_admin: bool) -> Set[str]:
    todas = set(Base.metadata.tables)
    visibles = todas - TABLAS_NUNCA
    if not es_admin:
        visibles -= TABLAS_SOLO_ADMIN
    return visibles


def _columnas_ocultas(es_admin: bool) -> Set[str]:
    return COLUMNAS_NUNCA | (set() if es_admin else COLUMNAS_SOLO_ADMIN)


def _tipo_corto(columna) -> str:
    tipo = columna.type
    if isinstance(tipo, Enum):
        return "enum[" + "|".join(tipo.enums) + "]"
    if isinstance(tipo, Boolean):
        return "bool"
    if isinstance(tipo, Integer):
        return "int"
    if isinstance(tipo, Numeric):
        return "num"
    if isinstance(tipo, (String, Text)):
        return "text"
    if isinstance(tipo, DateTime):
        return "tstz"
    if isinstance(tipo, Date):
        return "date"
    return "json"


_cache_esquema: Dict[bool, str] = {}


def esquema_texto(es_admin: bool) -> str:
    if es_admin in _cache_esquema:
        return _cache_esquema[es_admin]
    ocultas = _columnas_ocultas(es_admin)
    lineas: List[str] = []
    for nombre in sorted(_tablas_visibles(es_admin) - TABLAS_FUERA_DEL_ESQUEMA):
        tabla = Base.metadata.tables[nombre]
        columnas = []
        for columna in tabla.columns:
            if columna.name in ocultas or columna.name in COLUMNAS_OMITIDAS_EN_ESQUEMA:
                continue
            destino = ""
            for fk in columna.foreign_keys:
                destino = f"→{fk.column.table.name}"
                break
            columnas.append(f"{columna.name} {_tipo_corto(columna)}{destino}")
        lineas.append(f"{nombre}({', '.join(columnas)})")
    texto = "\n".join(lineas)
    _cache_esquema[es_admin] = texto
    return texto


def contexto_sql(es_admin: bool) -> str:
    return (
        "\n\nEsquema de la base de datos PostgreSQL para la herramienta consultar_base_datos "
        "(tabla(columna tipo→tabla_referenciada)):\n"
        f"{esquema_texto(es_admin)}\n"
        "Notas: las ventas confirmadas son pedidos con estado Aprobado o Entregado; los montos están en soles; "
        "las fechas son timestamptz en UTC, usa (fecha AT TIME ZONE 'America/Lima') para fechas de Lima; "
        "los clientes se unen con pedidos.cliente_id, los productos con detalles_pedido.producto_id."
    )


def validar(sql: str, es_admin: bool) -> str:
    texto = (sql or "").strip()
    if not texto:
        raise ErrorConsulta("La consulta está vacía.")
    if len(texto) > MAX_LARGO_SQL:
        raise ErrorConsulta("La consulta es demasiado larga; simplifícala.")
    if texto.endswith(";"):
        texto = texto[:-1].rstrip()
    if ";" in texto:
        raise ErrorConsulta("Solo se permite una consulta a la vez.")
    if "--" in texto or "/*" in texto:
        raise ErrorConsulta("No se permiten comentarios en la consulta.")

    bajo = texto.lower()
    if not PAT_INICIO.match(bajo):
        raise ErrorConsulta("Solo se permiten consultas SELECT de lectura.")
    if PAT_PROHIBIDAS.search(bajo) or PAT_FOR_UPDATE.search(bajo):
        raise ErrorConsulta("La consulta contiene operaciones no permitidas; solo se permite leer datos.")

    tokens = set(re.findall(r"[a-z_][a-z0-9_]*", bajo))
    todas = set(Base.metadata.tables)
    visibles = _tablas_visibles(es_admin)
    for tabla in todas:
        if tabla in tokens and tabla not in visibles:
            if tabla in TABLAS_SOLO_ADMIN and not es_admin:
                raise ErrorConsulta(f"La tabla «{tabla}» solo está disponible para administradores.")
            raise ErrorConsulta(f"La tabla «{tabla}» no está disponible para consultas.")
    for columna in _columnas_ocultas(es_admin):
        if columna in tokens:
            if columna in COLUMNAS_NUNCA:
                raise ErrorConsulta("Esa columna no está disponible.")
            raise ErrorConsulta("Los costos y márgenes solo están disponibles para administradores.")

    sin_conteo = PAT_COUNT_ASTERISCO.sub("count(1)", bajo)
    if PAT_ASTERISCO.search(sin_conteo) and (("usuarios" in tokens) or ("productos" in tokens and not es_admin)):
        raise ErrorConsulta("Escribe las columnas explícitamente en vez de usar *.")
    return texto


def _valor(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def ejecutar(sql: str, es_admin: bool) -> Dict[str, Any]:
    try:
        consulta = validar(sql, es_admin)
    except ErrorConsulta as exc:
        return {"error": str(exc)}

    try:
        with engine.connect() as conexion:
            with conexion.begin():
                conexion.exec_driver_sql("SET TRANSACTION READ ONLY")
                conexion.exec_driver_sql(f"SET LOCAL statement_timeout = {TIMEOUT_MS}")
                resultado = conexion.exec_driver_sql(
                    f"SELECT * FROM ({consulta}) AS consulta_agente LIMIT {MAX_FILAS + 1}"
                )
                columnas = list(resultado.keys())
                filas = resultado.fetchall()
    except DBAPIError as exc:
        detalle = str(getattr(exc, "orig", exc)).strip().splitlines()[0][:300]
        return {"error": f"Error al ejecutar la consulta: {detalle}"}
    except Exception as exc:
        return {"error": f"No se pudo ejecutar la consulta: {str(exc)[:200]}"}

    truncado = len(filas) > MAX_FILAS
    filas = filas[:MAX_FILAS]
    return {
        "columnas": columnas,
        "filas": [{c: _valor(v) for c, v in zip(columnas, fila)} for fila in filas],
        "truncado": truncado,
        "nota": f"Se muestran las primeras {MAX_FILAS} filas." if truncado else None,
    }
