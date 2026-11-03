import hashlib
import hmac
from typing import Optional

from app.core.config import settings


def _firma(pedido_id: int) -> str:
    clave = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(clave, f"ticket:{pedido_id}".encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def token_ticket(pedido_id: int) -> str:
    return f"{pedido_id}-{_firma(pedido_id)}"


def pedido_de_token(token: str) -> Optional[int]:
    inicio, _, firma = (token or "").partition("-")
    if not inicio.isdigit() or not firma:
        return None
    pedido_id = int(inicio)
    return pedido_id if hmac.compare_digest(firma, _firma(pedido_id)) else None
