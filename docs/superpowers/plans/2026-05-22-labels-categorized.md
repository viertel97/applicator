# Categorized Labels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group every `Label` under a fixed category enum, drive the extractor to emit per-category label lists, categorize the ~45 legacy labels on worker startup, and group chips by category in the UI filter and detail view.

**Architecture:** New `LabelCategory` enum + `Label.category` non-null column with server default `other`. Extractor schema replaces flat `suggested_labels: list[str]` with a structured `LabelSuggestions` (per-category fields). A shared `app/labels/upsert.py` module is the single write path for pipeline, backfill, and the new categorization task. Backfill is split into a `app/tasks/backfill/` package along the way. UI: filter uses collapsible `<details>` per category with localStorage state; detail view groups chips by category; LabelEditor requires a category dropdown on create.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Celery + Redis, Pydantic, Groq, React + TanStack Query, Vite.

---

## File Structure

**Backend — create:**
- `backend/app/labels/__init__.py` (empty)
- `backend/app/labels/upsert.py` — `upsert_and_assign_labels(db, app, suggestions)` (single write path)
- `backend/app/labels/categorize.py` — batch LLM categorizer for legacy labels
- `backend/app/tasks/backfill/` (package replacing `app/tasks/backfill.py`)
  - `__init__.py` — re-exports
  - `task.py` — celery task + Redis lock
  - `processor.py` — `pick_missing`, `process_row`, `_is_empty`, `ELIGIBLE_FIELDS`
  - `pacing.py` — `_adaptive_sleep` + thresholds
  - `query.py` — `_candidate_query`, `_db`, `_run`
- `backend/app/tasks/categorize_labels.py` — Celery task wrapping the categorizer
- `backend/alembic/versions/d2e3f4a5b6c7_label_category.py`
- Tests (one each):
  - `backend/tests/unit/test_label_category_enum.py`
  - `backend/tests/unit/test_label_suggestions_schema.py`
  - `backend/tests/unit/test_label_upsert.py`
  - `backend/tests/unit/test_label_categorizer.py`
  - `backend/tests/integration/test_label_category_migration.py`
  - `backend/tests/integration/test_categorize_labels_task.py`
  - `backend/tests/integration/test_label_api_category.py`

**Backend — modify:**
- `backend/app/db/models.py` — `LabelCategory` enum, `Label.category` column
- `backend/app/extractor/schemas.py` — `LabelSuggestions`, replace flat `suggested_labels`
- `backend/app/extractor/prompts.py` — adjust `SYSTEM` for per-category label emission
- `backend/app/pipeline/extract.py` — drop local `_upsert_and_assign_labels`, import shared
- `backend/app/api/labels.py` — `category` on `LabelOut`/`LabelCreate`, new `LabelPatch`, sorted listing
- `backend/app/main.py` — enqueue `tasks.categorize_existing_labels` from lifespan
- `backend/tests/integration/test_backfill.py` — adjust to new upsert signature

**Backend — delete:**
- `backend/app/tasks/backfill.py` (replaced by package)

**Frontend — create:**
- `frontend/src/components/LabelChipGroups.tsx` — chips bunched by category

**Frontend — modify:**
- `frontend/src/api/labels.ts` — add `category` field + PATCH client
- `frontend/src/api/applications.ts` — `Label` type gets `category`
- `frontend/src/components/LabelEditor.tsx` — required category dropdown
- `frontend/src/components/LabelFilter.tsx` (or wherever the filter chips render — adapt path; the list page already has the filter) — collapsible sections + localStorage
- `frontend/src/pages/ApplicationDetail.tsx` — render `LabelChipGroups` instead of flat chip row
- `frontend/tests/e2e.spec.ts` — extend with category UX

---

## Task 1: `LabelCategory` enum on the model

**Files:**
- Modify: `backend/app/db/models.py`
- Test: `backend/tests/unit/test_label_category_enum.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_label_category_enum.py`:

```python
from app.db.models import LabelCategory


def test_label_category_members_exact():
    expected = [
        "role",
        "tech",
        "domain",
        "seniority",
        "work_mode",
        "location",
        "company_size",
        "language",
        "company",
        "other",
    ]
    assert [m.value for m in LabelCategory] == expected


def test_label_category_string_backed():
    assert LabelCategory.tech.value == "tech"
    assert str(LabelCategory.tech) == "LabelCategory.tech"
```

- [ ] **Step 2: Run test, verify failure**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_label_category_enum.py -v
```
Expected: `ImportError: cannot import name 'LabelCategory'`.

- [ ] **Step 3: Add the enum**

In `backend/app/db/models.py`, find the existing enum block (search for `class ChatRole(str, enum.Enum):`) and add immediately after it:

```python
class LabelCategory(str, enum.Enum):
    role = "role"
    tech = "tech"
    domain = "domain"
    seniority = "seniority"
    work_mode = "work_mode"
    location = "location"
    company_size = "company_size"
    language = "language"
    company = "company"
    other = "other"
```

- [ ] **Step 4: Run test, verify pass**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_label_category_enum.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/unit/test_label_category_enum.py
git commit -m "feat(db): LabelCategory enum"
```

---

## Task 2: `Label.category` column

**Files:**
- Modify: `backend/app/db/models.py`
- Test: `backend/tests/unit/test_models_shape.py` (extend)

- [ ] **Step 1: Extend the failing test**

Append to `backend/tests/unit/test_models_shape.py`:

```python
def test_label_has_category_column():
    from app.db.models import Label, LabelCategory
    cols = {c.name for c in Label.__table__.columns}
    assert "category" in cols
    col = Label.__table__.columns["category"]
    assert col.nullable is False
    # server_default carries the literal string, not the enum member
    assert col.server_default is not None
    assert "other" in str(col.server_default.arg)


def test_label_default_instance_category_other():
    from app.db.models import Label, LabelCategory
    label = Label(name="x", color="#fff")
    # Python-side default flows from the column default; we explicitly test
    # by reading the default expression
    assert Label.__table__.columns["category"].default.arg is LabelCategory.other
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_models_shape.py -v
```
Expected: FAIL — `category` not in cols.

- [ ] **Step 3: Add the column**

In `backend/app/db/models.py`, locate `class Label(Base):` (around line 97) and add a `category` column right after the `is_auto` line:

```python
    category: Mapped["LabelCategory"] = mapped_column(
        Enum(LabelCategory, name="labelcategory"),
        nullable=False,
        default=LabelCategory.other,
        server_default=LabelCategory.other.value,
    )
```

`Enum` is already imported at the top of the file; `LabelCategory` was defined in Task 1.

- [ ] **Step 4: Run, verify pass**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_models_shape.py -v
```
Expected: previous 3 + 2 new = 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/unit/test_models_shape.py
git commit -m "feat(db): Label.category column with 'other' server default"
```

---

## Task 3: Alembic migration for `label.category`

**Files:**
- Create: `backend/alembic/versions/d2e3f4a5b6c7_label_category.py`
- Test: `backend/tests/integration/test_label_category_migration.py`

- [ ] **Step 1: Check current head**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/alembic heads
```
Expected: `c1d2e3f4a5b6` (head).

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/d2e3f4a5b6c7_label_category.py`:

