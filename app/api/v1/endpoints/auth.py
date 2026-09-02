from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.user import Usuario
from app.schemas.auth import LoginRequest, Token, UserAuthResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Autenticación"])


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


@router.post("/login", response_model=Token, summary="Login mediante JSON")
@limiter.limit("5/minute")
def login(request: Request, response: Response, credentials: LoginRequest, db: Session = Depends(get_db)):
    token = AuthService.login(db, credentials.nombre_usuario, credentials.password)
    _set_auth_cookie(response, token.access_token)
    return token


@router.post("/login-swagger", response_model=Token, summary="Login para Swagger UI")
@limiter.limit("5/minute")
def login_swagger(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    token = AuthService.login(db, form_data.username, form_data.password)
    _set_auth_cookie(response, token.access_token)
    return token


@router.post("/logout", summary="Cerrar sesión")
def logout(response: Response, current_user: Usuario = Depends(get_current_active_user)):
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path="/",
        secure=settings.ENVIRONMENT == "production",
        samesite=settings.COOKIE_SAMESITE,
    )
    return {"message": "Sesión cerrada correctamente"}


@router.get("/me", response_model=UserAuthResponse, summary="Obtener usuario autenticado")
def get_me(current_user: Usuario = Depends(get_current_active_user)):
    return current_user
