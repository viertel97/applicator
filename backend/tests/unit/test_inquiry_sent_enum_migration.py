"""Guards the inquiry_sent enum value against model/migration drift.

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. These DB-free checks assert both
the model member exists and that a migration adds the Postgres enum value, so
production deploys don't break on an unknown 'inquiry_sent'.
"""
from pathlib import Path

from app.db.models import InteractionCreatedFrom

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_model_has_inquiry_sent_member():
    assert InteractionCreatedFrom.inquiry_sent.value == "inquiry_sent"


def test_a_migration_adds_inquiry_sent_value():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        "inquiry_sent" in t and "ADD VALUE" in t and "interactioncreatedfrom" in t
        for t in texts
    ), "no Alembic migration ADDs 'inquiry_sent' to interactioncreatedfrom"
