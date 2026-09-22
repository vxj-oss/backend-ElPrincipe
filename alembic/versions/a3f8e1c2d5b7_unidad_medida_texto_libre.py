"""unidad_medida de productos pasa de enum cerrado a texto libre

Revision ID: a3f8e1c2d5b7
Revises: b8d2f4a6c1e9
Create Date: 2026-09-22 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f8e1c2d5b7'
down_revision: Union[str, None] = 'b8d2f4a6c1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ENUM_VALUES = ('Galón', 'Bidón 5L', 'Saco 15Kg', 'Unidad')
ENUM_NAME = 'unidad_medida_producto'


def upgrade() -> None:
    op.alter_column(
        'productos',
        'unidad_medida',
        existing_type=sa.Enum(*OLD_ENUM_VALUES, name=ENUM_NAME),
        type_=sa.String(length=100),
        postgresql_using='unidad_medida::text',
        existing_nullable=False,
    )
    op.execute(f'DROP TYPE IF EXISTS {ENUM_NAME}')


def downgrade() -> None:
    enum_type = sa.Enum(*OLD_ENUM_VALUES, name=ENUM_NAME)
    enum_type.create(op.get_bind(), checkfirst=True)
    op.alter_column(
        'productos',
        'unidad_medida',
        existing_type=sa.String(length=100),
        type_=enum_type,
        postgresql_using=f"unidad_medida::{ENUM_NAME}",
        existing_nullable=False,
    )
