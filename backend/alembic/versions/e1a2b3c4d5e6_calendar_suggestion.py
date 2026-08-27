"""calendar_suggestion: staged Outlook events for review

Revision ID: e1a2b3c4d5e6
Revises: d7e8f9a0b1c2
Create Date: 2026-08-27 00:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    status = postgresql.ENUM(
        "pending", "confirmed", "dismissed",
        name="calendarsuggestionstatus", create_type=False,
    )
    status.create(bind, checkfirst=True)

    op.create_table(
        "calendar_suggestion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"), nullable=False, index=True,
        ),
        sa.Column("external_source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column(
            "status", status, nullable=False, server_default="pending", index=True,
        ),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("organizer_email", sa.Text(), nullable=True),
        sa.Column(
            "suggested_application_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application.id"), nullable=True, index=True,
        ),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column(
            "interaction_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interaction.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "external_source", "external_id",
            name="uq_calsuggestion_external",
        ),
    )


def downgrade() -> None:
    op.drop_table("calendar_suggestion")
    postgresql.ENUM(name="calendarsuggestionstatus").drop(op.get_bind(), checkfirst=True)
