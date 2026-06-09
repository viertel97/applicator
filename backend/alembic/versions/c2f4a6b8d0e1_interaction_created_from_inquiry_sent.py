"""add inquiry_sent to interactioncreatedfrom enum

Single-purpose migration: a newly added Postgres enum value is only usable
after the adding transaction commits, so this migration does nothing but
ADD VALUE and must NOT be combined with code that consumes 'inquiry_sent'.

Revision ID: c2f4a6b8d0e1
Revises: f2a3b4c5d6e7
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "c2f4a6b8d0e1"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE interactioncreatedfrom ADD VALUE IF NOT EXISTS 'inquiry_sent'"
    )


def downgrade() -> None:
    # Postgres cannot drop a single enum value; no-op.
    pass
