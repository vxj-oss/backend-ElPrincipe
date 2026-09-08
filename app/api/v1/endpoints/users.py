from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin, get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.user import PasswordChangeRequest, UserResponse, UserUpdate
from app.services.history_service import HistoryService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Usuarios"])


@router.get(
    "/me", response_model=UserResponse, summary="Obtener perfil del usuario actual"
)
def get_my_profile(current_user: Usuario = Depends(get_current_active_user)):
    return current_user


@router.put(
    "/me", response_model=UserResponse, summary="Actualizar perfil del usuario actual"
)
def update_my_profile(
    user_in: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):

    user_in.password = None
    if current_user.rol != "administrador":
        user_in.rol = None
        user_in.esta_activo = None

    updated_user = UserService.update(db, current_user.id, user_in, actor_id=current_user.id)

    HistoryService.log(
        db=db,
        accion="ACTUALIZAR",
        modulo="Auth",
        usuario_id=current_user.id,
        detalle={
            "entidad": updated_user.correo,
            "descripcion": f"El usuario {updated_user.nombre_completo} actualizó sus datos de perfil",
        },
        ip=request.client.host if request.client else None,
    )
    return updated_user


@router.put(
    "/me/password",
    response_model=Dict[str, Any],
    summary="Cambiar la propia contraseña (verifica la actual)",
)
def change_my_password(
    payload: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    UserService.cambiar_password_propia(
        db, current_user, payload.actual, payload.nueva
    )
    HistoryService.log(
        db=db,
        accion="ACTUALIZAR",
        modulo="Auth",
        usuario_id=current_user.id,
        detalle={
            "entidad": current_user.correo,
            "descripcion": f"{current_user.nombre_completo} cambió su contraseña",
        },
        ip=request.client.host if request.client else None,
    )
    return {"message": "Contraseña actualizada correctamente"}


@router.get(
    "/me/settings",
    response_model=Dict[str, Any],
    summary="Obtener preferencias del usuario actual",
)
def get_my_settings(current_user: Usuario = Depends(get_current_active_user)):
    return current_user.preferencias or {}


@router.put(
    "/me/settings",
    response_model=Dict[str, Any],
    summary="Actualizar preferencias del usuario actual",
)
def update_my_settings(
    settings_in: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    return UserService.update_settings(db, current_user, settings_in)


@router.delete(
    "/me/settings",
    response_model=Dict[str, Any],
    summary="Restablecer preferencias del usuario actual",
)
def reset_my_settings(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    return UserService.reset_settings(db, current_user)


@router.get("/", response_model=List[UserResponse], summary="Listar usuarios")
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return UserService.get_all(db, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserResponse, summary="Obtener usuario por ID")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_admin),
):
    return UserService.get_by_id(db, user_id)


@router.put("/{user_id}", response_model=UserResponse, summary="Actualizar usuario")
def update_user(
    user_id: int,
    user_in: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_admin),
):
    user_in.password = None
    updated = UserService.update(db, user_id, user_in, actor_id=current_user.id)
    HistoryService.log(
        db=db,
        accion="ACTUALIZAR",
        modulo="Auth",
        usuario_id=current_user.id,
        detalle={
            "entidad": updated.correo,
            "descripcion": f"Actualizó al usuario {updated.nombre_completo}",
        },
        ip=request.client.host if request.client else None,
    )
    return updated


@router.delete("/{user_id}", summary="Eliminar usuario")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_admin),
):
    user = UserService.get_by_id(db, user_id)
    email = user.correo if user else f"ID {user_id}"
    resultado = UserService.delete(db, user_id, actor_id=current_user.id)
    accion_txt = "Desactivó" if resultado.get("soft_delete") else "Eliminó"
    HistoryService.log(
        db=db,
        accion="ELIMINAR",
        modulo="Auth",
        usuario_id=current_user.id,
        detalle={
            "entidad": email,
            "descripcion": f"{accion_txt} al usuario {email}",
        },
        ip=request.client.host if request.client else None,
    )
    return resultado