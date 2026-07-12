"""Guards InterviewStage model/migration drift (DB-free).

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. These checks assert the model
member set and that the column persists enum *values* (not member names).
"""
from pathlib import Path

from sqlalchemy.dialects import postgresql

from app.db.models import Interaction, InterviewStage


def test_interview_stage_members_exact():
    assert [m.value for m in InterviewStage] == [
        "phone_screen",
        "technical",
        "onsite",
        "hr",
        "final",
        "other",
    ]


def test_interview_stage_string_backed():
    assert InterviewStage.technical == "technical"
    assert isinstance(InterviewStage.technical, str)


def test_column_binds_enum_values_not_member_names():
    col_type = Interaction.__table__.c.interview_stage.type
    dialect = postgresql.dialect()
    bind = col_type.bind_processor(dialect)
    read = col_type.result_processor(dialect, None)
    for member in InterviewStage:
        assert bind(member) == member.value
        assert read(bind(member)) is member


VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_migration_adds_interview_stage_column():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        "interview_stage" in t
        and "interviewstage" in t
        and "add_column" in t
        for t in texts
    ), "no Alembic migration adds interaction.interview_stage"


def test_migration_chains_from_head():
    p = VERSIONS / "b4c5d6e7f8a9_interaction_interview_stage.py"
    assert p.exists()
    text = p.read_text()
    assert 'revision: str = "b4c5d6e7f8a9"' in text
    assert 'down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"' in text
