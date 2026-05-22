# Contact Extraction + Missing-Field Backfill + Soft Delete — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flat `contact_person` + `application_email` with a structured `contact` block, add an on-startup backfill that fills missing JobPosting fields without re-extracting non-null values, and add soft-delete for applications.

**Architecture:** Schema migration with in-place data copy. New `extract_fields` extractor entrypoint builds a Pydantic model dynamically from a subset of fields and asks the LLM only for those. Celery task `tasks.backfill_missing` is enqueued by a FastAPI lifespan handler at startup, takes a Redis lock so a second boot is a no-op, scans `job_posting` rows, runs the targeted pass, and records `backfill_attempts` so genuinely-empty fields are never retried. Soft delete adds `deleted_at` and filters list/get queries.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Celery + Redis, Pydantic, Groq LLM client, React + TanStack Query.

---

## File Structure

**Backend — modify:**
- `backend/app/extractor/schemas.py` — add `ContactInfo`, replace flat contact fields
- `backend/app/extractor/__init__.py` — add `extract_fields()` entrypoint
- `backend/app/extractor/prompts.py` — adjust SYSTEM prompt for contact + add SYSTEM_FIELDS for partial extract
- `backend/app/db/models.py` — JobPosting: drop two cols, add two, Application: add `deleted_at`
- `backend/app/api/applications.py` — update JobPostingOut/Patch, filter `deleted_at`, add DELETE endpoint
- `backend/app/pipeline/extract.py` — write `contact` instead of split fields
- `backend/app/pipeline/generate.py` — read `contact` for generator
- `backend/app/generator/prompts.py` — use `contact` in prompt
- `backend/app/main.py` — `lifespan` enqueues backfill on startup
- `backend/app/tasks/celery_app.py` — include new task module
- `backend/app/config.py` — add `redis_url` setting if not present (reused for lock)

**Backend — create:**
- `backend/alembic/versions/<rev>_contact_struct_backfill_softdelete.py`
- `backend/app/tasks/backfill.py` — Celery task + Redis lock helper

**Backend — tests (create):**
- `backend/tests/unit/test_extract_fields.py`
- `backend/tests/unit/test_backfill.py`
- `backend/tests/integration/test_delete_application.py`
- `backend/tests/unit/test_contact_migration.py` (data-copy logic in isolation)

**Frontend — modify:**
- `frontend/src/api/applications.ts` — types: drop two fields, add `contact`, add `remove` API
- `frontend/src/components/JobPostingPanel.tsx` — render contact section
- `frontend/src/pages/Applications.tsx` (or list page wherever the table lives) — trash icon
- `frontend/src/pages/Application.tsx` (or detail page) — Delete button
- `frontend/tests/e2e.spec.ts` — extend with delete flow

**Frontend — create:**
- `frontend/src/components/ConfirmDialog.tsx` — small shared modal
- `frontend/src/components/ContactBlock.tsx` — name/role/email/phone render

---

## Task 1: Add `ContactInfo` to extractor schema and replace flat fields

**Files:**
- Modify: `backend/app/extractor/schemas.py`
- Test: `backend/tests/unit/test_extract_fields.py`

- [x] **Step 1: Write the failing test for the new schema shape**

Create `backend/tests/unit/test_extract_fields.py`:

```python
from app.extractor.schemas import ContactInfo, ExtractedJobPosting


def test_extracted_job_posting_has_contact_block_not_flat_fields():
    fields = ExtractedJobPosting.model_fields
    assert "contact" in fields
    assert "contact_person" not in fields
    assert "application_email" not in fields


def test_contact_info_all_optional():
    c = ContactInfo()
    assert c.name is None and c.role is None and c.email is None and c.phone is None
    c2 = ContactInfo(name="Jane", email="j@x.com")
    assert c2.role is None and c2.phone is None


def test_extracted_job_posting_contact_default_none():
    j = ExtractedJobPosting(language="de")
    assert j.contact is None
```

- [x] **Step 2: Run test, verify failure**

```bash
cd backend && uv run pytest tests/unit/test_extract_fields.py -v
```
Expected: FAIL with `AssertionError: assert 'contact' in fields` (or import error if `ContactInfo` missing).

- [x] **Step 3: Update the schema**

Edit `backend/app/extractor/schemas.py`:

```python
from pydantic import BaseModel, Field

_LABEL_CANDIDATES = (
    "Startup (<50), KMU (50-500), Mittelstand (500-5000), Konzern (5000+), "
    "Remote, Hybrid, Finance, Tech, Agency, Consulting, NGO, Public Sector"
)
_DOC_VOCAB = "cv, cover_letter, portfolio, references, certificates, other"


class ContactInfo(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None


class ExtractedJobPosting(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact: ContactInfo | None = None
    deadline: str | None = None
    salary: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    seniority: str | None = None
    work_mode: str | None = None
    benefits: list[str] = Field(default_factory=list)
    language: str = Field(description="ISO 639-1 of the posting body, e.g. 'de' or 'en'")
    required_documents: list[str] = Field(
        default_factory=list,
        description=(
            f"Documents required to apply. Only use values from: {_DOC_VOCAB}"
        ),
    )
    suggested_labels: list[str] = Field(
        default_factory=list,
        description=(
            f"Labels from this set that apply to the company/role: {_LABEL_CANDIDATES}. "
            "Return only values from this set. "
            "Pick exactly one size bucket (Startup/KMU/Mittelstand/Konzern) using "
            "explicit headcount in the posting if mentioned, otherwise general "
            "knowledge of the named company. Omit size only if truly unknown."
        ),
    )
```

