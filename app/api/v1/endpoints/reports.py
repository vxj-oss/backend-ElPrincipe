from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import Usuario
from app.services.history_service import HistoryService
from app.services.report_service import ReportService


def registrar_exportacion(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    partes = [p for p in request.url.path.split("/") if p]
    formato = partes[-1] if partes else "archivo"
    tipo = partes[-2] if len(partes) >= 2 else "reporte"
    HistoryService.log(
        db, "EXPORTAR", "Reportes", current_user.id,
        {"entidad": f"{tipo}.{formato}", "descripcion": f"Exportó el reporte de {tipo} en {formato.upper()}"},
        request.client.host if request.client else None,
    )


router = APIRouter(
    prefix="/reports",
    tags=["Reportes"],
    dependencies=[Depends(registrar_exportacion)],
)


def _rango(desde: Optional[date], hasta: Optional[date]):
    ini = datetime.combine(desde, time.min) if desde else None
    fin = datetime.combine(hasta, time.max) if hasta else None
    return ini, fin


@router.get("/orders/excel", summary="Descargar reporte de pedidos en Excel")
def download_orders_excel(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_orders_excel(db, *_rango(desde, hasta))
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=pedidos.xlsx"},
    )


@router.get("/inventory/excel", summary="Descargar reporte de inventario en Excel")
def download_inventory_excel(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_inventory_excel(db)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=inventario.xlsx"},
    )


@router.get("/customers/excel", summary="Descargar reporte de clientes en Excel")
def download_customers_excel(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_customers_excel(db)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=clientes.xlsx"},
    )


@router.get(
    "/errors/excel", summary="Descargar reporte de pedidos con errores en Excel"
)
def download_order_errors_excel(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_order_errors_excel(db, *_rango(desde, hasta))
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=pedidos_errores.xlsx"},
    )


@router.get("/indicators/excel", summary="Descargar reporte de indicadores en Excel")
def download_indicators_excel(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_indicators_excel(db)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=indicadores.xlsx"},
    )


@router.get("/orders/pdf", summary="Descargar reporte de pedidos en PDF")
def download_orders_pdf(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_orders_pdf(db, *_rango(desde, hasta))
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=pedidos.pdf"},
    )


@router.get("/inventory/pdf", summary="Descargar reporte de inventario en PDF")
def download_inventory_pdf(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_inventory_pdf(db)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=inventario.pdf"},
    )


@router.get("/customers/pdf", summary="Descargar reporte de clientes en PDF")
def download_customers_pdf(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_customers_pdf(db)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=clientes.pdf"},
    )


@router.get("/errors/pdf", summary="Descargar reporte de pedidos con errores en PDF")
def download_order_errors_pdf(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_order_errors_pdf(db, *_rango(desde, hasta))
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=pedidos_errores.pdf"},
    )


@router.get("/indicators/pdf", summary="Descargar reporte de indicadores en PDF")
def download_indicators_pdf(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_indicators_pdf(db)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=indicadores.pdf"},
    )
