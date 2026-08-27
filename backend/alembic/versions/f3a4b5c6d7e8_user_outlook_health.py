"""user outlook_last_* health columns

Revision ID: f3a4b5c6d7e8
Revises: e1a2b3c4d5e6
Create Date: 2026-08-27 00:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("outlook_last_sync_at", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("outlook_last_status", sa.String(16), nullable=True))
    op.add_column("user", sa.Column("outlook_last_reason", sa.String(64), nullable=True))
    op.add_column("user", sa.Column("outlook_last_trigger", sa.String(16), nullable=True))
    op.add_column("user", sa.Column("outlook_last_counts", sa.JSON(), nullable=True))
    op.add_column("user", sa.Column("outlook_last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in (
        "outlook_last_error",
        "outlook_last_counts",
        "outlook_last_trigger",
        "outlook_last_reason",
        "outlook_last_status",
        "outlook_last_sync_at",
    ):
        op.drop_column("user", col)
