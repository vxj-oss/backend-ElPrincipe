"""add login lockout columns to usuarios

Revision ID: f2a7c9e1b3d4
Revises: a1c2d3e4f5g6
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a7c9e1b3d4'
down_revision: Union[str, None] = 'a1c2d3e4f5g6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('intentos_fallidos', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('usuarios', sa.Column('bloqueado_hasta', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('usuarios', 'bloqueado_hasta')
    op.drop_column('usuarios', 'intentos_fallidos')
