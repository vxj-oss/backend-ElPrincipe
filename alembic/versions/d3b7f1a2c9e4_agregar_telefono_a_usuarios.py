"""agregar telefono a usuarios

Revision ID: d3b7f1a2c9e4
Revises: 448642c928e3
Create Date: 2026-11-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd3b7f1a2c9e4'
down_revision: Union[str, None] = '448642c928e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefono VARCHAR(20)")


def downgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS telefono")
