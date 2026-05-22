"""Alembic round-trip for the label.category column."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


PRIOR_REVISION = "a1b2c3d4e5f6"
CATEGORY_REVISION = "d2e3f4a5b6c7"


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


def test_migration_adds_category_with_other_default(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))

    command.upgrade(cfg, PRIOR_REVISION)

    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO label (id, name, color, is_auto, created_at) "
            "VALUES (gen_random_uuid(), 'Legacy', '#fff', true, now())"
        ))

    command.upgrade(cfg, CATEGORY_REVISION)

    with engine.connect() as conn:
        cat = conn.execute(sa.text(
            "SELECT category FROM label WHERE name='Legacy'"
        )).scalar_one()
        assert cat == "other"


def test_migration_downgrade_drops_column(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))

    command.upgrade(cfg, CATEGORY_REVISION)
    command.downgrade(cfg, PRIOR_REVISION)

    with engine.connect() as conn:
        cols = {
            r[0] for r in conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='label'"
            ))
        }
        assert "category" not in cols
