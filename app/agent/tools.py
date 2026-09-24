import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Categoria
from app.models.commercial_term import CondicionComercial
from app.models.customer import Cliente
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.models.stock_movement import MovimientoStock
from app.models.user import Usuario
from app.services.decision_service import DecisionService
from app.services.history_service import HistoryService
from app.services.indicator_service import IndicatorService


class CommercialTools:
    STOP_WORDS = {
        "cuanto", "cuanta", "cuantos", "cuantas", "stock", "tenemos", "de", "del",
        "el", "la", "los", "las", "un", "una", "unos", "unas", "que", "y", "o",
        "puedo", "ofrecer", "ofrecerle", "a", "cliente", "mayorista", "descuento",
        "precio", "maximo", "minimo", "por", "favor", "dime", "hay", "estan",
        "pedidos", "pedido", "pendientes", "confirmar", "hoy", "compraron",
        "cuales", "son", "tengo", "mis", "quienes", "condiciones", "pactadas",
    }

    @classmethod
    def extract_keywords(cls, query: str) -> List[str]:
        cleaned = re.sub(r"[^\w\s]", "", query.lower())
        return [w for w in cleaned.split() if len(w) > 2 and w not in cls.STOP_WORDS]

    @staticmethod
    def get_commercial_terms(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
        stmt = (
            select(CondicionComercial)
            .options(selectinload(CondicionComercial.cliente))
            .order_by(CondicionComercial.id.desc())
            .limit(limit)
        )
        condiciones = db.scalars(stmt).all()
        resultado = []
        for c in condiciones:
            cliente_nom = c.cliente.razon_social if c.cliente else "General"
            resultado.append({
                "cliente": cliente_nom,
                "tipo_condicion": c.tipo_condicion,
                "plazo_dias": c.dias_plazo_pactados,
                "descuento_pct": float(c.porcentaje_descuento or 0),
                "forma_pago_pactada": c.forma_pago_pactada,
            })
        return resultado

    @staticmethod
    def get_all_customers_summary(db: Session, limit: int = 15) -> List[Dict[str, Any]]:
        stmt = select(Cliente).order_by(Cliente.id.desc()).limit(limit)
        clientes = db.scalars(stmt).all()

        ids = [c.id for c in clientes]
        condiciones_por_cliente: Dict[int, Any] = {}
        if ids:
            for cond_row in db.scalars(
                select(CondicionComercial)
                .where(CondicionComercial.cliente_id.in_(ids))
                .order_by(CondicionComercial.id.asc())
            ).all():
                condiciones_por_cliente[cond_row.cliente_id] = cond_row

        resultado = []
        for c in clientes:
            doc = getattr(c, "ruc_dni", None) or getattr(c, "numero_documento", "—")
            cond = condiciones_por_cliente.get(c.id)

            descuento_registrado = f"{float(cond.porcentaje_descuento)}%" if cond and cond.porcentaje_descuento else "Sin descuento pactado (0%)"
            plazo_registrado = f"{cond.dias_plazo_pactados} días" if cond and cond.dias_plazo_pactados else "Contado / No registrado"

            resultado.append({
                "id": c.id,
                "razon_social": c.razon_social,
                "documento": doc,
                "tipo_cliente": c.tipo_cliente,
                "clasificacion": c.clasificacion,
                "telefono": getattr(c, "telefono", "—"),
                "condicion_comercial": {
                    "tiene_condicion": cond is not None,
                    "descuento_pactado": descuento_registrado,
                    "plazo": plazo_registrado,
                }
            })
        return resultado

    @staticmethod
    def get_orders_summary(db: Session, estado: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        stmt = (
            select(Pedido)
            .options(
                selectinload(Pedido.cliente).selectinload(Cliente.condiciones),
                selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
                selectinload(Pedido.auditoria_condicion),
            )
            .order_by(Pedido.id.desc())
        )
        pedidos = db.scalars(stmt).all()

        if estado:
            pedidos = [p for p in pedidos if str(p.estado).lower() == estado.lower()]

        pedidos = pedidos[:limit]
        resultado = []
        for p in pedidos:
            cliente_nombre = p.cliente.razon_social if p.cliente else "Cliente General"
            tipo_cli = p.cliente.tipo_cliente if p.cliente else "Regular"
            items_list = [
                f"{d.cantidad}x {d.producto.nombre if d.producto else 'Item'} (S/ {float(d.subtotal or 0):,.2f})"
                for d in p.detalles
            ]

            conds_cliente = p.cliente.condiciones if p.cliente else []
            conds_p = [
                f"Descuento: {float(cd.porcentaje_descuento or 0)}%, Plazo: {cd.dias_plazo_pactados}d"
                for cd in conds_cliente
            ]

            falla = p.auditoria_condicion
            falla_condicion = f"Sí — {falla.motivo_falla}" if falla and falla.tiene_falla else "No"

            resultado.append({
                "codigo_pedido": p.codigo_pedido,
                "cliente": cliente_nombre,
                "tipo_cliente": tipo_cli,
                "fecha": p.fecha_pedido.strftime("%d/%m/%Y") if p.fecha_pedido else "—",
                "estado": str(p.estado),
                "forma_pago": p.forma_pago or "Contado",
                "monto_total": float(p.monto_total or 0),
                "items": items_list,
                "condiciones_pactadas_cliente": conds_p if conds_p else "Ninguna (0% descuento)",
                "falla_condicion_comercial": falla_condicion,
                "observaciones": p.observaciones or "Sin observaciones",
            })
        return resultado

    @classmethod
    def get_product_stock_and_price(cls, db: Session, query: str) -> List[Dict[str, Any]]:
        keywords = cls.extract_keywords(query)
        conditions = []
        if keywords:
            for kw in keywords:
                term = f"%{kw}%"
                conditions.append(Producto.nombre.ilike(term))
                conditions.append(Producto.sku.ilike(term))
        else:
            term = f"%{query.strip()}%"
            conditions.append(Producto.nombre.ilike(term))
            conditions.append(Producto.sku.ilike(term))

        stmt = (
            select(Producto, Categoria.nombre.label("categoria_nombre"))
            .outerjoin(Categoria, Producto.categoria_id == Categoria.id)
            .where(or_(*conditions))
            .limit(10)
        )
        results = db.execute(stmt).all()
        return [
            {
                "sku": prod.sku,
                "nombre": prod.nombre,
                "categoria": cat_nombre or "Sin categoría",
                "precio_unitario": float(prod.precio_unitario or 0),
                "precio_costo": float(getattr(prod, "precio_costo", 0) or 0),
                "stock_actual": prod.stock_actual or 0,
                "stock_minimo": prod.stock_minimo or 0,
                "alerta_stock": (prod.stock_actual or 0) <= (prod.stock_minimo or 0),
            }
            for prod, cat_nombre in results
        ]

    @staticmethod
    def get_critical_stock_products(db: Session) -> List[Dict[str, Any]]:
        stmt = (
            select(Producto, Categoria.nombre.label("categoria_nombre"))
            .outerjoin(Categoria, Producto.categoria_id == Categoria.id)
            .where(Producto.stock_actual <= Producto.stock_minimo)
            .order_by(Producto.stock_actual.asc())
        )
        results = db.execute(stmt).all()
        return [
            {
                "sku": prod.sku,
                "nombre": prod.nombre,
                "categoria": cat_nombre or "General",
                "stock_actual": prod.stock_actual or 0,
                "stock_minimo": prod.stock_minimo or 0,
                "unidades_faltantes": max(0, (prod.stock_minimo or 0) - (prod.stock_actual or 0)),
                "precio_venta": float(prod.precio_unitario or 0),
            }
            for prod, cat_nombre in results
        ]

    @staticmethod
    def get_purchased_products_history(db: Session, limit: int = 20) -> List[Dict[str, Any]]:
        stmt = (
            select(DetallePedido)
            .options(
                selectinload(DetallePedido.producto),
                selectinload(DetallePedido.pedido).selectinload(Pedido.cliente),
            )
            .order_by(DetallePedido.id.desc())
            .limit(limit)
        )
        detalles = db.scalars(stmt).all()
        return [
            {
                "producto": d.producto.nombre if d.producto else "Producto General",
                "cantidad": d.cantidad,
                "subtotal": float(d.subtotal or 0),
                "pedido": d.pedido.codigo_pedido if d.pedido else "—",
                "cliente": d.pedido.cliente.razon_social if d.pedido and d.pedido.cliente else "—",
            }
            for d in detalles
        ]

    @staticmethod
    def get_clients_bought_today(db: Session) -> Dict[str, Any]:
        ahora = datetime.now()
        hoy_str = ahora.strftime("%Y-%m-%d")

        stmt = (
            select(Pedido)
            .options(
                selectinload(Pedido.cliente),
                selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
            )
            .order_by(Pedido.id.desc())
        )
        pedidos = db.scalars(stmt).all()
        pedidos_hoy = [p for p in pedidos if p.fecha_pedido and p.fecha_pedido.strftime("%Y-%m-%d") == hoy_str]

        if not pedidos_hoy:
            ultimo = pedidos[0] if pedidos else None
            return {
                "compras_hoy": 0,
                "mensaje": "Hoy aún no se han registrado compras.",
                "ultimo_pedido": {
                    "codigo": ultimo.codigo_pedido,
                    "cliente": ultimo.cliente.razon_social if ultimo and ultimo.cliente else "—",
                    "fecha": ultimo.fecha_pedido.strftime("%d/%m/%Y") if ultimo and ultimo.fecha_pedido else "—",
                } if ultimo else None
            }

        return {
            "total_pedidos_hoy": len(pedidos_hoy),
            "pedidos": [
                {
                    "cliente": p.cliente.razon_social if p.cliente else "General",
                    "codigo": p.codigo_pedido,
                    "total": float(p.monto_total or 0),
                }
                for p in pedidos_hoy
            ]
        }

    @staticmethod
    def get_indicadores_comerciales(db: Session) -> Dict[str, Any]:
        ultimo = IndicatorService.get_latest(db)
        if not ultimo:
            return {"mensaje": "Aún no se ha calculado ningún indicador comercial en el sistema."}

        decisiones_no_efectivas = [
            d for d in DecisionService.get_all(db, limit=20) if d["es_efectiva"] is False
        ][:5]

        return {
            "fecha_calculo": ultimo.fecha_calculo.strftime("%d/%m/%Y %H:%M"),
            "NEPP": {
                "nombre": "Número de Errores en Productos Pedidos",
                "formula": "TEPP ÷ TPP",
                "valor": float(ultimo.valor_nepp or 0),
                "total_errores_productos": ultimo.total_errores_productos,
                "total_items_pedidos": ultimo.total_items_pedidos,
                "meta": "Menor a 0.05 es bueno; entre 0.05 y 0.10 es regular; mayor a 0.10 es crítico.",
            },
            "PFCC": {
                "nombre": "Porcentaje de Fallas en Condiciones Comerciales",
                "formula": "(TCCF ÷ TCCD) × 100",
                "valor_porcentaje": float(ultimo.valor_pfcc or 0),
                "total_fallas_condiciones": ultimo.total_fallas_condiciones,
                "total_condiciones_pactadas": ultimo.total_condiciones_pactadas,
                "meta": "Menor a 10% es bueno; entre 10% y 25% es regular; mayor a 25% es crítico.",
            },
            "NTDC": {
                "nombre": "Nivel de Toma de Decisiones Comerciales",
                "formula": "(TDCE ÷ TDCT) × 100",
                "valor_porcentaje": float(ultimo.valor_ntdc or 0),
                "total_decisiones_efectivas": ultimo.total_decisiones_efectivas,
                "total_decisiones_evaluadas": ultimo.total_decisiones_evaluadas,
                "total_decisiones_corregidas": ultimo.total_decisiones_corregidas,
                "meta": "75% o más es bueno; entre 50% y 74% es regular; menor a 50% es crítico.",
                "criterio": (
                    "Cada pedido registrado (salvo los cancelados) cuenta como una decisión comercial. "
                    "Es efectiva cuando el pedido no mantiene errores de ítem ni fallas de condición "
                    "comercial. Se evalúa en vivo: si el asesor corrige la incidencia, la decisión pasa "
                    "a efectiva y se marca como 'corregida'."
                ),
                "decisiones_no_efectivas_recientes": [
                    {
                        "pedido": d["pedido_codigo"],
                        "cliente": d["cliente_nombre"],
                        "vendedor": d["usuario_nombre"],
                        "motivo": d["observaciones_impacto"],
                    }
                    for d in decisiones_no_efectivas
                ],
            },
        }

    @staticmethod
    def get_order_by_code(db: Session, codigo: str) -> Dict[str, Any]:
        codigo = (codigo or "").strip()
        if not codigo:
            return {"encontrado": False, "mensaje": "No se indicó ningún código de pedido a buscar."}

        stmt = (
            select(Pedido)
            .options(
                selectinload(Pedido.cliente),
                selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
                selectinload(Pedido.auditoria_condicion),
            )
            .where(Pedido.codigo_pedido.ilike(f"%{codigo}%"))
            .order_by(Pedido.id.desc())
        )
        pedido = db.scalars(stmt).first()
        if not pedido:
            return {
                "encontrado": False,
                "mensaje": f"No existe ningún pedido cuyo código coincida con '{codigo}'.",
            }

        items_con_error = [
            f"{d.cantidad}x {d.producto.nombre if d.producto else 'Item'} — {d.tipo_error}"
            + (f" ({d.descripcion_error})" if d.descripcion_error else "")
            for d in pedido.detalles
            if d.tiene_error
        ]

        falla = pedido.auditoria_condicion
        falla_condicion = f"Sí — {falla.motivo_falla}" if falla and falla.tiene_falla else "No"

        decision = DecisionService._buscar_decision(db, pedido.id)
        decision_info = (
            {
                "es_efectiva": decision.es_efectiva,
                "requirio_correccion": decision.requirio_correccion,
                "observaciones": decision.observaciones_impacto,
            }
            if decision
            else "Sin decisión registrada (pedido cancelado o pendiente de sincronizar)."
        )

        return {
            "encontrado": True,
            "codigo_pedido": pedido.codigo_pedido,
            "cliente": pedido.cliente.razon_social if pedido.cliente else "Cliente General",
            "estado": str(pedido.estado),
            "fecha": pedido.fecha_pedido.strftime("%d/%m/%Y") if pedido.fecha_pedido else "—",
            "monto_total": float(pedido.monto_total or 0),
            "tiene_error_en_items": bool(items_con_error),
            "detalle_errores_items": items_con_error if items_con_error else "Ninguno",
            "falla_condicion_comercial": falla_condicion,
            "decision_comercial": decision_info,
        }

    @staticmethod
    def get_top_rotation_products(db: Session, limit: int = 5) -> List[Dict[str, Any]]:
        orden_rotacion = case(
            (Producto.nivel_rotacion == "Alta", 0),
            (Producto.nivel_rotacion == "Media", 1),
            (Producto.nivel_rotacion == "Baja", 2),
            else_=3,
        )
        stmt = (
            select(Producto, Categoria.nombre.label("cat_nombre"))
            .outerjoin(Categoria, Producto.categoria_id == Categoria.id)
            .order_by(orden_rotacion, Producto.stock_actual.desc())
            .limit(limit)
        )
        prods = db.execute(stmt).all()
        return [
            {
                "sku": p.sku,
                "nombre": p.nombre,
                "rotacion": p.nivel_rotacion,
                "stock": p.stock_actual,
                "precio": float(p.precio_unitario or 0),
            }
            for p, cat in prods
        ]

    @classmethod
    def get_customer_detail(cls, db: Session, query: str) -> Dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return {"encontrado": False, "mensaje": "No se indicó ningún cliente a buscar."}

        term = f"%{query}%"
        cliente = db.scalar(
            select(Cliente).where(
                or_(Cliente.razon_social.ilike(term), Cliente.ruc_dni.ilike(term))
            )
        )
        if not cliente:
            return {
                "encontrado": False,
                "mensaje": f"No existe ningún cliente registrado que coincida con '{query}'.",
            }

        condiciones = db.scalars(
            select(CondicionComercial).where(CondicionComercial.cliente_id == cliente.id)
        ).all()
        total_pedidos = db.scalar(
            select(func.count(Pedido.id)).where(Pedido.cliente_id == cliente.id)
        ) or 0
        total_solicitudes = db.scalar(
            select(func.count(SolicitudCliente.id)).where(
                SolicitudCliente.cliente_id == cliente.id
            )
        ) or 0

        return {
            "encontrado": True,
            "razon_social": cliente.razon_social,
            "ruc_dni": cliente.ruc_dni,
            "tipo_cliente": cliente.tipo_cliente,
            "clasificacion": cliente.clasificacion,
            "estado": cliente.estado,
            "direccion": cliente.direccion or "—",
            "distrito": cliente.distrito or "—",
            "telefono": cliente.telefono or "—",
            "correo": cliente.correo or "—",
            "condiciones_comerciales": [
                {
                    "tipo_condicion": c.tipo_condicion,
                    "plazo_dias": c.dias_plazo_pactados,
                    "descuento_pct": float(c.porcentaje_descuento or 0),
                    "forma_pago_pactada": c.forma_pago_pactada,
                }
                for c in condiciones
            ] or "Sin condiciones pactadas",
            "total_pedidos_registrados": total_pedidos,
            "total_solicitudes_registradas": total_solicitudes,
        }

    @staticmethod
    def get_customer_requests(
        db: Session, estado: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(SolicitudCliente)
            .options(
                selectinload(SolicitudCliente.cliente),
                selectinload(SolicitudCliente.detalles),
            )
            .order_by(SolicitudCliente.id.desc())
        )
        solicitudes = db.scalars(stmt).all()

        if estado:
            solicitudes = [
                s for s in solicitudes if str(s.estado).lower() == estado.lower()
            ]

        solicitudes = solicitudes[:limit]
        return [
            {
                "codigo_solicitud": s.codigo_solicitud,
                "cliente": s.cliente.razon_social if s.cliente else "—",
                "fecha": s.fecha_solicitud.strftime("%d/%m/%Y") if s.fecha_solicitud else "—",
                "estado": s.estado,
                "canal_recepcion": s.canal_recepcion or "—",
                "items_solicitados": [
                    f"{d.cantidad_solicitada}x {d.nombre_producto_solicitado}"
                    + (f" (S/ {float(d.precio_esperado):,.2f} esperado)" if d.precio_esperado else "")
                    for d in s.detalles
                ],
                "observaciones": s.observaciones or "Sin observaciones",
            }
            for s in solicitudes
        ]

    @staticmethod
    def get_customer_request_by_code(db: Session, codigo: str) -> Dict[str, Any]:
        codigo = (codigo or "").strip()
        if not codigo:
            return {"encontrado": False, "mensaje": "No se indicó ningún código de solicitud a buscar."}

        stmt = (
            select(SolicitudCliente)
            .options(
                selectinload(SolicitudCliente.cliente),
                selectinload(SolicitudCliente.detalles),
                selectinload(SolicitudCliente.usuario),
            )
            .where(SolicitudCliente.codigo_solicitud.ilike(f"%{codigo}%"))
            .order_by(SolicitudCliente.id.desc())
        )
        solicitud = db.scalars(stmt).first()
        if not solicitud:
            return {
                "encontrado": False,
                "mensaje": f"No existe ninguna solicitud cuyo código coincida con '{codigo}'.",
            }

        return {
            "encontrado": True,
            "codigo_solicitud": solicitud.codigo_solicitud,
            "cliente": solicitud.cliente.razon_social if solicitud.cliente else "—",
            "registrada_por": solicitud.usuario.nombre_completo if solicitud.usuario else "—",
            "fecha": solicitud.fecha_solicitud.strftime("%d/%m/%Y") if solicitud.fecha_solicitud else "—",
            "estado": solicitud.estado,
            "canal_recepcion": solicitud.canal_recepcion or "—",
            "items_solicitados": [
                {
                    "producto": d.nombre_producto_solicitado,
                    "cantidad": d.cantidad_solicitada,
                    "precio_esperado": float(d.precio_esperado) if d.precio_esperado else None,
                }
                for d in solicitud.detalles
            ],
            "observaciones": solicitud.observaciones or "Sin observaciones",
        }

    @classmethod
    def get_stock_movements(
        cls, db: Session, query: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(MovimientoStock)
            .options(selectinload(MovimientoStock.producto), selectinload(MovimientoStock.pedido))
            .order_by(MovimientoStock.id.desc())
        )
        movimientos = db.scalars(stmt).all()

        if query:
            keywords = cls.extract_keywords(query) or [query.strip().lower()]
            movimientos = [
                m
                for m in movimientos
                if m.producto
                and any(kw in m.producto.nombre.lower() or kw in m.producto.sku.lower() for kw in keywords)
            ]

        movimientos = movimientos[:limit]
        return [
            {
                "producto": m.producto.nombre if m.producto else "—",
                "tipo": m.tipo,
                "cantidad": m.cantidad,
                "stock_anterior": m.stock_anterior,
                "stock_nuevo": m.stock_nuevo,
                "motivo": m.motivo or "—",
                "pedido_relacionado": m.pedido.codigo_pedido if m.pedido else None,
                "fecha": m.creado_en.strftime("%d/%m/%Y %H:%M") if m.creado_en else "—",
            }
            for m in movimientos
        ]

    @staticmethod
    def get_categories(db: Session, limit: int = 20) -> List[Dict[str, Any]]:
        stmt = (
            select(Categoria, func.count(Producto.id).label("total_productos"))
            .outerjoin(Producto, Producto.categoria_id == Categoria.id)
            .group_by(Categoria.id)
            .order_by(Categoria.nombre.asc())
            .limit(limit)
        )
        rows = db.execute(stmt).all()
        return [
            {
                "nombre": cat.nombre,
                "descripcion": cat.descripcion or "—",
                "total_productos": total,
            }
            for cat, total in rows
        ]

    @staticmethod
    def get_audit_history(
        db: Session,
        current_user: Usuario,
        accion: Optional[str] = None,
        modulo: Optional[str] = None,
        limit: int = 20,
    ) -> Any:
        if current_user.rol != "administrador":
            return {
                "mensaje": "No tienes permisos para consultar el historial de auditoría del sistema; esa función está disponible solo para administradores."
            }

        resultado = HistoryService.get_all(
            db, modulo=modulo, accion=accion, pagina=1, por_pagina=min(limit, 50)
        )
        return [
            {
                "usuario": item["usuario_nombre"],
                "accion": item["accion"],
                "modulo_afectado": item["modulo_afectado"],
                "detalle": (item["detalle_cambio"] or {}).get("descripcion", "—"),
                "fecha": item["fecha_hora"].strftime("%d/%m/%Y %H:%M") if item["fecha_hora"] else "—",
            }
            for item in resultado["items"]
        ]

    @staticmethod
    def get_my_profile(current_user: Usuario) -> Dict[str, Any]:
        return {
            "nombre_completo": current_user.nombre_completo,
            "nombre_usuario": current_user.nombre_usuario,
            "correo": current_user.correo,
            "rol": current_user.rol,
            "esta_activo": current_user.esta_activo,
        }

    @staticmethod
    def find_worker_info(db: Session, current_user: Usuario, query: str) -> Dict[str, Any]:
        query = (query or "").strip()
        if current_user.rol != "administrador":
            return {
                "encontrado": False,
                "mensaje": "No se encontró ningún usuario registrado con ese nombre.",
            }
        if not query:
            return {"encontrado": False, "mensaje": "No se indicó ningún nombre o correo a buscar."}

        term = f"%{query}%"
        usuario = db.scalar(
            select(Usuario).where(
                or_(
                    Usuario.nombre_completo.ilike(term),
                    Usuario.correo.ilike(term),
                    Usuario.nombre_usuario.ilike(term),
                )
            )
        )
        if not usuario:
            return {
                "encontrado": False,
                "mensaje": f"No existe ningún trabajador registrado que coincida con '{query}'.",
            }
        return {
            "encontrado": True,
            "nombre_completo": usuario.nombre_completo,
            "nombre_usuario": usuario.nombre_usuario,
            "correo": usuario.correo,
            "rol": usuario.rol,
            "esta_activo": usuario.esta_activo,
        }

    @staticmethod
    def list_workers(db: Session, current_user: Usuario) -> Any:
        if current_user.rol != "administrador":
            return {"mensaje": "No tienes permisos para listar a los demás usuarios del sistema."}

        stmt = select(Usuario).order_by(Usuario.nombre_completo.asc())
        usuarios = db.scalars(stmt).all()
        return [
            {
                "nombre_completo": u.nombre_completo,
                "nombre_usuario": u.nombre_usuario,
                "correo": u.correo,
                "rol": u.rol,
                "esta_activo": u.esta_activo,
            }
            for u in usuarios
        ]

    @staticmethod
    def get_my_orders(db: Session, current_user: Usuario, limit: int = 10) -> List[Dict[str, Any]]:
        stmt = (
            select(Pedido)
            .options(
                selectinload(Pedido.cliente),
                selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
            )
            .where(Pedido.usuario_id == current_user.id)
            .order_by(Pedido.id.desc())
            .limit(limit)
        )
        pedidos = db.scalars(stmt).all()
        return [
            {
                "codigo_pedido": p.codigo_pedido,
                "cliente": p.cliente.razon_social if p.cliente else "Cliente General",
                "fecha": p.fecha_pedido.strftime("%d/%m/%Y") if p.fecha_pedido else "—",
                "estado": str(p.estado),
                "monto_total": float(p.monto_total or 0),
                "items": [
                    f"{d.cantidad}x {d.producto.nombre if d.producto else 'Item'}"
                    for d in p.detalles
                ],
            }
            for p in pedidos
        ]

    TOOL_SCHEMAS: List[Dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "listar_condiciones_comerciales",
                "description": "Condiciones comerciales (descuento, plazo, límite de crédito) pactadas por cliente.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_clientes",
                "description": "Cartera de clientes: tipo (Mayorista/Institucional/Minorista), clasificación (Regular/VIP) y condición comercial.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_pedidos",
                "description": "Pedidos: cliente, ítems, monto, estado, condiciones y fallas comerciales. Útil para ventas, metas o filtrar por estado.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "estado": {
                            "type": ["string", "null"],
                            "enum": ["Pendiente", "Aprobado", "Entregado", "Cancelado", None],
                            "description": "Filtra por estado.",
                        },
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buscar_producto_stock_precio",
                "description": "Busca un producto por nombre/SKU: stock actual, mínimo y precio.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Nombre o SKU a buscar."},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_productos_stock_critico",
                "description": "Productos con stock en o bajo el mínimo (necesitan reposición).",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "historial_productos_comprados",
                "description": "Historial de productos vendidos: qué, cuánto y en qué pedido.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "clientes_que_compraron_hoy",
                "description": "Clientes que compraron hoy y total de pedidos del día.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "obtener_indicadores_comerciales",
                "description": "Indicadores NEPP, PFCC y NTDC con sus metas y decisiones no efectivas recientes.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buscar_pedido_por_codigo",
                "description": "Busca un pedido por código (parcial válido, ej: DEFE0F67): estado, errores de ítems, falla de condición y decisión asociada.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "codigo": {
                            "type": "string",
                            "description": "Código completo o parcial (ej: PED-DEFE0F67).",
                        },
                    },
                    "required": ["codigo"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "productos_mayor_rotacion",
                "description": "Productos ordenados por rotación (Alta/Media/Baja); a igual nivel, desempata por stock.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buscar_cliente_detalle",
                "description": "Ficha completa de un cliente por razón social o RUC/DNI: contacto, condiciones pactadas y totales de pedidos/solicitudes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Razón social o RUC/DNI."},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_solicitudes_clientes",
                "description": "Solicitudes/cotizaciones de clientes (WhatsApp u otro canal) previas a un pedido formal: producto, cantidad, precio esperado, canal y estado.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "estado": {"type": ["string", "null"], "description": "Filtra por estado (ej: Pendiente, Atendida)."},
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buscar_solicitud_por_codigo",
                "description": "Busca una solicitud de cliente por código (parcial válido, ej: SOL-ABC12345) y devuelve su detalle.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "codigo": {"type": "string", "description": "Código completo o parcial."},
                    },
                    "required": ["codigo"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_movimientos_stock",
                "description": "Movimientos de inventario (entrada/salida/ajuste) con stock antes/después. Útil para explicar cambios de stock.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": ["string", "null"], "description": "Nombre o SKU del producto (opcional)."},
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_categorias",
                "description": "Lista las categorías de productos registradas, con su descripción y cuántos productos tiene cada una.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "consultar_historial_auditoria",
                "description": "Consulta el historial de auditoría del sistema (quién hizo qué acción, en qué módulo y cuándo). Solo disponible para el administrador.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "accion": {
                            "type": ["string", "null"],
                            "enum": [
                                "CREAR", "ACTUALIZAR", "ELIMINAR", "CONSULTA_IA",
                                "INICIAR_SESION", "CERRAR_SESION", "EXPORTAR", "ERROR", None,
                            ],
                            "description": "Filtra por tipo de acción.",
                        },
                        "modulo": {"type": ["string", "null"], "description": "Filtra por módulo afectado (ej: Pedidos, Clientes, Productos, Auth)."},
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "obtener_mi_perfil",
                "description": "Nombre, usuario, correo y rol de quien está chateando ahora. Para 'quién soy', 'mi correo', 'mi rol'.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buscar_informacion_trabajador",
                "description": "Busca nombre/correo/rol de OTRO usuario. Solo el administrador puede ver datos de otras personas; para los demás roles no revela nada.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nombre_o_correo": {
                            "type": "string",
                            "description": "Nombre, correo o usuario a buscar.",
                        },
                    },
                    "required": ["nombre_o_correo"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_trabajadores",
                "description": "Lista de todos los usuarios del sistema con su rol y estado. Solo administrador.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mis_pedidos_registrados",
                "description": "Pedidos registrados por el propio usuario autenticado (sus ventas).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": ["integer", "null"], "description": "Máximo a devolver."},
                    },
                    "required": [],
                },
            },
        },
    ]

    TOOL_CATEGORIES: Dict[str, set] = {
        "listar_condiciones_comerciales": {"clientes"},
        "listar_clientes": {"clientes"},
        "buscar_cliente_detalle": {"clientes"},
        "listar_pedidos": {"pedidos"},
        "buscar_pedido_por_codigo": {"pedidos"},
        "clientes_que_compraron_hoy": {"pedidos", "clientes"},
        "historial_productos_comprados": {"pedidos", "productos"},
        "mis_pedidos_registrados": {"pedidos", "identidad"},
        "buscar_producto_stock_precio": {"productos"},
        "listar_productos_stock_critico": {"productos"},
        "productos_mayor_rotacion": {"productos"},
        "listar_movimientos_stock": {"productos"},
        "listar_solicitudes_clientes": {"solicitudes"},
        "buscar_solicitud_por_codigo": {"solicitudes"},
        "obtener_indicadores_comerciales": {"indicadores"},
        "obtener_mi_perfil": {"identidad"},
        "buscar_informacion_trabajador": {"identidad"},
        "listar_trabajadores": {"identidad"},
        "listar_categorias": {"productos"},
        "consultar_historial_auditoria": {"auditoria"},
    }

    CATEGORY_KEYWORDS: Dict[str, List[str]] = {
        "clientes": [
            "cliente", "clientes", "cartera", "ruc", "dni", "razon social", "razón social",
        ],
        "pedidos": [
            "pedido", "pedidos", "venta", "ventas", "vendimos", "vendido", "compraron",
            "compró", "compro", "monto", "meta", "avance",
        ],
        "productos": [
            "producto", "productos", "stock", "precio", "precios", "sku", "rotacion",
            "rotación", "reposicion", "reposición", "inventario", "movimiento",
            "movimientos", "categoria", "categoría",
        ],
        "solicitudes": [
            "solicitud", "solicitudes", "cotizacion", "cotización", "cotizaciones",
            "whatsapp", "canal", "sol-",
        ],
        "indicadores": [
            "indicador", "indicadores", "nepp", "pfcc", "ntdc", "desempeño", "desempeno",
            "decision", "decisión", "decisiones",
        ],
        "identidad": [
            "quien soy", "quién soy", "mi correo", "mi nombre", "mi rol", "mi perfil",
            "trabajador", "trabajadores", "empleado", "empleados", "usuario", "usuarios",
            "perfil",
        ],
        "auditoria": [
            "auditoria", "auditoría", "historial", "log", "logs", "bitacora", "bitácora",
            "registro de actividad", "quien hizo", "quién hizo", "actividad del sistema",
        ],
    }

    @classmethod
    def select_relevant_tools(cls, query: str) -> List[Dict[str, Any]]:
        """Filtra las tools enviadas al modelo según palabras clave de la consulta,
        para no mandar siempre el esquema completo y ahorrar tokens por request.
        Si ninguna categoría matchea (consulta ambigua), se envían todas como respaldo."""
        texto = (query or "").lower()
        categorias_detectadas = {
            categoria
            for categoria, palabras in cls.CATEGORY_KEYWORDS.items()
            if any(palabra in texto for palabra in palabras)
        }
        if not categorias_detectadas:
            return cls.TOOL_SCHEMAS

        seleccionadas = [
            schema
            for schema in cls.TOOL_SCHEMAS
            if cls.TOOL_CATEGORIES.get(schema["function"]["name"], set()) & categorias_detectadas
        ]
        return seleccionadas or cls.TOOL_SCHEMAS

    @classmethod
    def dispatch(cls, db: Session, current_user: Usuario, name: str, arguments: Dict[str, Any]) -> Any:
        """Ejecuta la herramienta que el modelo decidió llamar, según su nombre y argumentos."""
        handlers: Dict[str, Any] = {
            "listar_condiciones_comerciales": lambda: cls.get_commercial_terms(
                db, limit=arguments.get("limit", 10)
            ),
            "listar_clientes": lambda: cls.get_all_customers_summary(
                db, limit=arguments.get("limit", 15)
            ),
            "listar_pedidos": lambda: cls.get_orders_summary(
                db, estado=arguments.get("estado"), limit=arguments.get("limit", 10)
            ),
            "buscar_producto_stock_precio": lambda: cls.get_product_stock_and_price(
                db, arguments.get("query", "")
            ),
            "listar_productos_stock_critico": lambda: cls.get_critical_stock_products(db),
            "buscar_pedido_por_codigo": lambda: cls.get_order_by_code(
                db, arguments.get("codigo", "")
            ),
            "historial_productos_comprados": lambda: cls.get_purchased_products_history(
                db, limit=arguments.get("limit", 20)
            ),
            "clientes_que_compraron_hoy": lambda: cls.get_clients_bought_today(db),
            "obtener_indicadores_comerciales": lambda: cls.get_indicadores_comerciales(db),
            "productos_mayor_rotacion": lambda: cls.get_top_rotation_products(
                db, limit=arguments.get("limit", 5)
            ),
            "buscar_cliente_detalle": lambda: cls.get_customer_detail(
                db, arguments.get("query", "")
            ),
            "listar_solicitudes_clientes": lambda: cls.get_customer_requests(
                db, estado=arguments.get("estado"), limit=arguments.get("limit", 10)
            ),
            "buscar_solicitud_por_codigo": lambda: cls.get_customer_request_by_code(
                db, arguments.get("codigo", "")
            ),
            "listar_movimientos_stock": lambda: cls.get_stock_movements(
                db, query=arguments.get("query"), limit=arguments.get("limit", 20)
            ),
            "listar_categorias": lambda: cls.get_categories(
                db, limit=arguments.get("limit", 20)
            ),
            "consultar_historial_auditoria": lambda: cls.get_audit_history(
                db,
                current_user,
                accion=arguments.get("accion"),
                modulo=arguments.get("modulo"),
                limit=arguments.get("limit", 20),
            ),
            "obtener_mi_perfil": lambda: cls.get_my_profile(current_user),
            "buscar_informacion_trabajador": lambda: cls.find_worker_info(
                db, current_user, arguments.get("nombre_o_correo", "")
            ),
            "listar_trabajadores": lambda: cls.list_workers(db, current_user),
            "mis_pedidos_registrados": lambda: cls.get_my_orders(
                db, current_user, limit=arguments.get("limit", 10)
            ),
        }
        handler = handlers.get(name)
        if not handler:
            return {"error": f"Herramienta '{name}' no reconocida."}
        return handler()