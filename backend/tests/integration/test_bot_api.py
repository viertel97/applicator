import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from app.api.deps import db_dep
from app.db import models  # noqa: F401
from app.db.models import Application, User
from app.db.session import Base


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
def db_session(pg, monkeypatch, reset_db_session_singletons):
    raw_url = pg.get_connection_url()
    url = (
        raw_url
        .replace("postgresql+psycopg2://", "postgresql+psycopg://")
        .replace("postgresql://", "postgresql+psycopg://")
    )
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def bot_client(db_session, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("BOT_API_KEY", "secret-bot-key")

    from app.main import create_app
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[db_dep] = override_db
    return TestClient(app)


@pytest.fixture
def bot_user(db_session, monkeypatch, bot_client):
    """Create a User and set APP_USER_ID to its id."""
    u = User(ms_oid="bot-oid", email="bot@test.com", display_name="Bot User")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    monkeypatch.setenv("APP_USER_ID", str(u.id))
    return u


@pytest.fixture
def no_celery(monkeypatch):
    import app.api.bot as bot_module
    monkeypatch.setattr(bot_module, "_start_bot_chain", lambda app_id, chat_id: None)


def test_bot_create_application(bot_client, bot_user, db_session, no_celery):
    resp = bot_client.post(
        "/api/bot/applications",
        json={"url": "https://example.com/job/123", "chat_id": 42},
        headers={"Authorization": "Bearer secret-bot-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://example.com/job/123"
    assert "app_id" in data

    app_row = db_session.query(Application).filter_by(url="https://example.com/job/123").first()
    assert app_row is not None
    assert app_row.user_id == bot_user.id


def test_bot_rejects_wrong_token(bot_client, bot_user, no_celery):
    resp = bot_client.post(
        "/api/bot/applications",
        json={"url": "https://example.com/job/456", "chat_id": 42},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_bot_rejects_missing_token(bot_client, bot_user, no_celery):
    resp = bot_client.post(
        "/api/bot/applications",
        json={"url": "https://example.com/job/789", "chat_id": 42},
    )
    assert resp.status_code == 401


def test_bot_deduplicates_url(bot_client, bot_user, db_session, no_celery):
    payload = {"url": "https://example.com/job/dup", "chat_id": 42}
    headers = {"Authorization": "Bearer secret-bot-key"}

    resp1 = bot_client.post("/api/bot/applications", json=payload, headers=headers)
    resp2 = bot_client.post("/api/bot/applications", json=payload, headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 409
