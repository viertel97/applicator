"""application discarded status and discard_reason

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-22 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'discarded'")
    op.add_column(
        "application",
        sa.Column("discard_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application", "discard_reason")
    # PostgreSQL does not support removing enum values; leave the enum value in place.
