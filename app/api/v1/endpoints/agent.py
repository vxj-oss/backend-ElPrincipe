import json
import queue
import threading
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.agent.daily_summary import resumen_del_dia
from app.agent.dashboard_reading import lectura_dashboard
from app.agent.notices import avisos_proactivos
from app.core.database import SessionLocal, get_db
from app.core.limiter import limiter
from app.models.agent_session import SesionAgente
from app.models.user import Usuario
from app.schemas.agent import (
    AgentQueryRequest,
    AgentQueryResponse,
    AgentSessionCreate,
    AgentSessionResponse,
    GraficoPdfRequest,
    InformePdfRequest,
)
from app.services.chart_pdf_service import generar_pdf_grafico, generar_pdf_informe
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


@router.post(
    "/chat/stream",
    summary="Interactuar con el agente recibiendo la respuesta por partes (SSE)",
)
@limiter.limit("15/minute")
def chat_with_agent_stream(
    request: Request,
    payload: AgentQueryRequest,
    current_user: Usuario = Depends(get_current_active_user),
):
    user_id = current_user.id
    cola: "queue.Queue" = queue.Queue()

    def trabajo() -> None:
        db = SessionLocal()
        try:
            usuario = db.get(Usuario, user_id)
            resultado = AgentService.execute_query(
                db=db,
                current_user=usuario,
                prompt=payload.mensaje,
                session_id=payload.sesion_id,
                contexto=payload.contexto_adicional,
                on_delta=lambda texto: cola.put({"t": "delta", "x": texto}),
            )
            cola.put({"t": "done", **resultado})
        except Exception as exc:
            cola.put({"t": "error", "detalle": str(exc)})
        finally:
            db.close()
            cola.put(None)

    threading.Thread(target=trabajo, daemon=True).start()

    def generador():
        while True:
            item = cola.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        generador(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/resumen-dia",
    summary="Resumen del día para el mensaje de bienvenida del chat",
)
def get_daily_summary(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    return {"texto": resumen_del_dia(db, current_user)}


@router.post(
    "/grafico/pdf",
    summary="Descargar en PDF un gráfico generado por el agente",
)
def download_chart_pdf(
    payload: GraficoPdfRequest,
    _: Usuario = Depends(get_current_active_user),
):
    return StreamingResponse(
        generar_pdf_grafico(payload.model_dump()),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=grafico.pdf"},
    )


@router.post(
    "/informe/pdf",
    summary="Descargar en PDF un informe generado por el agente",
)
def download_report_pdf(
    payload: InformePdfRequest,
    _: Usuario = Depends(get_current_active_user),
):
    return StreamingResponse(
        generar_pdf_informe(payload.model_dump()),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=informe.pdf"},
    )


@router.get(
    "/lectura-dashboard",
    summary="Lectura del agente sobre el dashboard: qué pasó, por qué y qué hacer",
)
def get_dashboard_reading(
    forzar: bool = False,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    return lectura_dashboard(db, forzar=forzar)


@router.get(
    "/avisos",
    summary="Avisos proactivos del agente: stock, recompra, seguimiento y meta",
)
def get_proactive_notices(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    return {"avisos": avisos_proactivos(db)}


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


@router.post(
    "/sessions",
    response_model=AgentSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una conversación nueva",
)
def create_session(
    payload: AgentSessionCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    titulo = (payload.titulo_sesion or "").strip()
    sesion = SesionAgente(
        usuario_id=current_user.id,
        titulo_sesion=titulo[:200] if titulo and titulo != "Nueva sesión" else "Consulta Asistente de Ventas",
        esta_activa=True,
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion


@router.delete(
    "/sessions",
    summary="Eliminar todas las conversaciones del usuario",
)
def delete_all_sessions(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    sesiones = db.scalars(select(SesionAgente).where(SesionAgente.usuario_id == current_user.id)).all()
    for sesion in sesiones:
        db.delete(sesion)
    db.commit()
    return {"eliminadas": len(sesiones)}


@router.delete(
    "/sessions/{session_id}",
    summary="Eliminar una conversación",
)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
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
    db.delete(sesion)
    db.commit()
    return {"message": "Conversación eliminada."}


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