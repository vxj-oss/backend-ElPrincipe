"""crear_tablas_iniciales

Revision ID: 283c107f0a82
Revises: 
Create Date: 2026-08-18 16:58:29.968031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '283c107f0a82'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('categorias',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre')
    )
    op.create_index(op.f('ix_categorias_id'), 'categorias', ['id'], unique=False)
    op.create_table('clientes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ruc_dni', sa.String(length=11), nullable=False),
    sa.Column('razon_social', sa.String(length=200), nullable=False),
    sa.Column('tipo_cliente', sa.Enum('Mayorista', 'Institucional', 'Minorista', name='tipo_cliente_enum'), nullable=False),
    sa.Column('direccion', sa.String(length=300), nullable=True),
    sa.Column('distrito', sa.String(length=100), nullable=True),
    sa.Column('telefono', sa.String(length=20), nullable=True),
    sa.Column('correo', sa.String(length=150), nullable=True),
    sa.Column('estado', sa.Enum('Activo', 'Inactivo', name='estado_cliente_enum'), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clientes_id'), 'clientes', ['id'], unique=False)
    op.create_index(op.f('ix_clientes_ruc_dni'), 'clientes', ['ruc_dni'], unique=True)
    op.create_table('registros_indicador',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fecha_calculo', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('total_pedidos_evaluados', sa.Integer(), nullable=False),
    sa.Column('total_items_pedidos', sa.Integer(), nullable=False),
    sa.Column('total_errores_productos', sa.Integer(), nullable=False),
    sa.Column('valor_nepp', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('total_condiciones_pactadas', sa.Integer(), nullable=False),
    sa.Column('total_fallas_condiciones', sa.Integer(), nullable=False),
    sa.Column('valor_pfcc', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('total_decisiones_evaluadas', sa.Integer(), nullable=False),
    sa.Column('total_decisiones_efectivas', sa.Integer(), nullable=False),
    sa.Column('valor_ntdc', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('resumen_operativo', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_registros_indicador_fecha_calculo'), 'registros_indicador', ['fecha_calculo'], unique=False)
    op.create_index(op.f('ix_registros_indicador_id'), 'registros_indicador', ['id'], unique=False)
    op.create_table('usuarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre_usuario', sa.String(length=50), nullable=False),
    sa.Column('clave_hash', sa.String(length=255), nullable=False),
    sa.Column('nombre_completo', sa.String(length=150), nullable=False),
    sa.Column('correo', sa.String(length=150), nullable=False),
    sa.Column('rol', sa.Enum('administrador', 'asesor_comercial', name='rol_usuario'), nullable=False),
    sa.Column('esta_activo', sa.Boolean(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('correo')
    )
    op.create_index(op.f('ix_usuarios_id'), 'usuarios', ['id'], unique=False)
    op.create_index(op.f('ix_usuarios_nombre_usuario'), 'usuarios', ['nombre_usuario'], unique=True)
    op.create_table('historial_auditoria',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('accion', sa.Enum('CREAR', 'ACTUALIZAR', 'ELIMINAR', 'CONSULTA_IA', name='accion_auditoria_enum'), nullable=False),
    sa.Column('modulo_afectado', sa.String(length=100), nullable=False),
    sa.Column('detalle_cambio', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('direccion_ip', sa.String(length=45), nullable=True),
    sa.Column('fecha_hora', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_historial_auditoria_fecha_hora'), 'historial_auditoria', ['fecha_hora'], unique=False)
    op.create_index(op.f('ix_historial_auditoria_id'), 'historial_auditoria', ['id'], unique=False)
    op.create_table('pedidos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('codigo_pedido', sa.String(length=30), nullable=False),
    sa.Column('fecha_pedido', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fecha_entrega', sa.DateTime(timezone=True), nullable=True),
    sa.Column('forma_pago', sa.Enum('Contado', 'Credito 15d', 'Credito 30d', name='forma_pago_enum'), nullable=False),
    sa.Column('estado', sa.Enum('Pendiente', 'Aprobado', 'Entregado', 'Cancelado', name='estado_pedido_enum'), nullable=False),
    sa.Column('monto_total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pedidos_codigo_pedido'), 'pedidos', ['codigo_pedido'], unique=True)
    op.create_index(op.f('ix_pedidos_id'), 'pedidos', ['id'], unique=False)
    op.create_table('productos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=False),
    sa.Column('sku', sa.String(length=50), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=True),
    sa.Column('unidad_medida', sa.Enum('Galón', 'Bidón 5L', 'Saco 15Kg', 'Unidad', name='unidad_medida_producto'), nullable=False),
    sa.Column('precio_unitario', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('precio_costo', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('stock_actual', sa.Integer(), nullable=False),
    sa.Column('stock_minimo', sa.Integer(), nullable=False),
    sa.Column('nivel_rotacion', sa.Enum('Alta', 'Media', 'Baja', name='nivel_rotacion_producto'), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['categoria_id'], ['categorias.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_productos_id'), 'productos', ['id'], unique=False)
    op.create_index(op.f('ix_productos_sku'), 'productos', ['sku'], unique=True)
    op.create_table('sesiones_agente',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('titulo_sesion', sa.String(length=200), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('esta_activa', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sesiones_agente_id'), 'sesiones_agente', ['id'], unique=False)
    op.create_table('condiciones_comerciales',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pedido_id', sa.Integer(), nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('tipo_condicion', sa.Enum('Plazo_Credito', 'Descuento_Volumen', 'Limite_Credito', 'Forma_Pago', name='tipo_condicion_enum'), nullable=False),
    sa.Column('dias_plazo_pactados', sa.Integer(), nullable=True),
    sa.Column('porcentaje_descuento', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('limite_credito_asignado', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('tiene_falla', sa.Boolean(), nullable=False),
    sa.Column('motivo_falla', sa.Text(), nullable=True),
    sa.Column('fecha_registro', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
    sa.ForeignKeyConstraint(['pedido_id'], ['pedidos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_condiciones_comerciales_id'), 'condiciones_comerciales', ['id'], unique=False)
    op.create_table('detalles_pedido',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pedido_id', sa.Integer(), nullable=False),
    sa.Column('producto_id', sa.Integer(), nullable=False),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('precio_unitario', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('tiene_error', sa.Boolean(), nullable=False),
    sa.Column('tipo_error', sa.Enum('Ninguno', 'SKU_Incorrecto', 'Precio_Desactualizado', 'Stock_Insuficiente', 'Cantidad_Erronea', name='tipo_error_detalle_enum'), nullable=False),
    sa.Column('descripcion_error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['pedido_id'], ['pedidos.id'], ),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_detalles_pedido_id'), 'detalles_pedido', ['id'], unique=False)
    op.create_table('mensajes_agente',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sesion_id', sa.Integer(), nullable=False),
    sa.Column('rol_emisor', sa.Enum('user', 'assistant', 'system', name='rol_emisor_enum'), nullable=False),
    sa.Column('contenido', sa.Text(), nullable=False),
    sa.Column('datos_estructurados', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('tiempo_respuesta_segundos', sa.Float(), nullable=True),
    sa.Column('fecha_hora', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['sesion_id'], ['sesiones_agente.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mensajes_agente_fecha_hora'), 'mensajes_agente', ['fecha_hora'], unique=False)
    op.create_index(op.f('ix_mensajes_agente_id'), 'mensajes_agente', ['id'], unique=False)
    op.create_table('decisiones_comerciales',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('pedido_id', sa.Integer(), nullable=True),
    sa.Column('mensaje_agente_id', sa.Integer(), nullable=True),
    sa.Column('tipo_decision', sa.Enum('Aprobacion_Descuento', 'Extension_Credito', 'Sustitucion_Producto', 'Ajuste_Precio', name='tipo_decision_enum'), nullable=False),
    sa.Column('recomendacion_ia', sa.Text(), nullable=True),
    sa.Column('decision_tomada', sa.Text(), nullable=True),
    sa.Column('es_efectiva', sa.Boolean(), nullable=True),
    sa.Column('observaciones_impacto', sa.Text(), nullable=True),
    sa.Column('fecha_decision', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['mensaje_agente_id'], ['mensajes_agente.id'], ),
    sa.ForeignKeyConstraint(['pedido_id'], ['pedidos.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_decisiones_comerciales_fecha_decision'), 'decisiones_comerciales', ['fecha_decision'], unique=False)
    op.create_index(op.f('ix_decisiones_comerciales_id'), 'decisiones_comerciales', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_decisiones_comerciales_id'), table_name='decisiones_comerciales')
    op.drop_index(op.f('ix_decisiones_comerciales_fecha_decision'), table_name='decisiones_comerciales')
    op.drop_table('decisiones_comerciales')
    op.drop_index(op.f('ix_mensajes_agente_id'), table_name='mensajes_agente')
    op.drop_index(op.f('ix_mensajes_agente_fecha_hora'), table_name='mensajes_agente')
    op.drop_table('mensajes_agente')
    op.drop_index(op.f('ix_detalles_pedido_id'), table_name='detalles_pedido')
    op.drop_table('detalles_pedido')
    op.drop_index(op.f('ix_condiciones_comerciales_id'), table_name='condiciones_comerciales')
    op.drop_table('condiciones_comerciales')
    op.drop_index(op.f('ix_sesiones_agente_id'), table_name='sesiones_agente')
    op.drop_table('sesiones_agente')
    op.drop_index(op.f('ix_productos_sku'), table_name='productos')
    op.drop_index(op.f('ix_productos_id'), table_name='productos')
    op.drop_table('productos')
    op.drop_index(op.f('ix_pedidos_id'), table_name='pedidos')
    op.drop_index(op.f('ix_pedidos_codigo_pedido'), table_name='pedidos')
    op.drop_table('pedidos')
    op.drop_index(op.f('ix_historial_auditoria_id'), table_name='historial_auditoria')
    op.drop_index(op.f('ix_historial_auditoria_fecha_hora'), table_name='historial_auditoria')
    op.drop_table('historial_auditoria')
    op.drop_index(op.f('ix_usuarios_nombre_usuario'), table_name='usuarios')
    op.drop_index(op.f('ix_usuarios_id'), table_name='usuarios')
    op.drop_table('usuarios')
    op.drop_index(op.f('ix_registros_indicador_id'), table_name='registros_indicador')
    op.drop_index(op.f('ix_registros_indicador_fecha_calculo'), table_name='registros_indicador')
    op.drop_table('registros_indicador')
    op.drop_index(op.f('ix_clientes_ruc_dni'), table_name='clientes')
    op.drop_index(op.f('ix_clientes_id'), table_name='clientes')
    op.drop_table('clientes')
    op.drop_index(op.f('ix_categorias_id'), table_name='categorias')
    op.drop_table('categorias')
