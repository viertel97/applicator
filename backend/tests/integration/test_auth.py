import pytest
from fastapi.testclient import TestClient

from app.api.deps import db_dep
from app.auth.session import create_session
from app.db.models import Session as SessionRow
from app.db.models import User


@pytest.fixture
def app_client(db_session, monkeypatch):
    # Required env for Settings()
    monkeypatch.setenv("APP_SECRET_KEY", "k" * 44)
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
    monkeypatch.setenv("LLM_API_KEY", "k")
    from app.main import create_app
    app = create_app()
    def override_db():
        yield db_session

    app.dependency_overrides[db_dep] = override_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_me_unauthenticated(app_client):
    r = app_client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_authenticated(db_session, app_client):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    r = app_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.c"


def test_logout_deletes_session(db_session, app_client):
    u = User(ms_oid="o2", email="x@y.z", display_name="X")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    r = app_client.post("/api/auth/logout")
    assert r.status_code == 200
    assert db_session.get(SessionRow, sid) is None
