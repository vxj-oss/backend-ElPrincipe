import re
import uuid
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import ahora_lima
from app.models.commercial_term import CondicionComercial
from app.models.commercial_term_failure import FallaCondicionComercial
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
from app.models.stock_movement import MovimientoStock
from app.schemas.customer_request import (
    ComparacionPedidoItem,
    ComparacionPedidoRequest,
)
from app.schemas.order import OrderCreate, OrderUpdate
from app.services.customer_request_service import SolicitudClienteService
from app.services.customer_service import CustomerService
from app.services.decision_service import DecisionService
from app.services.indicator_service import IndicatorService

ESTADOS_CONFIRMADOS = ("Aprobado", "Entregado")
TIPOS_ERROR_DETALLE_VALIDOS = {
    "Ninguno",
    "SKU_Incorrecto",
    "Precio_Desactualizado",
    "Stock_Insuficiente",
    "Cantidad_Erronea",
}


def normalizar_tipo_error(valor: Optional[str]) -> str:
    if not valor:
        return "Ninguno"
    limpio = valor.strip()
    if limpio in TIPOS_ERROR_DETALLE_VALIDOS:
        return limpio
    return "Cantidad_Erronea"


class OrderService:
    @staticmethod
    def _auditar_condicion_comercial_pedido(
        db: Session,
        pedido_id: int,
        cliente_id: int,
        forma_pago: str,
        monto_total: Decimal,
        condicion_comercial_id: Optional[int] = None,
    ) -> FallaCondicionComercial:
        politica_base = None
        if condicion_comercial_id:
            politica_base = db.scalar(
                select(CondicionComercial).where(CondicionComercial.id == condicion_comercial_id)
            )

        if not politica_base:
            stmt = (
                select(CondicionComercial)
                .where(CondicionComercial.cliente_id == cliente_id)
                .order_by(CondicionComercial.id.desc())
            )
            politica_base = db.scalar(stmt)

        tiene_falla = False
        motivo = "Condición comercial conforme con la política pactada."

        if not politica_base:
            if (forma_pago or "").strip().lower() != "contado":
                tiene_falla = True
                motivo = (
                    f"Discrepancia en condición comercial: Se digitó '{forma_pago}' pero el "
                    "cliente no tiene ninguna condición pactada (Estricto Contado)."
                )
        elif politica_base.tipo_condicion == "Credito":
            match = re.search(r"(\d+)", forma_pago or "")
            dias_digitados = int(match.group(1)) if match else 0
            dias_pactados = politica_base.dias_plazo_pactados or 0
            if dias_digitados != dias_pactados:
                tiene_falla = True
                motivo = (
                    f"Discrepancia en condición comercial: Se digitó 'Crédito {dias_digitados}d' "
                    f"pero la condición pactada es 'Crédito {dias_pactados}d'."
                )
        elif politica_base.tipo_condicion == "Descuento":
            match = re.search(r"(\d+)", forma_pago or "")
            pct_digitado = Decimal(match.group(1)) if match else Decimal("0")
            pct_pactado = politica_base.porcentaje_descuento or Decimal("0")
            if pct_digitado != pct_pactado:
                tiene_falla = True
                motivo = (
                    f"Discrepancia en condición comercial: Se digitó 'Descuento {pct_digitado}%' "
                    f"pero la condición pactada es 'Descuento {pct_pactado}%'."
                )
        elif politica_base.tipo_condicion == "Forma_Pago":
            digitado = (forma_pago or "").strip()
            pactado = politica_base.forma_pago_pactada or "Contado"
            if digitado.lower() != pactado.lower():
                tiene_falla = True
                motivo = (
                    f"Discrepancia en condición comercial: Se digitó '{digitado}' pero la "
                    f"condición pactada es '{pactado}'."
                )

        return FallaCondicionComercial(
            pedido_id=pedido_id,
            condicion_comercial_id=politica_base.id if politica_base else None,
            tiene_falla=tiene_falla,
            motivo_falla=motivo,
        )

    @staticmethod
    def _items_tuplas(detalles) -> List[tuple]:
        return [(d.producto_id, d.cantidad) for d in detalles]

    @staticmethod
    def _revertir_solicitud(db: Session, solicitud_id: Optional[int]) -> None:
        if not solicitud_id:
            return
        solicitud = db.scalar(
            select(SolicitudCliente).where(SolicitudCliente.id == solicitud_id)
        )
        if solicitud and solicitud.estado == "Atendida":
            solicitud.estado = "Pendiente"

    @staticmethod
    def _descuento_pactado(db: Session, cliente_id: int) -> Decimal:
        politica = db.scalar(
            select(CondicionComercial)
            .where(
                CondicionComercial.cliente_id == cliente_id,
                CondicionComercial.tipo_condicion == "Descuento",
            )
            .order_by(CondicionComercial.id.desc())
        )
        if politica and politica.porcentaje_descuento:
            return Decimal(str(politica.porcentaje_descuento))
        return Decimal("0")

    @staticmethod
    def _evaluar_precio(precio_digitado: Decimal, prod: Producto, descuento_pct: Decimal):
        vigente = Decimal(str(prod.precio_unitario or 0))
        esperado = (vigente * (Decimal("100") - descuento_pct) / Decimal("100")).quantize(Decimal("0.01"))
        digitado = Decimal(str(precio_digitado))
        if digitado > esperado + Decimal("0.01"):
            extra = f" (descuento pactado {descuento_pct:.0f}% no aplicado)" if descuento_pct > 0 else ""
            return (
                f"Precio digitado S/ {digitado:.2f} supera el precio pactado S/ {esperado:.2f}{extra}."
            )
        if digitado < esperado - Decimal("0.01"):
            return (
                f"Precio digitado S/ {digitado:.2f} es menor al precio pactado S/ {esperado:.2f}."
            )
        return None

    @staticmethod
    def _mover_stock(
        db: Session,
        items: List[tuple],
        signo: int,
        pedido_id: Optional[int] = None,
        motivo: Optional[str] = None,
    ) -> None:
        tipo = "Salida" if signo < 0 else "Entrada"
        for producto_id, cantidad in items:
            prod = db.scalar(
                select(Producto).where(Producto.id == producto_id).with_for_update()
            )
            if not prod:
                continue
            anterior = prod.stock_actual or 0
            nuevo = max(0, anterior + signo * cantidad)
            prod.stock_actual = nuevo
            db.add(
                MovimientoStock(
                    producto_id=producto_id,
                    pedido_id=pedido_id,
                    tipo=tipo,
                    cantidad=cantidad,
                    stock_anterior=anterior,
                    stock_nuevo=nuevo,
                    motivo=motivo,
                )
            )

    @staticmethod
    def _alertas_stock_de_items(db: Session, items: List[tuple]) -> List[dict]:
        alertas = []
        vistos = set()
        for producto_id, _ in items:
            if producto_id in vistos:
                continue
            vistos.add(producto_id)
            prod = db.scalar(select(Producto).where(Producto.id == producto_id))
            if not prod:
                continue
            actual = prod.stock_actual or 0
            minimo = prod.stock_minimo or 0
            if actual <= minimo:
                alertas.append(
                    {
                        "producto_id": prod.id,
                        "nombre": prod.nombre,
                        "stock_actual": actual,
                        "stock_minimo": minimo,
                        "agotado": actual == 0,
                    }
                )
        return alertas

    @staticmethod
    def get_by_id(db: Session, order_id: int) -> Optional[Pedido]:
        stmt = (
            select(Pedido)
            .options(
                selectinload(Pedido.cliente),
                selectinload(Pedido.usuario),
                selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
                selectinload(Pedido.auditoria_condicion).selectinload(FallaCondicionComercial.condicion_comercial),
            )
            .where(Pedido.id == order_id)
        )
        return db.scalar(stmt)

    @staticmethod
    def get_all(
        db: Session,
        cliente_id: Optional[int] = None,
        estado: Optional[str] = None,
        con_error: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Pedido]:
        stmt = select(Pedido).options(
            selectinload(Pedido.cliente),
            selectinload(Pedido.usuario),
            selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
            selectinload(Pedido.auditoria_condicion).selectinload(FallaCondicionComercial.condicion_comercial),
        )
        if cliente_id:
            stmt = stmt.where(Pedido.cliente_id == cliente_id)
        if estado:
            stmt = stmt.where(Pedido.estado == estado)
        if con_error is not None:
            if con_error:
                stmt = stmt.where(
                    Pedido.detalles.any(DetallePedido.tiene_error == True)
                )
            else:
                stmt = stmt.where(
                    ~Pedido.detalles.any(DetallePedido.tiene_error == True)
                )
        stmt = stmt.order_by(Pedido.id.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def create(db: Session, user_id: int, order_in: OrderCreate) -> Pedido:
        cliente = CustomerService.get_by_id(db, order_in.cliente_id)
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente no encontrado",
            )
        if cliente.estado != "Activo":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pueden crear pedidos para un cliente inactivo",
            )

        solicitud = None
        auditoria_ia = None
        cantidades_solicitadas = {}
        cantidades_solicitadas_por_nombre = {}

        if order_in.solicitud_id:
            solicitud = SolicitudClienteService.get_by_id(db, order_in.solicitud_id)
            if solicitud:
                for s_det in solicitud.detalles:
                    if s_det.producto_id:
                        cantidades_solicitadas[s_det.producto_id] = s_det.cantidad_solicitada
                    if s_det.nombre_producto_solicitado:
                        cantidades_solicitadas_por_nombre[s_det.nombre_producto_solicitado.strip().lower()] = s_det.cantidad_solicitada

                items_comparacion = []
                for item in order_in.items:
                    prod = db.scalar(
                        select(Producto).where(Producto.id == item.producto_id)
                    )
                    items_comparacion.append(
                        ComparacionPedidoItem(
                            producto_id=item.producto_id,
                            sku=prod.sku if prod else "—",
                            nombre=prod.nombre if prod else "Item",
                            cantidad=item.cantidad,
                            precio_unitario=item.precio_unitario,
                        )
                    )

                auditoria_ia = SolicitudClienteService.audit_order_against_request(
                    db,
                    ComparacionPedidoRequest(
                        solicitud_id=order_in.solicitud_id,
                        cliente_id=order_in.cliente_id,
                        forma_pago=order_in.forma_pago,
                        items_pedido=items_comparacion,
                    ),
                )

        codigo = order_in.codigo_pedido or f"PED-{uuid.uuid4().hex[:8].upper()}"
        fecha_ped = order_in.fecha_pedido or ahora_lima()
        fecha_ent = order_in.fecha_entrega
        if order_in.estado == "Entregado" and not fecha_ent:
            fecha_ent = ahora_lima()

        db_order = Pedido(
            cliente_id=order_in.cliente_id,
            usuario_id=user_id,
            solicitud_id=order_in.solicitud_id,
            codigo_pedido=codigo,
            fecha_pedido=fecha_ped,
            fecha_entrega=fecha_ent,
            forma_pago=order_in.forma_pago,
            observaciones=order_in.observaciones,
            estado=order_in.estado or "Pendiente",
            monto_total=Decimal("0.00"),
        )
        db.add(db_order)
        db.flush()

        descuento_pct = OrderService._descuento_pactado(db, order_in.cliente_id)

        total_pedido = Decimal("0.00")
        algun_item_con_error = False
        for item in order_in.items:
            prod = db.scalar(select(Producto).where(Producto.id == item.producto_id))
            if not prod:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Producto con id {item.producto_id} no existe",
                )

            subtotal = Decimal(str(item.cantidad)) * item.precio_unitario
            total_pedido += subtotal

            item_tiene_error = item.tiene_error
            item_tipo_error = normalizar_tipo_error(item.tipo_error)
            item_desc_error = item.descripcion_error

            esperado_id = cantidades_solicitadas.get(item.producto_id)
            esperado_nombre = cantidades_solicitadas_por_nombre.get(prod.nombre.strip().lower())
            esperado = esperado_id if esperado_id is not None else esperado_nombre
            desfase_precio = OrderService._evaluar_precio(item.precio_unitario, prod, descuento_pct)

            if (prod.stock_actual or 0) < item.cantidad:
                item_tiene_error = True
                item_tipo_error = "Stock_Insuficiente"
                item_desc_error = f"Stock insuficiente en almacén (Disponible: {prod.stock_actual}, Pedido: {item.cantidad})."
            elif bool(cantidades_solicitadas or cantidades_solicitadas_por_nombre) and esperado is None:
                item_tiene_error = True
                item_tipo_error = "SKU_Incorrecto"
                item_desc_error = f"Producto no solicitado: '{prod.nombre}' no figuraba en la solicitud original."
            elif esperado is not None and item.cantidad != esperado:
                item_tiene_error = True
                item_tipo_error = "Cantidad_Erronea"
                item_desc_error = f"Cantidad difiere de la solicitud (Solicitado: {esperado}, Registrado: {item.cantidad})."
            elif desfase_precio:
                item_tiene_error = True
                item_tipo_error = "Precio_Desactualizado"
                item_desc_error = desfase_precio
            elif (
                auditoria_ia
                and auditoria_ia.hay_discrepancia
                and not item_tiene_error
                and auditoria_ia.tipo_error in TIPOS_ERROR_DETALLE_VALIDOS
                and auditoria_ia.tipo_error != "Ninguno"
            ):
                item_tiene_error = True
                item_tipo_error = auditoria_ia.tipo_error
                item_desc_error = auditoria_ia.descripcion_discrepancia

            if item_tiene_error:
                algun_item_con_error = True

            detalle = DetallePedido(
                pedido_id=db_order.id,
                producto_id=item.producto_id,
                cantidad=item.cantidad,
                precio_unitario=item.precio_unitario,
                subtotal=subtotal,
                tiene_error=item_tiene_error,
                tipo_error=item_tipo_error,
                descripcion_error=item_desc_error,
            )
            db.add(detalle)

        auditoria_cond = OrderService._auditar_condicion_comercial_pedido(
            db=db,
            pedido_id=db_order.id,
            cliente_id=order_in.cliente_id,
            forma_pago=order_in.forma_pago,
            monto_total=total_pedido,
            condicion_comercial_id=order_in.condicion_comercial_id,
        )
        db.add(auditoria_cond)

        if solicitud:
            solicitud.estado = "Atendida"

        if (
            (algun_item_con_error or auditoria_cond.tiene_falla)
            and (db_order.estado or "Pendiente") in ESTADOS_CONFIRMADOS
        ):
            db_order.estado = "Pendiente"
            db_order.fecha_entrega = None

        db_order.monto_total = total_pedido

        items_pedido = [(it.producto_id, it.cantidad) for it in order_in.items]
        if db_order.estado in ESTADOS_CONFIRMADOS:
            OrderService._mover_stock(
                db, items_pedido, -1, db_order.id, f"Confirmación de pedido {db_order.codigo_pedido}"
            )
            db_order.stock_descontado = True

        db.commit()

        alertas = (
            OrderService._alertas_stock_de_items(db, items_pedido)
            if db_order.stock_descontado
            else []
        )

        pedido_creado = OrderService.get_by_id(db, db_order.id)
        DecisionService.sincronizar_pedido(db, pedido_creado)
        db.commit()
        IndicatorService.calculate_and_save(
            db, resumen="Recálculo automático tras registro de pedido"
        )
        pedido_creado = OrderService.get_by_id(db, db_order.id)
        pedido_creado.alertas_stock = alertas
        return pedido_creado

    @staticmethod
    def update(
        db: Session, order_id: int, order_in: OrderUpdate, usuario_id: Optional[int] = None
    ) -> Pedido:
        db_order = OrderService.get_by_id(db, order_id)
        if not db_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pedido no encontrado",
            )

        estado_anterior = db_order.estado
        stock_descontado_antes = db_order.stock_descontado
        items_antes = OrderService._items_tuplas(db_order.detalles)
        datos = order_in.model_dump(exclude_unset=True)

        items_reemplazados = "items" in datos and datos["items"] is not None

        target_cliente_id = datos.get("cliente_id", db_order.cliente_id)
        solicitud_id = datos.get("solicitud_id")

        solicitud = None
        if solicitud_id:
            solicitud = SolicitudClienteService.get_by_id(db, solicitud_id)
        else:
            stmt_sol = (
                select(SolicitudCliente)
                .options(selectinload(SolicitudCliente.detalles))
                .where(SolicitudCliente.cliente_id == target_cliente_id)
                .order_by(SolicitudCliente.id.desc())
            )
            solicitud = db.scalar(stmt_sol)

        cantidades_solicitadas = {}
        cantidades_solicitadas_por_nombre = {}
        if solicitud and solicitud.detalles:
            for s_det in solicitud.detalles:
                if s_det.producto_id:
                    cantidades_solicitadas[s_det.producto_id] = s_det.cantidad_solicitada
                if s_det.nombre_producto_solicitado:
                    cantidades_solicitadas_por_nombre[s_det.nombre_producto_solicitado.strip().lower()] = s_det.cantidad_solicitada

        if "estado" in datos:
            nuevo_estado = datos["estado"]
            if nuevo_estado == "Entregado":
                if not datos.get("fecha_entrega") and not db_order.fecha_entrega:
                    datos["fecha_entrega"] = ahora_lima()
            else:
                datos["fecha_entrega"] = None

        if "items" in datos and datos["items"] is not None:
            for detalle in list(db_order.detalles):
                db.delete(detalle)
            db.flush()

            descuento_pct = OrderService._descuento_pactado(db, target_cliente_id)
            total_pedido = Decimal("0.00")
            for item in order_in.items:
                prod = db.scalar(
                    select(Producto).where(Producto.id == item.producto_id)
                )
                if not prod:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Producto con id {item.producto_id} no existe",
                    )

                subtotal = Decimal(str(item.cantidad)) * item.precio_unitario
                total_pedido += subtotal

                item_tiene_error = False
                item_tipo_error = "Ninguno"
                item_desc_error = None

                esperado_id = cantidades_solicitadas.get(item.producto_id)
                esperado_nombre = cantidades_solicitadas_por_nombre.get(prod.nombre.strip().lower())
                esperado = esperado_id if esperado_id is not None else esperado_nombre

                tiene_referencia_solicitud = bool(cantidades_solicitadas or cantidades_solicitadas_por_nombre)
                desfase_precio = OrderService._evaluar_precio(item.precio_unitario, prod, descuento_pct)

                if (prod.stock_actual or 0) < item.cantidad:
                    item_tiene_error = True
                    item_tipo_error = "Stock_Insuficiente"
                    item_desc_error = f"Stock insuficiente en almacén (Disponible: {prod.stock_actual}, Pedido: {item.cantidad})."
                elif tiene_referencia_solicitud and esperado is None:
                    item_tiene_error = True
                    item_tipo_error = "SKU_Incorrecto"
                    item_desc_error = f"Producto no solicitado: '{prod.nombre}' no figuraba en la solicitud original."
                elif esperado is not None and item.cantidad != esperado:
                    item_tiene_error = True
                    item_tipo_error = "Cantidad_Erronea"
                    item_desc_error = f"Cantidad difiere de la solicitud (Solicitado: {esperado}, Registrado: {item.cantidad})."
                elif desfase_precio:
                    item_tiene_error = True
                    item_tipo_error = "Precio_Desactualizado"
                    item_desc_error = desfase_precio

                nuevo_detalle = DetallePedido(
                    pedido_id=db_order.id,
                    producto_id=item.producto_id,
                    cantidad=item.cantidad,
                    precio_unitario=item.precio_unitario,
                    subtotal=subtotal,
                    tiene_error=item_tiene_error,
                    tipo_error=normalizar_tipo_error(item_tipo_error),
                    descripcion_error=item_desc_error,
                )
                db.add(nuevo_detalle)

            db_order.monto_total = total_pedido
            del datos["items"]

        target_forma_pago = datos.get("forma_pago", db_order.forma_pago)
        target_cond_id = datos.get("condicion_comercial_id")
        if "condicion_comercial_id" in datos:
            del datos["condicion_comercial_id"]
        if "solicitud_id" in datos:
            del datos["solicitud_id"]

        for key, value in datos.items():
            setattr(db_order, key, value)

        evaluacion = OrderService._auditar_condicion_comercial_pedido(
            db=db,
            pedido_id=db_order.id,
            cliente_id=target_cliente_id,
            forma_pago=target_forma_pago,
            monto_total=db_order.monto_total,
            condicion_comercial_id=target_cond_id,
        )

        if db_order.auditoria_condicion:
            db_order.auditoria_condicion.condicion_comercial_id = evaluacion.condicion_comercial_id
            db_order.auditoria_condicion.tiene_falla = evaluacion.tiene_falla
            db_order.auditoria_condicion.motivo_falla = evaluacion.motivo_falla
            db_order.auditoria_condicion.fecha_evaluacion = ahora_lima()
        else:
            db.add(evaluacion)

        tiene_error_items = (
            db.scalar(
                select(func.count(DetallePedido.id)).where(
                    DetallePedido.pedido_id == db_order.id,
                    DetallePedido.tiene_error.is_(True),
                )
            )
            or 0
        ) > 0
        if (tiene_error_items or evaluacion.tiene_falla) and db_order.estado in ESTADOS_CONFIRMADOS:
            db_order.estado = "Pendiente"
            db_order.fecha_entrega = None

        if (
            db_order.estado in ESTADOS_CONFIRMADOS
            and estado_anterior not in ESTADOS_CONFIRMADOS
            and db_order.cliente
            and db_order.cliente.estado != "Activo"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede aprobar el pedido: el cliente está inactivo.",
            )

        items_despues = (
            [(it.producto_id, it.cantidad) for it in order_in.items]
            if items_reemplazados
            else items_antes
        )
        debe_descontar = db_order.estado in ESTADOS_CONFIRMADOS

        if stock_descontado_antes:
            OrderService._mover_stock(
                db, items_antes, 1, db_order.id, f"Reversión de pedido {db_order.codigo_pedido}"
            )
        if debe_descontar:
            OrderService._mover_stock(
                db, items_despues, -1, db_order.id, f"Confirmación de pedido {db_order.codigo_pedido}"
            )
        db_order.stock_descontado = debe_descontar

        if db_order.estado == "Cancelado":
            OrderService._revertir_solicitud(db, db_order.solicitud_id)

        db.commit()

        alertas = (
            OrderService._alertas_stock_de_items(db, items_despues)
            if debe_descontar
            else []
        )

        pedido_actualizado = OrderService.get_by_id(db, order_id)
        DecisionService.sincronizar_pedido(db, pedido_actualizado)
        db.commit()
        IndicatorService.calculate_and_save(
            db, resumen="Recálculo automático tras actualización de pedido"
        )
        pedido_actualizado = OrderService.get_by_id(db, order_id)
        pedido_actualizado.alertas_stock = alertas
        return pedido_actualizado

    @staticmethod
    def delete(db: Session, order_id: int) -> bool:
        db_order = OrderService.get_by_id(db, order_id)
        if not db_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pedido no encontrado",
            )
        if db_order.stock_descontado:
            OrderService._mover_stock(
                db,
                OrderService._items_tuplas(db_order.detalles),
                1,
                None,
                f"Eliminación de pedido {db_order.codigo_pedido}",
            )
        OrderService._revertir_solicitud(db, db_order.solicitud_id)
        db.delete(db_order)
        db.commit()
        IndicatorService.calculate_and_save(
            db, resumen="Recálculo automático tras eliminación de pedido"
        )
        return True

    @staticmethod
    def marcar_error(
        db: Session, order_id: int, tipo_error: str, descripcion: str
    ) -> Pedido:
        db_order = OrderService.get_by_id(db, order_id)
        if not db_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pedido no encontrado",
            )

        error_asignado = normalizar_tipo_error(tipo_error)

        for detalle in db_order.detalles:
            detalle.tiene_error = True
            detalle.tipo_error = error_asignado
            detalle.descripcion_error = descripcion

        if db_order.stock_descontado:
            OrderService._mover_stock(
                db,
                OrderService._items_tuplas(db_order.detalles),
                1,
                db_order.id,
                f"Marcado con error el pedido {db_order.codigo_pedido}",
            )
            db_order.stock_descontado = False

        db_order.estado = "Pendiente"
        db_order.fecha_entrega = None
        db_order.observaciones = f"[ERROR: {error_asignado}] {descripcion}".strip()

        db.commit()
        pedido = OrderService.get_by_id(db, order_id)
        DecisionService.sincronizar_pedido(db, pedido)
        db.commit()
        IndicatorService.calculate_and_save(
            db, resumen="Recálculo automático tras marcar error en pedido"
        )
        return OrderService.get_by_id(db, order_id)

    @staticmethod
    def limpiar_error(db: Session, order_id: int) -> Pedido:
        db_order = OrderService.get_by_id(db, order_id)
        if not db_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pedido no encontrado",
            )

        for detalle in db_order.detalles:
            detalle.tiene_error = False
            detalle.tipo_error = "Ninguno"
            detalle.descripcion_error = None

        db_order.observaciones = ""
        db.commit()
        pedido = OrderService.get_by_id(db, order_id)
        DecisionService.sincronizar_pedido(db, pedido)
        db.commit()
        IndicatorService.calculate_and_save(
            db, resumen="Recálculo automático tras limpiar error de pedido"
        )
        return OrderService.get_by_id(db, order_id)