"""contact struct, backfill_attempts, soft delete

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f6
Create Date: 2026-05-21 00:00:00.000000

"""
import json
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_posting", sa.Column("contact", sa.JSON(), nullable=True))
    op.add_column(
        "job_posting",
        sa.Column(
            "backfill_attempts",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("application", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    # Data copy: collapse contact_person + application_email into contact JSON.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, contact_person, application_email "
            "FROM job_posting "
            "WHERE contact_person IS NOT NULL OR application_email IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        payload = {}
        if row.contact_person:
            payload["name"] = row.contact_person
        if row.application_email:
            payload["email"] = row.application_email
        bind.execute(
            sa.text("UPDATE job_posting SET contact = CAST(:c AS JSON) WHERE id = :id"),
            {"c": json.dumps(payload), "id": row.id},
        )

    op.drop_column("job_posting", "contact_person")
    op.drop_column("job_posting", "application_email")


def downgrade() -> None:
    op.add_column(
        "job_posting", sa.Column("contact_person", sa.Text(), nullable=True)
    )
    op.add_column(
        "job_posting", sa.Column("application_email", sa.Text(), nullable=True)
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, contact FROM job_posting WHERE contact IS NOT NULL")
    ).fetchall()
    for row in rows:
        payload = row.contact or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        bind.execute(
            sa.text(
                "UPDATE job_posting SET contact_person = :n, application_email = :e "
                "WHERE id = :id"
            ),
            {
                "n": payload.get("name"),
                "e": payload.get("email"),
                "id": row.id,
            },
        )

    op.drop_column("job_posting", "contact")
    op.drop_column("job_posting", "backfill_attempts")
    op.drop_column("application", "deleted_at")
