from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
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
        return list(db.scalars(select(Usuario).offset(skip).limit(limit)).all())

    @staticmethod
    def create(db: Session, user_in: UserCreate) -> Usuario:
        if UserService.get_by_username(db, user_in.nombre_usuario):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre de usuario ya está registrado",
            )
        if UserService.get_by_email(db, user_in.correo):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
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
    def update(db: Session, user_id: int, user_in: UserUpdate) -> Usuario:
        db_user = UserService.get_by_id(db, user_id)
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )

        update_data = user_in.model_dump(exclude_unset=True)
        if "password" in update_data and update_data["password"]:
            db_user.clave_hash = get_password_hash(update_data.pop("password"))

        for key, value in update_data.items():
            setattr(db_user, key, value)

        db.commit()
        db.refresh(db_user)
        return db_user

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
    def delete(db: Session, user_id: int) -> bool:
        db_user = UserService.get_by_id(db, user_id)
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )
        db.delete(db_user)
        db.commit()
        return True