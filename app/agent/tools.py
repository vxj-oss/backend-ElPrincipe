import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Categoria
from app.models.commercial_term import CondicionComercial
from app.models.customer import Cliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.services.decision_service import DecisionService
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
                "limite_credito": float(c.limite_credito_asignado or 0),
            })
        return resultado

    @staticmethod
    def get_all_customers_summary(db: Session, limit: int = 15) -> List[Dict[str, Any]]:
        stmt = select(Cliente).order_by(Cliente.id.desc()).limit(limit)
        clientes = db.scalars(stmt).all()
        resultado = []
        for c in clientes:
            doc = getattr(c, "ruc_dni", None) or getattr(c, "numero_documento", "—")
            stmt_cond = select(CondicionComercial).where(CondicionComercial.cliente_id == c.id)
            cond = db.scalar(stmt_cond)
            
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
                "meta": "75% o más es bueno; entre 50% y 74% es regular; menor a 50% es crítico.",
                "criterio": (
                    "Una decisión es efectiva cuando el pedido se confirma sin errores ni fallas "
                    "de condición comercial. Es no efectiva cuando el asesor confirma el pedido "
                    "a pesar de tener un error o falla detectada."
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

    TOOL_SCHEMAS: List[Dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "listar_condiciones_comerciales",
                "description": "Lista las condiciones comerciales (descuentos, plazos, límites de crédito) pactadas por cliente.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Máximo de condiciones a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_clientes",
                "description": "Lista la cartera de clientes registrados, su tipo (Mayorista/Institucional/Minorista), su clasificación (Regular/VIP) y sus condiciones comerciales pactadas.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Máximo de clientes a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_pedidos",
                "description": "Lista pedidos registrados: cliente, items, monto total, estado, condiciones y si tuvieron fallas comerciales. Útil para calcular ventas, avances de meta, o revisar pedidos por estado.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "estado": {
                            "type": "string",
                            "enum": ["Pendiente", "Aprobado", "Entregado", "Cancelado"],
                            "description": "Filtra por estado del pedido.",
                        },
                        "limit": {"type": "integer", "description": "Máximo de pedidos a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buscar_producto_stock_precio",
                "description": "Busca productos por nombre/SKU y devuelve su stock actual, stock mínimo y precio.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Nombre o parte del nombre/SKU del producto a buscar."},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "listar_productos_stock_critico",
                "description": "Lista los productos cuyo stock actual está en o por debajo del stock mínimo (necesitan reposición).",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "historial_productos_comprados",
                "description": "Lista el historial de productos vendidos en pedidos (qué se compró, cuánto y en qué pedido).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Máximo de registros a devolver."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "clientes_que_compraron_hoy",
                "description": "Indica qué clientes compraron hoy y el total de pedidos registrados en el día.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "obtener_indicadores_comerciales",
                "description": "Obtiene los indicadores comerciales NEPP (errores en pedidos), PFCC (fallas en condiciones comerciales) y NTDC (nivel de toma de decisiones), con sus metas y decisiones no efectivas recientes.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "productos_mayor_rotacion",
                "description": "Lista los productos ordenados por su nivel de rotación registrado en el sistema (Alta, Media, Baja); a igual nivel, desempata por mayor stock disponible.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Máximo de productos a devolver."},
                    },
                    "required": [],
                },
            },
        },
    ]

    @classmethod
    def dispatch(cls, db: Session, name: str, arguments: Dict[str, Any]) -> Any:
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
            "historial_productos_comprados": lambda: cls.get_purchased_products_history(
                db, limit=arguments.get("limit", 20)
            ),
            "clientes_que_compraron_hoy": lambda: cls.get_clients_bought_today(db),
            "obtener_indicadores_comerciales": lambda: cls.get_indicadores_comerciales(db),
            "productos_mayor_rotacion": lambda: cls.get_top_rotation_products(
                db, limit=arguments.get("limit", 5)
            ),
        }
        handler = handlers.get(name)
        if not handler:
            return {"error": f"Herramienta '{name}' no reconocida."}
        return handler()