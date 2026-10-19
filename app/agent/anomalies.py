from datetime import timedelta
from statistics import mean, median, pstdev
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import ahora_lima
from app.models.customer import Cliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.services.profit_service import ESTADOS_CONFIRMADOS

DIAS_REVISION = 14
DIAS_LINEA_BASE = 90
MIN_PEDIDOS_BASE = 6
SIGMAS_MONTO = 2.5
VECES_MEDIANA_MONTO = 3.0
DESVIO_PRECIO = 0.30
MIN_LINEAS_CANTIDAD = 4
VECES_CANTIDAD = 5.0
MAX_POR_TIPO = 3


def _soles(valor: float) -> str:
    return f"S/ {valor:,.2f}"


def _pregunta(etiqueta: str, texto: str) -> Dict[str, Any]:
    return {"tipo": "pregunta", "etiqueta": etiqueta, "texto": texto}


def _montos_inusuales(db: Session, ahora) -> List[Dict[str, Any]]:
    corte = ahora - timedelta(days=DIAS_REVISION)
    base_desde = ahora - timedelta(days=DIAS_LINEA_BASE)
    base = [
        float(m)
        for (m,) in db.execute(
            select(Pedido.monto_total).where(
                Pedido.estado.in_(ESTADOS_CONFIRMADOS), Pedido.fecha_pedido >= base_desde, Pedido.fecha_pedido < corte
            )
        ).all()
    ]
    if len(base) < MIN_PEDIDOS_BASE:
        return []
    umbral = max(mean(base) + SIGMAS_MONTO * pstdev(base), VECES_MEDIANA_MONTO * median(base))
    filas = db.execute(
        select(Pedido.codigo_pedido, Pedido.monto_total, Cliente.razon_social)
        .join(Cliente, Cliente.id == Pedido.cliente_id)
        .where(Pedido.estado != "Cancelado", Pedido.fecha_pedido >= corte, Pedido.monto_total > umbral)
        .order_by(Pedido.monto_total.desc())
        .limit(MAX_POR_TIPO)
    ).all()
    return [
        {
            "tipo": "monto",
            "nivel": "media",
            "titulo": f"Revisa el monto de {codigo}",
            "detalle": f"{cliente}: {_soles(float(monto))}, cuando un pedido normal ronda {_soles(median(base))}.",
            "accion": _pregunta(f"Ver {codigo}", f"detalle del pedido {codigo}"),
        }
        for codigo, monto, cliente in filas
    ]


def _precios_fuera_de_catalogo(db: Session, ahora) -> List[Dict[str, Any]]:
    corte = ahora - timedelta(days=DIAS_REVISION)
    filas = db.execute(
        select(Pedido.codigo_pedido, Producto.nombre, DetallePedido.precio_unitario, Producto.precio_unitario)
        .join(DetallePedido, DetallePedido.pedido_id == Pedido.id)
        .join(Producto, Producto.id == DetallePedido.producto_id)
        .where(Pedido.estado != "Cancelado", Pedido.fecha_pedido >= corte)
    ).all()
    hallazgos = []
    for codigo, producto, precio, catalogo in filas:
        precio, catalogo = float(precio), float(catalogo)
        if catalogo <= 0:
            continue
        desvio = (precio - catalogo) / catalogo
        if abs(desvio) >= DESVIO_PRECIO:
            hallazgos.append((abs(desvio), codigo, producto, precio, catalogo, desvio))
    hallazgos.sort(reverse=True)
    return [
        {
            "tipo": "precio",
            "nivel": "media",
            "titulo": f"Revisa el precio de {producto}",
            "detalle": f"En {codigo} se vendió a {_soles(precio)} y el catálogo dice {_soles(catalogo)} ({desvio * 100:+.0f} %).",
            "accion": _pregunta(f"Ver {codigo}", f"detalle del pedido {codigo}"),
        }
        for _, codigo, producto, precio, catalogo, desvio in hallazgos[:MAX_POR_TIPO]
    ]


def _cantidades_inusuales(db: Session, ahora) -> List[Dict[str, Any]]:
    corte = ahora - timedelta(days=DIAS_REVISION)
    base_desde = ahora - timedelta(days=DIAS_LINEA_BASE)
    historico: Dict[int, List[float]] = {}
    for producto_id, cantidad in db.execute(
        select(DetallePedido.producto_id, DetallePedido.cantidad)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(Pedido.estado.in_(ESTADOS_CONFIRMADOS), Pedido.fecha_pedido >= base_desde, Pedido.fecha_pedido < corte)
    ).all():
        historico.setdefault(producto_id, []).append(float(cantidad))
    filas = db.execute(
        select(Pedido.codigo_pedido, Producto.id, Producto.nombre, DetallePedido.cantidad)
        .join(DetallePedido, DetallePedido.pedido_id == Pedido.id)
        .join(Producto, Producto.id == DetallePedido.producto_id)
        .where(Pedido.estado != "Cancelado", Pedido.fecha_pedido >= corte)
    ).all()
    hallazgos = []
    for codigo, producto_id, nombre, cantidad in filas:
        previas = historico.get(producto_id, [])
        if len(previas) < MIN_LINEAS_CANTIDAD:
            continue
        habitual = mean(previas)
        if habitual > 0 and cantidad >= VECES_CANTIDAD * habitual and cantidad - habitual >= 3:
            hallazgos.append((cantidad / habitual, codigo, nombre, cantidad, habitual))
    hallazgos.sort(reverse=True)
    return [
        {
            "tipo": "cantidad",
            "nivel": "media",
            "titulo": f"Revisa la cantidad de {nombre}",
            "detalle": f"En {codigo} se pidieron {cantidad} unidades; lo habitual por pedido es {habitual:.1f}.",
            "accion": _pregunta(f"Ver {codigo}", f"detalle del pedido {codigo}"),
        }
        for _, codigo, nombre, cantidad, habitual in hallazgos[:MAX_POR_TIPO]
    ]


def detectar_anomalias(db: Session) -> List[Dict[str, Any]]:
    ahora = ahora_lima()
    hallazgos: List[Dict[str, Any]] = []
    for detector in (
        lambda: _montos_inusuales(db, ahora),
        lambda: _precios_fuera_de_catalogo(db, ahora),
        lambda: _cantidades_inusuales(db, ahora),
    ):
        hallazgos += detector()
    return hallazgos

