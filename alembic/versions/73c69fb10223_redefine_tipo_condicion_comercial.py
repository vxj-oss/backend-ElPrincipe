"""redefine_tipo_condicion_comercial

Revision ID: 73c69fb10223
Revises: a3f8e1c2d5b7
Create Date: 2026-09-24 09:39:04.110199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '73c69fb10223'
down_revision: Union[str, None] = 'a3f8e1c2d5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TIPO_VALUES = ('Plazo_Credito', 'Descuento_Volumen', 'Limite_Credito', 'Forma_Pago')
NEW_TIPO_VALUES = ('Credito', 'Descuento', 'Forma_Pago')
TIPO_ENUM_NAME = 'tipo_condicion_enum'
FORMA_PAGO_ENUM_NAME = 'forma_pago_pactada_enum'


def upgrade() -> None:
    op.drop_column('condiciones_comerciales', 'tipo_condicion')
    op.execute(f'DROP TYPE IF EXISTS {TIPO_ENUM_NAME}')

    nuevo_tipo_enum = sa.Enum(*NEW_TIPO_VALUES, name=TIPO_ENUM_NAME)
    nuevo_tipo_enum.create(op.get_bind())
    op.add_column(
        'condiciones_comerciales',
        sa.Column('tipo_condicion', nuevo_tipo_enum, nullable=False),
    )

    forma_pago_enum = sa.Enum('Contado', 'Tarjeta', 'Otro', name=FORMA_PAGO_ENUM_NAME)
    forma_pago_enum.create(op.get_bind())
    op.add_column(
        'condiciones_comerciales',
        sa.Column('forma_pago_pactada', forma_pago_enum, nullable=True),
    )

    op.drop_column('condiciones_comerciales', 'limite_credito_asignado')

    op.alter_column('condiciones_comerciales', 'dias_plazo_pactados', server_default=None)
    op.alter_column('condiciones_comerciales', 'porcentaje_descuento', server_default=None)


def downgrade() -> None:
    op.add_column(
        'condiciones_comerciales',
        sa.Column('limite_credito_asignado', sa.Numeric(12, 2), nullable=True, server_default='0.00'),
    )

    op.drop_column('condiciones_comerciales', 'forma_pago_pactada')
    op.execute(f'DROP TYPE IF EXISTS {FORMA_PAGO_ENUM_NAME}')

    op.drop_column('condiciones_comerciales', 'tipo_condicion')
    op.execute(f'DROP TYPE IF EXISTS {TIPO_ENUM_NAME}')

    viejo_tipo_enum = sa.Enum(*OLD_TIPO_VALUES, name=TIPO_ENUM_NAME)
    viejo_tipo_enum.create(op.get_bind())
    op.add_column(
        'condiciones_comerciales',
        sa.Column('tipo_condicion', viejo_tipo_enum, nullable=False),
    )
