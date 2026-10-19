import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import LIMA_TZ, ahora_lima
from app.models.category import Categoria
from app.models.customer import Cliente
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.services.profit_service import ESTADOS_CONFIRMADOS

DIAS_VENTANA_ROTACION = 30
DIAS_OBJETIVO_STOCK = 15
UMBRAL_COBERTURA_DIAS = 14
MIN_PEDIDOS_CADENCIA = 3
FACTOR_TOCA = 0.8
FACTOR_MAXIMO = 3.0
MIN_INTERVALO_DIAS = 3
DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

_ETIQUETAS_BASE = {
    "hoy": "hoy",
    "ayer": "ayer",
    "semana": "esta semana",
    "semana_pasada": "la semana pasada",
    "mes": "este mes",
    "mes_pasado": "el mes pasado",
}
_ANTERIOR_BASE = {
    "hoy": "ayer",
    "ayer": "hoy",
    "semana": "semana_pasada",
    "semana_pasada": "semana",
    "mes": "mes_pasado",
    "mes_pasado": "mes",
}
PREFIJO_RANGO = "rango:"
DIAS_MAX_DIARIO = 45


def es_rango_libre(nombre: str) -> bool:
    return nombre.startswith(PREFIJO_RANGO)


def _fechas_rango(nombre: str) -> Tuple[date, date]:
    _, inicio, fin = nombre.split(":")
    return date.fromisoformat(inicio), date.fromisoformat(fin)


def dias_del_rango(nombre: str) -> int:
    inicio, fin = rango(nombre)
    return (fin.date() - inicio.date()).days


class _Etiquetas(dict):
    def __missing__(self, nombre: str) -> str:
        if not es_rango_libre(nombre):
            raise KeyError(nombre)
        inicio, fin = _fechas_rango(nombre)
        if inicio == fin:
            return f"el {inicio.strftime('%d/%m')}"
        mismo_anio = inicio.year == fin.year == ahora_lima().year
        formato = "%d/%m" if mismo_anio else "%d/%m/%Y"
        return f"del {inicio.strftime(formato)} al {fin.strftime(formato)}"


class _Anterior(dict):
    def __missing__(self, nombre: str) -> str:
        if not es_rango_libre(nombre):
            raise KeyError(nombre)
        inicio, fin = _fechas_rango(nombre)
        largo = (fin - inicio).days + 1
        fin_previo = inicio - timedelta(days=1)
        return f"{PREFIJO_RANGO}{(fin_previo - timedelta(days=largo - 1)).isoformat()}:{fin_previo.isoformat()}"


ETIQUETAS = _Etiquetas(_ETIQUETAS_BASE)
ANTERIOR = _Anterior(_ANTERIOR_BASE)


def _inicio_dia(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=LIMA_TZ)


def _fin_mes(d: date) -> date:
    siguiente = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return siguiente - timedelta(days=1)


def rango(nombre: str) -> Tuple[datetime, datetime]:
    if es_rango_libre(nombre):
        inicio_libre, fin_libre = _fechas_rango(nombre)
        return _inicio_dia(inicio_libre), _inicio_dia(fin_libre + timedelta(days=1))
    hoy = ahora_lima().date()
    lunes = hoy - timedelta(days=hoy.weekday())
    transcurridos = hoy.weekday() + 1
    if nombre == "hoy":
        return _inicio_dia(hoy), _inicio_dia(hoy + timedelta(days=1))
    if nombre == "ayer":
        return _inicio_dia(hoy - timedelta(days=1)), _inicio_dia(hoy)
    if nombre == "semana":
        return _inicio_dia(lunes), _inicio_dia(hoy + timedelta(days=1))
    if nombre == "semana_pasada":
        inicio = lunes - timedelta(days=7)
        return _inicio_dia(inicio), _inicio_dia(inicio + timedelta(days=transcurridos))
    if nombre == "mes":
        return _inicio_dia(hoy.replace(day=1)), _inicio_dia(hoy + timedelta(days=1))
    if nombre == "mes_pasado":
        primero_actual = hoy.replace(day=1)
        ultimo_prev = primero_actual - timedelta(days=1)
        inicio = ultimo_prev.replace(day=1)
        limite = min(hoy.day, ultimo_prev.day)
        return _inicio_dia(inicio), _inicio_dia(inicio + timedelta(days=limite))
    raise ValueError(f"Periodo desconocido: {nombre}")


