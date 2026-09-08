"""add stock_descontado column to pedidos

Revision ID: c5e8a1d4b7f2
Revises: f2a7c9e1b3d4
Create Date: 2026-09-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5e8a1d4b7f2'
down_revision: Union[str, None] = 'f2a7c9e1b3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'pedidos',
        sa.Column(
            'stock_descontado',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )


def downgrade() -> None:
    op.drop_column('pedidos', 'stock_descontado')
