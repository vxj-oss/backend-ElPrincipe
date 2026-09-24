"""add preferencias column to usuarios

Revision ID: 8d3f5b2a9c11
Revises: 3c8946c034cc
Create Date: 2026-08-27 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '8d3f5b2a9c11'
down_revision: Union[str, None] = '3c8946c034cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('preferencias', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('usuarios', 'preferencias')
