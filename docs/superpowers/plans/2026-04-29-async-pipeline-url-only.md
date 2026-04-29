# Async Pipeline + URL-Only Intake — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow URL-only application creation, run the pipeline asynchronously via Celery + Redis as three independent stage tasks (crawl/extract/generate), and let users edit extracted fields and trigger generation explicitly from the frontend.

**Architecture:** A new `redis` container is the broker; a new `worker` container reuses the backend image to run Celery. The monolithic `app/pipeline.py` is split into pure-function modules plus three Celery task wrappers. Generation no longer chains to extraction; users trigger it via a new `POST /generate` endpoint. The frontend exposes optional variant pickers, inline editing of extracted fields, an explicit Generate button, and a "regenerate?" banner when fields change after generation.

**Tech Stack:** FastAPI + SQLAlchemy + Postgres (existing). Celery 5 + Redis 7 (new). Alembic migrations. React + react-query + Tailwind (existing).

**Spec:** `docs/superpowers/specs/2026-04-29-async-pipeline-url-only-design.md`

---

## File Structure

**Backend — new:**
- `backend/app/tasks/__init__.py`
- `backend/app/tasks/celery_app.py` — Celery factory
- `backend/app/tasks/pipeline.py` — `crawl_task`, `extract_task`, `generate_task`
- `backend/app/pipeline/__init__.py` — exports
- `backend/app/pipeline/crawl.py` — `run_crawl(db, app, fetcher, settings)`
- `backend/app/pipeline/extract.py` — `run_extract(db, app, llm)`
- `backend/app/pipeline/generate.py` — `run_generate(db, app, llm, settings)`
- `backend/app/pipeline/url_hash.py` — `url_hash(url: str) -> str` (moved from `app/pipeline.py`)
- `backend/alembic/versions/<rev>_async_pipeline.py`
- `backend/tests/unit/test_pipeline_crawl.py`
- `backend/tests/unit/test_pipeline_extract.py`
- `backend/tests/unit/test_pipeline_generate.py`
- `backend/tests/integration/test_tasks.py`
- `backend/tests/integration/test_generate_endpoint.py`
- `backend/tests/integration/test_jobposting_patch.py`
- `backend/tests/integration/test_variants_patch.py`

**Backend — delete:**
- `backend/app/pipeline.py` (replaced by package)

**Backend — modify:**
- `backend/app/config.py` — add `redis_url`, `celery_broker_url`, `celery_result_backend`
- `backend/app/db/models.py` — add `JobState.extracted`, nullable variant FKs, `failed_stage`, `job_posting_dirty`, `FailedStage` enum
- `backend/app/api/applications.py` — variants optional in create, drop default fallback, add new endpoints, retry routing, response shape
- `backend/pyproject.toml` — add `celery[redis]>=5.4`
- `backend/tests/integration/test_pipeline.py` — adapt to package layout
- `backend/tests/integration/test_applications.py` — patch new task path

**Infra:**
- `docker-compose.yml` — add `redis` service, `worker` service

**Frontend — modify:**
- `frontend/src/api/applications.ts` — types + new endpoints
- `frontend/src/components/AddApplicationForm.tsx` — optional variant pickers
- `frontend/src/components/JobPostingPanel.tsx` — editable fields with Save
- `frontend/src/components/StatusBadge.tsx` — `extracted` state + failed_stage suffix
- `frontend/src/pages/ApplicationDetail.tsx` — variants section, generate button, regenerate banner

**Frontend — tests:**
- `frontend/tests/e2e.spec.ts` — extend happy path

---

## Task 1: Add Celery + Redis to settings and dependencies

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/tests/integration/test_pipeline.py`
- Test: `backend/tests/unit/test_config.py`

- [ ] **Step 1: Run existing config test to baseline**

```
cd backend && pytest tests/unit/test_config.py -v
```

Expected: all pass.

- [ ] **Step 2: Add failing test for Celery settings**

Append to `backend/tests/unit/test_config.py`:

```python
def test_celery_defaults_use_redis_url(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    from app.config import Settings
    s = Settings()
    assert s.redis_url == "redis://redis:6379/0"
    assert s.celery_broker_url == "redis://redis:6379/0"
    assert s.celery_result_backend == "redis://redis:6379/0"


def test_celery_overrides(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://other:6379/1")
    from app.config import Settings
    s = Settings()
    assert s.celery_broker_url == "redis://other:6379/1"
```

- [ ] **Step 3: Run new tests — expect failure**

```
cd backend && pytest tests/unit/test_config.py::test_celery_defaults_use_redis_url -v
```

Expected: FAIL — `redis_url` attribute missing.

- [ ] **Step 4: Add fields to `Settings`**

In `backend/app/config.py`, add after `session_cookie_secure` line:

```python
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def _default_broker(cls, v, info):
        return v or info.data.get("redis_url")

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def _default_backend(cls, v, info):
        return v or info.data.get("redis_url")
```

- [ ] **Step 5: Add Celery dep to pyproject**

In `backend/pyproject.toml`, append to `dependencies`:

```toml
  "celery[redis]>=5.4",
```

Run `cd backend && uv lock` to refresh `uv.lock`.

- [ ] **Step 6: Inject `REDIS_URL` env into test fixtures**

In `backend/tests/conftest.py`, add after the existing `LLM_API_KEY` line:

```python
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
```

In `backend/tests/integration/conftest.py`, add the same line in the `app_client` fixture after `LLM_API_KEY`.

In `backend/tests/integration/test_pipeline.py`, add the same line inside `settings` fixture after `LLM_API_KEY`.

- [ ] **Step 7: Run config tests and confirm pass**

```
cd backend && pytest tests/unit/test_config.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/tests
git commit -m "feat(config): redis + celery settings"
```

---

## Task 2: Extend models with new state, FailedStage enum, and new columns

**Files:**
- Modify: `backend/app/db/models.py`
- Test: `backend/tests/integration/test_models.py`

- [ ] **Step 1: Read existing model tests**

```
cd backend && cat tests/integration/test_models.py
```

Note the patterns used; we'll follow them.

- [ ] **Step 2: Add failing test for new model fields**

Append to `backend/tests/integration/test_models.py`:

```python
def test_application_url_only_creation_persists(db_session):
    from app.db.models import (
        Application,
        FailedStage,
        JobState,
        User,
    )

    u = User(ms_oid="om", email="m@b.c", display_name="M")
    db_session.add(u)
    db_session.flush()
    app = Application(
        user_id=u.id,
        url="https://x.test/url-only",
        url_hash="h" * 64,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    assert app.cv_variant_id is None
    assert app.anschreiben_variant_id is None
    assert app.failed_stage is None
    assert app.job_posting_dirty is False
    assert app.job_state == JobState.pending


def test_jobstate_extracted_value_exists():
    from app.db.models import JobState

    assert JobState.extracted.value == "extracted"


def test_failed_stage_enum_values():
    from app.db.models import FailedStage

    assert {s.value for s in FailedStage} == {"crawl", "extract", "generate"}
```

- [ ] **Step 3: Run tests — expect failure**

```
cd backend && pytest tests/integration/test_models.py::test_failed_stage_enum_values -v
```

Expected: FAIL — `FailedStage` does not exist.

- [ ] **Step 4: Update `backend/app/db/models.py`**

Add `FailedStage` enum after `JobState`:

```python
class FailedStage(str, enum.Enum):
    crawl = "crawl"
    extract = "extract"
    generate = "generate"
```

Add `extracted` value to `JobState`:

```python
class JobState(str, enum.Enum):
    pending = "pending"
    crawling = "crawling"
    extracting = "extracting"
    extracted = "extracted"
    generating = "generating"
    ready = "ready"
    failed = "failed"
```

Replace these two `Application` columns:

```python
    cv_variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cv_variant.id"))
    anschreiben_variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anschreiben_variant.id")
    )
```

with:

```python
    cv_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_variant.id"), nullable=True
    )
    anschreiben_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("anschreiben_variant.id"), nullable=True
    )
