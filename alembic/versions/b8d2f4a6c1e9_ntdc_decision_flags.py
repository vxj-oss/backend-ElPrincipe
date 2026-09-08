"""ntdc decision flags: requirio_correccion + corrected counter

Revision ID: b8d2f4a6c1e9
Revises: f1a3c5e7d9b2
Create Date: 2026-09-08 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d2f4a6c1e9'
down_revision: Union[str, None] = 'f1a3c5e7d9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'decisiones_comerciales',
        sa.Column('requirio_correccion', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column(
        'registros_indicador',
        sa.Column('total_decisiones_corregidas', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('registros_indicador', 'total_decisiones_corregidas')
    op.drop_column('decisiones_comerciales', 'requirio_correccion')
