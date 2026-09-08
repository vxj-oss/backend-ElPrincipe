from typing import Generator, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import Usuario
from app.services.user_service import UserService

# auto_error=False: permite que la cookie httpOnly sea la vía principal de
# autenticación del navegador; el header Authorization sigue disponible como
# respaldo (usado por Swagger UI / clientes API no-browser).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login-swagger", auto_error=False)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    header_token: Optional[str] = Depends(oauth2_scheme),
) -> Usuario:
    token = request.cookies.get(settings.COOKIE_NAME) or header_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo validar el identificador del usuario",
        )
    user = UserService.get_by_id(db, user_id_int)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    return user


def get_current_active_user(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    if not current_user.esta_activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario se encuentra inactivo",
        )
    return current_user


def get_current_active_admin(
    current_user: Usuario = Depends(get_current_active_user),
) -> Usuario:
    if current_user.rol != "administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos insuficientes. Se requiere rol de administrador.",
        )
    return current_user