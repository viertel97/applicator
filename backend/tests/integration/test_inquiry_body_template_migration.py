"""Alembic round-trip for inquiry_prompt_template body template columns."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PRIOR_REVISION = "e1f2a3b4c5d6"
BODY_REVISION = "f2a3b4c5d6e7"


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


def _columns(engine):
    with engine.connect() as conn:
        return {
            r[0] for r in conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='inquiry_prompt_template'"
            ))
        }


def test_migration_adds_body_template_columns(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))
    command.upgrade(cfg, BODY_REVISION)
    cols = _columns(engine)
    assert "body_template_de" in cols
    assert "body_template_en" in cols


def test_migration_downgrade_drops_columns(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))
    command.upgrade(cfg, BODY_REVISION)
    command.downgrade(cfg, PRIOR_REVISION)
    cols = _columns(engine)
    assert "body_template_de" not in cols
    assert "body_template_en" not in cols
