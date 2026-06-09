import json
import uuid

from app.db.models import (
    Application,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
    InteractionDirection,
    JobPosting,
    JobState,
)
from app.inquiry.prompts import DEFAULT_TEMPLATE


def _make_app(db_session, user, *, ho=False, pt=False):
    a = Application(
        user_id=user.id,
        url="https://x.test/u",
        url_hash="h" * 64,
        job_state=JobState.extracted,
        language="de",
    )
    db_session.add(a)
    db_session.flush()
    jp = JobPosting(
        application_id=a.id,
        raw_text="x",
        title="Dev",
        company="Acme",
        language="de",
        contact={"email": "hr@acme.test", "name": "HR Person", "role": None, "phone": None},
        mentions_home_office_policy=ho,
        mentions_part_time=pt,
    )
    db_session.add(jp)
    db_session.commit()
    return a


def _patch_llm(monkeypatch, payload):
    from app.api import applications as apps_module

    def fake_llm():
        class FakeLLM:
            def complete(self, messages, **kwargs):
                return json.dumps(payload)
        return FakeLLM()

    monkeypatch.setattr(apps_module, "_inquiry_llm", fake_llm)


def test_draft_returns_subject_and_body(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)
    _patch_llm(monkeypatch, {"subject": "Frage", "greeting": "Sehr geehrte Damen und Herren"})

    r = client.post(f"/api/applications/{a.id}/inquiry/draft")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["subject"] == "Frage"
    assert isinstance(data["body"], str) and data["body"]
    assert data["recipient"] == "hr@acme.test"
    # sent_at is now always None — draft does not persist anything
    assert data["sent_at"] is None


def test_patch_endpoint_is_gone(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)
    r = client.patch(
        f"/api/applications/{a.id}/inquiry",
        json={"subject": "edited", "body": "edited body"},
    )
    # Either 404 (route gone) or 405 (method not allowed) is acceptable
    assert r.status_code in (404, 405), r.text


def test_mark_sent_creates_outgoing_mail_interaction(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)

    r = client.post(
        f"/api/applications/{a.id}/inquiry/mark-sent",
        json={"subject": "My subject", "body": "My body"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sent_at"] is not None
    assert "interaction_id" in data

    interactions = (
        db_session.query(Interaction)
        .filter(Interaction.application_id == a.id)
        .all()
    )
    assert len(interactions) == 1
    it = interactions[0]
    assert str(it.id) == data["interaction_id"]
    assert it.direction == InteractionDirection.out
    assert it.channel == InteractionChannel.mail
    assert it.subject == "My subject"
    assert it.body == "My body"
    assert it.created_from == InteractionCreatedFrom.inquiry_sent
    # contact came from job_posting.contact
    assert it.contact_name == "HR Person"
    assert it.contact_handle == "hr@acme.test"


def test_mark_sent_visible_in_interactions_list(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)

    r = client.post(
        f"/api/applications/{a.id}/inquiry/mark-sent",
        json={"subject": "S", "body": "B"},
    )
    assert r.status_code == 200

    g = client.get(f"/api/applications/{a.id}/interactions")
    assert g.status_code == 200
    rows = g.json()
    assert len(rows) == 1
    assert rows[0]["subject"] == "S"
    assert rows[0]["direction"] == "out"
    assert rows[0]["channel"] == "mail"


def test_draft_seeds_default_prompt_when_missing(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)

    seen = {}

    def fake_llm():
        class FakeLLM:
            def complete(self, messages, **kwargs):
                seen["sys"] = messages[0]["content"]
                return json.dumps({"subject": "s", "greeting": "Hallo"})
        return FakeLLM()

    from app.api import applications as apps_module
    monkeypatch.setattr(apps_module, "_inquiry_llm", fake_llm)

    client.post(f"/api/applications/{a.id}/inquiry/draft")
    assert seen["sys"] == DEFAULT_TEMPLATE


def test_draft_404_when_other_user(auth_user, db_session, monkeypatch):
    client, _ = auth_user
    r = client.post(f"/api/applications/{uuid.uuid4()}/inquiry/draft")
    assert r.status_code == 404
