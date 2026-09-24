"""add Confirmacion_Pedido value to tipo_decision_enum

Revision ID: a1c2d3e4f5g6
Revises: 8d3f5b2a9c11
Create Date: 2026-08-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a1c2d3e4f5g6'
down_revision: Union[str, None] = '8d3f5b2a9c11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tipo_decision_enum ADD VALUE IF NOT EXISTS 'Confirmacion_Pedido'")


def downgrade() -> None:
    pass
