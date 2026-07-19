"""application posting offline reason + dismissed_at

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-17 00:00:00.000000

Adds two nullable columns supporting the draft-posting liveness suggestions
inbox:

- posting_offline_reason: why the checker judged a posting offline
  (e.g. http_404, redirect_root, keyword:..., llm_inactive).
- posting_offline_dismissed_at: set when the user permanently dismisses a
  suggestion; never auto-cleared.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column("posting_offline_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "application",
        sa.Column("posting_offline_dismissed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application", "posting_offline_dismissed_at")
    op.drop_column("application", "posting_offline_reason")
