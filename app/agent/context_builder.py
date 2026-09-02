from typing import Optional
from sqlalchemy.orm import Session


class ContextBuilder:
    @staticmethod
    def build_chat_history(db: Session, session_id: Optional[int], limit: int = 0) -> str:
        return "Consulta individual (sin historial previo)."