def texto_rango(nombre: str) -> str:
    inicio, fin = rango(nombre)
    ultimo = (fin - timedelta(days=1)).date()
    if inicio.date() == ultimo:
        return inicio.strftime("%d/%m/%Y")
    return f"{inicio.strftime('%d/%m/%Y')} al {ultimo.strftime('%d/%m/%Y')}"


def _confirmados(inicio: datetime, fin: datetime):
    return (
        Pedido.estado.in_(ESTADOS_CONFIRMADOS),
        Pedido.fecha_pedido >= inicio,
        Pedido.fecha_pedido < fin,
    )


def total_periodo(db: Session, nombre: str) -> Dict[str, Any]:
    inicio, fin = rango(nombre)
    ventas, pedidos = db.execute(
        select(func.coalesce(func.sum(Pedido.monto_total), 0), func.count(Pedido.id)).where(
            *_confirmados(inicio, fin)
        )
    ).one()
    cotizaciones = db.scalar(
        select(func.count(SolicitudCliente.id)).where(
            SolicitudCliente.fecha_solicitud >= inicio, SolicitudCliente.fecha_solicitud < fin
        )
    )
    ventas = float(ventas or 0)
    pedidos = int(pedidos or 0)
    return {
        "periodo": nombre,
        "ventas": ventas,
        "pedidos": pedidos,
        "cotizaciones": int(cotizaciones or 0),
        "ticket": ventas / pedidos if pedidos else 0.0,
    }


def ventas_por_dia(db: Session, nombre: str) -> Dict[date, float]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(Pedido.fecha_pedido, Pedido.monto_total).where(*_confirmados(inicio, fin))
    ).all()
    por_dia: Dict[date, float] = defaultdict(float)
    for fecha, monto in filas:
        por_dia[fecha.astimezone(LIMA_TZ).date()] += float(monto or 0)
    return por_dia


def serie_diaria(db: Session, nombre: str) -> Tuple[List[str], List[float]]:
    inicio, fin = rango(nombre)
    por_dia = ventas_por_dia(db, nombre)
    dias: List[date] = []
    dia = inicio.date()
    while dia < fin.date():
        dias.append(dia)
        dia += timedelta(days=1)

    if es_rango_libre(nombre) and len(dias) > DIAS_MAX_DIARIO:
        etiquetas, valores = [], []
        for i in range(0, len(dias), 7):
            bloque = dias[i : i + 7]
            etiquetas.append(bloque[0].strftime("%d/%m"))
            valores.append(round(sum(por_dia.get(d, 0.0) for d in bloque), 2))
        return etiquetas, valores

    if nombre.startswith("semana"):
        etiquetas = [DIAS_SEMANA[d.weekday()] for d in dias]
    elif es_rango_libre(nombre):
        etiquetas = [d.strftime("%d/%m") for d in dias]
    else:
        etiquetas = [str(d.day) for d in dias]
    return etiquetas, [round(por_dia.get(d, 0.0), 2) for d in dias]


def ventas_por_categoria(db: Session, nombre: str) -> List[Tuple[str, float]]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(Categoria.nombre, func.sum(DetallePedido.subtotal))
        .join(Producto, Producto.categoria_id == Categoria.id)
        .join(DetallePedido, DetallePedido.producto_id == Producto.id)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(*_confirmados(inicio, fin))
        .group_by(Categoria.nombre)
        .order_by(func.sum(DetallePedido.subtotal).desc())
    ).all()
    return [(n, float(v or 0)) for n, v in filas]


def ventas_de_productos(db: Session, producto_ids: List[int], nombre: str) -> Dict[int, Tuple[float, float]]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(DetallePedido.producto_id, func.sum(DetallePedido.cantidad), func.sum(DetallePedido.subtotal))
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(DetallePedido.producto_id.in_(producto_ids), *_confirmados(inicio, fin))
        .group_by(DetallePedido.producto_id)
    ).all()
    return {pid: (float(u or 0), float(v or 0)) for pid, u, v in filas}


