from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin, get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.schemas.user import UserCreate, UserResponse, UserUpdate
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

    if current_user.rol != "administrador":
        user_in.rol = None
        user_in.esta_activo = None

    updated_user = UserService.update(db, current_user.id, user_in)

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


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario",
)
def create_user(
    user_in: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_admin),
):
    new_user = UserService.create(db, user_in)
    HistoryService.log(
        db=db,
        accion="CREAR",
        modulo="Auth",
        usuario_id=current_user.id,
        detalle={
            "entidad": new_user.correo,
            "descripcion": f"Creó al usuario {new_user.nombre_completo} ({new_user.rol})",
        },
        ip=request.client.host if request.client else None,
    )
    return new_user


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
    updated = UserService.update(db, user_id, user_in)
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
    UserService.delete(db, user_id)
    HistoryService.log(
        db=db,
        accion="ELIMINAR",
        modulo="Auth",
        usuario_id=current_user.id,
        detalle={
            "entidad": email,
            "descripcion": f"Eliminó al usuario {email}",
        },
        ip=request.client.host if request.client else None,
    )
    return {"message": "Usuario eliminado correctamente"}