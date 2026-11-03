from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.enlace_ticket import pedido_de_token
from app.services.order_service import OrderService
from app.services.ticket_service import generar_ticket_pedido

router = APIRouter(prefix="/public", tags=["Público"])


@router.get("/tickets/{token}", summary="Ticket del pedido abierto desde el QR (enlace firmado)")
def ticket_publico(token: str, db: Session = Depends(get_db)):
    pedido_id = pedido_de_token(token)
    pedido = OrderService.get_by_id(db, pedido_id) if pedido_id else None
    if not pedido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")
    return StreamingResponse(
        generar_ticket_pedido(pedido),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={pedido.codigo_pedido}-ticket.pdf"},
    )
