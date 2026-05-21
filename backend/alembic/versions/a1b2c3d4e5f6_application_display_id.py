"""application display_id sequence

Revision ID: a1b2c3d4e5f6
Revises: f9e1b2c3d4a5
Create Date: 2026-05-20 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f9e1b2c3d4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE application_display_id_seq")
    op.add_column(
        "application",
        sa.Column("display_id", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
            FROM application
        )
        UPDATE application a
        SET display_id = n.rn
        FROM numbered n
        WHERE a.id = n.id
        """
    )
    op.execute(
        "SELECT setval('application_display_id_seq', "
        "COALESCE((SELECT MAX(display_id) FROM application), 0) + 1, false)"
    )
    op.alter_column(
        "application",
        "display_id",
        nullable=False,
        server_default=sa.text("nextval('application_display_id_seq')"),
    )
    op.create_unique_constraint(
        "uq_application_display_id", "application", ["display_id"]
    )
    op.execute(
        "ALTER SEQUENCE application_display_id_seq OWNED BY application.display_id"
    )


def downgrade() -> None:
    op.drop_constraint("uq_application_display_id", "application", type_="unique")
    op.drop_column("application", "display_id")
    op.execute("DROP SEQUENCE IF EXISTS application_display_id_seq")
