"""fold interview into interaction channel

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-27 14:30:00.000000

- Adds 'interview' value to enum `interactionchannel`
- Drops `interview` table and its enums (`interviewkind`, `interviewoutcome`)

Interviews are now logged as interaction rows with channel='interview'.
"""
from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PG 12+ allows ADD VALUE inside a transaction; the new value just
    # cannot be referenced in the same transaction (we don't here).
    op.execute("ALTER TYPE interactionchannel ADD VALUE IF NOT EXISTS 'interview'")
    op.drop_table("interview")
    op.execute("DROP TYPE IF EXISTS interviewkind")
    op.execute("DROP TYPE IF EXISTS interviewoutcome")


def downgrade() -> None:
    # destructive: scheduled_at / outcome / notes cannot be reconstructed
    op.execute(
        "CREATE TYPE interviewkind AS ENUM "
        "('phone', 'video', 'onsite', 'technical', 'final')"
    )
    op.execute(
        "CREATE TYPE interviewoutcome AS ENUM "
        "('pending', 'passed', 'failed', 'cancelled')"
    )
    op.execute(
        """
        CREATE TABLE interview (
            id UUID PRIMARY KEY,
            application_id UUID REFERENCES application(id),
            scheduled_at TIMESTAMP NOT NULL,
            kind interviewkind NOT NULL,
            notes TEXT,
            outcome interviewoutcome NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT now()
        )
        """
    )
    # 'interview' value cannot be removed from enum without recreating the type;
    # leaving it in place is harmless.
