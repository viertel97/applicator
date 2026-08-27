"""Guard: the Alembic chain actually creates calendar_suggestion + its enum.

The db_session fixture builds schema from models, which masks missing
migrations. This test runs `alembic upgrade head` against a fresh container.
"""
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_migration_creates_table_and_enum(pg_container, monkeypatch):
    raw = pg_container.get_connection_url()
    url = raw.replace("postgresql+psycopg2://", "postgresql+psycopg://").replace(
        "postgresql://", "postgresql+psycopg://"
    )
    monkeypatch.setenv("DATABASE_URL", url)

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    try:
        insp = inspect(engine)
        assert "calendar_suggestion" in insp.get_table_names()
        with engine.connect() as conn:
            labels = conn.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'calendarsuggestionstatus' "
                    "ORDER BY e.enumsortorder"
                )
            ).scalars().all()
        assert labels == ["pending", "confirmed", "dismissed"]
    finally:
        # Leave the container clean for other session-scoped users.
        command.downgrade(cfg, "base")
        engine.dispose()
