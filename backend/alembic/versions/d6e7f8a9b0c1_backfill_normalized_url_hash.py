"""backfill normalized url_hash

Recompute url_hash for existing application rows using the canonical
normalization (tracking/locale params stripped, etc.). Oldest row wins on a
collision: if two existing rows normalize to the same hash for one user, the
older keeps/gets the new hash and the newer is left untouched so the
uq_user_url_hash constraint is never violated.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-31

"""

from alembic import op
import sqlalchemy as sa

from app.pipeline.url_hash import url_hash

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, user_id, url, url_hash FROM application "
            "ORDER BY created_at ASC, display_id ASC"
        )
    ).fetchall()

    taken: set[tuple] = set()  # (user_id, hash) already assigned this pass
    for row in rows:
        new_hash = url_hash(row.url)
        key = (row.user_id, new_hash)
        if key in taken:
            # A newer duplicate of an already-seen job — leave it as-is.
            taken.add((row.user_id, row.url_hash))
            continue
        taken.add(key)
        if new_hash != row.url_hash:
            bind.execute(
                sa.text("UPDATE application SET url_hash = :h WHERE id = :id"),
                {"h": new_hash, "id": row.id},
            )


def downgrade() -> None:
    # Old hashes are not recoverable from the normalized form; no-op.
    pass
