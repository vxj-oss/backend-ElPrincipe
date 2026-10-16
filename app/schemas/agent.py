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
    mensaje_id: Optional[int] = None
    respuesta: str
    datos_estructurados: Optional[Dict[str, Any]] = None
    tiempo_respuesta: float


class SerieGrafico(BaseModel):
    nombre: str = Field(default="Valor", max_length=100)
    valores: List[Optional[float]] = Field(default_factory=list, max_length=400)
    tipo: Optional[str] = Field(default=None, max_length=20)


class SeccionInforme(BaseModel):
    titulo: str = Field(default="", max_length=120)
    lineas: List[str] = Field(default_factory=list, max_length=40)


class InformePdfRequest(BaseModel):
    titulo: str = Field(default="Informe", max_length=200)
    secciones: List[SeccionInforme] = Field(default_factory=list, max_length=12)
    grafico: Optional[Dict[str, Any]] = None


class GraficoPdfRequest(BaseModel):
    titulo: str = Field(default="Gráfico", max_length=200)
    grafico: Literal["bar", "line", "doughnut"] = "bar"
    labels: List[str] = Field(default_factory=list, max_length=400)
    series: List[SerieGrafico] = Field(default_factory=list, max_length=8)
    prefijo: str = Field(default="", max_length=10)
    horizontal: bool = False
    explicacion: Optional[Dict[str, Any]] = None