```

Add new columns to `Application` (after `job_error`):

```python
    failed_stage: Mapped[FailedStage | None] = mapped_column(
        Enum(FailedStage), nullable=True
    )
    job_posting_dirty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
```

- [ ] **Step 5: Run tests — confirm pass**

```
cd backend && pytest tests/integration/test_models.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add backend/app/db/models.py backend/tests/integration/test_models.py
git commit -m "feat(models): nullable variants, extracted state, failed_stage, job_posting_dirty"
```

---

## Task 3: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<rev>_async_pipeline.py`

- [ ] **Step 1: Generate revision file**

```
cd backend && alembic revision -m "async pipeline url only"
```

Note the generated path (e.g., `alembic/versions/abc123_async_pipeline_url_only.py`).

- [ ] **Step 2: Replace generated body**

Open the new file and replace `upgrade()` and `downgrade()`:

```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    # 1. Make variant FKs nullable
    op.alter_column("application", "cv_variant_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column(
        "application", "anschreiben_variant_id", existing_type=sa.UUID(), nullable=True
    )

    # 2. Extend JobState enum (Postgres requires non-transactional ALTER TYPE)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE jobstate ADD VALUE IF NOT EXISTS 'extracted'")

    # 3. Create FailedStage enum
    failed_stage_enum = sa.Enum("crawl", "extract", "generate", name="failedstage")
    failed_stage_enum.create(op.get_bind(), checkfirst=True)

    # 4. Add new columns
    op.add_column(
        "application",
        sa.Column("failed_stage", failed_stage_enum, nullable=True),
    )
    op.add_column(
        "application",
        sa.Column(
            "job_posting_dirty",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Drop server_default once all rows have a value
    op.alter_column("application", "job_posting_dirty", server_default=None)


def downgrade() -> None:
    op.drop_column("application", "job_posting_dirty")
    op.drop_column("application", "failed_stage")
    sa.Enum(name="failedstage").drop(op.get_bind(), checkfirst=True)
    # Note: Postgres cannot drop a single enum value; jobstate retains 'extracted' on downgrade.
    op.alter_column(
        "application", "anschreiben_variant_id", existing_type=sa.UUID(), nullable=False
    )
    op.alter_column("application", "cv_variant_id", existing_type=sa.UUID(), nullable=False)
```

- [ ] **Step 3: Verify migration applies cleanly against a temp db**

```
cd backend && pytest tests/integration/test_models.py -v
```

Expected: all pass (testcontainers spins up fresh Postgres). The model-level test already exercises new columns.

- [ ] **Step 4: Commit**

```
git add backend/alembic/versions
git commit -m "feat(db): migration for async pipeline + url-only intake"
```

---

## Task 4: Split pipeline into pure-function package

**Files:**
- Create: `backend/app/pipeline/__init__.py`
- Create: `backend/app/pipeline/url_hash.py`
- Create: `backend/app/pipeline/crawl.py`
- Create: `backend/app/pipeline/extract.py`
- Create: `backend/app/pipeline/generate.py`
- Delete: `backend/app/pipeline.py`
- Test: `backend/tests/unit/test_pipeline_crawl.py`
- Test: `backend/tests/unit/test_pipeline_extract.py`
- Test: `backend/tests/unit/test_pipeline_generate.py`

- [ ] **Step 1: Write unit test for `run_crawl`**

Create `backend/tests/unit/test_pipeline_crawl.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

from app.crawler.httpx_fetcher import FetchResult
from app.db.models import Application, JobState
from app.pipeline.crawl import run_crawl
from tests.fakes.fetcher import FakeFetcher


def test_run_crawl_writes_raw_html_and_sets_state(tmp_path):
    fetcher = FakeFetcher(
        result=FetchResult(url="u", status_code=200, html="<html>hi</html>", text="hi")
    )
    settings = MagicMock(data_dir=str(tmp_path))
    db = MagicMock()
    app = Application(url="https://x.test/j", url_hash="h" * 64)
    app.id = __import__("uuid").uuid4()
    app.user_id = __import__("uuid").uuid4()
    app.job_state = JobState.pending

    raw_path, fetch_result = run_crawl(db, app, fetcher, settings)

    assert Path(raw_path).read_text() == "<html>hi</html>"
    assert fetch_result.text == "hi"
    assert app.job_state == JobState.crawling
    db.commit.assert_called()
```

- [ ] **Step 2: Run — expect failure**

```
cd backend && pytest tests/unit/test_pipeline_crawl.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `app/pipeline/url_hash.py`**

```python
import hashlib


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()
```

- [ ] **Step 4: Implement `app/pipeline/crawl.py`**

```python
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.crawler.fetcher import HybridFetcher
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import Application, JobState


def run_crawl(
    db: Session,
    app: Application,
    fetcher: HybridFetcher,
    settings: Settings,
) -> tuple[Path, FetchResult]:
    app.job_state = JobState.crawling
    db.commit()
    result = fetcher.fetch(app.url)
    raw_path = (
        Path(settings.data_dir)
        / str(app.user_id)
        / str(app.id)
        / "raw.html"
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(result.html, encoding="utf-8")
    return raw_path, result
```

- [ ] **Step 5: Run crawl test — expect pass**

```
cd backend && pytest tests/unit/test_pipeline_crawl.py -v
```

Expected: PASS.

- [ ] **Step 6: Write extract unit test**

Create `backend/tests/unit/test_pipeline_extract.py`:

```python
import json
import uuid
from unittest.mock import MagicMock

from app.crawler.httpx_fetcher import FetchResult
from app.db.models import Application, JobPosting, JobState
from app.pipeline.extract import run_extract
from tests.fakes.llm import FakeLLM


def test_run_extract_creates_jobposting_and_advances_state():
    payload = {
        "title": "Dev",
        "company": "Acme",
        "language": "en",
        "description": "build things",
        "requirements": "py",
        "tech_stack": ["python"],
    }
    db = MagicMock()
    app = Application(url="u", url_hash="h" * 64)
    app.id = uuid.uuid4()
    app.user_id = uuid.uuid4()
    app.job_state = JobState.crawling
    fetch_result = FetchResult(url="u", status_code=200, html="<p>x</p>", text="x" * 1000)

    captured = {}

    def add(obj):
        if isinstance(obj, JobPosting):
            captured["jp"] = obj

    db.add.side_effect = add
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    raw_path = "/tmp/raw.html"

    run_extract(db, app, fetch_result, raw_path, llm)

    assert app.job_state == JobState.extracted
    assert app.language == "en"
    assert captured["jp"].title == "Dev"
    assert captured["jp"].application_id == app.id
```

- [ ] **Step 7: Run — expect failure**

```
cd backend && pytest tests/unit/test_pipeline_extract.py -v
```

Expected: FAIL.

- [ ] **Step 8: Implement `app/pipeline/extract.py`**

```python
from pathlib import Path

from sqlalchemy.orm import Session

from app.crawler.httpx_fetcher import FetchResult
from app.db.models import Application, JobPosting, JobState
from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from app.llm.base import LLMClient


def run_extract(
    db: Session,
    app: Application,
    fetch_result: FetchResult,
    raw_path: Path | str,
    llm: LLMClient,
) -> None:
    app.job_state = JobState.extracting
    db.commit()
    if app.job_posting is not None:
        db.delete(app.job_posting)
        db.flush()
    job: ExtractedJobPosting = extract(fetch_result.text, llm)
    jp = JobPosting(
        application_id=app.id,
        raw_text=fetch_result.text[:200000],
        raw_html_path=str(raw_path),
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description,
        requirements=job.requirements,
        contact_person=job.contact_person,
        application_email=job.application_email,
        deadline=job.deadline,
        salary=job.salary,
        tech_stack=job.tech_stack,
        seniority=job.seniority,
        work_mode=job.work_mode,
        benefits=job.benefits,
        language=job.language,
    )
    app.language = job.language
    db.add(jp)
    app.job_state = JobState.extracted
    db.commit()
```

- [ ] **Step 9: Run extract test — expect pass**

```
cd backend && pytest tests/unit/test_pipeline_extract.py -v
```

Expected: PASS.

- [ ] **Step 10: Write generate unit test**

Create `backend/tests/unit/test_pipeline_generate.py`:

```python
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from app.db.models import (
    AnschreibenVariant,
    Application,
    CVVariant,
    JobPosting,
    JobState,
)
from app.pipeline.generate import run_generate
from tests.fakes.llm import FakeLLM


def test_run_generate_writes_md_and_docx(tmp_path):
    settings = MagicMock(data_dir=str(tmp_path))
    db = MagicMock()
    app = Application(url="u", url_hash="h" * 64)
    app.id = uuid.uuid4()
    app.user_id = uuid.uuid4()
    app.job_state = JobState.extracted
    cv_id, an_id = uuid.uuid4(), uuid.uuid4()
    app.cv_variant_id = cv_id
    app.anschreiben_variant_id = an_id
    app.job_posting_dirty = True
    app.job_posting = JobPosting(
        application_id=app.id,
        raw_text="x",
        title="Dev",
        language="en",
    )
    cv = CVVariant(id=cv_id, name="cv", source_md="cv md")
    an = AnschreibenVariant(id=an_id, name="an", source_md="an md")

    def fake_get(model, key):
        if model is CVVariant:
            return cv
        if model is AnschreibenVariant:
            return an
        return None

    db.get.side_effect = fake_get
    llm = FakeLLM(handler=lambda m, s: "# Dear hiring team")

    run_generate(db, app, llm, settings)

    assert app.job_state == JobState.ready
    assert app.generated_md.startswith("# Dear")
    assert Path(app.generated_docx_path).exists()
    assert app.job_posting_dirty is False
    assert app.failed_stage is None
```

- [ ] **Step 11: Run — expect failure**

```
cd backend && pytest tests/unit/test_pipeline_generate.py -v
```

Expected: FAIL.

- [ ] **Step 12: Implement `app/pipeline/generate.py`**

```python
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    AnschreibenVariant,
    Application,
    CVVariant,
    JobState,
)
from app.extractor.schemas import ExtractedJobPosting
from app.generator import generate
from app.llm.base import LLMClient
from app.renderer.docx import to_docx


