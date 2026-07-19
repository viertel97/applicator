"""Guards the posting-offline columns against model/migration drift.

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. These DB-free checks assert the
model has both columns AND that a migration adds them, so production deploys
don't break (per the enum-drift convention).
"""
from pathlib import Path

from sqlalchemy import inspect

from app.db.models import Application

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_model_has_posting_offline_columns():
    cols = {c.key for c in inspect(Application).columns}
    assert "posting_offline_reason" in cols
    assert "posting_offline_dismissed_at" in cols


def test_a_migration_adds_both_columns():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        "add_column" in t
        and "posting_offline_reason" in t
        and "posting_offline_dismissed_at" in t
        for t in texts
    ), "no Alembic migration adds the posting_offline_* columns"
