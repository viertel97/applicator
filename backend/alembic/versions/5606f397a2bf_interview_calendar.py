"""interview_calendar

Revision ID: 5606f397a2bf
Revises: d6e7f8a9b0c1
Create Date: 2026-08-13 21:45:59.610585

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5606f397a2bf'
down_revision: Union[str, Sequence[str], None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE interactioncreatedfrom ADD VALUE IF NOT EXISTS 'email_webhook'"
    )
    op.add_column("interaction", sa.Column("location", sa.Text(), nullable=True))
    op.add_column("interaction", sa.Column("ends_at", sa.DateTime(), nullable=True))
    op.add_column(
        "interaction",
        sa.Column(
            "needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("user", sa.Column("ingest_token", sa.String(64), nullable=True))
    op.add_column("user", sa.Column("calendar_token", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_user_ingest_token", "user", ["ingest_token"])
    op.create_unique_constraint("uq_user_calendar_token", "user", ["calendar_token"])


def downgrade() -> None:
    op.drop_constraint("uq_user_calendar_token", "user", type_="unique")
    op.drop_constraint("uq_user_ingest_token", "user", type_="unique")
    op.drop_column("user", "calendar_token")
    op.drop_column("user", "ingest_token")
    op.drop_column("interaction", "needs_review")
    op.drop_column("interaction", "ends_at")
    op.drop_column("interaction", "location")
    # Postgres cannot drop a single enum value; leave 'email_webhook' in place.
