import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.commercial_term import CondicionComercial
from app.models.commercial_term_failure import FallaCondicionComercial
from app.models.customer_request import SolicitudCliente
from app.models.order import Pedido
from app.models.order_item import DetallePedido
from app.models.product import Producto
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

        dias_pedido = 0
        if "15d" in forma_pago or "15" in forma_pago:
            dias_pedido = 15
        elif "30d" in forma_pago or "30" in forma_pago:
            dias_pedido = 30

        tiene_falla = False
        motivos = []

        dias_permitidos = (
            politica_base.dias_plazo_pactados
            if politica_base and politica_base.dias_plazo_pactados is not None
            else 0
        )
        limite_credito = (
            politica_base.limite_credito_asignado
            if politica_base and politica_base.limite_credito_asignado
            else Decimal("0.00")
        )

        if dias_pedido != dias_permitidos:
            tiene_falla = True
            pactado_txt = f"Crédito {dias_permitidos}d" if dias_permitidos > 0 else "Contado"
            digitado_txt = f"Crédito {dias_pedido}d" if dias_pedido > 0 else "Contado"
            motivos.append(
                f"Discrepancia en condición comercial: Se digitó '{digitado_txt}' pero la condición pactada seleccionada es '{pactado_txt}'."
            )

        if dias_pedido > 0 and limite_credito > 0 and monto_total > limite_credito:
            tiene_falla = True
            motivos.append(
                f"Límite de crédito excedido: Total de S/ {monto_total:.2f} supera el límite autorizado de S/ {limite_credito:.2f}."
            )

        return FallaCondicionComercial(
            pedido_id=pedido_id,
            condicion_comercial_id=politica_base.id if politica_base else None,
            tiene_falla=tiene_falla,
            motivo_falla=(
                " | ".join(motivos)
                if tiene_falla
                else "Condición comercial conforme con la política pactada."
            ),
        )

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
        fecha_ped = order_in.fecha_pedido or datetime.now(timezone.utc)
        fecha_ent = order_in.fecha_entrega
        if order_in.estado == "Entregado" and not fecha_ent:
            fecha_ent = datetime.now(timezone.utc)

        db_order = Pedido(
            cliente_id=order_in.cliente_id,
            usuario_id=user_id,
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

        total_pedido = Decimal("0.00")
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
            item_tipo_error = item.tipo_error or "Ninguno"
            item_desc_error = item.descripcion_error

            esperado_id = cantidades_solicitadas.get(item.producto_id)
            esperado_nombre = cantidades_solicitadas_por_nombre.get(prod.nombre.strip().lower())
            esperado = esperado_id if esperado_id is not None else esperado_nombre

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
            elif (
                auditoria_ia and auditoria_ia.hay_discrepancia and not item_tiene_error
            ):
                item_tiene_error = True
                item_tipo_error = (
                    auditoria_ia.tipo_error
                    if auditoria_ia.tipo_error
                    in [
                        "SKU_Incorrecto",
                        "Precio_Desactualizado",
                        "Stock_Insuficiente",
                        "Cantidad_Erronea",
                    ]
                    else "Cantidad_Erronea"
                )
                item_desc_error = auditoria_ia.descripcion_discrepancia

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

        db_order.monto_total = total_pedido
        db.commit()

        pedido_creado = OrderService.get_by_id(db, db_order.id)
        if pedido_creado.estado in ESTADOS_CONFIRMADOS:
            DecisionService.registrar_confirmacion_pedido(db, pedido_creado, user_id)
            IndicatorService.calculate_and_save(
                db, resumen="Recálculo automático tras confirmación de pedido"
            )
            pedido_creado = OrderService.get_by_id(db, db_order.id)
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
        datos = order_in.model_dump(exclude_unset=True)

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
                    datos["fecha_entrega"] = datetime.now(timezone.utc)
            else:
                datos["fecha_entrega"] = None

        if "items" in datos and datos["items"] is not None:
            for detalle in list(db_order.detalles):
                db.delete(detalle)
            db.flush()

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

                nuevo_detalle = DetallePedido(
                    pedido_id=db_order.id,
                    producto_id=item.producto_id,
                    cantidad=item.cantidad,
                    precio_unitario=item.precio_unitario,
                    subtotal=subtotal,
                    tiene_error=item_tiene_error,
                    tipo_error=item_tipo_error,
                    descripcion_error=item_desc_error,
                )
                db.add(nuevo_detalle)

            db_order.monto_total = total_pedido
            del datos["items"]

            fecha_original = db_order.fecha_pedido.date() if db_order.fecha_pedido else None
            fecha_enviada = datos.get("fecha_pedido")
            fecha_enviada_date = fecha_enviada.date() if fecha_enviada else None
            if fecha_enviada_date is None or fecha_enviada_date == fecha_original:
                datos["fecha_pedido"] = datetime.now()

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
            db_order.auditoria_condicion.fecha_evaluacion = datetime.now(timezone.utc)
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

        db.commit()

        pedido_actualizado = OrderService.get_by_id(db, order_id)
        nuevo_estado = db_order.estado
        if (
            usuario_id
            and nuevo_estado in ESTADOS_CONFIRMADOS
            and estado_anterior not in ESTADOS_CONFIRMADOS
        ):
            DecisionService.registrar_confirmacion_pedido(db, pedido_actualizado, usuario_id)
            IndicatorService.calculate_and_save(
                db, resumen="Recálculo automático tras confirmación de pedido"
            )
            pedido_actualizado = OrderService.get_by_id(db, order_id)
        return pedido_actualizado

    @staticmethod
    def delete(db: Session, order_id: int) -> bool:
        db_order = OrderService.get_by_id(db, order_id)
        if not db_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pedido no encontrado",
            )
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

        error_asignado = tipo_error.strip() if tipo_error else "Error_No_Especificado"

        for detalle in db_order.detalles:
            detalle.tiene_error = True
            detalle.tipo_error = error_asignado
            detalle.descripcion_error = descripcion

        db_order.estado = "Pendiente"
        db_order.fecha_entrega = None
        db_order.observaciones = f"[ERROR: {error_asignado}] {descripcion}".strip()

        db.commit()
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
        return OrderService.get_by_id(db, order_id)