"""Guards model/migration enum drift.

The production `interactiondirection` Postgres type is created by migration
c4d5e6f7a8b9 with values ("out", "in"), but InteractionDirection.in_ has the
member *name* "in_". SQLAlchemy defaults to persisting member names, which the
DB rejects. These tests pin the column to persist enum *values* so the ORM
matches the migration-created type. They run without a database, so they catch
the drift that testcontainers (which builds the enum from the model) cannot.
"""
from sqlalchemy.dialects import postgresql

from app.db.models import Interaction, InteractionDirection


def _direction_type():
    return Interaction.__table__.c.direction.type


def test_direction_binds_enum_values_not_member_names():
    bind = _direction_type().bind_processor(postgresql.dialect())
    assert bind(InteractionDirection.in_) == "in"
    assert bind(InteractionDirection.out) == "out"


def test_direction_round_trips_db_value():
    dialect = postgresql.dialect()
    bind = _direction_type().bind_processor(dialect)
    read = _direction_type().result_processor(dialect, None)
    for member in InteractionDirection:
        assert read(bind(member)) is member