```python
"""label category column

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-22 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LABEL_CATEGORY_VALUES = (
    "role",
    "tech",
    "domain",
    "seniority",
    "work_mode",
    "location",
    "company_size",
    "language",
    "company",
    "other",
)


def upgrade() -> None:
    label_category = sa.Enum(*_LABEL_CATEGORY_VALUES, name="labelcategory")
    label_category.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "label",
        sa.Column(
            "category",
            label_category,
            nullable=False,
            server_default="other",
        ),
    )


def downgrade() -> None:
    op.drop_column("label", "category")
    sa.Enum(name="labelcategory").drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 3: Write migration round-trip test**

Create `backend/tests/integration/test_label_category_migration.py`:

```python
"""Alembic round-trip for the label.category column."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


PRIOR_REVISION = "c1d2e3f4a5b6"
CATEGORY_REVISION = "d2e3f4a5b6c7"


def _alembic_cfg(url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def fresh_db(pg_container, monkeypatch):
    raw_url = pg_container.get_connection_url()
    url = (
        raw_url
        .replace("postgresql+psycopg2://", "postgresql+psycopg://")
        .replace("postgresql://", "postgresql+psycopg://")
    )
    monkeypatch.setenv("DATABASE_URL", url)
    engine = sa.create_engine(url, future=True, isolation_level="AUTOCOMMIT")

    def _wipe():
        with engine.connect() as conn:
            conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(sa.text("CREATE SCHEMA public"))

    _wipe()
    yield engine, url
    _wipe()
    engine.dispose()


def test_migration_adds_category_with_other_default(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))

    command.upgrade(cfg, PRIOR_REVISION)

    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO label (id, name, color, is_auto, created_at) "
            "VALUES (gen_random_uuid(), 'Legacy', '#fff', true, now())"
        ))

    command.upgrade(cfg, CATEGORY_REVISION)

    with engine.connect() as conn:
        cat = conn.execute(sa.text(
            "SELECT category FROM label WHERE name='Legacy'"
        )).scalar_one()
        assert cat == "other"


def test_migration_downgrade_drops_column(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))

    command.upgrade(cfg, CATEGORY_REVISION)
    command.downgrade(cfg, PRIOR_REVISION)

    with engine.connect() as conn:
        cols = {
            r[0] for r in conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='label'"
            ))
        }
        assert "category" not in cols
```

- [ ] **Step 4: Run**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_label_category_migration.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/d2e3f4a5b6c7_label_category.py backend/tests/integration/test_label_category_migration.py
git commit -m "feat(db): migration for label.category column"
```

---

## Task 4: Refactor `app/tasks/backfill.py` into a package

No behavior change. Pure reorganization. Existing tests in `backend/tests/integration/test_backfill.py` and `backend/tests/unit/test_lifespan.py` must keep passing with their current imports.

**Files:**
- Create: `backend/app/tasks/backfill/__init__.py`
- Create: `backend/app/tasks/backfill/task.py`
- Create: `backend/app/tasks/backfill/processor.py`
- Create: `backend/app/tasks/backfill/pacing.py`
- Create: `backend/app/tasks/backfill/query.py`
- Delete: `backend/app/tasks/backfill.py`

- [ ] **Step 1: Run existing backfill tests to confirm green baseline**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_backfill.py tests/unit/test_lifespan.py -v
```
Expected: green (current code).

- [ ] **Step 2: Create `processor.py`**

`backend/app/tasks/backfill/processor.py`:

```python
"""Per-row backfill logic: which fields are missing, and how to write them."""

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.db.models import JobPosting
from app.extractor import extract_fields
from app.pipeline.extract import _upsert_and_assign_labels

logger = logging.getLogger(__name__)

ELIGIBLE_FIELDS = [
    "contact",
    "salary",
    "deadline",
    "tech_stack",
    "benefits",
    "required_documents",
    "work_mode",
    "seniority",
    "requirements",
    "description",
]
SUGGESTED_LABELS = "suggested_labels"


ExtractFn = Callable[[str, list[str], object], dict]


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def pick_missing(jp: JobPosting) -> list[str]:
    attempted = set(jp.backfill_attempts or {})
    missing = [
        f for f in ELIGIBLE_FIELDS
        if _is_empty(getattr(jp, f)) and f not in attempted
    ]
    if SUGGESTED_LABELS not in attempted and len(jp.application.labels) == 0:
        missing.append(SUGGESTED_LABELS)
    return missing


def process_row(
    db: Session,
    jp: JobPosting,
    llm,
    extract_fn: ExtractFn = extract_fields,
) -> None:
    missing = pick_missing(jp)
    if not missing:
        return
    try:
        result = extract_fn(jp.raw_text, missing, llm)
    except Exception as exc:
        logger.warning("backfill LLM call failed for jp=%s: %s", jp.id, exc)
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    attempts = dict(jp.backfill_attempts or {})

    for field in missing:
        new_value = result.get(field)
        if field == SUGGESTED_LABELS:
            if not _is_empty(new_value):
                _upsert_and_assign_labels(db, jp.application, new_value)
        elif not _is_empty(new_value) and _is_empty(getattr(jp, field)):
            setattr(jp, field, new_value)
        attempts[field] = now_iso
    jp.backfill_attempts = attempts
    db.commit()
```

- [ ] **Step 3: Create `pacing.py`**

`backend/app/tasks/backfill/pacing.py`:

```python
"""Adaptive inter-row pacing driven by Groq rate-limit headers."""

import time

_LOW_REMAINING_FRACTION = 0.10
_MAX_ADAPTIVE_SLEEP_S = 60.0


def _adaptive_sleep(llm) -> None:
    last = getattr(llm, "last_rate_limit", None)
    if not callable(last):
        return
    rl = last()
    if rl is None:
        return
    if (
        rl.remaining_tokens is None
        or not rl.limit_tokens
        or rl.reset_tokens_s is None
    ):
        return
    if rl.remaining_tokens / rl.limit_tokens >= _LOW_REMAINING_FRACTION:
        return
    time.sleep(min(rl.reset_tokens_s + 0.5, _MAX_ADAPTIVE_SLEEP_S))
```

- [ ] **Step 4: Create `query.py`**

`backend/app/tasks/backfill/query.py`:

```python
"""Candidate selection and run loop for the backfill task."""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from app.db.models import Application, JobPosting
from app.db.session import get_session_factory

from .pacing import _adaptive_sleep
from .processor import pick_missing, process_row


@contextmanager
def _db() -> Iterator[Session]:
    s = get_session_factory()()
    try:
        yield s
    finally:
        s.close()


def _candidate_query(db: Session):
    return (
        db.query(JobPosting)
        .join(Application, Application.id == JobPosting.application_id)
        .filter(Application.deleted_at.is_(None))
        .filter(JobPosting.raw_text.isnot(None))
        .order_by(JobPosting.extracted_at.asc())
    )


def _run(llm) -> dict:
    processed = skipped = 0
    with _db() as db:
        ids = [jp.id for jp in _candidate_query(db).all()]
    for jp_id in ids:
        with _db() as db:
            jp = db.get(JobPosting, jp_id)
            if jp is None:
                skipped += 1
                continue
            missing = pick_missing(jp)
            if not missing:
                skipped += 1
                continue
            process_row(db, jp, llm)
            processed += 1
        _adaptive_sleep(llm)
    return {"processed": processed, "skipped": skipped, "total": len(ids)}
```

- [ ] **Step 5: Create `task.py`**

`backend/app/tasks/backfill/task.py`:

```python
"""Celery entrypoint for the on-startup backfill."""

import logging

import redis

from app.config import get_settings
from app.llm.groq import GroqClient
from app.tasks.celery_app import celery_app

from .query import _run

logger = logging.getLogger(__name__)

_LOCK_KEY = "backfill:lock"
_LOCK_TTL = 3600


@celery_app.task(name="tasks.backfill_missing")
def backfill_missing_task() -> dict:
    settings = get_settings()
    redis_url = getattr(settings, "redis_url", None) or settings.celery_broker_url
    client = redis.Redis.from_url(redis_url)
    lock = client.lock(_LOCK_KEY, timeout=_LOCK_TTL, blocking_timeout=0)
    if not lock.acquire(blocking=False):
        logger.info("backfill_missing: another run holds the lock; skipping")
        return {"status": "skipped_locked"}
    try:
        llm = GroqClient(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )
        return _run(llm)
    finally:
        try:
            lock.release()
        except Exception:
            logger.warning("backfill_missing: failed to release lock")
```

- [ ] **Step 6: Create `__init__.py` re-exporting the public API**

`backend/app/tasks/backfill/__init__.py`:

```python
"""On-startup backfill: fills empty JobPosting fields and auto-labels via Groq."""

from .pacing import _adaptive_sleep
from .processor import (
    ELIGIBLE_FIELDS,
    SUGGESTED_LABELS,
    pick_missing,
    process_row,
)
from .task import backfill_missing_task

__all__ = [
    "ELIGIBLE_FIELDS",
    "SUGGESTED_LABELS",
    "_adaptive_sleep",
    "backfill_missing_task",
    "pick_missing",
    "process_row",
]
```

- [ ] **Step 7: Delete the old module**

```bash
rm backend/app/tasks/backfill.py
```

- [ ] **Step 8: Run all related tests**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_backfill.py tests/unit/test_lifespan.py -v
```
Expected: same count as before, all green. `from app.tasks.backfill import ...` keeps working because of `__init__.py`.

- [ ] **Step 9: Commit**

```bash
git add backend/app/tasks/backfill backend/app/tasks/backfill.py
git commit -m "refactor(tasks): split backfill.py into a package"
```

(`git add backend/app/tasks/backfill.py` records the deletion.)

---

## Task 5: `LabelSuggestions` structured extractor schema

**Files:**
- Modify: `backend/app/extractor/schemas.py`
- Modify: `backend/app/extractor/prompts.py`
- Test: `backend/tests/unit/test_label_suggestions_schema.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_label_suggestions_schema.py`:

```python
from app.extractor.schemas import ExtractedJobPosting, LabelSuggestions


def test_label_suggestions_defaults_all_empty_lists():
    s = LabelSuggestions()
    for field in (
        "role", "tech", "domain", "seniority", "work_mode",
        "location", "company_size", "language", "company",
    ):
        assert getattr(s, field) == []


def test_label_suggestions_has_no_other_field():
    fields = LabelSuggestions.model_fields
    assert "other" not in fields


def test_extracted_job_posting_uses_label_suggestions():
    j = ExtractedJobPosting(language="de")
    assert isinstance(j.suggested_labels, LabelSuggestions)
    assert j.suggested_labels.tech == []
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_label_suggestions_schema.py -v
```
Expected: ImportError for `LabelSuggestions`.

- [ ] **Step 3: Edit `backend/app/extractor/schemas.py`**

Add `LabelSuggestions` above `ExtractedJobPosting`:

```python
class LabelSuggestions(BaseModel):
    role: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    domain: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    company_size: list[str] = Field(
        default_factory=list,
        description="Exactly one of Startup, KMU, Mittelstand, Konzern when determinable.",
    )
    language: list[str] = Field(default_factory=list)
    company: list[str] = Field(default_factory=list)
```

In `ExtractedJobPosting`, replace the existing `suggested_labels` field:

```python
    suggested_labels: LabelSuggestions = Field(default_factory=LabelSuggestions)
```

Remove the `_LABEL_CANDIDATES` constant — no longer referenced.

- [ ] **Step 4: Update the SYSTEM prompt**

In `backend/app/extractor/prompts.py`, locate the `SYSTEM = (` block and replace the `For suggested_labels …` sentence with:

```
For suggested_labels, place each label under the matching category
field: role, tech, domain, seniority, work_mode, location,
company_size, language, company. Leave a category empty if nothing
fits. Pick exactly one company_size bucket
(Startup/KMU/Mittelstand/Konzern) when determinable from explicit
headcount or general knowledge of the named company.
```

- [ ] **Step 5: Run tests**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_label_suggestions_schema.py tests/unit/test_extractor.py -v
```
Expected: 3 new pass; existing `test_extractor.py` passes (it doesn't exercise suggested_labels content).

- [ ] **Step 6: Commit**

```bash
git add backend/app/extractor/schemas.py backend/app/extractor/prompts.py backend/tests/unit/test_label_suggestions_schema.py
git commit -m "feat(extractor): structured LabelSuggestions per category"
```

---

## Task 6: Shared `upsert_and_assign_labels` in `app/labels/upsert.py`

**Files:**
- Create: `backend/app/labels/__init__.py` (empty)
- Create: `backend/app/labels/upsert.py`
- Modify: `backend/app/pipeline/extract.py` (drop local, import shared)
- Modify: `backend/app/tasks/backfill/processor.py` (import shared)
- Test: `backend/tests/unit/test_label_upsert.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_label_upsert.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.db.models import LabelCategory
from app.extractor.schemas import LabelSuggestions


def _stub_app():
    """Application stub: only `.labels` matters for the test."""
    app = MagicMock()
    app.labels = []
    return app


class _StubLabel:
    def __init__(self, name, category):
        self.name = name
        self.category = category


def test_upsert_creates_labels_with_correct_category(monkeypatch):
    from app.labels import upsert as upsert_mod

    created: list[tuple[str, LabelCategory]] = []
    by_name: dict[str, _StubLabel] = {}

    def fake_get_or_create(_db, name, category):
        if name not in by_name:
            by_name[name] = _StubLabel(name, category)
            created.append((name, category))
        return by_name[name]

    monkeypatch.setattr(upsert_mod, "_get_or_create_label", fake_get_or_create)

    app = _stub_app()
    sug = LabelSuggestions(
        role=["AI Engineer"],
        tech=["Python", "AWS"],
        company_size=["Konzern"],
    )
    upsert_mod.upsert_and_assign_labels(MagicMock(), app, sug)

    assert ("AI Engineer", LabelCategory.role) in created
    assert ("Python", LabelCategory.tech) in created
    assert ("AWS", LabelCategory.tech) in created
    assert ("Konzern", LabelCategory.company_size) in created
    assert len(app.labels) == 4


def test_upsert_preserves_existing_category(monkeypatch):
    from app.labels import upsert as upsert_mod

    existing = _StubLabel("Python", LabelCategory.tech)
    by_name = {"Python": existing}

    def fake_get_or_create(_db, name, category):
        # existing match: do not change category
        return by_name.get(name) or _StubLabel(name, category)

    monkeypatch.setattr(upsert_mod, "_get_or_create_label", fake_get_or_create)

    app = _stub_app()
    sug = LabelSuggestions(role=["Python"])
    upsert_mod.upsert_and_assign_labels(MagicMock(), app, sug)

    assert existing.category == LabelCategory.tech  # not flipped to role


def test_upsert_idempotent_for_already_assigned(monkeypatch):
    from app.labels import upsert as upsert_mod

    existing = _StubLabel("Konzern", LabelCategory.company_size)

    def fake_get_or_create(_db, name, category):
        return existing

    monkeypatch.setattr(upsert_mod, "_get_or_create_label", fake_get_or_create)

    app = _stub_app()
    app.labels.append(existing)
    sug = LabelSuggestions(company_size=["Konzern"])
    upsert_mod.upsert_and_assign_labels(MagicMock(), app, sug)
    assert app.labels.count(existing) == 1


def test_upsert_accepts_dict_payload(monkeypatch):
    """Backfill hands in the raw LLM dict before pydantic validation."""
    from app.labels import upsert as upsert_mod

    monkeypatch.setattr(
        upsert_mod, "_get_or_create_label",
        lambda _db, name, category: _StubLabel(name, category),
    )

    app = _stub_app()
    upsert_mod.upsert_and_assign_labels(
        MagicMock(), app,
        {"tech": ["Python"], "role": ["Engineer"]},
    )
    names = {lab.name for lab in app.labels}
    assert names == {"Python", "Engineer"}
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_label_upsert.py -v
```
Expected: ImportError — `app.labels` doesn't exist yet.

- [ ] **Step 3: Create `app/labels/__init__.py`** (empty file)

```bash
mkdir -p backend/app/labels && : > backend/app/labels/__init__.py
```

- [ ] **Step 4: Create `app/labels/upsert.py`**

```python
"""Single write path for category-tagged labels.

