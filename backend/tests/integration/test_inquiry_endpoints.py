import json
import uuid

from app.db.models import Application, JobPosting, JobState
from app.inquiry.prompts import DEFAULT_TEMPLATE


def _make_app(db_session, user, *, ho=False, pt=False, email="hr@acme.test"):
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
        application_email=email,
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


def test_draft_creates_inquiry_when_both_flags_false(
    auth_user, db_session, monkeypatch,
):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)
    _patch_llm(monkeypatch, {"subject": "Frage", "body": "Hallo …"})

    r = client.post(f"/api/applications/{a.id}/inquiry/draft")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["subject"] == "Frage"
    assert data["body"] == "Hallo …"
    assert data["recipient"] == "hr@acme.test"

    # ApplicationOut now exposes the saved values
    g = client.get(f"/api/applications/{a.id}").json()
    assert g["inquiry_subject"] == "Frage"
    assert g["inquiry_body"] == "Hallo …"


def test_draft_rejected_when_both_flags_true(
    auth_user, db_session, monkeypatch,
):
    client, user = auth_user
    a = _make_app(db_session, user, ho=True, pt=True)
    _patch_llm(monkeypatch, {"subject": "x", "body": "x"})

    r = client.post(f"/api/applications/{a.id}/inquiry/draft")
    assert r.status_code == 400


def test_patch_updates_subject_and_body(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)
    _patch_llm(monkeypatch, {"subject": "s", "body": "b"})
    client.post(f"/api/applications/{a.id}/inquiry/draft")

    r = client.patch(
        f"/api/applications/{a.id}/inquiry",
        json={"subject": "edited", "body": "edited body"},
    )
    assert r.status_code == 200
    assert r.json()["subject"] == "edited"
    g = client.get(f"/api/applications/{a.id}").json()
    assert g["inquiry_subject"] == "edited"
    assert g["inquiry_body"] == "edited body"


def test_mark_sent_sets_timestamp(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)
    _patch_llm(monkeypatch, {"subject": "s", "body": "b"})
    client.post(f"/api/applications/{a.id}/inquiry/draft")

    r = client.post(f"/api/applications/{a.id}/inquiry/mark-sent")
    assert r.status_code == 200
    assert r.json()["sent_at"] is not None

    g = client.get(f"/api/applications/{a.id}").json()
    assert g["inquiry_sent_at"] is not None


def test_draft_seeds_default_prompt_when_missing(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)

    seen = {}

    def fake_llm():
        class FakeLLM:
            def complete(self, messages, **kwargs):
                seen["sys"] = messages[0]["content"]
                return json.dumps({"subject": "s", "body": "b"})
        return FakeLLM()

    from app.api import applications as apps_module
    monkeypatch.setattr(apps_module, "_inquiry_llm", fake_llm)

    client.post(f"/api/applications/{a.id}/inquiry/draft")
    assert seen["sys"] == DEFAULT_TEMPLATE


def test_draft_404_when_other_user(auth_user, db_session, monkeypatch):
    client, _ = auth_user
    r = client.post(f"/api/applications/{uuid.uuid4()}/inquiry/draft")
    assert r.status_code == 404