- [x] **Step 4: Update extractor SYSTEM prompt**

Edit `backend/app/extractor/prompts.py`:

```python
SYSTEM = (
    "You extract structured data from job postings. "
    "Return ONLY JSON matching the schema. "
    "If a field is not present, leave it null or empty list. "
    "Detect the posting language as ISO 639-1. "
    "For required_documents, only use the exact values listed in the schema. "
    "For suggested_labels, only pick from the exact values listed in the schema. "
    "Always include one company-size bucket when determinable. "
    "For 'contact', fill the sub-fields (name, role, email, phone) from any "
    "Ansprechpartner block, recruiter signature, sidebar contact card, mailto: "
    "or tel: link. Leave 'contact' null only when no identifiable contact "
    "info appears."
)
SYSTEM_PARTIAL = (
    "You extract a subset of fields from a job posting. "
    "Return ONLY JSON matching the provided schema. "
    "Only fill the fields shown in the schema. "
    "Use null or empty list when not present."
)


def user_prompt(raw_text: str) -> str:
    return f"Job posting raw text follows.\n\n---\n{raw_text}\n---"
```

- [x] **Step 5: Run tests, verify pass**

```bash
cd backend && uv run pytest tests/unit/test_extract_fields.py -v
```
Expected: 3 passed.

- [x] **Step 6: Commit**

```bash
git add backend/app/extractor/schemas.py backend/app/extractor/prompts.py backend/tests/unit/test_extract_fields.py
git commit -m "feat(extractor): structured contact block in ExtractedJobPosting"
```

---

## Task 2: Add `extract_fields()` partial extractor

**Files:**
- Modify: `backend/app/extractor/__init__.py`
- Test: `backend/tests/unit/test_extract_fields.py` (extend)

- [x] **Step 1: Add failing tests for partial extraction**

Append to `backend/tests/unit/test_extract_fields.py`:

```python
import json
from unittest.mock import MagicMock

from app.extractor import extract_fields


def _fake_llm(payload: dict) -> MagicMock:
    llm = MagicMock()
    llm.complete.return_value = json.dumps(payload)
    return llm


def test_extract_fields_returns_only_requested_keys():
    llm = _fake_llm({"salary": "60-70k", "deadline": "2026-06-01"})
    result = extract_fields("posting text", ["salary", "deadline"], llm)
    assert set(result.keys()) == {"salary", "deadline"}
    assert result["salary"] == "60-70k"
    assert result["deadline"] == "2026-06-01"


def test_extract_fields_nested_contact():
    llm = _fake_llm({"contact": {"name": "Jane", "email": "j@x.com"}})
    result = extract_fields("posting text", ["contact"], llm)
    assert result["contact"] == {
        "name": "Jane",
        "role": None,
        "email": "j@x.com",
        "phone": None,
    }


def test_extract_fields_missing_returns_none():
    llm = _fake_llm({})
    result = extract_fields("posting text", ["salary"], llm)
    assert result == {"salary": None}


def test_extract_fields_empty_list_raises():
    import pytest

    with pytest.raises(ValueError):
        extract_fields("text", [], _fake_llm({}))
```

- [x] **Step 2: Run, verify failure**

```bash
cd backend && uv run pytest tests/unit/test_extract_fields.py -v
```
Expected: ImportError for `extract_fields` (function not yet defined).

- [x] **Step 3: Implement `extract_fields`**

Replace `backend/app/extractor/__init__.py` with:

```python
from typing import Any

from pydantic import create_model

from app.extractor.prompts import SYSTEM, SYSTEM_PARTIAL, user_prompt
from app.extractor.schemas import ContactInfo, ExtractedJobPosting
from app.llm.base import LLMClient


def extract(raw_text: str, llm: LLMClient) -> ExtractedJobPosting:
    schema = ExtractedJobPosting.model_json_schema()
    raw = llm.complete(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt(raw_text)},
        ],
        json_schema=schema,
        temperature=0.0,
    )
    return ExtractedJobPosting.model_validate_json(raw)


def extract_fields(
    raw_text: str,
    fields: list[str],
    llm: LLMClient,
) -> dict[str, Any]:
    """Extract a subset of fields from a posting.

    Returns a dict whose keys are exactly `fields`; values may be None when
    the LLM did not find the field. Nested models (currently only
    `contact`) are returned as plain dicts.
    """
    if not fields:
        raise ValueError("fields must be non-empty")

    base_fields = ExtractedJobPosting.model_fields
    unknown = [f for f in fields if f not in base_fields]
    if unknown:
        raise ValueError(f"unknown fields: {unknown}")

    partial_field_defs = {}
    for name in fields:
        info = base_fields[name]
        partial_field_defs[name] = (info.annotation, info.default)
    Partial = create_model("PartialExtract", **partial_field_defs)

    raw = llm.complete(
        [
            {"role": "system", "content": SYSTEM_PARTIAL},
            {"role": "user", "content": user_prompt(raw_text)},
        ],
        json_schema=Partial.model_json_schema(),
        temperature=0.0,
    )
    parsed = Partial.model_validate_json(raw)

    result: dict[str, Any] = {}
    for name in fields:
        value = getattr(parsed, name)
        if isinstance(value, ContactInfo):
            result[name] = value.model_dump()
        else:
            result[name] = value
    return result
```

- [x] **Step 4: Run, verify pass**

```bash
cd backend && uv run pytest tests/unit/test_extract_fields.py -v
```
Expected: all tests passed.