Called by the extractor pipeline, the backfill processor, and any
future code that needs to attach labels to an Application.
"""

from typing import Mapping

from sqlalchemy.orm import Session

from app.db.models import Application, Label, LabelCategory
from app.extractor.schemas import LabelSuggestions

_AUTO_LABEL_COLOR = "#6366f1"


def _get_or_create_label(
    db: Session, name: str, category: LabelCategory
) -> Label:
    label = db.query(Label).filter_by(name=name).first()
    if label is None:
        label = Label(name=name, color=_AUTO_LABEL_COLOR, is_auto=True, category=category)
        db.add(label)
        db.flush()
    return label


def upsert_and_assign_labels(
    db: Session,
    app: Application,
    suggestions: LabelSuggestions | Mapping[str, list[str]],
) -> None:
    """Create any missing labels, then attach them to ``app``.

    Existing labels keep their category — a later extraction that
    classifies the same name differently does **not** overwrite the
    first classification.

    Accepts either a ``LabelSuggestions`` instance (pipeline path) or a
    plain dict keyed by category name (backfill receives the raw LLM
    output as a dict via ``extract_fields``).
    """
    if isinstance(suggestions, LabelSuggestions):
        items = suggestions.model_dump()
    else:
        items = dict(suggestions or {})

    for category_name, names in items.items():
        if not names:
            continue
        try:
            category = LabelCategory(category_name)
        except ValueError:
            # Unknown category from a misbehaving LLM payload — skip.
            continue
        for name in names:
            if not name:
                continue
            label = _get_or_create_label(db, name, category)
            if label not in app.labels:
                app.labels.append(label)
```

- [ ] **Step 5: Update `app/pipeline/extract.py`**

Replace the local `_upsert_and_assign_labels` and its single call site. Final file:

```python
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Application, JobPosting, JobState
from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from app.labels.upsert import upsert_and_assign_labels
from app.llm.base import LLMClient


def run_extract(
    db: Session,
    app: Application,
    text: str,
    raw_path: Path | str,
    llm: LLMClient,
) -> None:
    app.job_state = JobState.extracting
    db.commit()
    if app.job_posting is not None:
        db.delete(app.job_posting)
        db.flush()
    job: ExtractedJobPosting = extract(text, llm)
    jp = JobPosting(
        application_id=app.id,
        raw_text=text[:200000],
        raw_html_path=str(raw_path),
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description,
        requirements=job.requirements,
        contact=job.contact.model_dump() if job.contact else None,
        deadline=job.deadline,
        salary=job.salary,
        tech_stack=job.tech_stack,
        seniority=job.seniority,
        work_mode=job.work_mode,
        benefits=job.benefits,
        language=job.language,
        required_documents=job.required_documents,
    )
    app.language = job.language
    db.add(jp)
    upsert_and_assign_labels(db, app, job.suggested_labels)
    app.job_state = JobState.extracted
    db.commit()
```

- [ ] **Step 6: Update `app/tasks/backfill/processor.py`**

Replace the import and the routing block:

```python
from app.labels.upsert import upsert_and_assign_labels
```

(Remove `from app.pipeline.extract import _upsert_and_assign_labels`.)

In `process_row`, change the SUGGESTED_LABELS branch:

```python
        if field == SUGGESTED_LABELS:
            if not _is_empty(new_value):
                upsert_and_assign_labels(db, jp.application, new_value)
```

- [ ] **Step 7: Run all touched tests**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_label_upsert.py tests/integration/test_backfill.py tests/integration/test_pipeline_contact.py -v
```
Expected: green.

- [ ] **Step 8: Commit**

```bash
git add backend/app/labels backend/app/pipeline/extract.py backend/app/tasks/backfill/processor.py backend/tests/unit/test_label_upsert.py
git commit -m "feat(labels): shared category-aware upsert module"
```

---

## Task 7: Batch categorizer for legacy `other` labels

**Files:**
- Create: `backend/app/labels/categorize.py`
- Test: `backend/tests/unit/test_label_categorizer.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_label_categorizer.py`:

```python
import json
from unittest.mock import MagicMock

from app.db.models import LabelCategory


def test_categorize_returns_name_to_category_map():
    from app.labels.categorize import categorize_names

    llm = MagicMock()
    llm.complete.return_value = json.dumps({
        "Python": "tech",
        "Frankfurt": "location",
        "Senior": "seniority",
        "Konzern": "company_size",
    })
    result = categorize_names(["Python", "Frankfurt", "Senior", "Konzern"], llm)
    assert result == {
        "Python": LabelCategory.tech,
        "Frankfurt": LabelCategory.location,
        "Senior": LabelCategory.seniority,
        "Konzern": LabelCategory.company_size,
    }


def test_categorize_drops_unknown_category_values():
    from app.labels.categorize import categorize_names

    llm = MagicMock()
    llm.complete.return_value = json.dumps({"Foo": "tech", "Bar": "not-a-real-cat"})
    result = categorize_names(["Foo", "Bar"], llm)
    assert result == {"Foo": LabelCategory.tech}


def test_categorize_returns_empty_on_invalid_json():
    from app.labels.categorize import categorize_names

    llm = MagicMock()
    llm.complete.return_value = "not json"
    assert categorize_names(["X"], llm) == {}


def test_categorize_does_not_emit_other_in_schema():
    """`other` must not be an option the LLM can return."""
    from app.labels.categorize import _build_schema

    schema = _build_schema(["Python", "Senior"])
    enum_values = schema["properties"]["Python"]["enum"]
    assert "other" not in enum_values
    assert "tech" in enum_values
    assert sorted(enum_values) == sorted([
        "role", "tech", "domain", "seniority", "work_mode",
        "location", "company_size", "language", "company",
    ])
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_label_categorizer.py -v
```
Expected: ImportError — `app.labels.categorize` doesn't exist.

- [ ] **Step 3: Create `app/labels/categorize.py`**

```python
"""One-shot LLM categorization for legacy `other` labels.

