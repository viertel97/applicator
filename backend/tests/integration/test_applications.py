import json
from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker

from app.auth.session import create_session
from app.config import Settings
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import (
    AnschreibenVariant,
    Application,
    CVVariant,
    JobState,
    User,
)
from app.tasks.celery_app import celery_app
from tests.fakes.fetcher import FakeFetcher
from tests.fakes.llm import FakeLLM


def _patch_pipeline(monkeypatch, db_session, settings, llm_handler, fetcher_result):
    from app.tasks import pipeline as tp

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    engine = db_session.get_bind()
    fetcher = FakeFetcher(result=fetcher_result)

    @contextmanager
    def factory():
        s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        try:
            yield s
        finally:
            s.close()

    monkeypatch.setattr(tp, "_db_factory", lambda: factory)
    monkeypatch.setattr(tp, "_settings", lambda: settings)
    monkeypatch.setattr(tp, "_llm", lambda s: FakeLLM(handler=llm_handler))
    monkeypatch.setattr(tp, "_fetcher", lambda: fetcher)


def test_create_url_only_reaches_extracted(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/u", status_code=200, html="<p>x</p>", text="x" * 1000)
    payload = {"title": "Dev", "company": "Acme", "language": "en"}
    _patch_pipeline(
        monkeypatch, db_session, settings,
        lambda m, s: json.dumps(payload) if s else "# Letter", fr,
    )
    c, _ = auth_user
    r = c.post("/api/applications", json={"url": "https://x.test/u"})
    assert r.status_code == 202, r.text
    aid = r.json()["id"]
    g = c.get(f"/api/applications/{aid}").json()
    assert g["job_state"] == "extracted"
    assert g["generated_md"] is None
    assert g["has_docx"] is False
    assert g["cv_variant_id"] is None
    assert g["anschreiben_variant_id"] is None
    assert g["job_posting_dirty"] is False
    assert g["failed_stage"] is None


def test_create_runs_pipeline_and_lists(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/j", status_code=200, html="<p>x</p>", text="x" * 1000)
    job = {
        "title": "Dev", "company": "Acme", "language": "en",
        "description": "d", "requirements": "r",
    }

    def llm_handler(messages, schema):
        return json.dumps(job) if schema is not None else "# Letter"

    _patch_pipeline(monkeypatch, db_session, settings, llm_handler, fr)

    c, user = auth_user
    cv = db_session.query(CVVariant).filter_by(user_id=user.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=user.id).first()
    r = c.post(
        "/api/applications",
        json={
            "url": "https://x.test/j",
            "cv_variant_id": str(cv.id),
            "anschreiben_variant_id": str(an.id),
        },
    )
    assert r.status_code == 202, r.text
    aid = r.json()["id"]
    # URL-only chain only runs crawl+extract; user must trigger generate.
    c.post(f"/api/applications/{aid}/generate")
    g = c.get(f"/api/applications/{aid}").json()
    assert g["job_state"] == "ready"
    assert g["job_posting"]["title"] == "Dev"
    assert g["has_docx"] is True


def test_duplicate_url_returns_409(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="u", status_code=200, html="<p>x</p>", text="x" * 1000)
    _patch_pipeline(
        monkeypatch, db_session, settings,
        lambda m, s: '{"language":"en"}' if s else "letter",
        fr,
    )
    c, _ = auth_user
    c.post("/api/applications", json={"url": "https://x.test/j"})
    r = c.post("/api/applications", json={"url": "https://x.test/j"})
    assert r.status_code == 409


def test_status_patch(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="u", status_code=200, html="<p>x</p>", text="x" * 1000)
    _patch_pipeline(
        monkeypatch, db_session, settings,
        lambda m, s: '{"language":"en"}' if s else "letter",
        fr,
    )
    c, user = auth_user
    cv = db_session.query(CVVariant).filter_by(user_id=user.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=user.id).first()
    aid = c.post(
        "/api/applications",
        json={
            "url": "https://x.test/j",
            "cv_variant_id": str(cv.id),
            "anschreiben_variant_id": str(an.id),
        },
    ).json()["id"]
    r = c.patch(f"/api/applications/{aid}", json={"status": "applied"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied"


def test_docx_download(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="u", status_code=200, html="<p>x</p>", text="x" * 1000)
    _patch_pipeline(
        monkeypatch, db_session, settings,
        lambda m, s: '{"language":"en","title":"Dev"}' if s else "# Hi",
        fr,
    )
    c, user = auth_user
    cv = db_session.query(CVVariant).filter_by(user_id=user.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=user.id).first()
    aid = c.post(
        "/api/applications",
        json={
            "url": "https://x.test/j",
            "cv_variant_id": str(cv.id),
            "anschreiben_variant_id": str(an.id),
        },
    ).json()["id"]
    c.post(f"/api/applications/{aid}/generate")
    r = c.get(f"/api/applications/{aid}/docx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml"
    )


def test_other_users_cv_variant_rejected(monkeypatch, auth_user, db_session, app_client):
    """Passing another user's variant IDs must return 400, not 202."""
    # Create a second user with their own CV/Anschreiben variants
    other_user = User(ms_oid="other", email="other@example.com", display_name="Other")
    db_session.add(other_user)
    db_session.flush()
    other_cv = CVVariant(user_id=other_user.id, name="cv2", source_md="cv2", is_default=False)
    other_an = AnschreibenVariant(
        user_id=other_user.id, name="an2", source_md="an2", is_default=False
    )
    db_session.add_all([other_cv, other_an])
    db_session.commit()
    db_session.refresh(other_cv)
    db_session.refresh(other_an)

    c, _ = auth_user  # logged in as first user

    # Try to use other user's CV variant
    r = c.post(
        "/api/applications",
        json={"url": "https://x.test/j", "cv_variant_id": str(other_cv.id)},
    )
    assert r.status_code == 400, f"Expected 400 but got {r.status_code}: {r.text}"

    # Try to use other user's Anschreiben variant
    r = c.post(
        "/api/applications",
        json={"url": "https://x.test/j2", "anschreiben_variant_id": str(other_an.id)},
    )
    assert r.status_code == 400, f"Expected 400 but got {r.status_code}: {r.text}"


def test_discard_with_structured_fields(client, db_session, auth_user):
    _, user = auth_user
    a = Application(user_id=user.id, url="https://x.test/d", url_hash="hd")
    db_session.add(a)
    db_session.commit()

    # ensure reasons seeded
    reasons = client.get("/api/discard-reasons").json()
    rejected = next(r for r in reasons if r["slug"] == "rejected")

    # create an interaction to point to
    it = client.post(
        f"/api/applications/{a.id}/interactions",
        json={
            "direction": "in",
            "channel": "mail",
            "sentiment": "rejection",
            "body": "no",
        },
    ).json()["interaction"]

    r = client.patch(
        f"/api/applications/{a.id}",
        json={
            "status": "discarded",
            "discard_reason_id": rejected["id"],
            "discard_interaction_id": it["id"],
            "discard_note": "auto from rejection mail",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "discarded"
    assert body["discard_reason_id"] == rejected["id"]
    assert body["discard_interaction_id"] == it["id"]
    assert body["discard_note"] == "auto from rejection mail"


def test_un_discard_clears_structured_fields(client, db_session, auth_user):
    _, user = auth_user
    a = Application(user_id=user.id, url="https://x.test/u", url_hash="hu")
    db_session.add(a)
    db_session.commit()
    reasons = client.get("/api/discard-reasons").json()
    rid = reasons[0]["id"]
    client.patch(
        f"/api/applications/{a.id}",
        json={"status": "discarded", "discard_reason_id": rid},
    )
    r = client.patch(f"/api/applications/{a.id}", json={"status": "draft"})
    body = r.json()
    assert body["discard_reason_id"] is None
    assert body["discard_interaction_id"] is None
    assert body["discard_note"] is None