- [x] **Step 5: Commit**

```bash
git add backend/app/extractor/__init__.py backend/tests/unit/test_extract_fields.py
git commit -m "feat(extractor): add extract_fields for partial re-extraction"
```

---

## Task 3: Update `JobPosting` + `Application` SQLAlchemy models

**Files:**
- Modify: `backend/app/db/models.py`

- [x] **Step 1: Add failing test for model attributes**

Create `backend/tests/unit/test_models_shape.py`:

```python
from app.db.models import Application, JobPosting


def test_job_posting_has_contact_and_backfill_attempts():
    cols = {c.name for c in JobPosting.__table__.columns}
    assert "contact" in cols
    assert "backfill_attempts" in cols
    assert "contact_person" not in cols
    assert "application_email" not in cols


def test_application_has_deleted_at():
    cols = {c.name for c in Application.__table__.columns}
    assert "deleted_at" in cols
```

- [x] **Step 2: Run, verify failure**

```bash
cd backend && uv run pytest tests/unit/test_models_shape.py -v
```
Expected: FAIL — old columns still present, new ones absent.

- [x] **Step 3: Edit `backend/app/db/models.py`**

In `class JobPosting`, remove these two lines (around lines 204-205):

```python
    contact_person: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_email: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add in their place:

```python
    contact: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    backfill_attempts: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
```

In `class Application`, after `posting_checked_at`, add:

```python
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [x] **Step 4: Run, verify pass**

```bash
cd backend && uv run pytest tests/unit/test_models_shape.py -v
```
Expected: 2 passed.

