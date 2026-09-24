"""pedidos forma de pago texto libre

Revision ID: 6dc804a2d174
Revises: d86926a397cb
Create Date: 2026-09-24 15:58:24.775732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6dc804a2d174'
down_revision: Union[str, None] = 'd86926a397cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ENUM_VALUES = ('Contado', 'Credito 15d', 'Credito 30d')
ENUM_NAME = 'forma_pago_enum'


def upgrade() -> None:
    op.alter_column(
        'pedidos',
        'forma_pago',
        existing_type=sa.Enum(*OLD_ENUM_VALUES, name=ENUM_NAME),
        type_=sa.String(length=50),
        postgresql_using='forma_pago::text',
        existing_nullable=False,
    )
    op.execute(f'DROP TYPE IF EXISTS {ENUM_NAME}')


def downgrade() -> None:
    enum_type = sa.Enum(*OLD_ENUM_VALUES, name=ENUM_NAME)
    enum_type.create(op.get_bind(), checkfirst=True)
    op.alter_column(
        'pedidos',
        'forma_pago',
        existing_type=sa.String(length=50),
        type_=enum_type,
        postgresql_using=f"forma_pago::{ENUM_NAME}",
        existing_nullable=False,
    )