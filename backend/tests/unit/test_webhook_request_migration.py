"""Guards the webhook_request table against model/migration drift.

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. This DB-free check asserts a
migration actually creates the table, so production deploys don't break.
"""
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_a_migration_creates_webhook_request_table():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        "create_table" in t and '"webhook_request"' in t for t in texts
    ), "no Alembic migration creates the webhook_request table"


def test_migration_defines_core_columns():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    hit = next(
        t for t in texts if "create_table" in t and '"webhook_request"' in t
    )
    for col in (
        '"ingest_token"',
        '"source_ip"',
        '"headers"',
        '"raw_body"',
        '"status"',
        '"reason"',
        '"matched_application_id"',
    ):
        assert col in hit, f"migration missing column {col}"


def test_migration_adds_created_interaction_fk():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        '"created_interaction_id"' in t and "SET NULL" in t for t in texts
    ), "no migration adds created_interaction_id with ON DELETE SET NULL"
