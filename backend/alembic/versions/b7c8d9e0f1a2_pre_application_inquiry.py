"""pre-application inquiry: flags + persistence + prompt template

Revision ID: b7c8d9e0f1a2
Revises: c1d2e3f4a5b6, d2e3f4a5b6c7
Create Date: 2026-05-22 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = ("c1d2e3f4a5b6", "d2e3f4a5b6c7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_posting",
        sa.Column("mentions_home_office_policy", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "job_posting",
        sa.Column("mentions_part_time", sa.Boolean(), nullable=True),
    )
    op.add_column("application", sa.Column("inquiry_subject", sa.Text(), nullable=True))
    op.add_column("application", sa.Column("inquiry_body", sa.Text(), nullable=True))
    op.add_column("application", sa.Column("inquiry_sent_at", sa.DateTime(), nullable=True))
    op.create_table(
        "inquiry_prompt_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_md", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("inquiry_prompt_template")
    op.drop_column("application", "inquiry_sent_at")
    op.drop_column("application", "inquiry_body")
    op.drop_column("application", "inquiry_subject")
    op.drop_column("job_posting", "mentions_part_time")
    op.drop_column("job_posting", "mentions_home_office_policy")
