"""Guards the calendar-sync schema against model/migration drift.

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. These DB-free checks assert the
migration actually adds the columns + table, and that the models expose them.
"""
import importlib.util
from pathlib import Path

from app.db.models import CalendarSyncState, Interaction

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
MIG = VERSIONS / "d7e8f9a0b1c2_calendar_sync.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("calsync_mig", str(MIG))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_chains_from_head():
    mod = _load_migration()
    assert mod.revision == "d7e8f9a0b1c2"
    assert mod.down_revision == "c6d7e8f9a0b1"


def test_migration_adds_interaction_external_columns():
    text = MIG.read_text()
    assert '"external_source"' in text
    assert '"external_id"' in text
    assert "uq_interaction_external" in text


def test_migration_creates_calendar_sync_state_table():
    text = MIG.read_text()
    assert "create_table" in text and '"calendar_sync_state"' in text
    for col in ('"user_id"', '"calendar_id"', '"delta_link"', '"updated_at"'):
        assert col in text, f"migration missing column {col}"


def test_models_expose_new_columns():
    icols = {c.name for c in Interaction.__table__.columns}
    assert {"external_source", "external_id"} <= icols
    scols = {c.name for c in CalendarSyncState.__table__.columns}
    assert {"user_id", "calendar_id", "delta_link", "updated_at"} <= scols


def test_interaction_has_external_unique_constraint():
    names = {c.name for c in Interaction.__table__.constraints}
    assert "uq_interaction_external" in names
