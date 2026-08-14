"""webhook_request.created_interaction_id

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-14 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "webhook_request",
        sa.Column("created_interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_webhook_request_created_interaction",
        "webhook_request",
        "interaction",
        ["created_interaction_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_webhook_request_created_interaction_id",
        "webhook_request",
        ["created_interaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_request_created_interaction_id", table_name="webhook_request"
    )
    op.drop_constraint(
        "fk_webhook_request_created_interaction", "webhook_request", type_="foreignkey"
    )
    op.drop_column("webhook_request", "created_interaction_id")