def run_generate(
    db: Session,
    app: Application,
    llm: LLMClient,
    settings: Settings,
) -> None:
    if app.cv_variant_id is None or app.anschreiben_variant_id is None:
        raise RuntimeError("cv_variant_id and anschreiben_variant_id required")
    if app.job_posting is None:
        raise RuntimeError("job_posting missing — run extract first")
    cv = db.get(CVVariant, app.cv_variant_id)
    an = db.get(AnschreibenVariant, app.anschreiben_variant_id)
    if cv is None or an is None:
        raise RuntimeError("variant not found")

    app.job_state = JobState.generating
    db.commit()

    jp = app.job_posting
    job = ExtractedJobPosting(
        title=jp.title,
        company=jp.company,
        location=jp.location,
        description=jp.description,
        requirements=jp.requirements,
        contact_person=jp.contact_person,
        application_email=jp.application_email,
        deadline=jp.deadline,
        salary=jp.salary,
        tech_stack=jp.tech_stack,
        seniority=jp.seniority,
        work_mode=jp.work_mode,
        benefits=jp.benefits,
        language=jp.language,
    )
    md = generate(job, cv.source_md, an.source_md, jp.language, llm)
    app.generated_md = md

    docx_path = (
        Path(settings.data_dir)
        / str(app.user_id)
        / str(app.id)
        / "anschreiben.docx"
    )
    to_docx(md, docx_path)
    app.generated_docx_path = str(docx_path)

    app.job_state = JobState.ready
    app.job_posting_dirty = False
    app.failed_stage = None
    app.job_error = None
    db.commit()
```

- [ ] **Step 13: Implement `app/pipeline/__init__.py`**

```python
from app.pipeline.crawl import run_crawl
from app.pipeline.extract import run_extract
from app.pipeline.generate import run_generate
from app.pipeline.url_hash import url_hash

__all__ = ["run_crawl", "run_extract", "run_generate", "url_hash"]
```

- [ ] **Step 14: Delete `backend/app/pipeline.py`**

```
git rm backend/app/pipeline.py
```

- [ ] **Step 15: Run all unit pipeline tests**

```
cd backend && pytest tests/unit/test_pipeline_crawl.py tests/unit/test_pipeline_extract.py tests/unit/test_pipeline_generate.py -v
```

Expected: all pass.

- [ ] **Step 16: Commit**

```
git add backend/app/pipeline backend/tests/unit
git rm backend/app/pipeline.py
git commit -m "refactor(pipeline): split into pure-function package per stage"
```

Note: `app/api/applications.py` and `tests/integration/test_pipeline.py` still import the old monolithic `Pipeline`. They will break the test suite at this point. The next two tasks fix them.

---

## Task 5: Celery app + tasks

**Files:**
- Create: `backend/app/tasks/__init__.py`
- Create: `backend/app/tasks/celery_app.py`
- Create: `backend/app/tasks/pipeline.py`
- Test: `backend/tests/integration/test_tasks.py`

- [ ] **Step 1: Write integration test for the task chain (eager mode)**

Create `backend/tests/integration/test_tasks.py`:

```python
import json
import uuid
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
def settings_env(tmp_path, monkeypatch):
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
def eager(monkeypatch):
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


def _seed(db_session, with_variants: bool):
    u = User(ms_oid="ot", email="t@b.c", display_name="T")
    db_session.add(u)
    db_session.flush()
    cv_id = an_id = None
    if with_variants:
        cv = CVVariant(user_id=u.id, name="c", source_md="cv md", is_default=True)
        an = AnschreibenVariant(user_id=u.id, name="a", source_md="tpl md", is_default=True)
        db_session.add_all([cv, an])
        db_session.flush()
        cv_id, an_id = cv.id, an.id
    app = Application(
        user_id=u.id,
        url="https://x.test/j",
        url_hash=url_hash("https://x.test/j"),
        cv_variant_id=cv_id,
        anschreiben_variant_id=an_id,
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
    monkeypatch.setattr(tp, "_llm", lambda settings: FakeLLM(handler=llm_handler))
    monkeypatch.setattr(tp, "_fetcher", lambda: fetcher)


def test_chain_url_only_stops_at_extracted(eager, db_session, settings_env, monkeypatch):
    app = _seed(db_session, with_variants=False)
    fetcher = FakeFetcher(
        result=FetchResult(url=app.url, status_code=200, html="<p>x</p>", text="x" * 1000)
    )
    payload = {"title": "Dev", "company": "Acme", "language": "en"}
    _patch_factories(
        monkeypatch, db_session, settings_env,
        lambda m, s: json.dumps(payload), fetcher,
    )

    chain(crawl_task.s(str(app.id)), extract_task.s()).apply()

    db_session.refresh(app)
    assert app.job_state == JobState.extracted
    assert app.generated_md is None
    assert app.job_posting.title == "Dev"


def test_generate_task_completes_when_variants_set(
    eager, db_session, settings_env, monkeypatch
):
    app = _seed(db_session, with_variants=True)
    fetcher = FakeFetcher(
        result=FetchResult(url=app.url, status_code=200, html="<p>x</p>", text="x" * 1000)
    )
    payload = {"title": "Dev", "company": "Acme", "language": "en"}
    _patch_factories(
        monkeypatch, db_session, settings_env,
        lambda m, s: json.dumps(payload) if s else "# Letter", fetcher,
    )

    chain(crawl_task.s(str(app.id)), extract_task.s()).apply()
    generate_task.apply(args=[str(app.id)])

    db_session.refresh(app)
    assert app.job_state == JobState.ready
    assert app.generated_md.startswith("# Letter")
    assert Path(app.generated_docx_path).exists()


def test_crawl_failure_records_failed_stage(eager, db_session, settings_env, monkeypatch):
    app = _seed(db_session, with_variants=False)
    fetcher = FakeFetcher(error=RuntimeError("network down"))
    _patch_factories(
        monkeypatch, db_session, settings_env, lambda m, s: "{}", fetcher,
    )

    with pytest.raises(Exception):
        chain(crawl_task.s(str(app.id)), extract_task.s()).apply()

    db_session.refresh(app)
    assert app.job_state == JobState.failed
    assert app.failed_stage == FailedStage.crawl
    assert "network down" in app.job_error
```

- [ ] **Step 2: Run tests — expect failure**

```
cd backend && pytest tests/integration/test_tasks.py -v
```

Expected: FAIL — `app.tasks` does not exist.

- [ ] **Step 3: Implement `app/tasks/celery_app.py`**

```python
from celery import Celery

from app.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "applicator",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["app.tasks.pipeline"],
    )
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True
    app.conf.worker_prefetch_multiplier = 1
    return app


