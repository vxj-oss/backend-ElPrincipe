"""remove_cliente_id_from_condiciones_comerciales

Revision ID: 5a1e94e9f6bb
Revises: b4cd6d0bd8cf
Create Date: 2026-08-26 17:13:45.426920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '5a1e94e9f6bb'
down_revision: Union[str, None] = 'b4cd6d0bd8cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f('condiciones_comerciales_pedido_id_fkey'), 'condiciones_comerciales', type_='foreignkey')
    op.drop_constraint(op.f('condiciones_comerciales_cliente_id_fkey'), 'condiciones_comerciales', type_='foreignkey')
    op.create_foreign_key(None, 'condiciones_comerciales', 'pedidos', ['pedido_id'], ['id'], ondelete='CASCADE')
    op.drop_column('condiciones_comerciales', 'cliente_id')
    op.alter_column('solicitudes_cliente', 'fecha_solicitud',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               type_=sa.DateTime(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('solicitudes_cliente', 'creado_en',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               type_=sa.DateTime(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))


def downgrade() -> None:
    op.alter_column('solicitudes_cliente', 'creado_en',
               existing_type=sa.DateTime(),
               type_=postgresql.TIMESTAMP(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('solicitudes_cliente', 'fecha_solicitud',
               existing_type=sa.DateTime(),
               type_=postgresql.TIMESTAMP(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.add_column('condiciones_comerciales', sa.Column('cliente_id', sa.INTEGER(), autoincrement=False, nullable=False))
    op.drop_constraint(None, 'condiciones_comerciales', type_='foreignkey')
    op.create_foreign_key(op.f('condiciones_comerciales_cliente_id_fkey'), 'condiciones_comerciales', 'clientes', ['cliente_id'], ['id'])
    op.create_foreign_key(op.f('condiciones_comerciales_pedido_id_fkey'), 'condiciones_comerciales', 'pedidos', ['pedido_id'], ['id'])
