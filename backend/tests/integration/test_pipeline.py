import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from celery import chain
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import (
    AnschreibenVariant,
    Application,
    CVVariant,
    FailedStage,
    JobState,
    User,
)
from app.pipeline import url_hash
from app.tasks.celery_app import celery_app
from app.tasks.pipeline import crawl_task, extract_task, generate_task
from tests.fakes.fetcher import FakeFetcher
from tests.fakes.llm import FakeLLM


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    return Settings()


@pytest.fixture
def eager():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


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


def _patch_factories(monkeypatch, db_session, settings, llm_handler, fetcher):
    from app.tasks import pipeline as tp

    engine = db_session.get_bind()

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


def test_pipeline_happy_path(eager, db_session, settings, tmp_path, monkeypatch):
    app = _seed(db_session)
    fetcher = FakeFetcher(
        result=FetchResult(url=app.url, status_code=200, html="<p>x</p>", text="x" * 1000)
    )
    job_payload = {
        "title": "Dev", "company": "Acme", "language": "en",
        "description": "Build", "requirements": "Py", "tech_stack": ["python"],
    }

    def llm_handler(messages, schema):
        return json.dumps(job_payload) if schema is not None else "# Anschreiben"

    _patch_factories(monkeypatch, db_session, settings, llm_handler, fetcher)

    chain(crawl_task.s(str(app.id)), extract_task.s()).apply()
    generate_task.apply(args=[str(app.id)])

    db_session.refresh(app)
    assert app.job_state == JobState.ready
    assert app.generated_md.startswith("# Anschreiben")
    assert Path(app.generated_docx_path).exists()
    assert app.language == "en"


def test_pipeline_records_failure(eager, db_session, settings, monkeypatch):
    app = _seed(db_session)
    fetcher = FakeFetcher(error=RuntimeError("network down"))
    _patch_factories(
        monkeypatch, db_session, settings, lambda m, s: "{}", fetcher,
    )
    with pytest.raises(Exception):
        chain(crawl_task.s(str(app.id)), extract_task.s()).apply()
    db_session.refresh(app)
    assert app.job_state == JobState.failed
    assert app.failed_stage == FailedStage.crawl
    assert "network down" in app.job_error