celery_app = make_celery()
```

- [ ] **Step 4: Implement `app/tasks/__init__.py`**

```python
from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
```

- [ ] **Step 5: Implement `app/tasks/pipeline.py`**

```python
from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.crawler.fetcher import HybridFetcher
from app.db.models import Application, FailedStage, JobState
from app.db.session import get_engine
from app.llm.base import LLMClient
from app.llm.groq import GroqClient
from app.pipeline import run_crawl, run_extract, run_generate
from app.tasks.celery_app import celery_app


# Indirection points for tests to override
def _db_factory() -> Callable[[], "contextmanager[Session]"]:
    factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)

    @contextmanager
    def cm() -> Session:
        s = factory()
        try:
            yield s
        finally:
            s.close()

    return cm


def _settings() -> Settings:
    return get_settings()


def _llm(settings: Settings) -> LLMClient:
    return GroqClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )


def _fetcher() -> HybridFetcher:
    return HybridFetcher()


def _record_failure(db: Session, app: Application, stage: FailedStage, exc: Exception) -> None:
    app.job_state = JobState.failed
    app.failed_stage = stage
    app.job_error = str(exc)[:1000]
    db.commit()


@celery_app.task(
    name="pipeline.crawl",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2, "countdown": 10},
)
def crawl_task(self, app_id: str) -> dict:
    settings = _settings()
    cm = _db_factory()
    with cm() as db:
        app = db.get(Application, uuid.UUID(app_id))
        if app is None:
            return {"app_id": app_id, "skipped": True}
        try:
            raw_path, fetch_result = run_crawl(db, app, _fetcher(), settings)
        except Exception as exc:
            db.rollback()
            with cm() as db2:
                app2 = db2.get(Application, uuid.UUID(app_id))
                if app2:
                    _record_failure(db2, app2, FailedStage.crawl, exc)
            raise
        return {
            "app_id": app_id,
            "raw_path": str(raw_path),
            "text": fetch_result.text,
            "html": fetch_result.html,
            "url": fetch_result.url,
            "status_code": fetch_result.status_code,
        }


@celery_app.task(name="pipeline.extract", bind=True)
def extract_task(self, payload: dict) -> dict:
    from app.crawler.httpx_fetcher import FetchResult

    if payload.get("skipped"):
        return payload
    app_id = payload["app_id"]
    settings = _settings()
    cm = _db_factory()
    fetch_result = FetchResult(
        url=payload["url"],
        status_code=payload["status_code"],
        html=payload["html"],
        text=payload["text"],
    )
    with cm() as db:
        app = db.get(Application, uuid.UUID(app_id))
        if app is None:
            return {"app_id": app_id, "skipped": True}
        try:
            run_extract(db, app, fetch_result, payload["raw_path"], _llm(settings))
        except Exception as exc:
            db.rollback()
            with cm() as db2:
                app2 = db2.get(Application, uuid.UUID(app_id))
                if app2:
                    _record_failure(db2, app2, FailedStage.extract, exc)
            raise
    return {"app_id": app_id}


@celery_app.task(name="pipeline.generate", bind=True)
def generate_task(self, app_id: str) -> dict:
    if isinstance(app_id, dict):  # chain payload
        app_id = app_id["app_id"]
    settings = _settings()
    cm = _db_factory()
    with cm() as db:
        app = db.get(Application, uuid.UUID(app_id))
        if app is None:
            return {"app_id": app_id, "skipped": True}
        try:
            run_generate(db, app, _llm(settings), settings)
        except Exception as exc:
            db.rollback()
            with cm() as db2:
                app2 = db2.get(Application, uuid.UUID(app_id))
                if app2:
                    _record_failure(db2, app2, FailedStage.generate, exc)
            raise
    return {"app_id": app_id}
```

- [ ] **Step 6: Run tests — expect pass**

```
cd backend && pytest tests/integration/test_tasks.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 7: Replace `tests/integration/test_pipeline.py` with task-based equivalents**

Replace the file body of `backend/tests/integration/test_pipeline.py` entirely:

```python
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
```

- [ ] **Step 8: Run pipeline tests**

```
cd backend && pytest tests/integration/test_pipeline.py -v
```

Expected: 2 pass.

- [ ] **Step 9: Commit**

```
git add backend/app/tasks backend/tests/integration/test_tasks.py backend/tests/integration/test_pipeline.py
git commit -m "feat(tasks): celery app + crawl/extract/generate stage tasks"
```

---

## Task 6: API — applications.create + ApplicationOut + retry routing

**Files:**
- Modify: `backend/app/api/applications.py`
- Modify: `backend/tests/integration/test_applications.py`

- [ ] **Step 1: Update `test_applications.py` patch helper**

Replace the body of `_patch_pipeline` (lines 13–39) in `backend/tests/integration/test_applications.py` with one that patches the task module instead. Replace lines 1–39:

```python
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
```

Also remove the `BackgroundTasks`-era helpers and `from app.api import applications as applications_api` import (no longer needed).

- [ ] **Step 2: Add failing test for URL-only happy path**

Add to `backend/tests/integration/test_applications.py`:

```python
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
```

Update the existing `test_create_runs_pipeline_and_lists` to send variants explicitly. Replace its body:

```python
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
```

Update `test_docx_download` and `test_status_patch` similarly: pass the variants in the create body and call `POST /generate` before asserting `has_docx` / downloading.

- [ ] **Step 3: Run — expect failure**

```
cd backend && pytest tests/integration/test_applications.py -v
```

Expected: failures (endpoints not built; create still requires defaults).

- [ ] **Step 4: Replace `app/api/applications.py`**

Rewrite `backend/app/api/applications.py`:

