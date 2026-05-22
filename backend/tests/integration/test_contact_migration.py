"""Tests the data-copy logic of the contact-struct migration.

Walks alembic from the prior revision up to ``c1d2e3f4a5b6`` so that
rows inserted with the old flat ``contact_person`` / ``application_email``
columns are collapsed into the new ``contact`` JSON column.
"""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


PRIOR_REVISION = "a1b2c3d4e5f6"
CONTACT_REVISION = "c1d2e3f4a5b6"


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


def _seed_user_and_app(conn) -> str:
    user_id = conn.execute(sa.text(
        "INSERT INTO \"user\" (id, ms_oid, email, display_name) "
        "VALUES (gen_random_uuid(), 'oid-mig', 'm@x.com', 'M') RETURNING id"
    )).scalar_one()
    app_id = conn.execute(sa.text(
        "INSERT INTO application "
        "(id, user_id, url, url_hash, status, job_state, job_posting_dirty) "
        "VALUES (gen_random_uuid(), :uid, 'https://x/job', :h, "
        "'draft', 'pending', false) "
        "RETURNING id"
    ), {"uid": user_id, "h": "h" * 64}).scalar_one()
    return str(app_id)


def test_migration_copies_both_fields_into_contact_json(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))

    command.upgrade(cfg, PRIOR_REVISION)

    with engine.begin() as conn:
        app_id = _seed_user_and_app(conn)
        conn.execute(sa.text(
            "INSERT INTO job_posting "
            "(id, application_id, raw_text, contact_person, application_email) "
            "VALUES (gen_random_uuid(), :aid, 'raw', 'Jane Doe', 'j@x.com')"
        ), {"aid": app_id})

    command.upgrade(cfg, CONTACT_REVISION)

    with engine.connect() as conn:
        cols = {
            r[0] for r in conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='job_posting'"
            ))
        }
        assert "contact" in cols
        assert "backfill_attempts" in cols
        assert "contact_person" not in cols
        assert "application_email" not in cols

        contact = conn.execute(sa.text(
            "SELECT contact FROM job_posting WHERE application_id=:aid"
        ), {"aid": app_id}).scalar_one()
        assert contact == {"name": "Jane Doe", "email": "j@x.com"}


def test_migration_copies_name_only_when_email_missing(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))

    command.upgrade(cfg, PRIOR_REVISION)

    with engine.begin() as conn:
        app_id = _seed_user_and_app(conn)
        conn.execute(sa.text(
            "INSERT INTO job_posting "
            "(id, application_id, raw_text, contact_person, application_email) "
            "VALUES (gen_random_uuid(), :aid, 'raw', 'Solo', NULL)"
        ), {"aid": app_id})

    command.upgrade(cfg, CONTACT_REVISION)

    with engine.connect() as conn:
        contact = conn.execute(sa.text(
            "SELECT contact FROM job_posting WHERE application_id=:aid"
        ), {"aid": app_id}).scalar_one()
        assert contact == {"name": "Solo"}


def test_migration_leaves_contact_null_when_both_missing(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))

    command.upgrade(cfg, PRIOR_REVISION)

    with engine.begin() as conn:
        app_id = _seed_user_and_app(conn)
        conn.execute(sa.text(
            "INSERT INTO job_posting (id, application_id, raw_text) "
            "VALUES (gen_random_uuid(), :aid, 'raw')"
        ), {"aid": app_id})

    command.upgrade(cfg, CONTACT_REVISION)

    with engine.connect() as conn:
        contact = conn.execute(sa.text(
            "SELECT contact FROM job_posting WHERE application_id=:aid"
        ), {"aid": app_id}).scalar_one()
        assert contact is None


def test_migration_downgrade_restores_flat_fields(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))

    command.upgrade(cfg, CONTACT_REVISION)

    with engine.begin() as conn:
        app_id = _seed_user_and_app(conn)
        conn.execute(sa.text(
            "INSERT INTO job_posting (id, application_id, raw_text, contact) "
            "VALUES (gen_random_uuid(), :aid, 'raw', CAST(:c AS JSON))"
        ), {"aid": app_id, "c": '{"name": "Round Trip", "email": "r@x.com"}'})

    command.downgrade(cfg, PRIOR_REVISION)

    with engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT contact_person, application_email "
            "FROM job_posting WHERE application_id=:aid"
        ), {"aid": app_id}).one()
        assert row.contact_person == "Round Trip"
        assert row.application_email == "r@x.com"
