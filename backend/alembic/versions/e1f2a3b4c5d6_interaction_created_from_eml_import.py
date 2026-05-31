"""add eml_import to interactioncreatedfrom enum

Single-purpose migration: a newly added Postgres enum value is only usable
after the adding transaction commits, so this migration does nothing but
ADD VALUE and must NOT be combined with code that consumes 'eml_import'.

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE interactioncreatedfrom ADD VALUE IF NOT EXISTS 'eml_import'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value; no-op.
    pass