```python
import uuid
from pathlib import Path
from typing import Annotated

from celery import chain
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep, settings_dep
from app.config import Settings
from app.db.models import (
    AnschreibenVariant,
    Application,
    ApplicationStatus,
    CVVariant,
    FailedStage,
    JobPosting,
    JobState,
    User,
)
from app.pipeline import url_hash
from app.tasks.pipeline import crawl_task, extract_task, generate_task

router = APIRouter(prefix="/api/applications", tags=["applications"])

_RUNNING_STATES = {JobState.pending, JobState.crawling, JobState.extracting, JobState.generating}


class CreateApplication(BaseModel):
    url: HttpUrl
    cv_variant_id: uuid.UUID | None = None
    anschreiben_variant_id: uuid.UUID | None = None


class JobPostingOut(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact_person: str | None = None
    application_email: str | None = None
    deadline: str | None = None
    salary: str | None = None
    tech_stack: list[str] | None = None
    seniority: str | None = None
    work_mode: str | None = None
    benefits: list[str] | None = None
    language: str | None = None

    model_config = {"from_attributes": True}


class JobPostingPatch(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact_person: str | None = None
    application_email: str | None = None
    deadline: str | None = None
    salary: str | None = None
    tech_stack: list[str] | None = None
    seniority: str | None = None
    work_mode: str | None = None
    benefits: list[str] | None = None
    language: str | None = None


class VariantsPatch(BaseModel):
    cv_variant_id: uuid.UUID | None = None
    anschreiben_variant_id: uuid.UUID | None = None
    clear_cv: bool = False
    clear_anschreiben: bool = False


class ApplicationOut(BaseModel):
    id: uuid.UUID
    url: str
    status: ApplicationStatus
    job_state: JobState
    job_error: str | None
    failed_stage: FailedStage | None
    language: str | None
    generated_md: str | None
    has_docx: bool
    cv_variant_id: uuid.UUID | None
    anschreiben_variant_id: uuid.UUID | None
    job_posting_dirty: bool
    job_posting: JobPostingOut | None

    @classmethod
    def from_orm_row(cls, app: Application) -> "ApplicationOut":
        return cls(
            id=app.id,
            url=app.url,
            status=app.status,
            job_state=app.job_state,
            job_error=app.job_error,
            failed_stage=app.failed_stage,
            language=app.language,
            generated_md=app.generated_md,
            has_docx=app.generated_docx_path is not None,
            cv_variant_id=app.cv_variant_id,
            anschreiben_variant_id=app.anschreiben_variant_id,
            job_posting_dirty=app.job_posting_dirty,
            job_posting=(
                JobPostingOut.model_validate(app.job_posting) if app.job_posting else None
            ),
        )


def _check_variant_ownership(
    db: Session, variant_id: uuid.UUID | None, model, user: User, label: str
) -> uuid.UUID | None:
    if variant_id is None:
        return None
    row = db.query(model).filter_by(id=variant_id, user_id=user.id).first()
    if row is None:
        raise HTTPException(400, f"{label} not found or does not belong to current user")
    return row.id


def _start_crawl_chain(app_id: uuid.UUID) -> None:
    chain(crawl_task.s(str(app_id)), extract_task.s()).apply_async()


def _start_generate(app_id: uuid.UUID) -> None:
    generate_task.apply_async(args=[str(app_id)])


def _load_owned(db: Session, aid: uuid.UUID, user: User) -> Application:
    app = db.get(Application, aid)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "not found")
    return app


@router.post("", response_model=ApplicationOut, status_code=202)
def create(
    body: CreateApplication,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    cv_id = _check_variant_ownership(db, body.cv_variant_id, CVVariant, user, "cv_variant_id")
    an_id = _check_variant_ownership(
        db, body.anschreiben_variant_id, AnschreibenVariant, user, "anschreiben_variant_id"
    )
    h = url_hash(str(body.url))
    existing = db.query(Application).filter_by(user_id=user.id, url_hash=h).first()
    if existing:
        raise HTTPException(409, f"application already exists: {existing.id}")
    app_row = Application(
        user_id=user.id,
        url=str(body.url),
        url_hash=h,
        cv_variant_id=cv_id,
        anschreiben_variant_id=an_id,
    )
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    _start_crawl_chain(app_row.id)
    return ApplicationOut.from_orm_row(app_row)


@router.get("", response_model=list[ApplicationOut])
def list_apps(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    rows = (
        db.query(Application)
        .filter_by(user_id=user.id)
        .order_by(Application.created_at.desc())
        .all()
    )
    return [ApplicationOut.from_orm_row(r) for r in rows]


@router.get("/{aid}", response_model=ApplicationOut)
def get_app(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    return ApplicationOut.from_orm_row(_load_owned(db, aid, user))


class StatusUpdate(BaseModel):
    status: ApplicationStatus


@router.patch("/{aid}", response_model=ApplicationOut)
def update_status(
    aid: uuid.UUID,
    body: StatusUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    app_row.status = body.status
    db.commit()
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.patch("/{aid}/job-posting", response_model=ApplicationOut)
def patch_job_posting(
    aid: uuid.UUID,
    body: JobPostingPatch,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if app_row.job_state in {JobState.crawling, JobState.extracting, JobState.generating}:
        raise HTTPException(409, "pipeline running")
    if app_row.job_posting is None:
        raise HTTPException(404, "no job posting yet")
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(app_row.job_posting, k, v)
    if app_row.generated_md is not None and updates:
        app_row.job_posting_dirty = True
    db.commit()
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.patch("/{aid}/variants", response_model=ApplicationOut)
def patch_variants(
    aid: uuid.UUID,
    body: VariantsPatch,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if app_row.job_state == JobState.generating:
        raise HTTPException(409, "generation running")
    if body.cv_variant_id is not None:
        app_row.cv_variant_id = _check_variant_ownership(
            db, body.cv_variant_id, CVVariant, user, "cv_variant_id"
        )
    elif body.clear_cv:
        app_row.cv_variant_id = None
    if body.anschreiben_variant_id is not None:
        app_row.anschreiben_variant_id = _check_variant_ownership(
            db, body.anschreiben_variant_id, AnschreibenVariant, user, "anschreiben_variant_id"
        )
    elif body.clear_anschreiben:
        app_row.anschreiben_variant_id = None
    db.commit()
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.post("/{aid}/generate", response_model=ApplicationOut, status_code=202)
def generate_endpoint(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if not app_row.cv_variant_id or not app_row.anschreiben_variant_id:
        raise HTTPException(400, "cv_variant_id and anschreiben_variant_id required")
    if app_row.job_posting is None:
        raise HTTPException(400, "no job posting yet — run extraction first")
    allowed = {JobState.extracted, JobState.ready}
    if app_row.job_state == JobState.failed:
        if app_row.failed_stage != FailedStage.generate:
            raise HTTPException(409, "earlier stage failed — use /retry")
    elif app_row.job_state not in allowed:
        raise HTTPException(409, "pipeline busy")
    app_row.failed_stage = None
    app_row.job_error = None
    app_row.job_state = JobState.generating
    db.commit()
    db.refresh(app_row)
    _start_generate(app_row.id)
    return ApplicationOut.from_orm_row(app_row)


@router.post("/{aid}/retry", response_model=ApplicationOut)
def retry(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if app_row.job_state in _RUNNING_STATES and app_row.job_state != JobState.pending:
        raise HTTPException(409, "pipeline already running")

    failed_stage = app_row.failed_stage
    if app_row.job_state in (JobState.ready, JobState.extracted) or failed_stage in (
        FailedStage.crawl,
        None,
    ):
        if app_row.job_posting:
            db.delete(app_row.job_posting)
        app_row.generated_md = None
        app_row.generated_docx_path = None
        app_row.job_error = None
        app_row.failed_stage = None
        app_row.job_posting_dirty = False
        app_row.job_state = JobState.pending
        db.commit()
        db.refresh(app_row)
        _start_crawl_chain(app_row.id)
        return ApplicationOut.from_orm_row(app_row)

    if failed_stage == FailedStage.extract:
        # extract_task needs the crawl payload, which isn't persisted —
        # rerun the full crawl→extract chain.
        if app_row.job_posting:
            db.delete(app_row.job_posting)
        app_row.job_error = None
        app_row.failed_stage = None
        app_row.job_posting_dirty = False
        app_row.job_state = JobState.pending
        db.commit()
        db.refresh(app_row)
        _start_crawl_chain(app_row.id)
        return ApplicationOut.from_orm_row(app_row)

    # failed_stage == generate
    if not app_row.cv_variant_id or not app_row.anschreiben_variant_id:
        raise HTTPException(400, "cannot retry generate without variants")
    app_row.job_error = None
    app_row.failed_stage = None
    app_row.job_state = JobState.generating
    db.commit()
    db.refresh(app_row)
    _start_generate(app_row.id)
    return ApplicationOut.from_orm_row(app_row)


@router.get("/{aid}/docx")
def download_docx(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if not app_row.generated_docx_path or not Path(app_row.generated_docx_path).exists():
        raise HTTPException(404, "docx not ready")
    return FileResponse(
        app_row.generated_docx_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename="anschreiben.docx",
    )
```