def ventas_de_clientes(db: Session, cliente_ids: List[int], nombre: str) -> Dict[int, Tuple[int, float]]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(Pedido.cliente_id, func.count(Pedido.id), func.sum(Pedido.monto_total))
        .where(Pedido.cliente_id.in_(cliente_ids), *_confirmados(inicio, fin))
        .group_by(Pedido.cliente_id)
    ).all()
    return {cid: (int(n or 0), float(v or 0)) for cid, n, v in filas}


def _ventas_por_producto(db: Session, nombre: str) -> Dict[int, Tuple[str, float]]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(Producto.id, Producto.nombre, func.sum(DetallePedido.subtotal))
        .join(DetallePedido, DetallePedido.producto_id == Producto.id)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(*_confirmados(inicio, fin))
        .group_by(Producto.id, Producto.nombre)
    ).all()
    return {pid: (n, float(v or 0)) for pid, n, v in filas}


def _ventas_por_cliente(db: Session, nombre: str) -> Dict[int, Tuple[str, float]]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(Cliente.id, Cliente.razon_social, func.sum(Pedido.monto_total))
        .join(Pedido, Pedido.cliente_id == Cliente.id)
        .where(*_confirmados(inicio, fin))
        .group_by(Cliente.id, Cliente.razon_social)
    ).all()
    return {cid: (n, float(v or 0)) for cid, n, v in filas}


def _diferencias(actual: Dict[int, Tuple[str, float]], previo: Dict[int, Tuple[str, float]]):
    claves = set(actual) | set(previo)
    resultado = []
    for k in claves:
        nombre = (actual.get(k) or previo.get(k))[0]
        a = actual.get(k, ("", 0.0))[1]
        p = previo.get(k, ("", 0.0))[1]
        resultado.append((nombre, a - p, a, p))
    return resultado


def diagnostico(db: Session, nombre: str) -> Dict[str, Any]:
    previo_nombre = ANTERIOR[nombre]
    actual = total_periodo(db, nombre)
    previo = total_periodo(db, previo_nombre)
    por_producto = _diferencias(_ventas_por_producto(db, nombre), _ventas_por_producto(db, previo_nombre))
    por_cliente = _diferencias(_ventas_por_cliente(db, nombre), _ventas_por_cliente(db, previo_nombre))
    caidas_prod = sorted([d for d in por_producto if d[1] < 0], key=lambda d: d[1])[:3]
    subidas_prod = sorted([d for d in por_producto if d[1] > 0], key=lambda d: -d[1])[:3]
    caidas_cli = sorted([d for d in por_cliente if d[1] < 0], key=lambda d: d[1])[:3]
    subidas_cli = sorted([d for d in por_cliente if d[1] > 0], key=lambda d: -d[1])[:3]

    caidos_ids = [d[0] for d in caidas_prod]
    sin_stock = []
    if caidos_ids:
        sin_stock = [
            p.nombre
            for p in db.scalars(
                select(Producto).where(Producto.nombre.in_(caidos_ids), Producto.stock_actual <= Producto.stock_minimo)
            ).all()
        ]
    return {
        "periodo": nombre,
        "previo": previo_nombre,
        "actual": actual,
        "anterior": previo,
        "caidas_producto": caidas_prod,
        "subidas_producto": subidas_prod,
        "caidas_cliente": caidas_cli,
        "subidas_cliente": subidas_cli,
        "productos_caidos_con_poco_stock": sin_stock,
    }


