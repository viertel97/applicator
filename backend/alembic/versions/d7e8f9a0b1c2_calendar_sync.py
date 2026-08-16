"""interaction external ids + calendar_sync_state

Adds provenance columns to `interaction` (external_source, external_id) with a
unique constraint for idempotent upserts, and a `calendar_sync_state` table
holding the MS Graph delta cursor per synced calendar.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-08-16

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interaction",
        sa.Column("external_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "interaction",
        sa.Column("external_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_interaction_external",
        "interaction",
        ["external_source", "external_id"],
    )

    op.create_table(
        "calendar_sync_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("calendar_id", sa.String(length=255), nullable=False),
        sa.Column("delta_link", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "calendar_id", name="uq_calsync_user_calendar"
        ),
    )
    op.create_index(
        "ix_calendar_sync_state_user_id",
        "calendar_sync_state",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_calendar_sync_state_user_id", table_name="calendar_sync_state"
    )
    op.drop_table("calendar_sync_state")
    op.drop_constraint("uq_interaction_external", "interaction", type_="unique")
    op.drop_column("interaction", "external_id")
    op.drop_column("interaction", "external_source")
