from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.tools import CommercialTools
from app.core.time import ahora_lima
from app.models.customer import Cliente
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.product import Producto
from app.models.user import Usuario

SEGUIMIENTO_HORAS = 24
SEGUIMIENTO_DIAS_MAX = 14
DIAS_SIN_COMPRAR = 30

DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def resumen_del_dia(db: Session, usuario: Usuario) -> str:
    ahora = ahora_lima()
    saludo = "Buenos días" if ahora.hour < 12 else ("Buenas tardes" if ahora.hour < 19 else "Buenas noches")
    partes_nombre = (usuario.nombre_completo or "").split()
    nombre = f", {partes_nombre[0]}" if partes_nombre else ""

    datos = CommercialTools.get_indicadores_actividad(db)
    ncca, npp, tptd = datos["NCCA"], datos["NPP"], datos["TPTD"]

    pedidos_pendientes = db.scalar(select(func.count(Pedido.id)).where(Pedido.estado == "Pendiente")) or 0
    por_seguimiento = db.scalar(
        select(func.count(SolicitudCliente.id)).where(
            SolicitudCliente.estado == "Pendiente",
            SolicitudCliente.fecha_solicitud < ahora - timedelta(hours=SEGUIMIENTO_HORAS),
            SolicitudCliente.fecha_solicitud >= ahora - timedelta(days=SEGUIMIENTO_DIAS_MAX),
        )
    ) or 0
    stock_critico = db.scalar(
        select(func.count(Producto.id)).where(
            Producto.activo.is_(True), Producto.stock_actual <= Producto.stock_minimo
        )
    ) or 0

    ultimas = (
        select(Pedido.cliente_id, func.max(Pedido.fecha_pedido).label("ultima"))
        .where(Pedido.estado != "Cancelado")
        .group_by(Pedido.cliente_id)
        .subquery()
    )
    sin_comprar = db.scalar(
        select(func.count())
        .select_from(ultimas)
        .join(Cliente, Cliente.id == ultimas.c.cliente_id)
        .where(
            Cliente.estado == "Activo",
            ultimas.c.ultima < ahora - timedelta(days=DIAS_SIN_COMPRAR),
        )
    ) or 0

    if tptd["valor_hoy_segundos"] is None:
        linea_tptd = "• Tiempo promedio de decisión: aún sin pedidos aprobados hoy."
    else:
        linea_tptd = (
            f"• Tiempo promedio de decisión: {tptd['valor_hoy_segundos']} s "
            f"(semáforo {tptd['color_semaforo']})."
        )

    lineas = [
        f"{saludo}{nombre}. Esto es lo importante de hoy, {DIAS_SEMANA[ahora.weekday()]} {ahora.strftime('%d/%m')}:",
        f"• Cotizaciones atendidas: {ncca['valor_hoy']} (semáforo {ncca['color_semaforo']}, meta {ncca['meta']}).",
        f"• Pedidos procesados: {npp['valor_hoy']} (semáforo {npp['color_semaforo']}, meta {npp['meta']}).",
        linea_tptd,
        f"• Pedidos pendientes de confirmar: {pedidos_pendientes}.",
        f"• Cotizaciones por dar seguimiento: {por_seguimiento}.",
        f"• Productos en stock crítico: {stock_critico}.",
        f"• Clientes con más de {DIAS_SIN_COMPRAR} días sin comprar: {sin_comprar}.",
        "¿En qué te ayudo?",
    ]
    return "\n".join(lineas)