def cobertura_stock(db: Session, limite: int = 8) -> List[Dict[str, Any]]:
    ahora = ahora_lima()
    inicio = ahora - timedelta(days=DIAS_VENTANA_ROTACION)
    vendidas = dict(
        db.execute(
            select(DetallePedido.producto_id, func.sum(DetallePedido.cantidad))
            .join(Pedido, Pedido.id == DetallePedido.pedido_id)
            .where(Pedido.estado.in_(ESTADOS_CONFIRMADOS), Pedido.fecha_pedido >= inicio)
            .group_by(DetallePedido.producto_id)
        ).all()
    )
    resultado = []
    for producto in db.scalars(select(Producto).where(Producto.activo.is_(True))).all():
        unidades = float(vendidas.get(producto.id, 0) or 0)
        diario = unidades / DIAS_VENTANA_ROTACION
        stock = float(producto.stock_actual or 0)
        bajo_minimo = stock <= float(producto.stock_minimo or 0)
        if diario <= 0 and not bajo_minimo:
            continue
        dias = stock / diario if diario > 0 else None
        if dias is not None and dias > UMBRAL_COBERTURA_DIAS and not bajo_minimo:
            continue
        sugerido = max(0, math.ceil(diario * DIAS_OBJETIVO_STOCK - stock))
        if sugerido == 0 and bajo_minimo:
            sugerido = max(0, math.ceil(float(producto.stock_minimo or 0) * 2 - stock))
        resultado.append(
            {
                "id": producto.id,
                "nombre": producto.nombre,
                "stock": int(stock),
                "minimo": int(producto.stock_minimo or 0),
                "ritmo_diario": round(diario, 2),
                "dias_cobertura": round(dias, 1) if dias is not None else None,
                "sugerido": sugerido,
            }
        )
    resultado.sort(key=lambda r: (r["dias_cobertura"] is None, r["dias_cobertura"] or 0))
    return resultado[:limite]


def cadencia_clientes(db: Session, limite: int = 8) -> List[Dict[str, Any]]:
    hoy = ahora_lima().date()
    filas = db.execute(
        select(Pedido.cliente_id, Pedido.fecha_pedido).where(Pedido.estado != "Cancelado")
    ).all()
    fechas: Dict[int, List[date]] = defaultdict(list)
    for cliente_id, fecha in filas:
        fechas[cliente_id].append(fecha.astimezone(LIMA_TZ).date())

    candidatos = []
    for cliente_id, lista in fechas.items():
        dias = sorted(set(lista))
        if len(dias) < MIN_PEDIDOS_CADENCIA:
            continue
        intervalos = [(b - a).days for a, b in zip(dias, dias[1:]) if (b - a).days > 0]
        if not intervalos:
            continue
        significativos = [i for i in intervalos if i >= MIN_INTERVALO_DIAS]
        if not significativos:
            continue
        habitual = median(significativos)
        sin_comprar = (hoy - dias[-1]).days
        razon = sin_comprar / habitual
        if FACTOR_TOCA <= razon <= FACTOR_MAXIMO:
            candidatos.append((cliente_id, habitual, sin_comprar, razon, dias[-1]))
    if not candidatos:
        return []
    clientes = {
        c.id: c
        for c in db.scalars(
            select(Cliente).where(Cliente.id.in_([c[0] for c in candidatos]), Cliente.estado == "Activo")
        ).all()
    }
    resultado = []
    for cliente_id, habitual, sin_comprar, razon, ultima in sorted(candidatos, key=lambda c: -c[3]):
        cliente = clientes.get(cliente_id)
        if not cliente:
            continue
        resultado.append(
            {
                "id": cliente.id,
                "nombre": cliente.razon_social,
                "telefono": cliente.telefono,
                "intervalo_dias": int(round(habitual)),
                "dias_sin_comprar": sin_comprar,
                "ultima_compra": ultima.isoformat(),
                "atrasado": razon >= 1.5,
            }
        )
    return resultado[:limite]


def cotizaciones_sin_seguimiento(db: Session) -> int:
    ahora = ahora_lima()
    return int(
        db.scalar(
            select(func.count(SolicitudCliente.id)).where(
                SolicitudCliente.estado == "Pendiente",
                SolicitudCliente.fecha_solicitud < ahora - timedelta(hours=24),
                SolicitudCliente.fecha_solicitud >= ahora - timedelta(days=14),
            )
        )
        or 0
    )


