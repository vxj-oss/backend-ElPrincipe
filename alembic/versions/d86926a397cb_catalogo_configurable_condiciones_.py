"""catalogo_configurable_condiciones_comerciales

Revision ID: d86926a397cb
Revises: 73c69fb10223
Create Date: 2026-09-24 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd86926a397cb'
down_revision: Union[str, None] = '73c69fb10223'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIPO_ENUM_NAME = 'tipo_condicion_enum'

OPCIONES_INICIALES = [
    {"tipo_condicion": "Credito", "valor": "10", "etiqueta": "Crédito 10d", "orden": 1},
    {"tipo_condicion": "Credito", "valor": "15", "etiqueta": "Crédito 15d", "orden": 2},
    {"tipo_condicion": "Credito", "valor": "30", "etiqueta": "Crédito 30d", "orden": 3},
    {"tipo_condicion": "Descuento", "valor": "10", "etiqueta": "Descuento 10%", "orden": 1},
    {"tipo_condicion": "Descuento", "valor": "15", "etiqueta": "Descuento 15%", "orden": 2},
    {"tipo_condicion": "Descuento", "valor": "20", "etiqueta": "Descuento 20%", "orden": 3},
    {"tipo_condicion": "Descuento", "valor": "40", "etiqueta": "Descuento 40%", "orden": 4},
    {"tipo_condicion": "Descuento", "valor": "50", "etiqueta": "Descuento 50%", "orden": 5},
    {"tipo_condicion": "Forma_Pago", "valor": "Contado", "etiqueta": "Contado", "orden": 1},
    {"tipo_condicion": "Forma_Pago", "valor": "Tarjeta", "etiqueta": "Tarjeta", "orden": 2},
    {"tipo_condicion": "Forma_Pago", "valor": "Otro", "etiqueta": "Otro", "orden": 3},
]


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE opciones_condicion_comercial (
            id SERIAL PRIMARY KEY,
            tipo_condicion {TIPO_ENUM_NAME} NOT NULL,
            valor VARCHAR(50) NOT NULL,
            etiqueta VARCHAR(100) NOT NULL,
            orden INTEGER NOT NULL DEFAULT 0,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        'ix_opciones_condicion_comercial_tipo_condicion',
        'opciones_condicion_comercial',
        ['tipo_condicion'],
    )

    tabla = sa.table(
        'opciones_condicion_comercial',
        sa.column('tipo_condicion', sa.String()),
        sa.column('valor', sa.String()),
        sa.column('etiqueta', sa.String()),
        sa.column('orden', sa.Integer()),
    )
    op.bulk_insert(tabla, OPCIONES_INICIALES)


def downgrade() -> None:
    op.drop_index('ix_opciones_condicion_comercial_tipo_condicion', table_name='opciones_condicion_comercial')
    op.drop_table('opciones_condicion_comercial')
