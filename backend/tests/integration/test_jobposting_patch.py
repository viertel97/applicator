import json
from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.crawler.httpx_fetcher import FetchResult
from app.tasks.celery_app import celery_app
from tests.fakes.fetcher import FakeFetcher
from tests.fakes.llm import FakeLLM


def _eager_patch(monkeypatch, db_session, settings, llm_handler, fr):
    from app.tasks import pipeline as tp

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    engine = db_session.get_bind()
    fetcher = FakeFetcher(result=fr)

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


def test_patch_job_posting_updates_fields(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/p", status_code=200, html="<p>x</p>", text="x" * 1000)
    payload = {"title": "Dev", "company": "Acme", "language": "en"}
    _eager_patch(monkeypatch, db_session, settings,
                 lambda m, s: json.dumps(payload), fr)

    c, _ = auth_user
    aid = c.post("/api/applications", json={"url": "https://x.test/p"}).json()["id"]
    r = c.patch(f"/api/applications/{aid}/job-posting", json={"title": "Senior Dev"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_posting"]["title"] == "Senior Dev"
    assert body["job_posting_dirty"] is False  # no generated_md yet


def test_patch_job_posting_sets_dirty_after_generate(
    monkeypatch, auth_user, db_session, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/d", status_code=200, html="<p>x</p>", text="x" * 1000)
    payload = {"title": "Dev", "company": "Acme", "language": "en"}
    _eager_patch(monkeypatch, db_session, settings,
                 lambda m, s: json.dumps(payload) if s else "# Letter", fr)

    c, user = auth_user
    from app.db.models import AnschreibenVariant, CVVariant
    cv = db_session.query(CVVariant).filter_by(user_id=user.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=user.id).first()
    aid = c.post(
        "/api/applications",
        json={
            "url": "https://x.test/d",
            "cv_variant_id": str(cv.id),
            "anschreiben_variant_id": str(an.id),
        },
    ).json()["id"]
    c.post(f"/api/applications/{aid}/generate")
    r = c.patch(f"/api/applications/{aid}/job-posting", json={"title": "X"})
    assert r.status_code == 200
    assert r.json()["job_posting_dirty"] is True


def test_patch_job_posting_404_when_no_posting(monkeypatch, auth_user, db_session, tmp_path):
    """Pipeline still running, no JobPosting yet → 404."""
    # Make the fake LLM raise so extraction never completes
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/n", status_code=200, html="<p>x</p>", text="x" * 1000)

    def boom(m, s):
        raise RuntimeError("llm offline")

    _eager_patch(monkeypatch, db_session, settings, boom, fr)
    c, _ = auth_user
    # Eager mode propagates → use a dummy URL pre-existing instead by hitting create; failure is recorded
    try:
        c.post("/api/applications", json={"url": "https://x.test/n"})
    except Exception:
        pass
    # Find application id
    apps = c.get("/api/applications").json()
    aid = apps[0]["id"]
    r = c.patch(f"/api/applications/{aid}/job-posting", json={"title": "x"})
    assert r.status_code == 404
