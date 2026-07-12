"""interaction interview_stage

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-12 00:00:00.000000

Adds a nullable structured interview stage to interaction rows. Only set when
channel == 'interview'; existing interview rows keep interview_stage = NULL.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    stage = postgresql.ENUM(
        "phone_screen", "technical", "onsite", "hr", "final", "other",
        name="interviewstage", create_type=False,
    )
    stage.create(bind, checkfirst=True)
    op.add_column(
        "interaction",
        sa.Column("interview_stage", stage, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interaction", "interview_stage")
    postgresql.ENUM(name="interviewstage").drop(op.get_bind(), checkfirst=True)
