from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.agent_session import SesionAgente
from app.models.user import Usuario
from app.schemas.agent import (
    AgentQueryRequest,
    AgentQueryResponse,
    AgentSessionCreate,
    AgentSessionResponse,
)
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent", tags=["Agente IA"])


@router.post(
    "/chat",
    response_model=AgentQueryResponse,
    summary="Interactuar con el agente comercial inteligente",
)
@limiter.limit("15/minute")
def chat_with_agent(
    request: Request,
    payload: AgentQueryRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    """Procesa una consulta comercial con el Agente IA, que consulta inventario y contexto de negocio"""
    return AgentService.execute_query(
        db=db,
        current_user=current_user,
        prompt=payload.mensaje,
        session_id=payload.sesion_id,
        contexto=payload.contexto_adicional,
    )


@router.get(
    "/sessions",
    response_model=List[AgentSessionResponse],
    summary="Listar sesiones de chat del usuario autenticado",
)
def list_user_sessions(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    """Obtiene el historial de sesiones de conversación del asesor/administrador actual."""
    stmt = (
        select(SesionAgente)
        .where(SesionAgente.usuario_id == current_user.id)
        .order_by(SesionAgente.fecha_creacion.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(stmt).all()


@router.get(
    "/sessions/{session_id}",
    response_model=AgentSessionResponse,
    summary="Obtener detalle y mensajes de una sesión",
)
def get_session_detail(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    """Recupera los mensajes y contexto de una sesión específica."""
    sesion = db.scalar(
        select(SesionAgente).where(
            SesionAgente.id == session_id,
            SesionAgente.usuario_id == current_user.id,
        )
    )
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de conversación no encontrada.",
        )
    return sesion