- [ ] **Step 5: Run application tests**

```
cd backend && pytest tests/integration/test_applications.py -v
```

Expected: all updated tests pass.

- [ ] **Step 6: Commit**

```
git add backend/app/api/applications.py backend/tests/integration/test_applications.py
git commit -m "feat(api): url-only create, generate endpoint, retry routing, response shape"
```

---

## Task 7: API tests for new endpoints (PATCH /job-posting, PATCH /variants, POST /generate)

**Files:**
- Create: `backend/tests/integration/test_jobposting_patch.py`
- Create: `backend/tests/integration/test_variants_patch.py`
- Create: `backend/tests/integration/test_generate_endpoint.py`

- [ ] **Step 1: Write `test_jobposting_patch.py`**

```python
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
```

- [ ] **Step 2: Write `test_variants_patch.py`**

```python
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
```

- [ ] **Step 3: Write `test_generate_endpoint.py`**

```python
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
```

- [ ] **Step 4: Run new tests**

```
cd backend && pytest tests/integration/test_jobposting_patch.py tests/integration/test_variants_patch.py tests/integration/test_generate_endpoint.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full backend suite**

```
cd backend && pytest -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add backend/tests/integration/test_jobposting_patch.py backend/tests/integration/test_variants_patch.py backend/tests/integration/test_generate_endpoint.py
git commit -m "test(api): cover job-posting/variants/generate endpoints"
```

---

## Task 8: Docker compose — redis + worker services

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md`

- [ ] **Step 1: Replace `docker-compose.yml` body**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: applicator
      POSTGRES_USER: applicator
      POSTGRES_PASSWORD: applicator
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U applicator -d applicator"]
      interval: 2s
      timeout: 3s
      retries: 20

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 3s
      retries: 20

  api:
    build: ./backend
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://applicator:applicator@db:5432/applicator
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./data:/app/data
    command: ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

  worker:
    build: ./backend
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://applicator:applicator@db:5432/applicator
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./data:/app/data
    command: ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=2"]

  web:
    build: ./frontend
    depends_on: [api]
    ports: ["8080:80"]

volumes:
  pgdata:
```

- [ ] **Step 2: Update `README.md`**

In the Run-locally section, add note after the existing override list item:

```markdown
   - `REDIS_URL` defaults to `redis://redis:6379/0` under compose.
```

- [ ] **Step 3: Smoke-test compose**

```
docker compose up --build -d
docker compose ps
docker compose logs worker --tail=30
docker compose down
```

Expected: `worker` logs include `celery@... ready.`

- [ ] **Step 4: Commit**

```
git add docker-compose.yml README.md
git commit -m "feat(infra): redis broker + celery worker service"
```

---

## Task 9: Frontend API client + types

**Files:**
- Modify: `frontend/src/api/applications.ts`

- [ ] **Step 1: Replace file body**

```ts
import { api } from "./client";

export type AppStatus = "draft" | "applied" | "offer" | "rejected" | "accepted" | "withdrawn";
export type JobState =
  | "pending"
  | "crawling"
  | "extracting"
  | "extracted"
  | "generating"
  | "ready"
  | "failed";
export type FailedStage = "crawl" | "extract" | "generate";

export type JobPosting = {
  title: string | null;
  company: string | null;
  location: string | null;
  description: string | null;
  requirements: string | null;
  contact_person: string | null;
  application_email: string | null;
  deadline: string | null;
  salary: string | null;
  tech_stack: string[] | null;
  seniority: string | null;
  work_mode: string | null;
  benefits: string[] | null;
  language: string | null;
};

export type Application = {
  id: string;
  url: string;
  status: AppStatus;
  job_state: JobState;
  job_error: string | null;
  failed_stage: FailedStage | null;
  language: string | null;
  generated_md: string | null;
  has_docx: boolean;
  cv_variant_id: string | null;
  anschreiben_variant_id: string | null;
  job_posting_dirty: boolean;
  job_posting: JobPosting | null;
};

export type CreateApplicationBody = {
  url: string;
  cv_variant_id?: string | null;
  anschreiben_variant_id?: string | null;
};

export type VariantsPatchBody = {
  cv_variant_id?: string;
  anschreiben_variant_id?: string;
  clear_cv?: boolean;
  clear_anschreiben?: boolean;
};

