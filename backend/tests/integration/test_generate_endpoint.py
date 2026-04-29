import json
from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import AnschreibenVariant, CVVariant
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


def test_generate_400_without_variants(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/g", status_code=200, html="<p>x</p>", text="x" * 1000)
    _eager_patch(monkeypatch, db_session, settings,
                 lambda m, s: '{"language":"en"}' if s else "letter", fr)

    c, _ = auth_user
    aid = c.post("/api/applications", json={"url": "https://x.test/g"}).json()["id"]
    r = c.post(f"/api/applications/{aid}/generate")
    assert r.status_code == 400


def test_generate_happy_path(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/h", status_code=200, html="<p>x</p>", text="x" * 1000)
    _eager_patch(monkeypatch, db_session, settings,
                 lambda m, s: '{"title":"Dev","language":"en"}' if s else "# Letter", fr)

    c, user = auth_user
    cv = db_session.query(CVVariant).filter_by(user_id=user.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=user.id).first()
    aid = c.post(
        "/api/applications",
        json={
            "url": "https://x.test/h",
            "cv_variant_id": str(cv.id),
            "anschreiben_variant_id": str(an.id),
        },
    ).json()["id"]

    r = c.post(f"/api/applications/{aid}/generate")
    assert r.status_code == 202
    assert r.json()["job_state"] == "ready"  # eager mode runs synchronously
    assert r.json()["has_docx"] is True