- [x] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/unit/test_models_shape.py
git commit -m "feat(db): contact JSON + backfill_attempts + deleted_at columns"
```

---

## Task 4: Alembic migration

**Files:**
- Create: `backend/alembic/versions/c1d2e3f4a5b6_contact_struct_backfill_softdelete.py`
- Test: `backend/tests/unit/test_contact_migration.py`

- [x] **Step 1: Generate migration file**

Find current head:

```bash
cd backend && uv run alembic heads
```
Expected: `f9e1b2c3d4a5`.

- [x] **Step 2: Write the migration**

Create `backend/alembic/versions/c1d2e3f4a5b6_contact_struct_backfill_softdelete.py`:

```python
"""contact struct, backfill_attempts, soft delete

Revision ID: c1d2e3f4a5b6
Revises: f9e1b2c3d4a5
Create Date: 2026-05-21 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "f9e1b2c3d4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_posting", sa.Column("contact", sa.JSON(), nullable=True))
    op.add_column(
        "job_posting",
        sa.Column(
            "backfill_attempts",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("application", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    # Data copy: collapse contact_person + application_email into contact JSON.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, contact_person, application_email "
            "FROM job_posting "
            "WHERE contact_person IS NOT NULL OR application_email IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        payload = {}
        if row.contact_person:
            payload["name"] = row.contact_person
        if row.application_email:
            payload["email"] = row.application_email
        bind.execute(
            sa.text("UPDATE job_posting SET contact = :c WHERE id = :id"),
            {"c": payload, "id": row.id},
        )

    op.drop_column("job_posting", "contact_person")
    op.drop_column("job_posting", "application_email")


def downgrade() -> None:
    op.add_column(
        "job_posting", sa.Column("contact_person", sa.Text(), nullable=True)
    )
    op.add_column(
        "job_posting", sa.Column("application_email", sa.Text(), nullable=True)
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, contact FROM job_posting WHERE contact IS NOT NULL")
    ).fetchall()
    for row in rows:
        payload = row.contact or {}
        bind.execute(
            sa.text(
                "UPDATE job_posting SET contact_person = :n, application_email = :e "
                "WHERE id = :id"
            ),
            {
                "n": payload.get("name"),
                "e": payload.get("email"),
                "id": row.id,
            },
        )

    op.drop_column("job_posting", "contact")
    op.drop_column("job_posting", "backfill_attempts")
    op.drop_column("application", "deleted_at")
```

- [x] **Step 3: Apply migration to test DB and verify roundtrip**

```bash
cd backend && uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: each command completes without errors.

- [x] **Step 4: Write contact-copy unit test**

Create `backend/tests/unit/test_contact_migration.py`:

```python
"""Tests the data-copy logic used by the contact-struct migration."""

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Application, JobPosting, User


def _make_app(db: Session) -> Application:
    user = User(ms_oid="oid", email="u@x.com", display_name="U")
    db.add(user)
    db.flush()
    app = Application(user_id=user.id, url="https://x.com/job", url_hash="h" * 64)
    db.add(app)
    db.flush()
    return app


def test_contact_copy_collapses_both_fields(db: Session):
    app = _make_app(db)
    db.execute(
        sa.text(
            "INSERT INTO job_posting (id, application_id, raw_text, contact) "
            "VALUES (gen_random_uuid(), :aid, 'x', :c)"
        ),
        {
            "aid": str(app.id),
            "c": {"name": "Jane Doe", "email": "j@x.com"},
        },
    )
    db.commit()
    jp = db.query(JobPosting).filter_by(application_id=app.id).one()
    assert jp.contact == {"name": "Jane Doe", "email": "j@x.com"}


def test_contact_copy_handles_only_name(db: Session):
    app = _make_app(db)
    db.execute(
        sa.text(
            "INSERT INTO job_posting (id, application_id, raw_text, contact) "
            "VALUES (gen_random_uuid(), :aid, 'x', :c)"
        ),
        {"aid": str(app.id), "c": {"name": "Solo"}},
    )
    db.commit()
    jp = db.query(JobPosting).filter_by(application_id=app.id).one()
    assert jp.contact == {"name": "Solo"}
```

This relies on the existing `db` fixture in `backend/tests/integration/conftest.py`. Move the file there if needed.

- [x] **Step 5: Run migration + tests**

```bash
cd backend && uv run pytest tests/unit/test_models_shape.py tests/integration/test_contact_migration.py -v
```
Expected: passed.

- [x] **Step 6: Commit**

```bash
git add backend/alembic/versions/c1d2e3f4a5b6_contact_struct_backfill_softdelete.py backend/tests/integration/test_contact_migration.py
git commit -m "feat(db): migration for contact struct, backfill_attempts, deleted_at"
```

---

## Task 5: Wire pipeline extract to new contact field

**Files:**
- Modify: `backend/app/pipeline/extract.py`

- [x] **Step 1: Write the failing test**

Create `backend/tests/integration/test_pipeline_contact.py`:

```python
from unittest.mock import MagicMock

from app.db.models import Application, JobPosting, User
from app.extractor.schemas import ContactInfo, ExtractedJobPosting
from app.pipeline.extract import run_extract


def _user(db):
    u = User(ms_oid="oid1", email="u@x.com", display_name="U")
    db.add(u); db.flush(); return u


def test_run_extract_writes_contact_block(db, monkeypatch):
    u = _user(db)
    app = Application(user_id=u.id, url="https://x.com/1", url_hash="h" * 64)
    db.add(app); db.commit()

    fake = ExtractedJobPosting(
        title="Eng", company="Acme", language="en",
        contact=ContactInfo(name="Jane", email="j@x.com", phone="+49 30 1"),
    )
    monkeypatch.setattr("app.pipeline.extract.extract", lambda *_a, **_k: fake)

    run_extract(db, app, "raw", "/tmp/raw.html", MagicMock())
    db.refresh(app)
    jp = db.query(JobPosting).filter_by(application_id=app.id).one()
    assert jp.contact == {
        "name": "Jane", "role": None, "email": "j@x.com", "phone": "+49 30 1",
    }
```

- [x] **Step 2: Run, verify failure**

```bash
cd backend && uv run pytest tests/integration/test_pipeline_contact.py -v
```
Expected: FAIL — `JobPosting` constructor no longer accepts `contact_person`/`application_email`, but current `run_extract` still passes them.

- [x] **Step 3: Update `backend/app/pipeline/extract.py`**

Replace the `JobPosting(...)` construction with:

```python
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
```

- [x] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/integration/test_pipeline_contact.py tests/integration/test_pipeline.py -v
```
Expected: passed.

- [x] **Step 5: Commit**

```bash
git add backend/app/pipeline/extract.py backend/tests/integration/test_pipeline_contact.py
git commit -m "feat(pipeline): write structured contact in run_extract"
```

---

## Task 6: Wire generator to new contact field

**Files:**
- Modify: `backend/app/pipeline/generate.py`, `backend/app/generator/prompts.py`

- [x] **Step 1: Update `backend/app/pipeline/generate.py`**

Replace lines 46-61 (`job = ExtractedJobPosting(...)`) with:

```python
    from app.extractor.schemas import ContactInfo

    job = ExtractedJobPosting(
        title=jp.title,
        company=jp.company,
        location=jp.location,
        description=jp.description,
        requirements=jp.requirements,
        contact=ContactInfo(**jp.contact) if jp.contact else None,
        deadline=jp.deadline,
        salary=jp.salary,
        tech_stack=jp.tech_stack or [],
        seniority=jp.seniority,
        work_mode=jp.work_mode,
        benefits=jp.benefits or [],
        language=jp.language,
    )
```

- [x] **Step 2: Update `backend/app/generator/prompts.py`**

Replace the `Contact person:` line with a contact block:

```python
def user_prompt(
    job: ExtractedJobPosting,
    cv_md: str,
    anschreiben_md: str,
    language: str,
) -> str:
    c = job.contact
    contact_line = (
        f"Contact: {c.name or '-'} ({c.role or '-'}), "
        f"email: {c.email or '-'}, phone: {c.phone or '-'}"
        if c else "Contact: -"
    )
    return (
        f"Target language: {language}\n\n"
        f"=== JOB POSTING ===\n"
        f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n"
        f"Description:\n{job.description}\nRequirements:\n{job.requirements}\n"
        f"Tech stack: {', '.join(job.tech_stack)}\n"
        f"{contact_line}\n\n"
        f"=== CANDIDATE CV (Markdown) ===\n{cv_md}\n\n"
        f"=== DEFAULT ANSCHREIBEN TEMPLATE (Markdown) ===\n{anschreiben_md}\n\n"
        f"Now produce the tailored Anschreiben in Markdown, in {language}."
    )
```

- [x] **Step 3: Run existing generator tests**

```bash
cd backend && uv run pytest tests/integration/test_pipeline.py -v
```
Expected: passed.

- [x] **Step 4: Commit**

```bash
git add backend/app/pipeline/generate.py backend/app/generator/prompts.py
git commit -m "feat(generator): consume structured contact in prompt"
```

---

## Task 7: Update API schemas (`JobPostingOut`/`Patch`)

**Files:**
- Modify: `backend/app/api/applications.py`

- [x] **Step 1: Add failing API test**

Create `backend/tests/integration/test_application_contact_api.py`:

```python
def test_application_response_exposes_contact_block(client, sample_app_with_contact):
    aid = sample_app_with_contact
    r = client.get(f"/api/applications/{aid}")
    body = r.json()
    jp = body["job_posting"]
    assert "contact" in jp
    assert jp["contact"]["name"] == "Jane"
    assert "contact_person" not in jp
    assert "application_email" not in jp
```

Add a `sample_app_with_contact` fixture in `backend/tests/integration/conftest.py` that creates an Application + JobPosting with `contact={"name": "Jane", "email": "j@x.com"}` and returns the app id (follow the pattern of any existing application fixture).

- [x] **Step 2: Update `JobPostingOut` and `JobPostingPatch`**

In `backend/app/api/applications.py`, replace:

```python
    contact_person: str | None = None
    application_email: str | None = None
```

(in both classes) with:

```python
    contact: dict | None = None
```

The pydantic `dict | None` field passes through the JSON as stored.

For `JobPostingPatch`, no special handling needed beyond using `dict | None`.

- [x] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/integration/test_application_contact_api.py -v
```
Expected: passed.

- [x] **Step 4: Commit**

```bash
git add backend/app/api/applications.py backend/tests/integration/test_application_contact_api.py backend/tests/integration/conftest.py
git commit -m "feat(api): expose contact block on JobPostingOut/Patch"
```

---

## Task 8: Soft-delete API + filtering

**Files:**
- Modify: `backend/app/api/applications.py`
- Test: `backend/tests/integration/test_delete_application.py`

- [x] **Step 1: Write failing tests**

Create `backend/tests/integration/test_delete_application.py`:

```python
def test_delete_application_sets_deleted_at(client, sample_application):
    aid = sample_application
    r = client.delete(f"/api/applications/{aid}")
    assert r.status_code == 204


def test_deleted_application_excluded_from_list(client, sample_application):
    aid = sample_application
    client.delete(f"/api/applications/{aid}")
    r = client.get("/api/applications")
    ids = [a["id"] for a in r.json()]
    assert aid not in ids


def test_deleted_application_get_returns_404(client, sample_application):
    aid = sample_application
    client.delete(f"/api/applications/{aid}")
    r = client.get(f"/api/applications/{aid}")
    assert r.status_code == 404


def test_delete_is_idempotent(client, sample_application):
    aid = sample_application
    client.delete(f"/api/applications/{aid}")
    r = client.delete(f"/api/applications/{aid}")
    assert r.status_code == 204


def test_delete_unknown_id_returns_404(client):
    import uuid as _u
    r = client.delete(f"/api/applications/{_u.uuid4()}")
    assert r.status_code == 404
```

Use existing `sample_application` fixture or add one if absent (mirror the contact fixture pattern, no contact needed).

- [x] **Step 2: Run, verify failure**

```bash
cd backend && uv run pytest tests/integration/test_delete_application.py -v
```
Expected: FAIL — DELETE route does not exist (405 / 404).

- [x] **Step 3: Update `_load_owned` to filter soft-deleted**

In `backend/app/api/applications.py`, change `_load_owned`:

```python
def _load_owned(db: Session, aid: uuid.UUID, user: User) -> Application:
    app = db.get(Application, aid)
    if not app or app.user_id != user.id or app.deleted_at is not None:
        raise HTTPException(404, "not found")
    return app
```

- [x] **Step 4: Filter list endpoint**

In `list_apps`, change the base query to:

```python
    q = db.query(Application).filter(
        Application.user_id == user.id,
        Application.deleted_at.is_(None),
    )
```

- [x] **Step 5: Add DELETE endpoint**

Append to `backend/app/api/applications.py`:

```python
from datetime import datetime, timezone


@router.delete("/{aid}", status_code=204)
def delete_application(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    if app_row.deleted_at is None:
        app_row.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return None
```

(Move the `from datetime ...` import to the existing import block at the top of the file.)

- [x] **Step 6: Run tests**

```bash
cd backend && uv run pytest tests/integration/test_delete_application.py -v
```
Expected: all 5 passed.

- [x] **Step 7: Commit**

```bash
git add backend/app/api/applications.py backend/tests/integration/test_delete_application.py
git commit -m "feat(api): soft-delete applications with deleted_at filter"
```

---

## Task 9: Backfill Celery task with Redis lock

**Files:**
- Create: `backend/app/tasks/backfill.py`
- Modify: `backend/app/tasks/celery_app.py`, `backend/app/config.py` (if `redis_url` not present)
- Test: `backend/tests/unit/test_backfill.py`

- [x] **Step 1: Verify Redis URL is in settings**

```bash
cd backend && uv run python -c "from app.config import get_settings; print(get_settings().model_dump())"
```
Look for a `redis_url` or equivalent. If absent, add to `backend/app/config.py`:

```python
    redis_url: str = "redis://localhost:6379/0"
```

- [x] **Step 2: Write failing unit test**

Create `backend/tests/unit/test_backfill.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.db.models import Application, JobPosting, User
from app.tasks.backfill import (
    ELIGIBLE_FIELDS,
    pick_missing,
    process_row,
)


def _user(db):
    u = User(ms_oid="b1", email="b@x.com", display_name="B")
    db.add(u); db.flush(); return u


def _row(db, **overrides):
    u = _user(db)
    app = Application(user_id=u.id, url="https://x", url_hash="h" * 64)
    db.add(app); db.flush()
    jp = JobPosting(
        application_id=app.id,
        raw_text="some posting text",
        language="en",
    )
    for k, v in overrides.items():
        setattr(jp, k, v)
    db.add(jp); db.commit()
    return jp


def test_pick_missing_excludes_already_attempted(db):
    jp = _row(db, salary="60k", backfill_attempts={"deadline": "2026-05-01T00:00:00+00:00"})
    missing = pick_missing(jp)
    assert "salary" not in missing
    assert "deadline" not in missing
    assert "contact" in missing


def test_pick_missing_returns_empty_when_nothing_to_do(db):
    full = {f: "x" for f in ELIGIBLE_FIELDS if f != "contact"}
    jp = _row(
        db,
        contact={"name": "j"},
        **{k: ("x" if k not in {"tech_stack", "benefits", "required_documents"}
              else ["x"]) for k in ELIGIBLE_FIELDS if k != "contact"},
    )
    assert pick_missing(jp) == []


def test_process_row_writes_only_non_null_and_stamps_all(db):
    jp = _row(db)
    llm = MagicMock()
    fake_extract = MagicMock(return_value={
        "contact": {"name": "Jane", "role": None, "email": None, "phone": None},
        "salary": None,
        "deadline": "2026-06-01",
    })
    process_row(db, jp, llm, extract_fn=fake_extract)
    db.refresh(jp)
    assert jp.contact == {"name": "Jane", "role": None, "email": None, "phone": None}
    assert jp.salary is None
    assert jp.deadline == "2026-06-01"
    assert "contact" in jp.backfill_attempts
    assert "salary" in jp.backfill_attempts
    assert "deadline" in jp.backfill_attempts


def test_process_row_does_not_overwrite_existing(db):
    jp = _row(db, salary="60k existing")
    fake_extract = MagicMock(return_value={"salary": "999k"})
    process_row(db, jp, MagicMock(), extract_fn=fake_extract)
    db.refresh(jp)
    assert jp.salary == "60k existing"


def test_process_row_skips_when_no_missing(db):
    full_kwargs = {
        "contact": {"name": "x"},
        "salary": "x", "deadline": "x", "requirements": "x", "description": "x",
        "tech_stack": ["x"], "benefits": ["x"], "required_documents": ["x"],
        "work_mode": "x", "seniority": "x",
    }
    jp = _row(db, **full_kwargs)
    fake_extract = MagicMock()
    process_row(db, jp, MagicMock(), extract_fn=fake_extract)
    fake_extract.assert_not_called()
```

- [x] **Step 3: Run, verify failure**

```bash
cd backend && uv run pytest tests/unit/test_backfill.py -v
```
Expected: ImportError — module does not exist.

- [x] **Step 4: Implement `backend/app/tasks/backfill.py`**

```python
"""On-startup backfill task: fills empty JobPosting fields from raw_text
using a targeted LLM pass, without overwriting non-null values or retrying
fields that were already attempted."""

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Iterator

import redis
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Application, JobPosting
from app.db.session import get_session_factory
from app.extractor import extract_fields
from app.llm.groq import GroqClient
from app.tasks.celery_app import celery_app

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
_RATE_LIMIT_SLEEP = 1.0
_LOCK_KEY = "backfill:lock"
_LOCK_TTL = 3600


ExtractFn = Callable[[str, list[str], object], dict]


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def pick_missing(jp: JobPosting) -> list[str]:
    attempted = set(jp.backfill_attempts or {})
    return [
        f for f in ELIGIBLE_FIELDS
        if _is_empty(getattr(jp, f)) and f not in attempted
    ]


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
        if not _is_empty(new_value) and _is_empty(getattr(jp, field)):
            setattr(jp, field, new_value)
        attempts[field] = now_iso
    jp.backfill_attempts = attempts
    db.commit()


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
    for i, jp_id in enumerate(ids):
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
        if i < len(ids) - 1:
            time.sleep(_RATE_LIMIT_SLEEP)
    return {"processed": processed, "skipped": skipped, "total": len(ids)}


@celery_app.task(name="tasks.backfill_missing")
def backfill_missing_task() -> dict:
    settings = get_settings()
    client = redis.Redis.from_url(settings.redis_url)
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

- [x] **Step 5: Register task module in celery_app**

Edit `backend/app/tasks/celery_app.py`:

```python
        include=["app.tasks.pipeline", "app.tasks.check_postings", "app.tasks.backfill"],
```

- [x] **Step 6: Run tests**

```bash
cd backend && uv run pytest tests/unit/test_backfill.py -v
```
Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
git add backend/app/tasks/backfill.py backend/app/tasks/celery_app.py backend/app/config.py backend/tests/unit/test_backfill.py
git commit -m "feat(tasks): backfill_missing task with Redis lock and per-field stamping"
```

---

## Task 10: Enqueue backfill on FastAPI startup

**Files:**
- Modify: `backend/app/main.py`

- [x] **Step 1: Add failing test**

Create `backend/tests/unit/test_lifespan.py`:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_enqueues_backfill():
    with patch("app.main.backfill_missing_task") as task:
        app = create_app()
        with TestClient(app):
            pass
        task.apply_async.assert_called_once()
```

- [x] **Step 2: Run, verify failure**

```bash
cd backend && uv run pytest tests/unit/test_lifespan.py -v
```
Expected: AttributeError / ImportError — symbol not in `app.main`.

- [x] **Step 3: Wire `lifespan` in `backend/app/main.py`**

Replace contents with:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import applications as applications_api
from app.api import auth as auth_api
from app.api import chat as chat_api
from app.api import documents as documents_api
from app.api import interviews as interviews_api
from app.api import labels as labels_api
from app.config import get_settings
from app.tasks.backfill import backfill_missing_task

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        backfill_missing_task.apply_async()
        logger.info("backfill_missing enqueued on startup")
    except Exception as exc:
        logger.warning("failed to enqueue backfill on startup: %s", exc)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Applicator", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_api.router)
    app.include_router(documents_api.router)
    app.include_router(applications_api.router)
    app.include_router(chat_api.router)
    app.include_router(interviews_api.router)
    app.include_router(labels_api.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [x] **Step 4: Run test**

```bash
cd backend && uv run pytest tests/unit/test_lifespan.py -v
```
Expected: passed.

- [x] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/unit/test_lifespan.py
git commit -m "feat(main): enqueue backfill_missing on FastAPI startup via lifespan"
```

---

## Task 11: Frontend types and API client

**Files:**
- Modify: `frontend/src/api/applications.ts`

- [x] **Step 1: Update type and add `remove` method**

In `frontend/src/api/applications.ts`:

Replace these two lines in the `JobPosting` type:

```ts
  contact_person: string | null;
  application_email: string | null;
```

with:

```ts
  contact: {
    name: string | null;
    role: string | null;
    email: string | null;
    phone: string | null;
  } | null;
```

Inside the `applications` object literal, add (place near `setStatus`):

```ts
  remove: (id: string) =>
    api<void>(`/api/applications/${id}`, { method: "DELETE" }),
```

(If the existing `api()` helper rejects non-JSON responses, ensure it tolerates 204; adjust if necessary — check `frontend/src/api/client.ts`.)

- [x] **Step 2: Run frontend type-check / build**

```bash
cd frontend && npm run typecheck
```
Expected: type-check passes (TS may flag old usages — fix them in following tasks).

- [x] **Step 3: Commit**

```bash
git add frontend/src/api/applications.ts
git commit -m "feat(fe): contact type + remove API"
```

---

## Task 12: Frontend ContactBlock + JobPostingPanel update

**Files:**
- Create: `frontend/src/components/ContactBlock.tsx`
- Modify: `frontend/src/components/JobPostingPanel.tsx`

- [x] **Step 1: Create `ContactBlock.tsx`**

```tsx
import type { JobPosting } from "../api/applications";

type Props = { contact: JobPosting["contact"] };

export function ContactBlock({ contact }: Props) {
  if (!contact) return null;
  const anyField = contact.name || contact.role || contact.email || contact.phone;
  if (!anyField) return null;
  return (
    <div className="mb-3">
      <label className="block text-xs uppercase text-slate-500">Contact</label>
      <div className="border rounded px-2 py-1 space-y-0.5 text-sm">
        {contact.name && <div>{contact.name}</div>}
        {contact.role && <div className="text-slate-600">{contact.role}</div>}
        {contact.email && (
          <div>
            <a
              className="text-blue-600 hover:underline"
              href={`mailto:${contact.email}`}
            >
              {contact.email}
            </a>
          </div>
        )}
        {contact.phone && (
          <div>
            <a className="text-blue-600 hover:underline" href={`tel:${contact.phone}`}>
              {contact.phone}
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [x] **Step 2: Edit `JobPostingPanel.tsx`**

Remove these two entries from `TEXT_FIELDS`:

```tsx
  { key: "contact_person", label: "Contact" },
  { key: "application_email", label: "Email" },
```

Add the import:

```tsx
import { ContactBlock } from "./ContactBlock";
```

Insert `<ContactBlock contact={jp.contact} />` immediately above the `{TEXT_FIELDS.map(...)}` block.

- [x] **Step 3: Run typecheck**

```bash
cd frontend && npm run typecheck
```
Expected: passes.

- [x] **Step 4: Manual smoke test**

```bash
cd frontend && npm run dev
```
Open an application detail with a contact and verify name/role/email(mailto)/phone(tel) render. Hide entire section when contact is null.

- [x] **Step 5: Commit**

```bash
git add frontend/src/components/ContactBlock.tsx frontend/src/components/JobPostingPanel.tsx
git commit -m "feat(fe): structured contact block in job posting panel"
```

---

## Task 13: Frontend ConfirmDialog + Delete in list + detail

**Files:**
- Create: `frontend/src/components/ConfirmDialog.tsx`
- Modify: application list page and detail page

- [x] **Step 1: Create `ConfirmDialog.tsx`**

```tsx
type Props = {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
};

export function ConfirmDialog({
  open, title, body, confirmLabel = "Delete", onConfirm, onCancel, busy,
}: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded shadow-lg w-96 p-4">
        <div className="text-lg font-semibold mb-2">{title}</div>
        <div className="text-sm text-slate-700 mb-4">{body}</div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-3 py-1 rounded border"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="px-3 py-1 rounded bg-rose-600 text-white disabled:opacity-50"
          >
            {busy ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [x] **Step 2: Locate list and detail page files**

```bash
cd frontend && rg -l "applications\.(list|get)\b" src
```
Identify the list component (renders rows) and detail component (renders single application). Names may be `Applications.tsx` / `Application.tsx` / `pages/Index.tsx` — adapt below.

- [x] **Step 3: Add trash icon + confirm flow in list row**

In the list component, import:

```tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { applications } from "../api/applications";
```

In the row render, add at the end of each row:

```tsx
<button
  type="button"
  className="text-slate-400 hover:text-rose-600 px-2"
  onClick={(e) => { e.stopPropagation(); setPendingDelete(app); }}
  aria-label="delete"
>
  🗑
</button>
```

Add state and mutation at component top:

```tsx
const qc = useQueryClient();
const [pendingDelete, setPendingDelete] = useState<Application | null>(null);
const remove = useMutation({
  mutationFn: (id: string) => applications.remove(id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["applications"] });
    setPendingDelete(null);
  },
});
```

Render the dialog at the bottom of the component (still inside the root element):

```tsx
<ConfirmDialog
  open={!!pendingDelete}
  title="Delete application"
  body={
    pendingDelete
      ? `Delete application to ${pendingDelete.job_posting?.company ?? "this company"}? This hides it from your list.`
      : ""
  }
  busy={remove.isPending}
  onCancel={() => setPendingDelete(null)}
  onConfirm={() => pendingDelete && remove.mutate(pendingDelete.id)}
/>
```

Replace `Application` with the imported type name used in the file.

- [x] **Step 4: Add Delete button in detail page**

In the detail component, import the same ConfirmDialog + applications API + react-router navigate (or whatever navigation mechanism the project uses — check existing imports).

Add a header button:

```tsx
<button
  type="button"
  className="text-rose-600 border border-rose-300 rounded px-2 py-1 text-sm"
  onClick={() => setConfirmOpen(true)}
>
  Delete
</button>
```

Add state + mutation:

```tsx
const [confirmOpen, setConfirmOpen] = useState(false);
const navigate = useNavigate(); // adjust to project router
const remove = useMutation({
  mutationFn: () => applications.remove(app.id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["applications"] });
    navigate("/applications"); // adjust path
  },
});
```

Render the dialog:

```tsx
<ConfirmDialog
  open={confirmOpen}
  title="Delete application"
  body={`Delete application to ${app.job_posting?.company ?? "this company"}? This hides it from your list.`}
  busy={remove.isPending}
  onCancel={() => setConfirmOpen(false)}
  onConfirm={() => remove.mutate()}
/>
```

- [x] **Step 5: Typecheck**

```bash
cd frontend && npm run typecheck
```
Expected: passes.

- [x] **Step 6: Manual smoke**

```bash
cd frontend && npm run dev
```
Verify both list-row and detail Delete flows: confirm modal appears, cancel does nothing, confirm hides row / navigates back, refresh keeps it hidden.

- [x] **Step 7: Commit**

```bash
git add frontend/src/components/ConfirmDialog.tsx frontend/src/pages
git commit -m "feat(fe): delete application from list and detail with confirm modal"
```

---

## Task 14: E2E coverage

**Files:**
- Modify: `frontend/tests/e2e.spec.ts`

- [x] **Step 1: Add an e2e block for delete flow**

Append to `frontend/tests/e2e.spec.ts`:

```ts
test("delete from list row removes the application", async ({ page }) => {
  await login(page); // reuse existing helper
  await page.goto("/applications");
  const firstRow = page.locator("[data-testid=app-row]").first();
  const company = await firstRow.locator("[data-testid=app-company]").innerText();
  await firstRow.locator("button[aria-label=delete]").click();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText(company)).toHaveCount(0);
});
```

Adjust selectors to match what already exists in the list component. Add `data-testid="app-row"` and `data-testid="app-company"` where needed in the list component.

- [x] **Step 2: Add an e2e block for contact display**

```ts
test("contact block renders mailto and tel links when present", async ({ page }) => {
  await login(page);
  await page.goto("/applications/<seed-id-with-contact>"); // use seeded fixture
  await expect(page.locator("a[href^=mailto]")).toBeVisible();
  await expect(page.locator("a[href^=tel]")).toBeVisible();
});
```

Adapt the URL / seeding to whatever the project's e2e fixtures use.

- [x] **Step 3: Run e2e**

```bash
cd frontend && npm run test:e2e
```
Expected: green.

- [x] **Step 4: Commit**

```bash
git add frontend/tests/e2e.spec.ts frontend/src
git commit -m "test(fe): e2e coverage for delete + contact block"
```

---

## Task 15: Full backend + frontend regression run

- [x] **Step 1: Backend full suite**

```bash
cd backend && uv run pytest
```
Expected: all green.

- [x] **Step 2: Frontend typecheck + tests**

```bash
cd frontend && npm run typecheck && npm test
```
Expected: green.

- [x] **Step 3: Boot the docker stack and observe one backfill cycle**

```bash
docker compose up -d
docker compose logs -f backend worker | head -50
```
Expected: backend log "backfill_missing enqueued on startup"; worker log shows `tasks.backfill_missing` executed and a summary dict.

- [x] **Step 4: Manual verification**

In a browser:
- Open an application that previously had `contact_person`: now renders structured contact block.
- Open an older application that was missing required_documents: after backfill cycle and reload, badges appear (if the LLM identified any).
- Delete an application from the list; verify it disappears and is gone after reload.

- [x] **Step 5: Final commit / branch wrap-up**

If there are stray changes:

```bash
git status
git add -A
git commit -m "chore: post-implementation cleanup"
```

Otherwise nothing to commit.

---

## Self-Review Notes

- Spec §1 (data model) → Tasks 3, 4
- Spec §2 (extractor schema) → Task 1
- Spec §3 (backfill subsystem) → Tasks 9, 10
- Spec §4 (extract_fields) → Task 2
- Spec §5 (frontend contact) → Tasks 11, 12
- Spec §6 (API) → Task 7
- Spec §7 (soft delete) → Tasks 3, 4 (column + migration), 8 (API), 13 (frontend), 14 (e2e)
- Spec §9 (testing) → Tests embedded in Tasks 1, 2, 5, 7, 8, 9, 10, 14
