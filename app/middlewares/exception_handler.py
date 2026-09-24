import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.middlewares.exception_handler")


def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos los manejadores globales de excepciones en la instancia de FastAPI."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Captura errores HTTP lanzados explícitamente (400, 401, 403, 404, etc.)."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "status_code": exc.status_code,
                "error": {
                    "tipo": "HTTPException",
                    "mensaje": exc.detail,
                    "ruta": str(request.url.path),
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Captura errores de validación de datos en esquemas Pydantic / payloads."""
        detalles = []
        for error in exc.errors():
            campo = " -> ".join([str(loc) for loc in error.get("loc", [])])
            detalles.append(
                {
                    "campo": campo,
                    "mensaje": error.get("msg"),
                    "tipo": error.get("type"),
                }
            )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "error": {
                    "tipo": "ValidationError",
                    "mensaje": "Error de validación en los datos enviados",
                    "detalles": detalles,
                    "ruta": str(request.url.path),
                },
            },
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        """Captura el límite de solicitudes por IP excedido (slowapi)."""
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "success": False,
                "status_code": status.HTTP_429_TOO_MANY_REQUESTS,
                "error": {
                    "tipo": "RateLimitExceeded",
                    "mensaje": "Demasiadas solicitudes. Intenta nuevamente en unos momentos.",
                    "ruta": str(request.url.path),
                },
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        """Captura errores de clave duplicada, llaves foráneas inexistentes o restricciones únicas en BD."""
        logger.error(f"IntegrityError en {request.url.path}: {exc.orig}")

        detalle_sql = str(getattr(exc, "orig", "")).lower()
        es_borrado = request.method == "DELETE"
        referencia = (
            "fkey" in detalle_sql
            or "foreign key" in detalle_sql
            or "foránea" in detalle_sql
            or "foranea" in detalle_sql
            or "referencia" in detalle_sql
        )
        if referencia or (es_borrado and ("not null" in detalle_sql or "no nulo" in detalle_sql)):
            mensaje_usuario = (
                "El registro está siendo utilizado por otros datos del sistema "
                "y no puede eliminarse. Intenta desactivarlo en su lugar."
            )
        elif "unique" in detalle_sql or "duplicate key" in detalle_sql or "llave duplicada" in detalle_sql:
            mensaje_usuario = "Ya existe un registro con esos mismos datos."
        elif "not null" in detalle_sql or "no nulo" in detalle_sql:
            mensaje_usuario = "Faltan datos obligatorios para completar la operación."
        else:
            mensaje_usuario = "Conflicto de integridad en la base de datos."

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "status_code": status.HTTP_409_CONFLICT,
                "error": {
                    "tipo": "DatabaseIntegrityError",
                    "mensaje": mensaje_usuario,
                    "ruta": str(request.url.path),
                },
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        """Captura fallas generales de la base de datos."""
        logger.error(f"SQLAlchemyError en {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "error": {
                    "tipo": "DatabaseError",
                    "mensaje": "Ocurrió un problema de comunicación con la base de datos.",
                    "ruta": str(request.url.path),
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Captura cualquier excepción no controlada (código 500) evitando caída del servidor."""
        logger.exception(f"Excepción no controlada en {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "error": {
                    "tipo": "InternalServerError",
                    "mensaje": "Ocurrió un error inesperado en el servidor.",
                    "ruta": str(request.url.path),
                },
            },
        )