"""product activo flag, order solicitud link, system config

Revision ID: e9f1a2b3c4d5
Revises: d7b3f2a9c1e4
Create Date: 2026-09-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e9f1a2b3c4d5'
down_revision: Union[str, None] = 'd7b3f2a9c1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'productos',
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )

    op.add_column('pedidos', sa.Column('solicitud_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'pedidos_solicitud_id_fkey',
        'pedidos',
        'solicitudes_cliente',
        ['solicitud_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_pedidos_solicitud_id', 'pedidos', ['solicitud_id'])

    op.create_table(
        'configuracion_sistema',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meta_diaria_ventas', sa.Numeric(precision=12, scale=2), nullable=False, server_default='6000.00'),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute("INSERT INTO configuracion_sistema (id, meta_diaria_ventas) VALUES (1, 6000.00)")


def downgrade() -> None:
    op.drop_table('configuracion_sistema')
    op.drop_index('ix_pedidos_solicitud_id', table_name='pedidos')
    op.drop_constraint('pedidos_solicitud_id_fkey', 'pedidos', type_='foreignkey')
    op.drop_column('pedidos', 'solicitud_id')
    op.drop_column('productos', 'activo')
