from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.user import Usuario
from app.schemas.auth import LoginRequest, Token, UserAuthResponse
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import AuthService
from app.services.history_service import HistoryService
from app.services.user_service import UserService

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
    usuario = UserService.get_by_username(db, credentials.nombre_usuario)
    if usuario:
        HistoryService.log(
            db, "INICIAR_SESION", "Auth", usuario.id,
            {"entidad": usuario.nombre_usuario, "descripcion": f"{usuario.nombre_completo} inició sesión"},
            request.client.host if request.client else None,
        )
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


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Auto-registro de asesor comercial",
)
@limiter.limit("5/minute")
def register(
    request: Request,
    user_in: UserCreate,
    db: Session = Depends(get_db),
):
    user_in.rol = "asesor_comercial"
    user_in.esta_activo = True
    new_user = UserService.create(db, user_in)
    HistoryService.log(
        db,
        "CREAR",
        "Auth",
        new_user.id,
        {
            "entidad": new_user.correo,
            "descripcion": f"Auto-registro de asesor comercial: {new_user.nombre_completo}",
        },
        request.client.host if request.client else None,
    )
    return new_user


@router.post("/logout", summary="Cerrar sesión")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path="/",
        secure=settings.ENVIRONMENT == "production",
        samesite=settings.COOKIE_SAMESITE,
    )
    HistoryService.log(
        db, "CERRAR_SESION", "Auth", current_user.id,
        {"entidad": current_user.nombre_usuario, "descripcion": f"{current_user.nombre_completo} cerró sesión"},
        request.client.host if request.client else None,
    )
    return {"message": "Sesión cerrada correctamente"}


@router.get("/me", response_model=UserAuthResponse, summary="Obtener usuario autenticado")
def get_me(current_user: Usuario = Depends(get_current_active_user)):
    return current_user
