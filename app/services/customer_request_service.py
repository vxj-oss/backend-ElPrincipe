import json
import re
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agent.llm_client import llm_client
from app.models.commercial_term import CondicionComercial
from app.models.customer_request import SolicitudCliente
from app.models.customer_request_item import SolicitudClienteDetalle
from app.models.product import Producto
from app.schemas.customer_request import (
    ComparacionPedidoRequest,
    ComparacionPedidoResponse,
    SolicitudClienteCreate,
)


class SolicitudClienteService:
    @staticmethod
    def create_request(
        db: Session, user_id: int, payload: SolicitudClienteCreate
    ) -> SolicitudCliente:
        codigo = f"SOL-{uuid.uuid4().hex[:8].upper()}"
        solicitud = SolicitudCliente(
            codigo_solicitud=codigo,
            cliente_id=payload.cliente_id,
            usuario_id=user_id,
            canal_recepcion=payload.canal_recepcion,
            observaciones=payload.observaciones,
            estado="Pendiente",
        )
        db.add(solicitud)
        db.flush()

        for item in payload.detalles:
            detalle = SolicitudClienteDetalle(
                solicitud_id=solicitud.id,
                producto_id=item.producto_id,
                nombre_producto_solicitado=item.nombre_producto_solicitado,
                cantidad_solicitada=item.cantidad_solicitada,
                precio_esperado=item.precio_esperado,
            )
            db.add(detalle)

        db.commit()
        db.refresh(solicitud)
        return solicitud

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 50) -> List[SolicitudCliente]:
        stmt = (
            select(SolicitudCliente)
            .options(
                selectinload(SolicitudCliente.detalles),
                selectinload(SolicitudCliente.cliente),
            )
            .order_by(SolicitudCliente.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def delete(db: Session, request_id: int) -> Dict[str, Any]:
        solicitud = SolicitudClienteService.get_by_id(db, request_id)
        if not solicitud:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Solicitud de cliente no encontrada.",
            )
        codigo = solicitud.codigo_solicitud
        cliente_nombre = (
            solicitud.cliente.razon_social if solicitud.cliente else str(solicitud.cliente_id)
        )
        db.delete(solicitud)
        db.commit()
        return {"codigo_solicitud": codigo, "cliente_nombre": cliente_nombre}

    @staticmethod
    def get_by_id(db: Session, request_id: int) -> Optional[SolicitudCliente]:
        stmt = (
            select(SolicitudCliente)
            .options(
                selectinload(SolicitudCliente.detalles),
                selectinload(SolicitudCliente.cliente),
            )
            .where(SolicitudCliente.id == request_id)
        )
        return db.scalar(stmt)

    @staticmethod
    def audit_order_against_request(
        db: Session, payload: ComparacionPedidoRequest
    ) -> ComparacionPedidoResponse:
        discrepancias_condicion = []
        sugerencias_condicion = []

        stmt_cond = (
            select(CondicionComercial)
            .where(CondicionComercial.cliente_id == payload.cliente_id)
            .order_by(CondicionComercial.id.desc())
        )
        politica = db.scalar(stmt_cond)

        forma_pago = payload.forma_pago or "Contado"

        if not politica:
            if forma_pago.strip().lower() != "contado":
                discrepancias_condicion.append(
                    f"Discrepancia en condición comercial: Se seleccionó '{forma_pago}' pero el "
                    "cliente no tiene ninguna condición pactada (Estricto Contado)."
                )
                sugerencias_condicion.append("Alinear la condición de pago a 'Contado'.")
        elif politica.tipo_condicion == "Credito":
            match = re.search(r"(\d+)", forma_pago)
            dias_digitados = int(match.group(1)) if match else 0
            dias_pactados = politica.dias_plazo_pactados or 0
            if dias_digitados != dias_pactados:
                pactado_txt = f"Crédito {dias_pactados}d"
                digitado_txt = f"Crédito {dias_digitados}d"
                discrepancias_condicion.append(
                    f"Discrepancia en condición comercial: Se seleccionó '{digitado_txt}' pero la condición pactada es '{pactado_txt}'."
                )
                sugerencias_condicion.append(f"Alinear la condición de pago a '{pactado_txt}'.")
        elif politica.tipo_condicion == "Descuento":
            match = re.search(r"(\d+)", forma_pago)
            pct_digitado = int(match.group(1)) if match else 0
            pct_pactado = int(politica.porcentaje_descuento or 0)
            if pct_digitado != pct_pactado:
                discrepancias_condicion.append(
                    f"Discrepancia en condición comercial: Se seleccionó 'Descuento {pct_digitado}%' pero la condición pactada es 'Descuento {pct_pactado}%'."
                )
                sugerencias_condicion.append(f"Alinear el descuento aplicado a {pct_pactado}%.")
        elif politica.tipo_condicion == "Forma_Pago":
            pactado = politica.forma_pago_pactada or "Contado"
            if forma_pago.strip().lower() != pactado.lower():
                discrepancias_condicion.append(
                    f"Discrepancia en condición comercial: Se seleccionó '{forma_pago}' pero la condición pactada es '{pactado}'."
                )
                sugerencias_condicion.append(f"Alinear la condición de pago a '{pactado}'.")

        solicitud = None
        solicitado_data = []
        if payload.solicitud_id:
            solicitud = SolicitudClienteService.get_by_id(db, payload.solicitud_id)
            if solicitud:
                solicitado_data = [
                    {
                        "producto_id": d.producto_id,
                        "producto_nombre": d.nombre_producto_solicitado,
                        "cantidad": d.cantidad_solicitada,
                        "precio_esperado": float(d.precio_esperado or 0),
                    }
                    for d in solicitud.detalles
                ]

        pedido_data = [
            {
                "producto_id": it.producto_id,
                "sku": it.sku,
                "producto_nombre": it.nombre,
                "cantidad": it.cantidad,
                "precio_unitario": float(it.precio_unitario or 0),
            }
            for it in payload.items_pedido
        ]

        discrepancias_locales = []
        for it in payload.items_pedido:
            prod = db.scalar(select(Producto).where(Producto.id == it.producto_id))
            if prod and (prod.stock_actual or 0) < it.cantidad:
                discrepancias_locales.append(
                    f"Stock insuficiente para {prod.nombre}: Disponible {prod.stock_actual}, Solicitado {it.cantidad}."
                )

        if not payload.solicitud_id:
            hay_error = (
                len(discrepancias_condicion) > 0 or len(discrepancias_locales) > 0
            )
            todas_discrepancias = discrepancias_condicion + discrepancias_locales
            todas_sugerencias = sugerencias_condicion + (
                ["Verificar existencias en almacén."] if discrepancias_locales else []
            )

            tipo_error = None
            if discrepancias_condicion:
                tipo_error = "Condicion_Comercial"
            elif discrepancias_locales:
                tipo_error = "Stock_Insuficiente"

            return ComparacionPedidoResponse(
                hay_discrepancia=hay_error,
                tipo_error=tipo_error,
                descripcion_discrepancia=(
                    " | ".join(todas_discrepancias) if hay_error else "Conforme."
                ),
                analisis_ia="Auditoría directa completada sin solicitud previa vinculada.",
                sugerencias_correccion=todas_sugerencias,
            )

        system_prompt = (
            "Eres el Auditor de Pedidos de Distribuidora EL PRÍNCIPE. "
            "Tu tarea es auditar lo que el cliente solicitó contra lo que se va a registrar en el pedido. "
            "REGLAS OBLIGATORIAS:\n"
            "1. SKU: Si el campo 'sku' es null o está vacío, NO es un error (ignóralo si el producto coincide por nombre o ID). Solo marca 'SKU_Incorrecto' si se registró un producto completamente diferente al solicitado.\n"
            "2. FORMA DE PAGO: Cualquier discrepancia en la condición comercial frente a la política ya ha sido evaluada preliminarmente; mantén 'Condicion_Comercial' si se reportan alertas de ese tipo.\n"
            "3. Enfócate en discrepancias reales: Condicion_Comercial, SKU_Incorrecto, Cantidad_Erronea, Precio_Desactualizado o Stock_Insuficiente.\n"
            "Responde estrictamente en formato JSON con la siguiente estructura: "
            '{"hay_discrepancia": bool, "tipo_error": str, "descripcion_discrepancia": str, "analisis_ia": str, "sugerencias_correccion": [str]}'
        )

        user_prompt = (
            f"=== POLÍTICA Y CONDICIONES COMERCIALES ===\n"
            f"Forma de Pago en Pedido: {forma_pago}\n"
            f"Alertas Comerciales: {json.dumps(discrepancias_condicion, ensure_ascii=False)}\n\n"
            f"=== LO QUE PIDIÓ EL CLIENTE EN SU SOLICITUD ===\n{json.dumps(solicitado_data, ensure_ascii=False, indent=2)}\n\n"
            f"=== LO QUE VA A REGISTRAR EN EL PEDIDO ===\n{json.dumps(pedido_data, ensure_ascii=False, indent=2)}\n\n"
            f"=== ALERTAS PREVIAS DE STOCK ===\n{json.dumps(discrepancias_locales, ensure_ascii=False, indent=2)}\n\n"
            "Analiza todo integralmente y genera el informe de discrepancias."
        )

        respuesta_ia = llm_client.generate_response(
            system_prompt=system_prompt, user_prompt=user_prompt
        )

        try:
            inicio = respuesta_ia.find("{")
            fin = respuesta_ia.rfind("}") + 1
            parsed = json.loads(respuesta_ia[inicio:fin])
            resultado = ComparacionPedidoResponse(**parsed)

            if discrepancias_condicion and not resultado.hay_discrepancia:
                resultado.hay_discrepancia = True
                resultado.tipo_error = "Condicion_Comercial"
                resultado.descripcion_discrepancia = " | ".join(discrepancias_condicion)
                resultado.sugerencias_correccion.extend(sugerencias_condicion)

            return resultado
        except Exception:
            todas_discrepancias = discrepancias_condicion + discrepancias_locales
            hay_error = len(todas_discrepancias) > 0 or len(solicitado_data) != len(
                pedido_data
            )
            return ComparacionPedidoResponse(
                hay_discrepancia=hay_error,
                tipo_error=(
                    "Condicion_Comercial"
                    if discrepancias_condicion
                    else (
                        "Stock_Insuficiente"
                        if discrepancias_locales
                        else "Discrepancia_Detectada"
                    )
                ),
                descripcion_discrepancia=(
                    " | ".join(todas_discrepancias)
                    if todas_discrepancias
                    else "Revisión requerida."
                ),
                analisis_ia=(
                    "El asistente de IA no está disponible en este momento; "
                    "se aplicaron solo las validaciones automáticas del sistema."
                ),
                sugerencias_correccion=sugerencias_condicion
                or [
                    "Verificar cantidades, condiciones comerciales y precios antes de guardar."
                ],
            )