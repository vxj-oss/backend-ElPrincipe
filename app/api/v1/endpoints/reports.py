from datetime import date, datetime, time
from typing import Optional

import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.time import ahora_lima
from app.services.day_close_service import generar_cierre_dia_pdf
from app.services.restock_service import generar_reposicion_excel
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


def _nombre_archivo(db: Session, cliente_id: int) -> str:
    from app.models.customer import Cliente

    cliente = db.get(Cliente, cliente_id)
    base = unicodedata.normalize("NFKD", cliente.razon_social if cliente else "cliente")
    base = re.sub(r"[^A-Za-z0-9]+", "_", base.encode("ascii", "ignore").decode()).strip("_").lower()
    return f"historial_{base or 'cliente'}"


@router.get("/customer-history/excel", summary="Descargar el historial de un cliente en Excel")
def download_customer_history_excel(
    cliente_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_customer_history_excel(db, cliente_id)
    if buffer is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={_nombre_archivo(db, cliente_id)}.xlsx"},
    )


@router.get("/customer-history/pdf", summary="Descargar el historial de un cliente en PDF")
def download_customer_history_pdf(
    cliente_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_customer_history_pdf(db, cliente_id)
    if buffer is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={_nombre_archivo(db, cliente_id)}.pdf"},
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


@router.get(
    "/indicators/actividad/excel",
    summary="Descargar serie diaria de un indicador comercial (NCCA/NPP/TPTD) en Excel",
)
def download_actividad_comercial_excel(
    indicador: str,
    dias: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    sigla = indicador.upper()
    buffer = ReportService.generate_actividad_comercial_excel(db, sigla, dias)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={sigla.lower()}_por_dia.xlsx"},
    )


@router.get(
    "/indicators/tpd/por-pedido/excel",
    summary="Descargar tiempo de toma de decisión por pedido individual en Excel",
)
def download_tpd_por_pedido_excel(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = ReportService.generate_tpd_por_pedido_excel(db)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=tpd_por_pedido.xlsx"},
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


@router.get("/reposicion/excel", summary="Descargar la lista de reposición de stock en Excel")
def download_reposicion_excel(
    factor: int = Query(2, ge=1, le=5),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    buffer = generar_reposicion_excel(db, factor)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=lista_reposicion.xlsx"},
    )


@router.get("/cierre-dia/pdf", summary="Descargar el cierre del día en PDF")
def download_cierre_dia_pdf(
    fecha: Optional[date] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_active_user),
):
    dia = fecha or ahora_lima().date()
    buffer = generar_cierre_dia_pdf(db, dia)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cierre_dia_{dia.isoformat()}.pdf"},
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
