from app.auth.session import create_session
from app.db.models import Session as SessionRow
from app.db.models import User


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
