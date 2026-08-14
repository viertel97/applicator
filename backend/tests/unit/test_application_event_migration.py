from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_a_migration_adds_event_interaction_fk_cascade():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        '"interaction_id"' in t and "application_event" in t and "CASCADE" in t
        for t in texts
    ), "no migration adds application_event.interaction_id with ON DELETE CASCADE"
