"""application_event.interaction_id

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-14 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "application_event",
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_application_event_interaction",
        "application_event",
        "interaction",
        ["interaction_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_application_event_interaction_id",
        "application_event",
        ["interaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_event_interaction_id", table_name="application_event"
    )
    op.drop_constraint(
        "fk_application_event_interaction", "application_event", type_="foreignkey"
    )
    op.drop_column("application_event", "interaction_id")
