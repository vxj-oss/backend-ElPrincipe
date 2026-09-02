from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class AgentMessageBase(BaseModel):
    rol_emisor: Literal["user", "assistant", "system"]
    contenido: str
    datos_estructurados: Optional[Dict[str, Any]] = None
    tiempo_respuesta_segundos: Optional[float] = None


class AgentMessageCreate(AgentMessageBase):
    sesion_id: int


class AgentMessageResponse(AgentMessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sesion_id: int
    fecha_hora: datetime


class AgentSessionBase(BaseModel):
    titulo_sesion: str = Field(default="Nueva sesión", max_length=200)
    esta_activa: bool = True


class AgentSessionCreate(BaseModel):
    titulo_sesion: Optional[str] = Field(default="Nueva sesión", max_length=200)


class AgentSessionResponse(AgentSessionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    fecha_creacion: datetime
    mensajes: List[AgentMessageResponse] = []


class AgentQueryRequest(BaseModel):
    sesion_id: Optional[int] = None
    mensaje: str = Field(..., min_length=1)
    contexto_adicional: Optional[Dict[str, Any]] = None


class AgentQueryResponse(BaseModel):
    sesion_id: int
    respuesta: str
    datos_estructurados: Optional[Dict[str, Any]] = None
    tiempo_respuesta: float