"""inquiry_prompt: user prompt template + custom question texts

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-05-22 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("inquiry_prompt_template", sa.Column("user_prompt_md", sa.Text(), nullable=True))
    op.add_column("inquiry_prompt_template", sa.Column("question_home_office_de", sa.Text(), nullable=True))
    op.add_column("inquiry_prompt_template", sa.Column("question_home_office_en", sa.Text(), nullable=True))
    op.add_column("inquiry_prompt_template", sa.Column("question_part_time_de", sa.Text(), nullable=True))
    op.add_column("inquiry_prompt_template", sa.Column("question_part_time_en", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("inquiry_prompt_template", "question_part_time_en")
    op.drop_column("inquiry_prompt_template", "question_part_time_de")
    op.drop_column("inquiry_prompt_template", "question_home_office_en")
    op.drop_column("inquiry_prompt_template", "question_home_office_de")
    op.drop_column("inquiry_prompt_template", "user_prompt_md")
