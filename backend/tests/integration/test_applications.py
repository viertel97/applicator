import json

from app.api import applications as applications_api
from app.config import Settings
from app.crawler.httpx_fetcher import FetchResult
from app.pipeline import Pipeline
from tests.fakes.fetcher import FakeFetcher
from tests.fakes.llm import FakeLLM


def _patch_pipeline(monkeypatch, db_session, settings, llm_handler, fetcher_result):
    from contextlib import contextmanager

    from sqlalchemy.orm import sessionmaker

    engine = db_session.get_bind()
    fetcher = FakeFetcher(result=fetcher_result)

    def fake_kickoff(bg, app_id, s):
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        @contextmanager
        def factory():
            ses = session_factory()
            try:
                yield ses
            finally:
                ses.close()

        Pipeline(
            db_factory=factory,
            llm=FakeLLM(handler=llm_handler),
            settings=settings,
            fetcher=fetcher,
        ).run(app_id)

    monkeypatch.setattr(applications_api, "_kickoff", fake_kickoff)


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

    c, _ = auth_user
    r = c.post("/api/applications", json={"url": "https://x.test/j"})
    assert r.status_code == 202, r.text
    aid = r.json()["id"]
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
    c, _ = auth_user
    aid = c.post("/api/applications", json={"url": "https://x.test/j"}).json()["id"]
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
    c, _ = auth_user
    aid = c.post("/api/applications", json={"url": "https://x.test/j"}).json()["id"]
    r = c.get(f"/api/applications/{aid}/docx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml"
    )