export const applications = {
  list: () => api<Application[]>("/api/applications"),
  get: (id: string) => api<Application>(`/api/applications/${id}`),
  create: (body: CreateApplicationBody) =>
    api<Application>("/api/applications", { method: "POST", body: JSON.stringify(body) }),
  setStatus: (id: string, status: AppStatus) =>
    api<Application>(`/api/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  patchJobPosting: (id: string, fields: Partial<JobPosting>) =>
    api<Application>(`/api/applications/${id}/job-posting`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    }),
  patchVariants: (id: string, body: VariantsPatchBody) =>
    api<Application>(`/api/applications/${id}/variants`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  generate: (id: string) =>
    api<Application>(`/api/applications/${id}/generate`, { method: "POST" }),
  retry: (id: string) =>
    api<Application>(`/api/applications/${id}/retry`, { method: "POST" }),
  docxUrl: (id: string) => `/api/applications/${id}/docx`,
};
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors. If callers of `applications.create(url)` (string) exist, they will fail compilation — fix them in the next task.

- [ ] **Step 3: Commit**

```
git add frontend/src/api/applications.ts
git commit -m "feat(fe-api): typed shape + new endpoints"
```

---

## Task 10: AddApplicationForm with optional variant pickers

**Files:**
- Modify: `frontend/src/components/AddApplicationForm.tsx`
- Reference: `frontend/src/api/documents.ts` (variant listing API; check for existing hook)

- [ ] **Step 1: Note existing variant API shape**

`frontend/src/api/documents.ts` exports `cv` and `anschreiben`, each with a `list()` returning `Variant[]` where `Variant = {id, name, source_md, is_default}`.

- [ ] **Step 2: Replace `AddApplicationForm.tsx`**

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";
import { cv as cvApi, anschreiben as anApi } from "../api/documents";

export function AddApplicationForm() {
  const [url, setUrl] = useState("");
  const [cvId, setCvId] = useState<string>("");
  const [anId, setAnId] = useState<string>("");
  const qc = useQueryClient();

  const cvs = useQuery({ queryKey: ["cv-variants"], queryFn: () => cvApi.list() });
  const ans = useQuery({ queryKey: ["an-variants"], queryFn: () => anApi.list() });

  const m = useMutation({
    mutationFn: () =>
      applications.create({
        url: url.trim(),
        cv_variant_id: cvId || undefined,
        anschreiben_variant_id: anId || undefined,
      }),
    onSuccess: () => {
      setUrl("");
      setCvId("");
      setAnId("");
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });

  return (
    <form
      className="grid gap-2 mb-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (url.trim()) m.mutate();
      }}
    >
      <input
        type="url"
        required
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste job posting URL"
        className="border rounded px-3 py-2"
      />
      <div className="grid grid-cols-2 gap-2">
        <select
          value={cvId}
          onChange={(e) => setCvId(e.target.value)}
          className="border rounded px-3 py-2"
        >
          <option value="">CV — skip, add later</option>
          {(cvs.data ?? []).map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
        <select
          value={anId}
          onChange={(e) => setAnId(e.target.value)}
          className="border rounded px-3 py-2"
        >
          <option value="">Anschreiben — skip, add later</option>
          {(ans.data ?? []).map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={m.isPending}
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          Add
        </button>
        {m.isError && (
          <span className="text-rose-600">{(m.error as Error).message}</span>
        )}
      </div>
    </form>
  );
}
```

- [ ] **Step 3: Compile and lint**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors. If `documents.listCV` / `listAnschreiben` names differ, adjust to match what's exported from `frontend/src/api/documents.ts`.

- [ ] **Step 4: Commit**

```
git add frontend/src/components/AddApplicationForm.tsx
git commit -m "feat(fe): optional cv/anschreiben pickers in add form"
```

---

## Task 11: Editable JobPostingPanel

**Files:**
- Modify: `frontend/src/components/JobPostingPanel.tsx`

- [ ] **Step 1: Replace file body**

```tsx
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { JobPosting } from "../api/applications";
import { applications } from "../api/applications";

type Props = {
  appId: string;
  jp: JobPosting | null;
  disabled: boolean;
};

const TEXT_FIELDS: Array<{ key: keyof JobPosting; label: string; multiline?: boolean }> = [
  { key: "title", label: "Title" },
  { key: "company", label: "Company" },
  { key: "location", label: "Location" },
  { key: "work_mode", label: "Work mode" },
  { key: "seniority", label: "Seniority" },
  { key: "salary", label: "Salary" },
  { key: "deadline", label: "Deadline" },
  { key: "contact_person", label: "Contact" },
  { key: "application_email", label: "Email" },
  { key: "language", label: "Language" },
  { key: "requirements", label: "Requirements", multiline: true },
  { key: "description", label: "Description", multiline: true },
];

const LIST_FIELDS: Array<{ key: keyof JobPosting; label: string }> = [
  { key: "tech_stack", label: "Tech stack (comma-separated)" },
  { key: "benefits", label: "Benefits (comma-separated)" },
];

export function JobPostingPanel({ appId, jp, disabled }: Props) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Partial<JobPosting>>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (jp) {
      setDraft({});
      setDirty(false);
    }
  }, [jp?.title, jp?.company]);

  const save = useMutation({
    mutationFn: () => applications.patchJobPosting(appId, draft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", appId] });
      setDraft({});
      setDirty(false);
    },
  });

  if (!jp) return <div className="text-slate-500">Awaiting extraction…</div>;

  const update = (key: keyof JobPosting, value: unknown) => {
    setDraft((d) => ({ ...d, [key]: value }));
    setDirty(true);
  };

  const value = <K extends keyof JobPosting>(key: K): JobPosting[K] =>
    (draft[key] !== undefined ? draft[key] : jp[key]) as JobPosting[K];

  return (
    <div>
      {TEXT_FIELDS.map((f) => (
        <div className="mb-3" key={f.key}>
          <label className="block text-xs uppercase text-slate-500">{f.label}</label>
          {f.multiline ? (
            <textarea
              className="border rounded px-2 py-1 w-full"
              rows={4}
              disabled={disabled}
              value={(value(f.key) as string | null) ?? ""}
              onChange={(e) => update(f.key, e.target.value || null)}
            />
          ) : (
            <input
              className="border rounded px-2 py-1 w-full"
              disabled={disabled}
              value={(value(f.key) as string | null) ?? ""}
              onChange={(e) => update(f.key, e.target.value || null)}
            />
          )}
        </div>
      ))}
      {LIST_FIELDS.map((f) => (
        <div className="mb-3" key={f.key}>
          <label className="block text-xs uppercase text-slate-500">{f.label}</label>
          <input
            className="border rounded px-2 py-1 w-full"
            disabled={disabled}
            value={((value(f.key) as string[] | null) ?? []).join(", ")}
            onChange={(e) =>
              update(
                f.key,
                e.target.value
                  ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                  : null,
              )
            }
          />
        </div>
      ))}
      <button
        type="button"
        disabled={!dirty || disabled || save.isPending}
        onClick={() => save.mutate()}
        className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
      >
        Save changes
      </button>
      {save.isError && (
        <span className="text-rose-600 ml-2 text-sm">
          {(save.error as Error).message}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update caller in `ApplicationDetail.tsx`**

In `frontend/src/pages/ApplicationDetail.tsx`, replace the `<JobPostingPanel jp={a.job_posting} />` line with:

```tsx
<JobPostingPanel
  appId={a.id}
  jp={a.job_posting}
  disabled={["crawling", "extracting", "generating"].includes(a.job_state)}
/>
```

- [ ] **Step 3: Compile**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```
git add frontend/src/components/JobPostingPanel.tsx frontend/src/pages/ApplicationDetail.tsx
git commit -m "feat(fe): editable job posting fields with save"
```

---

## Task 12: Variants picker, Generate button, regenerate banner, status updates

**Files:**
- Modify: `frontend/src/pages/ApplicationDetail.tsx`
- Modify: `frontend/src/components/StatusBadge.tsx`

- [ ] **Step 1: Update `StatusBadge.tsx`**

Replace `JOB_STATE_LABEL` and `JobStateBadge`:

```tsx
const JOB_STATE_LABEL: Record<JobState, string> = {
  pending: "Queued",
  crawling: "Crawling…",
  extracting: "Extracting…",
  extracted: "Extracted",
  generating: "Generating…",
  ready: "Ready",
  failed: "Failed",
};

export function JobStateBadge({
  state,
  failedStage,
}: {
  state: JobState;
  failedStage?: FailedStage | null;
}) {
  const cls =
    state === "ready"
      ? "bg-emerald-100 text-emerald-700"
      : state === "failed"
        ? "bg-rose-100 text-rose-700"
        : state === "extracted"
          ? "bg-sky-100 text-sky-700"
          : "bg-amber-100 text-amber-700";
  const label =
    state === "failed" && failedStage
      ? `Failed (${failedStage})`
      : JOB_STATE_LABEL[state];
  return <span className={`px-2 py-0.5 rounded text-xs ${cls}`}>{label}</span>;
}
```

Add `FailedStage` to the existing `import type` line:

```tsx
import type { AppStatus, FailedStage, JobState } from "../api/applications";
```

- [ ] **Step 2: Replace `ApplicationDetail.tsx` body (full file)**

```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";
import type { AppStatus } from "../api/applications";
import { cv as cvApi, anschreiben as anApi } from "../api/documents";
import { JobPostingPanel } from "../components/JobPostingPanel";
import { AnschreibenEditor } from "../components/AnschreibenEditor";
import { ChatPanel } from "../components/ChatPanel";
import { InterviewsList } from "../components/InterviewsList";
import { JobStateBadge, StatusBadge } from "../components/StatusBadge";

const STATUSES: AppStatus[] = ["draft", "applied", "offer", "rejected", "accepted", "withdrawn"];

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["application", id],
    queryFn: () => applications.get(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const a = query.state.data;
      if (!a) return false;
      return ["pending", "crawling", "extracting", "generating"].includes(a.job_state)
        ? 2000
        : false;
    },
  });
  const cvs = useQuery({ queryKey: ["cv-variants"], queryFn: () => cvApi.list() });
  const ans = useQuery({ queryKey: ["an-variants"], queryFn: () => anApi.list() });

  const [md, setMd] = useState("");
  useEffect(() => {
    if (q.data?.generated_md != null) setMd(q.data.generated_md);
  }, [q.data?.generated_md]);

  const setStatus = useMutation({
    mutationFn: (s: AppStatus) => applications.setStatus(id!, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });
  const retry = useMutation({
    mutationFn: () => applications.retry(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });
  const setVariants = useMutation({
    mutationFn: (b: { cv_variant_id?: string; clear_cv?: boolean;
                       anschreiben_variant_id?: string; clear_anschreiben?: boolean }) =>
      applications.patchVariants(id!, b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });
  const generate = useMutation({
    mutationFn: () => applications.generate(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });

  if (q.isLoading || !q.data) return <div className="p-6">Loading…</div>;
  const a = q.data;
  const running = ["pending", "crawling", "extracting", "generating"].includes(a.job_state);
  const canGenerate =
    !!a.cv_variant_id &&
    !!a.anschreiben_variant_id &&
    !!a.job_posting &&
    (a.job_state === "extracted" ||
      a.job_state === "ready" ||
      (a.job_state === "failed" && a.failed_stage === "generate"));

  return (
    <div className="p-6 grid grid-cols-2 gap-6 max-w-7xl mx-auto">
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h1 className="text-xl font-semibold flex-1 truncate">
            {a.job_posting?.title ?? a.url}
          </h1>
          <JobStateBadge state={a.job_state} failedStage={a.failed_stage} />
          <StatusBadge status={a.status} />
        </div>

        {a.job_state === "failed" && (
          <div className="bg-rose-50 border border-rose-200 p-3 rounded mb-3">
            <div className="text-rose-700 text-sm mb-2">
              Failed at {a.failed_stage}: {a.job_error}
            </div>
            <button
              onClick={() => retry.mutate()}
              className="bg-rose-600 text-white px-3 py-1 rounded"
            >
              Retry
            </button>
          </div>
        )}

        {a.job_posting_dirty && a.generated_md && (
          <div className="bg-amber-50 border border-amber-200 p-3 rounded mb-3 flex items-center justify-between">
            <span className="text-amber-800 text-sm">
              Job info changed — regenerate the Anschreiben?
            </span>
            <button
              onClick={() => generate.mutate()}
              disabled={!canGenerate || generate.isPending}
              className="bg-amber-600 text-white px-3 py-1 rounded disabled:opacity-50"
            >
              Regenerate
            </button>
          </div>
        )}

        <div className="bg-white border rounded p-3">
          <JobPostingPanel appId={a.id} jp={a.job_posting} disabled={running} />
        </div>

        <div className="mt-4 grid gap-2">
          <div className="grid grid-cols-2 gap-2">
            <select
              value={a.cv_variant_id ?? ""}
              disabled={a.job_state === "generating"}
              onChange={(e) =>
                setVariants.mutate(
                  e.target.value
                    ? { cv_variant_id: e.target.value }
                    : { clear_cv: true },
                )
              }
              className="border rounded px-2 py-1"
            >
              <option value="">CV — none</option>
              {(cvs.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
            <select
              value={a.anschreiben_variant_id ?? ""}
              disabled={a.job_state === "generating"}
              onChange={(e) =>
                setVariants.mutate(
                  e.target.value
                    ? { anschreiben_variant_id: e.target.value }
                    : { clear_anschreiben: true },
                )
              }
              className="border rounded px-2 py-1"
            >
              <option value="">Anschreiben — none</option>
              {(ans.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            disabled={!canGenerate || generate.isPending}
            onClick={() => generate.mutate()}
            className="bg-blue-600 text-white px-3 py-2 rounded disabled:opacity-50"
            title={
              !a.cv_variant_id || !a.anschreiben_variant_id
                ? "Pick a CV and an Anschreiben variant"
                : !a.job_posting
                  ? "Awaiting extraction"
                  : ""
            }
          >
            {a.generated_md ? "Regenerate Anschreiben" : "Generate Anschreiben"}
          </button>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <span>Status:</span>
          <select
            value={a.status}
            onChange={(e) => setStatus.mutate(e.target.value as AppStatus)}
            className="border rounded px-2 py-1"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <InterviewsList appId={a.id} />
      </div>
      <div>
        {a.generated_md != null ? (
          <>
            <AnschreibenEditor appId={a.id} md={md} onChange={setMd} hasDocx={a.has_docx} />
            <ChatPanel appId={a.id} />
          </>
        ) : (
          <div className="text-slate-500">
            {a.job_state === "extracted"
              ? "Pick variants and click Generate to produce the Anschreiben."
              : "Anschreiben pending…"}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Compile**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Manual smoke check**

```
cd frontend && npm run dev
```

Open the app, log in, add an application URL only, watch state become `extracted`, edit a field, attach variants, click Generate, confirm DOCX downloads.

- [ ] **Step 5: Commit**

```
git add frontend/src/pages/ApplicationDetail.tsx frontend/src/components/StatusBadge.tsx
git commit -m "feat(fe): variants picker, generate button, regenerate banner, extracted state"
```

---

## Task 13: E2E test — URL-only flow

**Files:**
- Modify: `frontend/tests/e2e.spec.ts`

- [ ] **Step 1: Find existing e2e file**

```
ls frontend/tests
```

Read the current e2e spec to learn the mock-API pattern used. This task assumes a Playwright spec under `frontend/tests/e2e.spec.ts` (per recent commits) that mocks `/api/applications/*`.

- [ ] **Step 2: Add new spec block**

Append the following test to `frontend/tests/e2e.spec.ts` (adapt route mocks to match the pattern already used in the file):

```ts
test("URL-only add → edit → generate", async ({ page }) => {
  // 1. POST /api/applications returns extracted state
  await page.route("**/api/applications", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          id: "app-1",
          url: "https://x.test/j",
          status: "draft",
          job_state: "extracted",
          job_error: null,
          failed_stage: null,
          language: "en",
          generated_md: null,
          has_docx: false,
          cv_variant_id: null,
          anschreiben_variant_id: null,
          job_posting_dirty: false,
          job_posting: { title: "Dev", company: "Acme", language: "en",
            location: null, description: null, requirements: null,
            contact_person: null, application_email: null, deadline: null,
            salary: null, tech_stack: null, seniority: null, work_mode: null,
            benefits: null },
        }),
      });
      return;
    }
    await route.continue();
  });

  // 2. GET /api/applications/app-1 returns extracted application
  await page.route("**/api/applications/app-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "app-1",
        url: "https://x.test/j",
        status: "draft",
        job_state: "extracted",
        job_error: null,
        failed_stage: null,
        language: "en",
        generated_md: null,
        has_docx: false,
        cv_variant_id: null,
        anschreiben_variant_id: null,
        job_posting_dirty: false,
        job_posting: { title: "Dev", company: "Acme", language: "en",
          location: null, description: null, requirements: null,
          contact_person: null, application_email: null, deadline: null,
          salary: null, tech_stack: null, seniority: null, work_mode: null,
          benefits: null },
      }),
    });
  });

  await page.goto("/");
  await page.fill('input[type="url"]', "https://x.test/j");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Extracted")).toBeVisible();
  await expect(page.getByLabel("Title")).toHaveValue("Dev");
});
```

- [ ] **Step 3: Run e2e**

```
cd frontend && npx playwright test
```

Expected: pass.

- [ ] **Step 4: Commit**

```
git add frontend/tests/e2e.spec.ts
git commit -m "test(e2e): url-only intake flow"
```

---

## Task 14: Final verification + cleanup

- [ ] **Step 1: Run full backend suite**

```
cd backend && pytest -v
```

Expected: all pass.

- [ ] **Step 2: Run frontend type-check + lint**

```
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: no errors. (If `npm run lint` is not configured, skip silently.)

- [ ] **Step 3: Run e2e**

```
cd frontend && npx playwright test
```

Expected: pass.

- [ ] **Step 4: docker compose smoke**

```
docker compose up --build -d
docker compose logs worker --tail=30 | grep "celery@"
docker compose down
```

Expected: worker logs include `ready.`

- [ ] **Step 5: Final commit if anything changed**

```
git status
```

If clean, no commit. Otherwise commit per change.

---
