"""stock movements ledger and decision cascade on order delete

Revision ID: d7b3f2a9c1e4
Revises: c5e8a1d4b7f2
Create Date: 2026-09-07 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7b3f2a9c1e4'
down_revision: Union[str, None] = 'c5e8a1d4b7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'movimientos_stock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=False),
        sa.Column('pedido_id', sa.Integer(), nullable=True),
        sa.Column(
            'tipo',
            sa.Enum('Salida', 'Entrada', 'Ajuste', name='tipo_movimiento_stock_enum'),
            nullable=False,
        ),
        sa.Column('cantidad', sa.Integer(), nullable=False),
        sa.Column('stock_anterior', sa.Integer(), nullable=False),
        sa.Column('stock_nuevo', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.String(length=200), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pedido_id'], ['pedidos.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_movimientos_stock_id', 'movimientos_stock', ['id'])
    op.create_index('ix_movimientos_stock_producto_id', 'movimientos_stock', ['producto_id'])
    op.create_index('ix_movimientos_stock_pedido_id', 'movimientos_stock', ['pedido_id'])
    op.create_index('ix_movimientos_stock_creado_en', 'movimientos_stock', ['creado_en'])

    op.drop_constraint('decisiones_comerciales_pedido_id_fkey', 'decisiones_comerciales', type_='foreignkey')
    op.create_foreign_key(
        'decisiones_comerciales_pedido_id_fkey',
        'decisiones_comerciales',
        'pedidos',
        ['pedido_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('decisiones_comerciales_pedido_id_fkey', 'decisiones_comerciales', type_='foreignkey')
    op.create_foreign_key(
        'decisiones_comerciales_pedido_id_fkey',
        'decisiones_comerciales',
        'pedidos',
        ['pedido_id'],
        ['id'],
    )

    op.drop_index('ix_movimientos_stock_creado_en', table_name='movimientos_stock')
    op.drop_index('ix_movimientos_stock_pedido_id', table_name='movimientos_stock')
    op.drop_index('ix_movimientos_stock_producto_id', table_name='movimientos_stock')
    op.drop_index('ix_movimientos_stock_id', table_name='movimientos_stock')
    op.drop_table('movimientos_stock')

    sa.Enum(name='tipo_movimiento_stock_enum').drop(op.get_bind(), checkfirst=True)
