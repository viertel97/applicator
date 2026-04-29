import pytest

from app.auth.session import create_session
from app.db.models import User


@pytest.fixture
def auth_client(app_client, db_session):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    return app_client, u


def test_create_and_list_cv(auth_client):
    c, _ = auth_client
    r = c.post("/api/cv-variants", json={"name": "default", "source_md": "x", "is_default": True})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "default" and body["is_default"] is True
    r2 = c.get("/api/cv-variants")
    assert len(r2.json()) == 1


def test_set_default_exclusive(auth_client):
    c, _ = auth_client
    a = c.post("/api/cv-variants", json={"name": "a", "source_md": "x", "is_default": True}).json()
    b = c.post("/api/cv-variants", json={"name": "b", "source_md": "y", "is_default": True}).json()
    items = c.get("/api/cv-variants").json()
    flags = {it["id"]: it["is_default"] for it in items}
    assert flags[a["id"]] is False
    assert flags[b["id"]] is True


def test_anschreiben_endpoints(auth_client):
    c, _ = auth_client
    r = c.post("/api/anschreiben-variants", json={"name": "t", "source_md": "tpl"})
    assert r.status_code == 200
    assert c.get("/api/anschreiben-variants").json()[0]["name"] == "t"
