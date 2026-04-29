import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import (
    AnschreibenVariant,
    Application,
    CVVariant,
    JobState,
    User,
)
from app.pipeline import Pipeline, url_hash
from tests.fakes.fetcher import FakeFetcher
from tests.fakes.llm import FakeLLM


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "k")
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return Settings()


def _seed(db_session):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u)
    db_session.flush()
    cv = CVVariant(user_id=u.id, name="c", source_md="cv md", is_default=True)
    an = AnschreibenVariant(user_id=u.id, name="a", source_md="tpl md", is_default=True)
    db_session.add_all([cv, an])
    db_session.flush()
    app = Application(
        user_id=u.id,
        url="https://x.test/job",
        url_hash=url_hash("https://x.test/job"),
        cv_variant_id=cv.id,
        anschreiben_variant_id=an.id,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


@contextmanager
def _session_cm(engine):
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


def test_pipeline_happy_path(db_session, settings, tmp_path):
    app = _seed(db_session)
    fetcher = FakeFetcher(
        result=FetchResult(
            url=app.url,
            status_code=200,
            html="<html>x</html>",
            text="x" * 1000,
        )
    )
    job_payload = {
        "title": "Dev",
        "company": "Acme",
        "language": "en",
        "description": "Build",
        "requirements": "Py",
        "tech_stack": ["python"],
    }

    def llm_handler(messages, schema):
        if schema is not None:
            return json.dumps(job_payload)
        return "# Anschreiben\n\nDear hiring team..."

    engine = db_session.get_bind()

    p = Pipeline(
        db_factory=lambda: _session_cm(engine),
        llm=FakeLLM(handler=llm_handler),
        settings=settings,
        fetcher=fetcher,
    )
    p.run(app.id)

    db_session.refresh(app)
    assert app.job_state == JobState.ready
    assert app.generated_md.startswith("# Anschreiben")
    assert Path(app.generated_docx_path).exists()
    assert app.language == "en"


def test_pipeline_records_failure(db_session, settings):
    app = _seed(db_session)
    fetcher = FakeFetcher(error=RuntimeError("network down"))
    engine = db_session.get_bind()
    p = Pipeline(
        db_factory=lambda: _session_cm(engine),
        llm=FakeLLM(handler=lambda m, s: "{}"),
        settings=settings,
        fetcher=fetcher,
    )
    p.run(app.id)
    db_session.refresh(app)
    assert app.job_state == JobState.failed
    assert "network down" in app.job_error
