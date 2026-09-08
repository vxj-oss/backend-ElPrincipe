"""extend audit action enum with login, export and error actions

Revision ID: f1a3c5e7d9b2
Revises: e9f1a2b3c4d5
Create Date: 2026-09-07 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f1a3c5e7d9b2'
down_revision: Union[str, None] = 'e9f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NUEVOS_VALORES = ('INICIAR_SESION', 'CERRAR_SESION', 'EXPORTAR', 'ERROR')


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for valor in NUEVOS_VALORES:
            op.execute(f"ALTER TYPE accion_auditoria_enum ADD VALUE IF NOT EXISTS '{valor}'")


def downgrade() -> None:
    pass
