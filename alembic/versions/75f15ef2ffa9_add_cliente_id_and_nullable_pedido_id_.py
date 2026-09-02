"""add_cliente_id_and_nullable_pedido_id_in_commercial_terms

Revision ID: 75f15ef2ffa9
Revises: 5a1e94e9f6bb
Create Date: 2026-08-26 17:27:44.559902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '75f15ef2ffa9'
down_revision: Union[str, None] = '5a1e94e9f6bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Limpiar registros antiguos de prueba para evitar conflicto con NOT NULL
    op.execute("TRUNCATE TABLE condiciones_comerciales RESTART IDENTITY CASCADE;")

    # 2. Agregar columna cliente_id y hacer pedido_id opcional
    op.add_column('condiciones_comerciales', sa.Column('cliente_id', sa.Integer(), nullable=False))
    op.alter_column('condiciones_comerciales', 'pedido_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.drop_constraint(op.f('condiciones_comerciales_pedido_id_fkey'), 'condiciones_comerciales', type_='foreignkey')
    op.create_foreign_key(None, 'condiciones_comerciales', 'pedidos', ['pedido_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'condiciones_comerciales', 'clientes', ['cliente_id'], ['id'], ondelete='CASCADE')

    # 3. Ajuste de timestamps en solicitudes_cliente
    op.alter_column('solicitudes_cliente', 'fecha_solicitud',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('solicitudes_cliente', 'creado_en',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))


def downgrade() -> None:
    op.alter_column('solicitudes_cliente', 'creado_en',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('solicitudes_cliente', 'fecha_solicitud',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.drop_constraint(None, 'condiciones_comerciales', type_='foreignkey')
    op.drop_constraint(None, 'condiciones_comerciales', type_='foreignkey')
    op.create_foreign_key(op.f('condiciones_comerciales_pedido_id_fkey'), 'condiciones_comerciales', 'pedidos', ['pedido_id'], ['id'], ondelete='CASCADE')
    op.alter_column('condiciones_comerciales', 'pedido_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_column('condiciones_comerciales', 'cliente_id')