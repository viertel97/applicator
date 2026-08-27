"""Guard: the Alembic chain adds the outlook_last_* health columns to user.

The db_session fixture builds schema from models, which masks a missing
migration. This test runs `alembic upgrade head` against a fresh container.
"""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


def _alembic_cfg(url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def fresh_db(pg_container, monkeypatch):
    raw_url = pg_container.get_connection_url()
    url = (
        raw_url
        .replace("postgresql+psycopg2://", "postgresql+psycopg://")
        .replace("postgresql://", "postgresql+psycopg://")
    )
    monkeypatch.setenv("DATABASE_URL", url)
    engine = sa.create_engine(url, future=True, isolation_level="AUTOCOMMIT")

    def _wipe():
        with engine.connect() as conn:
            conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(sa.text("CREATE SCHEMA public"))

    _wipe()
    yield engine, url
    _wipe()
    engine.dispose()


def test_migration_adds_outlook_health_columns(fresh_db):
    engine, url = fresh_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "head")

    cols = {c["name"] for c in inspect(engine).get_columns("user")}
    for name in (
        "outlook_last_sync_at",
        "outlook_last_status",
        "outlook_last_reason",
        "outlook_last_trigger",
        "outlook_last_counts",
        "outlook_last_error",
    ):
        assert name in cols, f"missing column {name}"
