"""inquiry_prompt: editable DE/EN body templates

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-08 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("inquiry_prompt_template", sa.Column("body_template_de", sa.Text(), nullable=True))
    op.add_column("inquiry_prompt_template", sa.Column("body_template_en", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("inquiry_prompt_template", "body_template_en")
    op.drop_column("inquiry_prompt_template", "body_template_de")