def cotizaciones_por_convertir(db: Session, limite: int = 4) -> Dict[str, Any]:
    ahora = ahora_lima()
    condicion = (
        SolicitudCliente.estado == "Pendiente",
        SolicitudCliente.fecha_solicitud >= ahora - timedelta(days=14),
    )
    total = int(db.scalar(select(func.count(SolicitudCliente.id)).where(*condicion)) or 0)
    filas = db.execute(
        select(SolicitudCliente.codigo_solicitud, Cliente.razon_social, SolicitudCliente.fecha_solicitud)
        .join(Cliente, Cliente.id == SolicitudCliente.cliente_id)
        .where(*condicion)
        .order_by(SolicitudCliente.fecha_solicitud.asc())
        .limit(limite)
    ).all()
    return {
        "total": total,
        "items": [
            {"codigo": codigo, "cliente": cliente, "horas": max(0, int((ahora - fecha).total_seconds() // 3600))}
            for codigo, cliente, fecha in filas
        ],
    }


def pedidos_por_aprobar(db: Session, limite: int = 4) -> Dict[str, Any]:
    ahora = ahora_lima()
    total = int(db.scalar(select(func.count(Pedido.id)).where(Pedido.estado == "Pendiente")) or 0)
    filas = db.execute(
        select(Pedido.codigo_pedido, Cliente.razon_social, Pedido.fecha_pedido, Pedido.monto_total)
        .join(Cliente, Cliente.id == Pedido.cliente_id)
        .where(Pedido.estado == "Pendiente")
        .order_by(Pedido.fecha_pedido.asc())
        .limit(limite)
    ).all()
    return {
        "total": total,
        "items": [
            {
                "codigo": codigo,
                "cliente": cliente,
                "horas": max(0, int((ahora - fecha).total_seconds() // 3600)),
                "monto": float(monto or 0),
            }
            for codigo, cliente, fecha, monto in filas
        ],
    }


def productos_habituales(db: Session, cliente_id: int, cantidad: int = 2) -> List[str]:
    filas = db.execute(
        select(Producto.nombre, func.sum(DetallePedido.cantidad))
        .join(DetallePedido, DetallePedido.producto_id == Producto.id)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(Pedido.cliente_id == cliente_id, Pedido.estado != "Cancelado")
        .group_by(Producto.nombre)
        .order_by(func.sum(DetallePedido.cantidad).desc())
        .limit(cantidad)
    ).all()
    return [nombre for nombre, _ in filas]


def pedidos_del_periodo(db: Session, nombre: str, limite: int = 15) -> List[Dict[str, Any]]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(Pedido.codigo_pedido, Pedido.monto_total, Pedido.estado, Cliente.razon_social, Pedido.fecha_pedido)
        .join(Cliente, Cliente.id == Pedido.cliente_id)
        .where(Pedido.estado != "Cancelado", Pedido.fecha_pedido >= inicio, Pedido.fecha_pedido < fin)
        .order_by(Pedido.fecha_pedido.asc())
        .limit(limite)
    ).all()
    return [
        {
            "codigo": codigo,
            "total": float(monto or 0),
            "estado": estado,
            "cliente": cliente,
            "hora": fecha.astimezone(LIMA_TZ).strftime("%H:%M"),
        }
        for codigo, monto, estado, cliente, fecha in filas
    ]


def top_clientes(db: Session, nombre: str, limite: int = 8) -> List[Tuple[str, int, float]]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(Cliente.razon_social, func.count(Pedido.id), func.sum(Pedido.monto_total))
        .join(Pedido, Pedido.cliente_id == Cliente.id)
        .where(*_confirmados(inicio, fin))
        .group_by(Cliente.id, Cliente.razon_social)
        .order_by(func.sum(Pedido.monto_total).desc())
        .limit(limite)
    ).all()
    return [(n, int(c or 0), float(v or 0)) for n, c, v in filas]


def top_productos(db: Session, nombre: str, limite: int = 8) -> List[Tuple[str, float, float]]:
    inicio, fin = rango(nombre)
    filas = db.execute(
        select(Producto.nombre, func.sum(DetallePedido.cantidad), func.sum(DetallePedido.subtotal))
        .join(DetallePedido, DetallePedido.producto_id == Producto.id)
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(*_confirmados(inicio, fin))
        .group_by(Producto.id, Producto.nombre)
    ).all()
    return [(n, float(u or 0), float(v or 0)) for n, u, v in filas]
