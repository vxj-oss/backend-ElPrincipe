"""agregar hora_apertura_modal a solicitudes_cliente

Revision ID: 448642c928e3
Revises: b2d5f6008792
Create Date: 2026-09-28 23:05:14.745470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '448642c928e3'
down_revision: Union[str, None] = 'b2d5f6008792'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('solicitudes_cliente', sa.Column('hora_apertura_modal', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('solicitudes_cliente', 'hora_apertura_modal')