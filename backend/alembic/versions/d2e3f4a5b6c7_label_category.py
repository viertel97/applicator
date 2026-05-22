"""label category column

Revision ID: d2e3f4a5b6c7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-22 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LABEL_CATEGORY_VALUES = (
    "role",
    "tech",
    "domain",
    "seniority",
    "work_mode",
    "location",
    "company_size",
    "language",
    "company",
    "other",
)


def upgrade() -> None:
    label_category = sa.Enum(*_LABEL_CATEGORY_VALUES, name="labelcategory")
    label_category.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "label",
        sa.Column(
            "category",
            label_category,
            nullable=False,
            server_default="other",
        ),
    )


def downgrade() -> None:
    op.drop_column("label", "category")
    sa.Enum(name="labelcategory").drop(op.get_bind(), checkfirst=True)
