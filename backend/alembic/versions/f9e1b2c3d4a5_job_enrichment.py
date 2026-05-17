"""job enrichment: labels, online check, required_documents

Revision ID: f9e1b2c3d4a5
Revises: 3a9e1b7c2d44
Create Date: 2026-05-17 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f9e1b2c3d4a5"
down_revision: Union[str, Sequence[str], None] = "3a9e1b7c2d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "label",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("is_auto", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "application_label",
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("application.id"), primary_key=True),
        sa.Column("label_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("label.id"), primary_key=True),
    )
    op.add_column("application", sa.Column("posting_online", sa.Boolean(), nullable=True))
    op.add_column("application", sa.Column("posting_checked_at", sa.DateTime(), nullable=True))
    op.add_column("job_posting", sa.Column("required_documents", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_posting", "required_documents")
    op.drop_column("application", "posting_checked_at")
    op.drop_column("application", "posting_online")
    op.drop_table("application_label")
    op.drop_table("label")
