"""Guards InterviewStage model/migration drift (DB-free).

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. These checks assert the model
member set and that the column persists enum *values* (not member names).
"""
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
