"""application interview status

Revision ID: a3b4c5d6e7f8
Revises: c2f4a6b8d0e1
Create Date: 2026-06-25 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "c2f4a6b8d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'interview'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value; no-op.
    pass
