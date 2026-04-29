import json

import pytest

from app.api import chat as chat_api
from app.db.models import (
    AnschreibenVariant,
    Application,
    ApplicationStatus,
    CVVariant,
    JobState,
)
from tests.fakes.llm import FakeLLM


@pytest.fixture
def app_with_letter(auth_user, db_session):
    c, u = auth_user
    cv = db_session.query(CVVariant).filter_by(user_id=u.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=u.id).first()
    app_row = Application(
        user_id=u.id,
        url="https://x.test/j",
        url_hash="h-chat-1",
        cv_variant_id=cv.id,
        anschreiben_variant_id=an.id,
        generated_md="# Letter\n\nHello",
        language="en",
        status=ApplicationStatus.draft,
        job_state=JobState.ready,
    )
    db_session.add(app_row)
    db_session.commit()
    db_session.refresh(app_row)
    return c, u, app_row


def test_chat_refines_and_persists(monkeypatch, app_with_letter):
    c, _, app_row = app_with_letter
    payload = {"assistant_message": "Tweaked.", "updated_md": "# Letter v2\n\nHello!"}
    fake = FakeLLM(handler=lambda m, s: json.dumps(payload))
    monkeypatch.setattr(chat_api, "_llm", lambda settings: fake)

    r = c.post(f"/api/applications/{app_row.id}/chat", json={"message": "Make it shorter"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated_md"].startswith("# Letter v2")
    assert body["assistant_message"] == "Tweaked."

    msgs = c.get(f"/api/applications/{app_row.id}/chat").json()
    assert len(msgs) == 2
    assert any("shorter" in m["content"] for m in msgs)
    assert any(m["role"] == "assistant" for m in msgs)


def test_chat_requires_existing_anschreiben(auth_user, db_session):
    c, u = auth_user
    cv = db_session.query(CVVariant).filter_by(user_id=u.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=u.id).first()
    app_row = Application(
        user_id=u.id,
        url="https://y.test/j",
        url_hash="h-chat-2",
        cv_variant_id=cv.id,
        anschreiben_variant_id=an.id,
        status=ApplicationStatus.draft,
        job_state=JobState.pending,
    )
    db_session.add(app_row)
    db_session.commit()
    db_session.refresh(app_row)
    r = c.post(f"/api/applications/{app_row.id}/chat", json={"message": "x"})
    assert r.status_code == 400


def test_chat_404_for_other_user(auth_user, db_session):
    """Verify ownership check."""
    c, u = auth_user
    import uuid as _uuid
    r = c.post(f"/api/applications/{_uuid.uuid4()}/chat", json={"message": "x"})
    assert r.status_code == 404
