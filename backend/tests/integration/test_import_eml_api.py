import uuid
from pathlib import Path

import app.api.interactions as interactions_module
from app.db.models import Application

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "eml"


def _read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def _make_app(db_session, user):
    a = Application(user_id=user.id, url="https://x.test/eml", url_hash="heml")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def test_import_single_message(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user  # u.email == "a@b.c"
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("mail.eml", _read("single_plain.eml"), "message/rfc822")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["used_llm"] is False
    it = body["interactions"][0]
    assert it["channel"] == "mail"
    assert it["created_from"] == "eml_import"
    assert it["direction"] == "in"  # sender anna@acme.test != user a@b.c
    assert it["contact_handle"] == "anna@acme.test"
    assert it["sentiment"] is None


def test_import_outlook_thread_creates_two(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("t.eml", _read("outlook_thread.eml"), "message/rfc822")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    # newest first by occurred_at desc when listed
    listing = client.get(f"/api/applications/{a.id}/interactions").json()
    assert len(listing) == 2


def test_import_direction_out_when_sender_is_user(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user  # a@b.c
    a = _make_app(db_session, u)
    raw = (
        b"From: Me <a@b.c>\r\n"
        b"To: Recruiter <anna@acme.test>\r\n"
        b"Subject: Hi\r\n"
        b"Date: Thu, 01 May 2026 09:30:00 +0000\r\n"
        b'Content-Type: text/plain; charset="utf-8"\r\n\r\n'
        b"My note.\r\n"
    )
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("o.eml", raw, "message/rfc822")},
    )
    it = r.json()["interactions"][0]
    assert it["direction"] == "out"
    assert it["contact_handle"] == "anna@acme.test"  # the recipient


def test_import_unowned_app_404(client, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    r = client.post(
        f"/api/applications/{uuid.uuid4()}/interactions/import-eml",
        files={"file": ("m.eml", b"From: x@y.z\r\n\r\nhi", "message/rfc822")},
    )
    assert r.status_code == 404


def test_import_wrong_extension_400(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("m.txt", b"hi", "text/plain")},
    )
    assert r.status_code == 400


def test_import_oversize_413(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user
    a = _make_app(db_session, u)
    big = b"From: x@y.z\r\n\r\n" + b"a" * (10 * 1024 * 1024 + 1)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("big.eml", big, "message/rfc822")},
    )
    assert r.status_code == 413


def test_import_empty_parse_422(client, db_session, auth_user, monkeypatch):
    # force parse_eml to yield no messages
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    from app.email_ingest.models import ParsedThread

    monkeypatch.setattr(
        interactions_module,
        "parse_eml",
        lambda raw, *, llm: ParsedThread(messages=[], used_llm=False),
    )
    _, u = auth_user
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("e.eml", b"From: x@y.z\r\n\r\n", "message/rfc822")},
    )
    assert r.status_code == 422