Used by the worker-startup ``tasks.categorize_existing_labels`` task.
Synchronous, batched, idempotent at the row level (only writes when
the LLM picks a real category and only touches `category = 'other'`
rows).
"""

import json
import logging
from typing import Iterable

from app.db.models import LabelCategory

logger = logging.getLogger(__name__)

BATCH_SIZE = 20

# `other` is intentionally excluded — the LLM must commit to a real
# category or leave the row to fall through.
_CATEGORY_CHOICES = [
    c.value for c in LabelCategory if c is not LabelCategory.other
]

SYSTEM = (
    "You categorize free-form job-posting labels into a fixed taxonomy. "
    "Return ONLY a JSON object mapping each input label name (exactly as "
    "given) to one category value from the schema. Do not invent "
    "categories. Pick the single best fit."
)


def _build_schema(names: list[str]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(names),
        "properties": {
            name: {"enum": _CATEGORY_CHOICES} for name in names
        },
    }


def _user_prompt(names: list[str]) -> str:
    listing = "\n".join(f"- {n}" for n in names)
    return (
        "Label names:\n"
        f"{listing}\n\n"
        "Categories: " + ", ".join(_CATEGORY_CHOICES) + "."
    )


def categorize_names(names: list[str], llm) -> dict[str, LabelCategory]:
    """Classify ``names`` in one LLM call. Returns name→category map.

    Names whose LLM answer is not a valid category are omitted from
    the map. JSON parse errors return an empty map.
    """
    if not names:
        return {}
    schema = _build_schema(names)
    raw = llm.complete(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _user_prompt(names)},
        ],
        json_schema=schema,
        temperature=0.0,
    )
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("categorize: JSON decode error: %s", exc)
        return {}
    out: dict[str, LabelCategory] = {}
    for name, value in decoded.items():
        try:
            out[name] = LabelCategory(value)
        except ValueError:
            logger.warning("categorize: invalid category %r for %r", value, name)
    return out


def iter_batches(names: list[str], size: int = BATCH_SIZE) -> Iterable[list[str]]:
    for i in range(0, len(names), size):
        yield names[i : i + size]
```

- [ ] **Step 4: Run**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_label_categorizer.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/labels/categorize.py backend/tests/unit/test_label_categorizer.py
git commit -m "feat(labels): batch LLM categorizer for legacy labels"
```

---

## Task 8: Celery task to categorize existing labels

**Files:**
- Create: `backend/app/tasks/categorize_labels.py`
- Modify: `backend/app/tasks/celery_app.py` (include the new module)
- Test: `backend/tests/integration/test_categorize_labels_task.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/test_categorize_labels_task.py`:

```python
import json
from unittest.mock import MagicMock, patch

from app.db.models import Label, LabelCategory


def _seed_labels(db, names_auto):
    """names_auto: list of (name, is_auto) tuples."""
    out = []
    for name, is_auto in names_auto:
        lab = Label(name=name, color="#fff", is_auto=is_auto)
        db.add(lab)
        out.append(lab)
    db.commit()
    return out


def test_task_categorizes_other_labels(db_session, monkeypatch):
    db = db_session
    _seed_labels(db, [
        ("Python", True),
        ("Frankfurt", True),
        ("Senior", True),
    ])

    fake_llm = MagicMock()
    fake_llm.complete.return_value = json.dumps({
        "Python": "tech",
        "Frankfurt": "location",
        "Senior": "seniority",
    })

    with patch("app.tasks.categorize_labels._build_groq_client", return_value=fake_llm):
        from app.tasks.categorize_labels import categorize_existing_labels_task
        result = categorize_existing_labels_task.run()

    assert result["updated"] == 3
    cats = {l.name: l.category for l in db.query(Label).all()}
    assert cats["Python"] == LabelCategory.tech
    assert cats["Frankfurt"] == LabelCategory.location
    assert cats["Senior"] == LabelCategory.seniority


def test_task_skips_user_created_labels(db_session, monkeypatch):
    db = db_session
    _seed_labels(db, [
        ("Custom User Label", False),
        ("Python", True),
    ])

    fake_llm = MagicMock()
    fake_llm.complete.return_value = json.dumps({"Python": "tech"})

    with patch("app.tasks.categorize_labels._build_groq_client", return_value=fake_llm):
        from app.tasks.categorize_labels import categorize_existing_labels_task
        categorize_existing_labels_task.run()

    db.expire_all()
    custom = db.query(Label).filter_by(name="Custom User Label").one()
    assert custom.category == LabelCategory.other  # untouched


def test_task_is_idempotent(db_session, monkeypatch):
    db = db_session
    _seed_labels(db, [("Python", True)])

    fake_llm = MagicMock()
    fake_llm.complete.return_value = json.dumps({"Python": "tech"})

    with patch("app.tasks.categorize_labels._build_groq_client", return_value=fake_llm):
        from app.tasks.categorize_labels import categorize_existing_labels_task
        categorize_existing_labels_task.run()
        result = categorize_existing_labels_task.run()

    # Second run: no rows still 'other' & is_auto, so updated stays at 0
    assert result["updated"] == 0
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_categorize_labels_task.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `app/tasks/categorize_labels.py`**

```python
"""Worker-startup task that assigns categories to legacy `other` labels."""

import logging

import redis

from app.config import get_settings
from app.db.models import Label, LabelCategory
from app.db.session import get_session_factory
from app.labels.categorize import categorize_names, iter_batches
from app.llm.groq import GroqClient
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_LOCK_KEY = "labels:categorize:lock"
_LOCK_TTL = 3600


def _build_groq_client() -> GroqClient:
    settings = get_settings()
    return GroqClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )


def _candidate_names(db) -> list[str]:
    rows = (
        db.query(Label.name)
        .filter(Label.category == LabelCategory.other)
        .filter(Label.is_auto.is_(True))
        .all()
    )
    return [r[0] for r in rows]


def _apply_batch(db, mapping: dict[str, LabelCategory]) -> int:
    updated = 0
    for name, category in mapping.items():
        lab = (
            db.query(Label)
            .filter(Label.name == name)
            .filter(Label.category == LabelCategory.other)
            .filter(Label.is_auto.is_(True))
            .first()
        )
        if lab is None:
            continue
        lab.category = category
        updated += 1
    db.commit()
    return updated


@celery_app.task(name="tasks.categorize_existing_labels")
def categorize_existing_labels_task() -> dict:
    settings = get_settings()
    redis_url = getattr(settings, "redis_url", None) or settings.celery_broker_url
    client = redis.Redis.from_url(redis_url)
    lock = client.lock(_LOCK_KEY, timeout=_LOCK_TTL, blocking_timeout=0)
    if not lock.acquire(blocking=False):
        logger.info("categorize_existing_labels: locked; skipping")
        return {"status": "skipped_locked"}
    try:
        llm = _build_groq_client()
        session_factory = get_session_factory()
        db = session_factory()
        try:
            names = _candidate_names(db)
            if not names:
                return {"updated": 0, "batches": 0, "total": 0}
            total_updated = 0
            batch_count = 0
            for batch in iter_batches(names):
                try:
                    mapping = categorize_names(batch, llm)
                except Exception as exc:
                    logger.warning("categorize: batch failed: %s", exc)
                    continue
                if mapping:
                    total_updated += _apply_batch(db, mapping)
                batch_count += 1
            return {
                "updated": total_updated,
                "batches": batch_count,
                "total": len(names),
            }
        finally:
            db.close()
    finally:
        try:
            lock.release()
        except Exception:
            logger.warning("categorize_existing_labels: failed to release lock")
```

- [ ] **Step 4: Register module in `celery_app.py`**

In `backend/app/tasks/celery_app.py`, add the new module to the `include=` list. Current include should look like:

```python
include=[
    "app.tasks.pipeline",
    "app.tasks.check_postings",
    "app.tasks.backfill",
    "app.tasks.categorize_labels",
],
```

- [ ] **Step 5: Run**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_categorize_labels_task.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/tasks/categorize_labels.py backend/app/tasks/celery_app.py backend/tests/integration/test_categorize_labels_task.py
git commit -m "feat(tasks): categorize_existing_labels Celery task"
```

---

## Task 9: Enqueue categorize task on app startup

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_lifespan.py` (extend)

- [ ] **Step 1: Extend the lifespan test**

In `backend/tests/unit/test_lifespan.py`, replace the file with:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_enqueues_backfill_and_categorize():
    with (
        patch("app.main.backfill_missing_task") as backfill,
        patch("app.main.categorize_existing_labels_task") as categorize,
    ):
        app = create_app()
        with TestClient(app):
            pass
        backfill.apply_async.assert_called_once()
        categorize.apply_async.assert_called_once()
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_lifespan.py -v
```
Expected: AttributeError on `categorize_existing_labels_task` (not yet imported in `main`).

- [ ] **Step 3: Wire it into `app/main.py`**

In `backend/app/main.py`, add the import next to the existing backfill import:

```python
from app.tasks.backfill import backfill_missing_task
from app.tasks.categorize_labels import categorize_existing_labels_task
```

Inside `lifespan`, add the second enqueue with the same defensive try/except:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        backfill_missing_task.apply_async()
        logger.info("backfill_missing enqueued on startup")
    except Exception as exc:
        logger.warning("failed to enqueue backfill on startup: %s", exc)
    try:
        categorize_existing_labels_task.apply_async()
        logger.info("categorize_existing_labels enqueued on startup")
    except Exception as exc:
        logger.warning("failed to enqueue categorize on startup: %s", exc)
    yield
```

- [ ] **Step 4: Run**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/unit/test_lifespan.py -v
```
Expected: passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/unit/test_lifespan.py
git commit -m "feat(main): enqueue categorize_existing_labels on startup"
```

---

## Task 10: API — `category` on labels, required on create, PATCH endpoint

**Files:**
- Modify: `backend/app/api/labels.py`
- Test: `backend/tests/integration/test_label_api_category.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/integration/test_label_api_category.py`:

```python
def test_get_labels_returns_category(client, db_session):
    from app.db.models import Label, LabelCategory
    db_session.add(Label(name="Python", color="#fff", category=LabelCategory.tech))
    db_session.commit()
    r = client.get("/api/labels")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["category"] == "tech"


def test_create_label_requires_category(client):
    r = client.post("/api/labels", json={"name": "X", "color": "#fff"})
    assert r.status_code == 422


def test_create_label_with_category(client, db_session):
    r = client.post(
        "/api/labels",
        json={"name": "Custom", "color": "#fff", "category": "other"},
    )
    assert r.status_code == 201
    assert r.json()["category"] == "other"


def test_patch_label_updates_category(client, db_session):
    from app.db.models import Label, LabelCategory
    lab = Label(name="OldName", color="#fff", category=LabelCategory.other)
    db_session.add(lab)
    db_session.commit()

    r = client.patch(
        f"/api/labels/{lab.id}",
        json={"category": "tech", "name": "NewName"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "tech"
    assert body["name"] == "NewName"


def test_get_labels_sorted_by_category_then_name(client, db_session):
    from app.db.models import Label, LabelCategory
    db_session.add_all([
        Label(name="Python", color="#fff", category=LabelCategory.tech),
        Label(name="AWS", color="#fff", category=LabelCategory.tech),
        Label(name="Senior", color="#fff", category=LabelCategory.seniority),
    ])
    db_session.commit()
    r = client.get("/api/labels")
    names = [(l["category"], l["name"]) for l in r.json()]
    assert names == [
        ("seniority", "Senior"),
        ("tech", "AWS"),
        ("tech", "Python"),
    ]
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_label_api_category.py -v
```
Expected: failures across the board.

- [ ] **Step 3: Update `app/api/labels.py`**

Replace contents:

```python
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import Label, LabelCategory, User

router = APIRouter(prefix="/api/labels", tags=["labels"])


class LabelCreate(BaseModel):
    name: str
    color: str
    category: LabelCategory


class LabelPatch(BaseModel):
    name: str | None = None
    color: str | None = None
    category: LabelCategory | None = None


class LabelOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    is_auto: bool
    category: LabelCategory

    model_config = {"from_attributes": True}


@router.get("", response_model=list[LabelOut])
def list_labels(
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    return (
        db.query(Label)
        .order_by(Label.category, Label.name)
        .all()
    )


@router.post("", response_model=LabelOut, status_code=201)
def create_label(
    body: LabelCreate,
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    if db.query(Label).filter_by(name=body.name).first():
        raise HTTPException(409, "label already exists")
    label = Label(
        name=body.name,
        color=body.color,
        is_auto=False,
        category=body.category,
    )
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


@router.patch("/{label_id}", response_model=LabelOut)
def patch_label(
    label_id: uuid.UUID,
    body: LabelPatch,
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(404, "not found")
    if body.name is not None:
        label.name = body.name
    if body.color is not None:
        label.color = body.color
    if body.category is not None:
        label.category = body.category
    db.commit()
    db.refresh(label)
    return label
```

- [ ] **Step 4: Run**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_label_api_category.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/labels.py backend/tests/integration/test_label_api_category.py
git commit -m "feat(api): category on labels, required on create, PATCH endpoint"
```

---

## Task 11: Frontend — `Label` type gets `category` + `labels.update` client

**Files:**
- Modify: `frontend/src/api/labels.ts`
- Modify: `frontend/src/api/applications.ts`

- [ ] **Step 1: Update `frontend/src/api/applications.ts`**

Find the existing `Label` type (search `type Label =` or `export type Label`). Update to:

```ts
export type LabelCategory =
  | "role" | "tech" | "domain" | "seniority"
  | "work_mode" | "location" | "company_size"
  | "language" | "company" | "other";

export type Label = {
  id: string;
  name: string;
  color: string;
  is_auto: boolean;
  category: LabelCategory;
};
```

- [ ] **Step 2: Update `frontend/src/api/labels.ts`**

Inside the `labels` object literal, add an `update` method next to `create` (or wherever methods sit). Also update the `create` body type:

```ts
import { api } from "./client";
import type { Label, LabelCategory } from "./applications";

export const labels = {
  list: () => api<Label[]>("/api/labels"),
  create: (body: { name: string; color: string; category: LabelCategory }) =>
    api<Label>("/api/labels", { method: "POST", body }),
  update: (id: string, body: Partial<{ name: string; color: string; category: LabelCategory }>) =>
    api<Label>(`/api/labels/${id}`, { method: "PATCH", body }),
  assign: (appId: string, labelId: string) =>
    api<void>(`/api/applications/${appId}/labels/${labelId}`, { method: "POST" }),
  remove: (appId: string, labelId: string) =>
    api<void>(`/api/applications/${appId}/labels/${labelId}`, { method: "DELETE" }),
};
```

(Match existing key names — `remove` may already be present or named differently; do not break the existing names.)

- [ ] **Step 3: Typecheck**

```bash
cd frontend && node_modules/.bin/tsc -b --noEmit
```
Expected: no errors. TypeScript will flag any consumer of `Label` that ignores `category` if a destructuring pattern was exhaustive — fix only the obvious ones in this task. (Subsequent tasks deal with consumers.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/applications.ts frontend/src/api/labels.ts
git commit -m "feat(fe): Label.category type and labels.update client"
```

---

## Task 12: Frontend — LabelEditor requires a category dropdown

**Files:**
- Modify: `frontend/src/components/LabelEditor.tsx`

- [ ] **Step 1: Read the file once**

```bash
cat frontend/src/components/LabelEditor.tsx
```

Locate the create form (state hooks for new label name + color, the mutation that calls `labels.create`).

- [ ] **Step 2: Add category state + dropdown**

Near the existing `useState` declarations, add:

```tsx
const CATEGORIES: { value: LabelCategory; label: string }[] = [
  { value: "role", label: "Role" },
  { value: "tech", label: "Tech" },
  { value: "domain", label: "Domain" },
  { value: "seniority", label: "Seniority" },
  { value: "work_mode", label: "Work mode" },
  { value: "location", label: "Location" },
  { value: "company_size", label: "Company size" },
  { value: "language", label: "Language" },
  { value: "company", label: "Company" },
  { value: "other", label: "Other" },
];

const [newCategory, setNewCategory] = useState<LabelCategory | "">("");
```

Add `LabelCategory` to the existing import from `../api/applications`.

Render the dropdown next to the color picker:

```tsx
<select
  value={newCategory}
  onChange={(e) => setNewCategory(e.target.value as LabelCategory)}
  className="border rounded px-1 py-0.5 text-sm"
>
  <option value="">Category…</option>
  {CATEGORIES.map((c) => (
    <option key={c.value} value={c.value}>{c.label}</option>
  ))}
</select>
```

- [ ] **Step 3: Block the create button without a category**

Find the create button (calls the create mutation). Update its `disabled` and `onClick`:

```tsx
<button
  type="button"
  disabled={!search.trim() || !newCategory || create.isPending}
  onClick={() => create.mutate({ name: search.trim(), color: colorPick, category: newCategory as LabelCategory })}
  className="..."  // keep existing classes
>
  Create
</button>
```

Update the `create` mutation's `mutationFn` to pass the category:

```tsx
const create = useMutation({
  mutationFn: (body: { name: string; color: string; category: LabelCategory }) =>
    labelsApi.create(body),
  onSuccess: ...
});
```

- [ ] **Step 4: Reset category after successful create**

In the `create.onSuccess` handler (or equivalent), add `setNewCategory("")` so the dropdown resets between creates.

- [ ] **Step 5: Typecheck**

```bash
cd frontend && node_modules/.bin/tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/LabelEditor.tsx
git commit -m "feat(fe): LabelEditor requires category on create"
```

---

## Task 13: Frontend — `LabelChipGroups` component for the detail view

**Files:**
- Create: `frontend/src/components/LabelChipGroups.tsx`
- Modify: `frontend/src/pages/ApplicationDetail.tsx`

- [ ] **Step 1: Create the component**

`frontend/src/components/LabelChipGroups.tsx`:

```tsx
import type { Label, LabelCategory } from "../api/applications";
import { LabelChip } from "./LabelChip";

const CATEGORY_ORDER: LabelCategory[] = [
  "role", "tech", "domain", "seniority",
  "work_mode", "location", "company_size",
  "language", "company", "other",
];

const CATEGORY_LABEL: Record<LabelCategory, string> = {
  role: "Role",
  tech: "Tech",
  domain: "Domain",
  seniority: "Seniority",
  work_mode: "Work mode",
  location: "Location",
  company_size: "Company size",
  language: "Language",
  company: "Company",
  other: "Other",
};

type Props = {
  labels: Label[];
};

export function LabelChipGroups({ labels }: Props) {
  if (labels.length === 0) return null;

  const groups = new Map<LabelCategory, Label[]>();
  for (const lab of labels) {
    const arr = groups.get(lab.category) ?? [];
    arr.push(lab);
    groups.set(lab.category, arr);
  }

  return (
    <div className="space-y-2">
      {CATEGORY_ORDER.map((cat) => {
        const items = groups.get(cat);
        if (!items || items.length === 0) return null;
        return (
          <div key={cat}>
            <div className="text-xs uppercase text-slate-500 mb-1">
              {CATEGORY_LABEL[cat]}
            </div>
            <div className="flex flex-wrap gap-1">
              {items.map((lab) => (
                <LabelChip key={lab.id} label={lab} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

(Adjust the `LabelChip` import path / props to match whatever the existing chip component expects. If it needs `name`+`color` directly instead of a `label` object, pass those.)

- [ ] **Step 2: Wire into the detail page**

In `frontend/src/pages/ApplicationDetail.tsx`, find where assigned labels currently render as a flat chip row (look for `.labels.map(`). Replace with:

```tsx
import { LabelChipGroups } from "../components/LabelChipGroups";

// in the JSX:
<LabelChipGroups labels={app.labels ?? []} />
```

Remove the now-dead flat-map JSX.

- [ ] **Step 3: Typecheck**

```bash
cd frontend && node_modules/.bin/tsc -b --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LabelChipGroups.tsx frontend/src/pages/ApplicationDetail.tsx
git commit -m "feat(fe): LabelChipGroups bunches detail-view chips by category"
```

---

## Task 14: Frontend — collapsible category sections in the label filter

**Files:**
- Modify: the label filter component on the applications list page

- [ ] **Step 1: Locate the filter component**

```bash
cd frontend && rg -l "labels\.list\|label.*filter" src
```

Identify the component that renders the label chips inside the filter dropdown on the list page. Below, that file is referred to as `<filter file>`. Typical candidates: `frontend/src/components/LabelFilter.tsx`, `frontend/src/pages/ApplicationsList.tsx`.

- [ ] **Step 2: Add localStorage helpers and category constants**

At the top of `<filter file>`, add:

```tsx
import type { Label, LabelCategory } from "../api/applications";

const FILTER_OPEN_KEY = "applicator.labelFilter.openCategories";

const CATEGORY_ORDER: LabelCategory[] = [
  "role", "tech", "domain", "seniority",
  "work_mode", "location", "company_size",
  "language", "company", "other",
];

const CATEGORY_LABEL: Record<LabelCategory, string> = {
  role: "Role",
  tech: "Tech",
  domain: "Domain",
  seniority: "Seniority",
  work_mode: "Work mode",
  location: "Location",
  company_size: "Company size",
  language: "Language",
  company: "Company",
  other: "Other",
};

function loadOpenCategories(): Set<LabelCategory> {
  try {
    const raw = localStorage.getItem(FILTER_OPEN_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as LabelCategory[];
    return new Set(arr);
  } catch {
    return new Set();
  }
}

function saveOpenCategories(s: Set<LabelCategory>) {
  localStorage.setItem(FILTER_OPEN_KEY, JSON.stringify([...s]));
}
```

- [ ] **Step 3: Replace the flat chip render with collapsible sections**

Where the filter currently renders all label chips in a single row, replace that JSX with:

```tsx
const [openCats, setOpenCats] = useState<Set<LabelCategory>>(() => loadOpenCategories());

function toggle(cat: LabelCategory) {
  setOpenCats((prev) => {
    const next = new Set(prev);
    if (next.has(cat)) next.delete(cat); else next.add(cat);
    saveOpenCategories(next);
    return next;
  });
}

const grouped = new Map<LabelCategory, Label[]>();
for (const lab of allLabels) {
  const arr = grouped.get(lab.category) ?? [];
  arr.push(lab);
  grouped.set(lab.category, arr);
}

// ...
<div className="space-y-1">
  {CATEGORY_ORDER.map((cat) => {
    const items = grouped.get(cat);
    if (!items || items.length === 0) return null;
    const open = openCats.has(cat);
    return (
      <div key={cat} className="border rounded">
        <button
          type="button"
          onClick={() => toggle(cat)}
          className="w-full flex justify-between items-center px-2 py-1 text-sm"
        >
          <span>{CATEGORY_LABEL[cat]}</span>
          <span className="text-slate-500">{items.length} {open ? "▾" : "▸"}</span>
        </button>
        {open && (
          <div className="flex flex-wrap gap-1 p-2">
            {items.map((lab) => (
              // existing chip render; preserve onClick toggle into selected filter set
              <button
                key={lab.id}
                type="button"
                className={`text-xs rounded px-2 py-0.5 border ${
                  selected.has(lab.id) ? "bg-indigo-100 border-indigo-300" : "bg-white"
                }`}
                onClick={() => toggleSelected(lab.id)}
              >
                {lab.name}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  })}
</div>
```

(`selected` / `toggleSelected` come from the existing filter state — preserve those.)

- [ ] **Step 4: Verify default-collapsed and persistence**

```bash
cd frontend && node_modules/.bin/tsc -b --noEmit
```

(Manual: open list page, every section collapsed; open one, reload → still open; open another, navigate away and back → both open.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components frontend/src/pages
git commit -m "feat(fe): collapsible category sections in label filter"
```

---

## Task 15: Backfill processor — build LabelSuggestions when LLM returns dict

The backfill receives the `suggested_labels` payload from the LLM as a plain dict (because `extract_fields` validates against a dynamically created `PartialExtract` model whose `suggested_labels` is typed as `LabelSuggestions`; the `.model_dump()` round-trip produces a dict). `upsert_and_assign_labels` already accepts a dict (Task 6), so this task just verifies the integration end-to-end.

**Files:**
- Test: `backend/tests/integration/test_backfill.py` (extend existing label tests)

- [ ] **Step 1: Update the existing `test_process_row_upserts_labels_from_extract`**

In `backend/tests/integration/test_backfill.py`, replace the existing test:

```python
def test_process_row_upserts_labels_from_extract(db_session):
    db = db_session
    from app.db.models import Label, LabelCategory
    jp = _row(db)
    fake_extract = MagicMock(return_value={
        "suggested_labels": {
            "role": ["AI Engineer"],
            "tech": ["Python"],
            "company_size": ["Konzern"],
        },
        "contact": None,
        "salary": None,
        "deadline": None,
        "tech_stack": None,
        "benefits": None,
        "required_documents": None,
        "work_mode": None,
        "seniority": None,
        "requirements": None,
        "description": None,
    })
    process_row(db, jp, MagicMock(), extract_fn=fake_extract)
    db.refresh(jp.application)
    by_name = {lab.name: lab for lab in jp.application.labels}
    assert by_name["AI Engineer"].category == LabelCategory.role
    assert by_name["Python"].category == LabelCategory.tech
    assert by_name["Konzern"].category == LabelCategory.company_size
    assert "suggested_labels" in jp.backfill_attempts
```

- [ ] **Step 2: Run**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_backfill.py -v
```
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_backfill.py
git commit -m "test(tasks): backfill upserts categorized labels via shared module"
```

---

## Task 16: Full regression + manual smoke

- [ ] **Step 1: Full backend suite**

```bash
cd backend && /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest
```
Expected: all green.

- [ ] **Step 2: Frontend typecheck**

```bash
cd frontend && node_modules/.bin/tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 3: Rebuild and boot stack**

```bash
cd /Users/Janik/private/code/applicator/.worktrees/contact-backfill
docker compose up -d --build api worker
docker compose logs -f api worker | grep -iE "backfill|categorize"
```

Expected lines:
- `backfill_missing enqueued on startup`
- `categorize_existing_labels enqueued on startup`
- worker: `tasks.categorize_existing_labels[...] succeeded in ...s: {'updated': N, ...}` with N>0.

- [ ] **Step 4: Manual verification**

In a browser:

- `/applications` filter dropdown shows collapsible categories; all collapsed by default; each contains the labels that fall in it; opening a section toggles persistence after reload.
- Open application detail (e.g. `/applications/fd586df5-fdde-4871-aa05-d690c073393c`): chips appear bunched by category.
- Open `LabelEditor`, try to create without a category → button disabled. Pick a category → enabled, creates label that appears in the right group after reload.
- Edit a label via PATCH (e.g. via DevTools or future UI) and verify the row moves to a new category group.

- [ ] **Step 5: Final commit / branch wrap-up**

```bash
git status
```
If any stray changes, commit; otherwise nothing to do.

---

## Self-Review Notes

- Spec §1 (data model) → Tasks 1, 2, 3
- Spec §2 (extractor schema) → Task 5
- Spec §3 (pipeline + backfill + categorize task) → Tasks 6, 7, 8, 9, 15
- Spec §4 (API) → Task 10
- Spec §5 (frontend) → Tasks 11, 12, 13, 14
- Spec §6 (refactor backfill) → Task 4
- Spec §7 (migration) → Task 3
- Spec §8 (testing) → Tests embedded in every implementation task plus Task 16
- Spec §9 (rollout) → Task 16
- Spec §10 (non-goals) → no tasks, intentional
