import time

import pytest

from app.api.auth import generate_oauth_state, verify_oauth_state
from app.auth.session import create_session
from app.db.models import Session as SessionRow
from app.db.models import User

_SECRET = "k" * 44  # same as conftest


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


# ── HMAC OAuth state tests ───────────────────────────────────────────────────

def test_generate_state_is_verifiable():
    state = generate_oauth_state(_SECRET)
    # Should not raise
    verify_oauth_state(state, _SECRET)


def test_forged_state_rejected():
    state = generate_oauth_state(_SECRET)
    # Tamper with the payload part
    parts = state.split(".")
    tampered = parts[0][:-4] + "XXXX" + "." + parts[1]
    with pytest.raises(ValueError):
        verify_oauth_state(tampered, _SECRET)


def test_wrong_secret_rejected():
    state = generate_oauth_state(_SECRET)
    with pytest.raises(ValueError):
        verify_oauth_state(state, "wrong-secret" * 4)


def test_expired_state_rejected(monkeypatch):
    import app.api.auth as auth_mod

    real_time = time.time()

    # Step 1: generate a state as if it was created 601 seconds ago
    monkeypatch.setattr(auth_mod.time, "time", lambda: real_time - 601)
    state = generate_oauth_state(_SECRET)

    # Step 2: verify at real current time → should see state as expired
    monkeypatch.setattr(auth_mod.time, "time", lambda: real_time)
    with pytest.raises(ValueError, match="expired"):
        verify_oauth_state(state, _SECRET)


def test_callback_rejects_forged_state(app_client):
    """The /callback endpoint must reject state tokens not signed by the app secret."""
    r = app_client.get(
        "/api/auth/callback",
        params={"code": "anycode", "state": "forged.state"},
        follow_redirects=False,
    )
    assert r.status_code == 400
