"""async pipeline url only

Revision ID: cb4656bd8fff
Revises: 15b2385a2a40
Create Date: 2026-04-29 17:22:12.216124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb4656bd8fff'
down_revision: Union[str, Sequence[str], None] = '15b2385a2a40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Make variant FKs nullable
    op.alter_column("application", "cv_variant_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column(
        "application", "anschreiben_variant_id", existing_type=sa.UUID(), nullable=True
    )

    # 2. Extend JobState enum (Postgres requires non-transactional ALTER TYPE)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE jobstate ADD VALUE IF NOT EXISTS 'extracted'")

    # 3. Create FailedStage enum
    failed_stage_enum = sa.Enum("crawl", "extract", "generate", name="failedstage")
    failed_stage_enum.create(op.get_bind(), checkfirst=True)

    # 4. Add new columns
    op.add_column(
        "application",
        sa.Column("failed_stage", failed_stage_enum, nullable=True),
    )
    op.add_column(
        "application",
        sa.Column(
            "job_posting_dirty",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Drop server_default once all rows have a value
    op.alter_column("application", "job_posting_dirty", server_default=None)


def downgrade() -> None:
    # Safety prelude: clean up data states introduced by upgrade so the
    # NOT NULL re-tightening and pre-migration enum invariants hold.
    op.execute(
        "UPDATE application SET job_state = 'pending' WHERE job_state = 'extracted'"
    )
    op.execute("DELETE FROM application WHERE cv_variant_id IS NULL OR anschreiben_variant_id IS NULL")

    op.drop_column("application", "job_posting_dirty")
    op.drop_column("application", "failed_stage")
    sa.Enum(name="failedstage").drop(op.get_bind(), checkfirst=True)
    # Note: Postgres cannot drop a single enum value; jobstate retains 'extracted' on downgrade,
    # but the prelude above resets such rows to 'pending' so the app's pre-migration enum holds.
    op.alter_column(
        "application", "anschreiben_variant_id", existing_type=sa.UUID(), nullable=False
    )
    op.alter_column("application", "cv_variant_id", existing_type=sa.UUID(), nullable=False)
