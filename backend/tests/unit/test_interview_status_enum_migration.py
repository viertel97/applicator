"""Guards the interview ApplicationStatus enum value against model/migration drift.

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. These DB-free checks assert both
the model member exists and that a migration adds the Postgres enum value, so
production deploys don't break on an unknown 'interview'.
"""
from pathlib import Path

from app.db.models import ApplicationStatus

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_model_has_interview_member():
    assert ApplicationStatus.interview.value == "interview"


def test_a_migration_adds_interview_value():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        "interview" in t and "ADD VALUE" in t and "applicationstatus" in t
        for t in texts
    ), "no Alembic migration ADDs 'interview' to applicationstatus"
