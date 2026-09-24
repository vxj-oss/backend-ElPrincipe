"""create_customer_request_tables

Revision ID: b4cd6d0bd8cf
Revises: 283c107f0a82
Create Date: 2026-08-26 12:46:19.615237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4cd6d0bd8cf'
down_revision: Union[str, None] = '283c107f0a82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('clientes', 'limite_credito',
               existing_type=sa.NUMERIC(precision=12, scale=2),
               nullable=False,
               existing_server_default=sa.text('0.00'))

    op.create_table('solicitudes_cliente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo_solicitud', sa.String(length=50), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('fecha_solicitud', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('estado', sa.String(length=50), server_default='Pendiente', nullable=False),
        sa.Column('canal_recepcion', sa.String(length=50), server_default='WhatsApp', nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_solicitudes_cliente_codigo_solicitud'), 'solicitudes_cliente', ['codigo_solicitud'], unique=True)
    op.create_index(op.f('ix_solicitudes_cliente_id'), 'solicitudes_cliente', ['id'], unique=False)

    op.create_table('solicitud_cliente_detalles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('solicitud_id', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=True),
        sa.Column('nombre_producto_solicitado', sa.String(length=255), nullable=False),
        sa.Column('cantidad_solicitada', sa.Integer(), nullable=False),
        sa.Column('precio_esperado', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['solicitud_id'], ['solicitudes_cliente.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_solicitud_cliente_detalles_id'), 'solicitud_cliente_detalles', ['id'], unique=False)


def downgrade() -> None:
    pass