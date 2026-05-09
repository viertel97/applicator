"""widen jobposting text cols to Text

Revision ID: 3a9e1b7c2d44
Revises: cb4656bd8fff
Create Date: 2026-04-29 18:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "3a9e1b7c2d44"
down_revision: Union[str, Sequence[str], None] = "cb4656bd8fff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLS = ("deadline", "seniority", "work_mode", "language")


def upgrade() -> None:
    for col in _COLS:
        op.alter_column("job_posting", col, type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    sizes = {"deadline": 32, "seniority": 64, "work_mode": 32, "language": 2}
    for col, n in sizes.items():
        op.alter_column(
            "job_posting", col, type_=sa.String(length=n), existing_nullable=True
        )
