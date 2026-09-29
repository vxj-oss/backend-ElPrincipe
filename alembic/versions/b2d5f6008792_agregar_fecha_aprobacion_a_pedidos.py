"""agregar fecha_aprobacion a pedidos

Revision ID: b2d5f6008792
Revises: 6dc804a2d174
Create Date: 2026-09-28 22:33:09.042337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2d5f6008792'
down_revision: Union[str, None] = '6dc804a2d174'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pedidos', sa.Column('fecha_aprobacion', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('pedidos', 'fecha_aprobacion')