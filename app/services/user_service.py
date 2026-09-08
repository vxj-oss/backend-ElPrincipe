from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.models.decision import DecisionComercial
from app.models.history import HistorialAuditoria
from app.models.order import Pedido
from app.models.user import Usuario
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[Usuario]:
        return db.scalar(select(Usuario).where(Usuario.id == user_id))

    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[Usuario]:
        return db.scalar(select(Usuario).where(Usuario.nombre_usuario == username))

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[Usuario]:
        return db.scalar(select(Usuario).where(Usuario.correo == email))

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[Usuario]:
        return list(
            db.scalars(
                select(Usuario).order_by(Usuario.id).offset(skip).limit(limit)
            ).all()
        )

    @staticmethod
    def _admins_activos_restantes(db: Session, excluir_id: int) -> int:
        return (
            db.scalar(
                select(func.count(Usuario.id)).where(
                    Usuario.rol == "administrador",
                    Usuario.esta_activo.is_(True),
                    Usuario.id != excluir_id,
                )
            )
            or 0
        )

    @staticmethod
    def _es_ultimo_admin_activo(db: Session, user: Usuario) -> bool:
        if user.rol != "administrador" or not user.esta_activo:
            return False
        return UserService._admins_activos_restantes(db, user.id) == 0

    @staticmethod
    def create(db: Session, user_in: UserCreate) -> Usuario:
        if UserService.get_by_username(db, user_in.nombre_usuario):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El nombre de usuario ya está registrado",
            )
        if UserService.get_by_email(db, user_in.correo):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El correo ya se encuentra registrado",
            )

        db_user = Usuario(
            nombre_usuario=user_in.nombre_usuario,
            clave_hash=get_password_hash(user_in.password),
            nombre_completo=user_in.nombre_completo,
            correo=user_in.correo,
            rol=user_in.rol,
            esta_activo=user_in.esta_activo,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    @staticmethod
    def update(
        db: Session,
        user_id: int,
        user_in: UserUpdate,
        actor_id: Optional[int] = None,
    ) -> Usuario:
        db_user = UserService.get_by_id(db, user_id)
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )

        update_data = user_in.model_dump(exclude_unset=True)

        nuevo_usuario = update_data.get("nombre_usuario")
        if nuevo_usuario and nuevo_usuario != db_user.nombre_usuario:
            existente = UserService.get_by_username(db, nuevo_usuario)
            if existente and existente.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El nombre de usuario ya está registrado",
                )

        nuevo_correo = update_data.get("correo")
        if nuevo_correo and nuevo_correo != db_user.correo:
            existente = UserService.get_by_email(db, nuevo_correo)
            if existente and existente.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El correo ya se encuentra registrado",
                )

        quiere_degradar = (
            "rol" in update_data
            and update_data["rol"] != "administrador"
            and db_user.rol == "administrador"
        )
        quiere_desactivar = (
            update_data.get("esta_activo") is False and db_user.esta_activo
        )

        if actor_id is not None and actor_id == user_id:
            if quiere_degradar:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No puedes cambiar tu propio rol de administrador.",
                )
            if quiere_desactivar:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No puedes desactivar tu propia cuenta.",
                )

        if (quiere_degradar or quiere_desactivar) and UserService._es_ultimo_admin_activo(
            db, db_user
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Debe existir al menos un administrador activo en el sistema.",
            )

        if "password" in update_data and update_data["password"]:
            db_user.clave_hash = get_password_hash(update_data.pop("password"))
        update_data.pop("password", None)

        for key, value in update_data.items():
            setattr(db_user, key, value)

        db.commit()
        db.refresh(db_user)
        return db_user

    @staticmethod
    def cambiar_password_propia(
        db: Session, user: Usuario, actual: str, nueva: str
    ) -> Usuario:
        if not verify_password(actual, user.clave_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La contraseña actual no es correcta.",
            )
        if verify_password(nueva, user.clave_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La nueva contraseña debe ser distinta de la actual.",
            )
        user.clave_hash = get_password_hash(nueva)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_settings(db: Session, user: Usuario, patch: Dict[str, Any]) -> Dict[str, Any]:
        user.preferencias = {**(user.preferencias or {}), **patch}
        db.commit()
        db.refresh(user)
        return user.preferencias or {}

    @staticmethod
    def reset_settings(db: Session, user: Usuario) -> Dict[str, Any]:
        user.preferencias = {}
        db.commit()
        db.refresh(user)
        return user.preferencias or {}

    @staticmethod
    def _tiene_historial(db: Session, user_id: int) -> bool:
        pedidos = db.scalar(
            select(func.count(Pedido.id)).where(Pedido.usuario_id == user_id)
        ) or 0
        decisiones = db.scalar(
            select(func.count(DecisionComercial.id)).where(
                DecisionComercial.usuario_id == user_id
            )
        ) or 0
        eventos = db.scalar(
            select(func.count(HistorialAuditoria.id)).where(
                HistorialAuditoria.usuario_id == user_id
            )
        ) or 0
        return (pedidos + decisiones + eventos) > 0

    @staticmethod
    def delete(db: Session, user_id: int, actor_id: Optional[int] = None) -> dict:
        db_user = UserService.get_by_id(db, user_id)
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )

        if actor_id is not None and actor_id == user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No puedes eliminar tu propia cuenta.",
            )

        if UserService._es_ultimo_admin_activo(db, db_user):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No puedes eliminar al único administrador activo del sistema.",
            )

        if UserService._tiene_historial(db, user_id):
            if not db_user.esta_activo:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El usuario ya está inactivo.",
                )
            db_user.esta_activo = False
            db.commit()
            return {
                "message": (
                    "El usuario tiene actividad registrada, por lo que se desactivó "
                    "en lugar de eliminarlo."
                ),
                "soft_delete": True,
            }

        db.delete(db_user)
        db.commit()
        return {"message": "Usuario eliminado exitosamente", "soft_delete": False}