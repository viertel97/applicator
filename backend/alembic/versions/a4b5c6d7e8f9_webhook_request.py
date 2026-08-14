"""webhook_request

Revision ID: a4b5c6d7e8f9
Revises: 5606f397a2bf
Create Date: 2026-08-14 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "5606f397a2bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=True,
        ),
        sa.Column("ingest_token", sa.String(64), nullable=False),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("raw_body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column(
            "matched_application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_webhook_request_user_id", "webhook_request", ["user_id"]
    )
    op.create_index(
        "ix_webhook_request_created_at", "webhook_request", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_request_created_at", table_name="webhook_request")
    op.drop_index("ix_webhook_request_user_id", table_name="webhook_request")
    op.drop_table("webhook_request")
