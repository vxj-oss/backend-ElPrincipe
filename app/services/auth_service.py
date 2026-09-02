from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.user import Usuario
from app.schemas.auth import Token


class AccountLockedError(Exception):
    def __init__(self, unlock_at: datetime):
        self.unlock_at = unlock_at


class AuthService:
    @staticmethod
    def authenticate_user(
        db: Session, nombre_usuario: str, password: str
    ) -> Optional[Usuario]:
        user = db.scalar(select(Usuario).where(Usuario.nombre_usuario == nombre_usuario))
        if not user:
            return None

        now = datetime.now(timezone.utc)
        if user.bloqueado_hasta:
            if user.bloqueado_hasta > now:
                raise AccountLockedError(user.bloqueado_hasta)
            user.intentos_fallidos = 0
            user.bloqueado_hasta = None

        if not verify_password(password, user.clave_hash) or not user.esta_activo:
            user.intentos_fallidos += 1
            if user.intentos_fallidos >= settings.LOGIN_MAX_ATTEMPTS:
                user.bloqueado_hasta = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            db.commit()
            return None

        if user.intentos_fallidos or user.bloqueado_hasta:
            user.intentos_fallidos = 0
            user.bloqueado_hasta = None
            db.commit()
        return user

    @staticmethod
    def generate_token_for_user(user: Usuario) -> Token:
        token_str = create_access_token(
            subject=user.id,
            role=user.rol,
        )
        return Token(access_token=token_str, token_type="bearer")

    @staticmethod
    def login(db: Session, nombre_usuario: str, password: str) -> Token:
        try:
            user = AuthService.authenticate_user(db, nombre_usuario, password)
        except AccountLockedError as exc:
            remaining_min = max(
                1,
                int((exc.unlock_at - datetime.now(timezone.utc)).total_seconds() // 60) + 1,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Cuenta bloqueada temporalmente por múltiples intentos fallidos. "
                    f"Intenta nuevamente en {remaining_min} minuto(s)."
                ),
            )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas o usuario inactivo",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthService.generate_token_for_user(user)
