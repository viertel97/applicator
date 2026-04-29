import json
from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import AnschreibenVariant, CVVariant, User
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


def test_patch_variants_attaches_and_clears(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/v", status_code=200, html="<p>x</p>", text="x" * 1000)
    payload = {"title": "Dev", "company": "A", "language": "en"}
    _eager_patch(monkeypatch, db_session, settings,
                 lambda m, s: json.dumps(payload), fr)

    c, user = auth_user
    aid = c.post("/api/applications", json={"url": "https://x.test/v"}).json()["id"]
    cv = db_session.query(CVVariant).filter_by(user_id=user.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=user.id).first()

    r = c.patch(
        f"/api/applications/{aid}/variants",
        json={"cv_variant_id": str(cv.id), "anschreiben_variant_id": str(an.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["cv_variant_id"] == str(cv.id)

    r = c.patch(f"/api/applications/{aid}/variants", json={"clear_cv": True})
    assert r.status_code == 200
    assert r.json()["cv_variant_id"] is None


def test_patch_variants_rejects_other_users_variant(
    monkeypatch, auth_user, db_session, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/o", status_code=200, html="<p>x</p>", text="x" * 1000)
    _eager_patch(monkeypatch, db_session, settings,
                 lambda m, s: '{"language":"en"}', fr)

    c, _ = auth_user
    aid = c.post("/api/applications", json={"url": "https://x.test/o"}).json()["id"]

    other = User(ms_oid="oo", email="o@b.c", display_name="O")
    db_session.add(other)
    db_session.flush()
    other_cv = CVVariant(user_id=other.id, name="cv2", source_md="cv2")
    db_session.add(other_cv)
    db_session.commit()

    r = c.patch(
        f"/api/applications/{aid}/variants",
        json={"cv_variant_id": str(other_cv.id)},
    )
    assert r.status_code == 400
