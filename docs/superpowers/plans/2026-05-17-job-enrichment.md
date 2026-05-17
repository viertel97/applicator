# Job Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add labels, posting-online status check, submission requirements extraction, and job link display to the applicator.

**Architecture:** Four additive features sharing one Alembic migration. Labels use a global `Label` table + `application_label` join table with a SQLAlchemy secondary relationship. Online check runs as a Celery Beat task every 6 hours using httpx + heuristics + LLM fallback. Submission requirements and auto-labels extend the existing extractor schema and `run_extract` pipeline step. Link display is frontend-only.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), Celery Beat (scheduling), httpx (online check), React/TypeScript/TailwindCSS (frontend), Alembic (migrations), testcontainers/pytest (tests)

---

## File Map

**Create:**
- `backend/app/api/labels.py` — GET/POST /api/labels endpoints
- `backend/app/tasks/check_postings.py` — Celery Beat task + heuristic/LLM check logic
- `backend/tests/integration/test_labels.py` — labels API integration tests
- `backend/tests/unit/test_check_postings.py` — heuristic + _check_one unit tests
- `backend/alembic/versions/f9e1b2c3d4a5_job_enrichment.py` — migration
- `frontend/src/api/labels.ts` — labels API client
- `frontend/src/components/LabelChip.tsx` — colored label chip with optional remove button
- `frontend/src/components/LabelEditor.tsx` — label assign/create/remove UI

**Modify:**
- `backend/app/db/models.py` — Label, application_label, new columns
- `backend/app/api/applications.py` — ApplicationOut + LabelOut, label assign/remove endpoints, label_ids filter
- `backend/app/main.py` — wire labels router
- `backend/app/tasks/celery_app.py` — include check_postings, configure Beat schedule
- `backend/app/extractor/schemas.py` — add required_documents + suggested_labels
- `backend/app/extractor/prompts.py` — update system prompt
- `backend/app/pipeline/extract.py` — map required_documents, auto-label upsert
- `frontend/src/api/applications.ts` — add posting_online, labels, required_documents types
- `frontend/src/pages/ApplicationsList.tsx` — link icon, online badge, label chips, label filter
- `frontend/src/pages/ApplicationDetail.tsx` — URL link in header, LabelEditor
- `frontend/src/components/StatusBadge.tsx` — add OnlineBadge
- `frontend/src/components/JobPostingPanel.tsx` — required_documents display

---

## Task 1: DB Models + Alembic Migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/alembic/versions/f9e1b2c3d4a5_job_enrichment.py`

- [ ] **Step 1: Write the failing model test**

Add a new test file that will fail until the new models exist:

```python
# backend/tests/unit/test_job_enrichment_models.py
import uuid
from app.db.models import Label, application_label, Application


def test_label_model_has_expected_fields():
    label = Label(name="Startup", color="#6366f1")
    assert label.name == "Startup"
    assert label.color == "#6366f1"
    assert label.is_auto is False


def test_application_label_table_exists():
    cols = {c.name for c in application_label.columns}
    assert "application_id" in cols
    assert "label_id" in cols


def test_application_has_posting_online_field():
    app = Application(url="https://x.test/j", url_hash="h" * 64)
    assert app.posting_online is None
    assert app.posting_checked_at is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/unit/test_job_enrichment_models.py -v
```
Expected: `ImportError` or `AttributeError`

- [ ] **Step 3: Update models.py**

Replace the contents of `backend/app/db/models.py` with the full updated version. Changes: add `Label` class, `application_label` Table, `labels` relationship on `Application`, `posting_online`/`posting_checked_at` columns on `Application`, `required_documents` column on `JobPosting`.

```python
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    applied = "applied"
    offer = "offer"
    rejected = "rejected"
    accepted = "accepted"
    withdrawn = "withdrawn"


class JobState(str, enum.Enum):
    pending = "pending"
    crawling = "crawling"
    extracting = "extracting"
    extracted = "extracted"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class FailedStage(str, enum.Enum):
    crawl = "crawl"
    extract = "extract"
    generate = "generate"


class InterviewKind(str, enum.Enum):
    phone = "phone"
    video = "video"
    onsite = "onsite"
    technical = "technical"
    final = "final"


class InterviewOutcome(str, enum.Enum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    cancelled = "cancelled"


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


application_label = Table(
    "application_label",
    Base.metadata,
    Column(
        "application_id",
        UUID(as_uuid=True),
        ForeignKey("application.id"),
        primary_key=True,
    ),
    Column(
        "label_id",
        UUID(as_uuid=True),
        ForeignKey("label.id"),
        primary_key=True,
    ),
)


class Label(Base):
    __tablename__ = "label"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    color: Mapped[str] = mapped_column(String(7))
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "user"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ms_oid: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    ms_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CVVariant(Base):
    __tablename__ = "cv_variant"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str] = mapped_column(String(200))
    source_md: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AnschreibenVariant(Base):
    __tablename__ = "anschreiben_variant"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str] = mapped_column(String(200))
    source_md: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Application(Base):
    __tablename__ = "application"
    __table_args__ = (UniqueConstraint("user_id", "url_hash", name="uq_user_url_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.draft
    )
    cv_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_variant.id"), nullable=True
    )
    anschreiben_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("anschreiben_variant.id"), nullable=True
    )
    generated_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_docx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    job_state: Mapped[JobState] = mapped_column(Enum(JobState), default=JobState.pending)
    job_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_stage: Mapped[FailedStage | None] = mapped_column(
        Enum(FailedStage), nullable=True
    )
    job_posting_dirty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    posting_online: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    posting_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    job_posting: Mapped[JobPosting | None] = relationship(
        "JobPosting", uselist=False, back_populates="application"
    )
    labels: Mapped[list[Label]] = relationship(
        "Label", secondary=application_label, lazy="selectin"
    )


class JobPosting(Base):
    __tablename__ = "job_posting"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id"), unique=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    raw_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_person: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    seniority: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_documents: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    application: Mapped[Application] = relationship("Application", back_populates="job_posting")


class Interview(Base):
    __tablename__ = "interview"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[InterviewKind] = mapped_column(Enum(InterviewKind))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[InterviewOutcome] = mapped_column(
        Enum(InterviewOutcome), default=InterviewOutcome.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_message"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application.id"))
    role: Mapped[ChatRole] = mapped_column(Enum(ChatRole))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Session(Base):
    __tablename__ = "session"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/unit/test_job_enrichment_models.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Create the Alembic migration**

Create `backend/alembic/versions/f9e1b2c3d4a5_job_enrichment.py`:

```python
"""job enrichment: labels, online check, required_documents

Revision ID: f9e1b2c3d4a5
Revises: 3a9e1b7c2d44
Create Date: 2026-05-17 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f9e1b2c3d4a5"
down_revision: Union[str, Sequence[str], None] = "3a9e1b7c2d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "label",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("is_auto", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "application_label",
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("application.id"), primary_key=True),
        sa.Column("label_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("label.id"), primary_key=True),
    )
    op.add_column("application", sa.Column("posting_online", sa.Boolean(), nullable=True))
    op.add_column("application", sa.Column("posting_checked_at", sa.DateTime(), nullable=True))
    op.add_column("job_posting", sa.Column("required_documents", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_posting", "required_documents")
    op.drop_column("application", "posting_checked_at")
    op.drop_column("application", "posting_online")
    op.drop_table("application_label")
    op.drop_table("label")
```

- [ ] **Step 6: Verify migration history chain**

```bash
cd backend && alembic check
```
Expected: no errors (or "ok")

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/f9e1b2c3d4a5_job_enrichment.py backend/tests/unit/test_job_enrichment_models.py
git commit -m "feat(db): add Label, application_label, posting_online, required_documents"
```

---

## Task 2: Labels API

**Files:**
- Create: `backend/app/api/labels.py`
- Modify: `backend/app/api/applications.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_labels.py`

- [ ] **Step 1: Write failing integration tests**

```python
# backend/tests/integration/test_labels.py
import pytest


def test_list_labels_empty(auth_user):
    client, _ = auth_user
    r = client.get("/api/labels")
    assert r.status_code == 200
    assert r.json() == []


def test_create_label(auth_user):
    client, _ = auth_user
    r = client.post("/api/labels", json={"name": "Startup", "color": "#6366f1"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Startup"
    assert data["color"] == "#6366f1"
    assert data["is_auto"] is False
    assert "id" in data


def test_create_duplicate_label_returns_409(auth_user):
    client, _ = auth_user
    client.post("/api/labels", json={"name": "Tech", "color": "#3b82f6"})
    r = client.post("/api/labels", json={"name": "Tech", "color": "#ef4444"})
    assert r.status_code == 409


def test_assign_and_list_label_on_application(auth_user):
    client, _ = auth_user

    label_r = client.post("/api/labels", json={"name": "Finance", "color": "#f59e0b"})
    label_id = label_r.json()["id"]

    app_r = client.post("/api/applications", json={"url": "https://example.com/job/label-test"})
    assert app_r.status_code == 202
    app_id = app_r.json()["id"]

    r = client.post(f"/api/applications/{app_id}/labels/{label_id}")
    assert r.status_code == 200
    data = r.json()
    assert any(lbl["id"] == label_id for lbl in data["labels"])


def test_remove_label_from_application(auth_user):
    client, _ = auth_user

    label_r = client.post("/api/labels", json={"name": "Remote", "color": "#10b981"})
    label_id = label_r.json()["id"]

    app_r = client.post("/api/applications", json={"url": "https://example.com/job/remove-test"})
    app_id = app_r.json()["id"]

    client.post(f"/api/applications/{app_id}/labels/{label_id}")
    r = client.delete(f"/api/applications/{app_id}/labels/{label_id}")
    assert r.status_code == 200
    assert not any(lbl["id"] == label_id for lbl in r.json()["labels"])


def test_filter_applications_by_label(auth_user):
    client, _ = auth_user

    label_r = client.post("/api/labels", json={"name": "Agency", "color": "#8b5cf6"})
    label_id = label_r.json()["id"]

    r1 = client.post("/api/applications", json={"url": "https://example.com/job/filter-a"})
    app1_id = r1.json()["id"]
    r2 = client.post("/api/applications", json={"url": "https://example.com/job/filter-b"})
    app2_id = r2.json()["id"]

    client.post(f"/api/applications/{app1_id}/labels/{label_id}")

    r = client.get(f"/api/applications?label_ids={label_id}")
    assert r.status_code == 200
    ids = [a["id"] for a in r.json()]
    assert app1_id in ids
    assert app2_id not in ids


def test_applications_list_includes_labels(auth_user):
    client, _ = auth_user
    r = client.get("/api/applications")
    assert r.status_code == 200
    for a in r.json():
        assert "labels" in a
        assert "posting_online" in a
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/integration/test_labels.py -v
```
Expected: all FAIL (404 / missing fields)

- [ ] **Step 3: Create backend/app/api/labels.py**

```python
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import Label, User

router = APIRouter(prefix="/api/labels", tags=["labels"])


class LabelCreate(BaseModel):
    name: str
    color: str


class LabelOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    is_auto: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[LabelOut])
def list_labels(
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    return db.query(Label).order_by(Label.name).all()


@router.post("", response_model=LabelOut, status_code=201)
def create_label(
    body: LabelCreate,
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    if db.query(Label).filter_by(name=body.name).first():
        raise HTTPException(409, "label already exists")
    label = Label(name=body.name, color=body.color, is_auto=False)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label
```

- [ ] **Step 4: Update ApplicationOut and add label endpoints to applications.py**

At the top of `backend/app/api/applications.py`, add the import:

```python
from app.api.labels import LabelOut
```

Update `ApplicationOut` to add two new fields (insert after `job_posting_dirty`):

```python
posting_online: bool | None
labels: list[LabelOut]
```

Update `from_orm_row` to populate them (insert after `job_posting_dirty=app.job_posting_dirty,`):

```python
posting_online=app.posting_online,
labels=[LabelOut.model_validate(lbl) for lbl in app.labels],
```

Update `JobPostingOut` to add `required_documents` field (insert after `language`):

```python
required_documents: list[str] | None = None
```

Update `list_apps` to accept `label_ids` filter. Replace the existing `list_apps` function:

```python
@router.get("", response_model=list[ApplicationOut])
def list_apps(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    label_ids: list[uuid.UUID] | None = Query(default=None),
):
    from app.db.models import Label as LabelModel
    q = db.query(Application).filter_by(user_id=user.id)
    if label_ids:
        q = q.filter(Application.labels.any(LabelModel.id.in_(label_ids)))
    rows = q.order_by(Application.created_at.desc()).all()
    return [ApplicationOut.from_orm_row(r) for r in rows]
```

Add `Query` to the fastapi imports at the top of applications.py:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
```

Add label assign/remove endpoints at the end of `applications.py`:

```python
@router.post("/{aid}/labels/{label_id}", response_model=ApplicationOut)
def assign_label(
    aid: uuid.UUID,
    label_id: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    from app.db.models import Label as LabelModel
    app_row = _load_owned(db, aid, user)
    label = db.get(LabelModel, label_id)
    if label is None:
        raise HTTPException(404, "label not found")
    if label not in app_row.labels:
        app_row.labels.append(label)
        db.commit()
        db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.delete("/{aid}/labels/{label_id}", response_model=ApplicationOut)
def remove_label(
    aid: uuid.UUID,
    label_id: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    from app.db.models import Label as LabelModel
    app_row = _load_owned(db, aid, user)
    label = db.get(LabelModel, label_id)
    if label and label in app_row.labels:
        app_row.labels.remove(label)
        db.commit()
        db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)
```

- [ ] **Step 5: Wire labels router into main.py**

Add after the existing imports:
```python
from app.api import labels as labels_api
```

Add inside `create_app()` after `app.include_router(interviews_api.router)`:
```python
app.include_router(labels_api.router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/integration/test_labels.py -v
```
Expected: all PASSED

- [ ] **Step 7: Run full backend test suite to check for regressions**

```bash
cd backend && python -m pytest -x -q
```
Expected: all PASSED

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/labels.py backend/app/api/applications.py backend/app/main.py backend/tests/integration/test_labels.py
git commit -m "feat(api): labels endpoints, assign/remove, filter, ApplicationOut fields"
```

---

## Task 3: Extractor — required_documents + auto-labels

**Files:**
- Modify: `backend/app/extractor/schemas.py`
- Modify: `backend/app/extractor/prompts.py`
- Modify: `backend/app/pipeline/extract.py`
- Modify: `backend/tests/unit/test_pipeline_extract.py`

- [ ] **Step 1: Write failing unit test**

Add to `backend/tests/unit/test_pipeline_extract.py`:

```python
def test_run_extract_stores_required_documents_and_auto_labels():
    payload = {
        "title": "Backend Engineer",
        "company": "Acme",
        "language": "en",
        "required_documents": ["cv", "cover_letter"],
        "suggested_labels": ["Startup", "Tech"],
    }
    db = MagicMock()
    app = Application(url="u", url_hash="h" * 64)
    app.id = uuid.uuid4()
    app.user_id = uuid.uuid4()
    app.job_state = JobState.crawling
    app.labels = []

    captured = {}

    def add(obj):
        if isinstance(obj, JobPosting):
            captured["jp"] = obj

    db.add.side_effect = add
    db.query.return_value.filter_by.return_value.first.return_value = None
    db.flush = MagicMock()
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))

    run_extract(db, app, "x" * 1000, "/tmp/raw.html", llm)

    assert captured["jp"].required_documents == ["cv", "cover_letter"]
    # Two labels appended to app.labels
    assert len(app.labels) == 2
    label_names = {lbl.name for lbl in app.labels}
    assert label_names == {"Startup", "Tech"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/unit/test_pipeline_extract.py::test_run_extract_stores_required_documents_and_auto_labels -v
```
Expected: FAIL

- [ ] **Step 3: Update extractor/schemas.py**

```python
from pydantic import BaseModel, Field

_LABEL_CANDIDATES = (
    "Startup, Konzern, Remote, Hybrid, Finance, Tech, "
    "Agency, Consulting, NGO, Public Sector"
)
_DOC_VOCAB = "cv, cover_letter, portfolio, references, certificates, other"


class ExtractedJobPosting(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact_person: str | None = None
    application_email: str | None = None
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
            "Return only values from this set."
        ),
    )
```

- [ ] **Step 4: Update extractor/prompts.py**

```python
SYSTEM = (
    "You extract structured data from job postings. "
    "Return ONLY JSON matching the schema. "
    "If a field is not present, leave it null or empty list. "
    "Detect the posting language as ISO 639-1. "
    "For required_documents, only use the exact values listed in the schema. "
    "For suggested_labels, only pick from the exact values listed in the schema."
)


def user_prompt(raw_text: str) -> str:
    return f"Job posting raw text follows.\n\n---\n{raw_text}\n---"
```

- [ ] **Step 5: Update pipeline/extract.py**

```python
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Application, JobPosting, JobState, Label
from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from app.llm.base import LLMClient

_AUTO_LABEL_COLOR = "#6366f1"


def _upsert_and_assign_labels(db: Session, app: Application, names: list[str]) -> None:
    for name in names:
        label = db.query(Label).filter_by(name=name).first()
        if label is None:
            label = Label(name=name, color=_AUTO_LABEL_COLOR, is_auto=True)
            db.add(label)
            db.flush()
        if label not in app.labels:
            app.labels.append(label)


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
        contact_person=job.contact_person,
        application_email=job.application_email,
        deadline=job.deadline,
        salary=job.salary,
        tech_stack=job.tech_stack,
        seniority=job.seniority,
        work_mode=job.work_mode,
        benefits=job.benefits,
        language=job.language,
        required_documents=job.required_documents or None,
    )
    app.language = job.language
    db.add(jp)
    _upsert_and_assign_labels(db, app, job.suggested_labels)
    app.job_state = JobState.extracted
    db.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/unit/test_pipeline_extract.py -v
```
Expected: all PASSED

- [ ] **Step 7: Run full suite for regressions**

```bash
cd backend && python -m pytest -x -q
```
Expected: all PASSED

- [ ] **Step 8: Commit**

```bash
git add backend/app/extractor/schemas.py backend/app/extractor/prompts.py backend/app/pipeline/extract.py backend/tests/unit/test_pipeline_extract.py
git commit -m "feat(extractor): required_documents + auto-label suggestions"
```

---

## Task 4: Online Status Check — Celery Beat Task

**Files:**
- Create: `backend/app/tasks/check_postings.py`
- Modify: `backend/app/tasks/celery_app.py`
- Create: `backend/tests/unit/test_check_postings.py`

- [ ] **Step 1: Write failing unit tests**

```python
# backend/tests/unit/test_check_postings.py
from app.tasks.check_postings import _heuristic, _check_one
from tests.fakes.llm import FakeLLM


def test_heuristic_404_is_offline():
    assert _heuristic(404, "") is False


def test_heuristic_410_is_offline():
    assert _heuristic(410, "") is False


def test_heuristic_200_no_keywords_is_online():
    assert _heuristic(200, "Senior Python Engineer at Acme — apply now") is True


def test_heuristic_200_keyword_german_is_offline():
    assert _heuristic(200, "Diese Stelle ist leider nicht mehr verfügbar.") is False


def test_heuristic_200_keyword_english_is_offline():
    assert _heuristic(200, "Sorry, this position has been filled.") is False


def test_heuristic_503_is_inconclusive():
    assert _heuristic(503, "Service Unavailable") is None


def test_check_one_conclusive_heuristic_skips_llm():
    def fake_fetch(url):
        return 404, ""

    llm = FakeLLM()
    result = _check_one("https://example.com/job", llm, fetch_fn=fake_fetch)
    assert result is False
    assert len(llm.calls) == 0


def test_check_one_inconclusive_falls_back_to_llm():
    def fake_fetch(url):
        return 503, "temporarily unavailable"

    llm = FakeLLM(handler=lambda m, s: "yes")
    result = _check_one("https://example.com/job", llm, fetch_fn=fake_fetch)
    assert result is True
    assert len(llm.calls) == 1


def test_check_one_llm_no_answer():
    def fake_fetch(url):
        return 503, "error"

    llm = FakeLLM(handler=lambda m, s: "no")
    result = _check_one("https://example.com/job", llm, fetch_fn=fake_fetch)
    assert result is False


def test_check_one_fetch_error_returns_none():
    def fake_fetch(url):
        raise ConnectionError("no route to host")

    llm = FakeLLM()
    result = _check_one("https://example.com/job", llm, fetch_fn=fake_fetch)
    assert result is None
    assert len(llm.calls) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/unit/test_check_postings.py -v
```
Expected: `ImportError` (module doesn't exist yet)

- [ ] **Step 3: Create backend/app/tasks/check_postings.py**

```python
import logging
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Application, ApplicationStatus
from app.db.session import get_session_factory
from app.llm.groq import GroqClient
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_OFFLINE_STATUSES = frozenset((404, 410))
_OFFLINE_KEYWORDS = [
    "stelle nicht mehr verfügbar",
    "position filled",
    "job no longer available",
    "diese stelle wurde",
    "anzeige abgelaufen",
    "no longer accepting",
    "position has been filled",
]
_SKIP_WITHIN = timedelta(hours=4)
_RATE_LIMIT_SLEEP = 1.0

FetchFn = Callable[[str], tuple[int, str]]


def _strip_tags(html: str) -> str:
    no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    no_tags = re.sub(r"<[^>]+>", " ", no_scripts)
    return re.sub(r"\s+", " ", no_tags).strip()


def _default_fetch(url: str) -> tuple[int, str]:
    with httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": _UA}) as c:
        r = c.get(url)
    return r.status_code, _strip_tags(r.text)


def _heuristic(status_code: int, text: str) -> bool | None:
    """Returns True=online, False=offline, None=inconclusive."""
    if status_code in _OFFLINE_STATUSES:
        return False
    if status_code == 200:
        lower = text.lower()
        return not any(kw in lower for kw in _OFFLINE_KEYWORDS)
    return None


def _llm_check(text: str, llm) -> bool | None:
    try:
        resp = llm.complete(
            [
                {"role": "system", "content": "Answer only 'yes' or 'no'."},
                {
                    "role": "user",
                    "content": (
                        f"Is this page still an active job posting? Answer yes or no.\n\n{text[:3000]}"
                    ),
                },
            ],
            temperature=0.0,
        )
        return resp.strip().lower().startswith("y")
    except Exception as exc:
        logger.warning("LLM online check failed: %s", exc)
        return None


def _check_one(url: str, llm, fetch_fn: FetchFn | None = None) -> bool | None:
    _fetch = fetch_fn or _default_fetch
    try:
        status, text = _fetch(url)
    except Exception as exc:
        logger.warning("fetch error for %s: %s", url, exc)
        return None
    result = _heuristic(status, text)
    if result is None:
        result = _llm_check(text, llm)
    return result


@contextmanager
def _db() -> Iterator[Session]:
    s = get_session_factory()()
    try:
        yield s
    finally:
        s.close()


@celery_app.task(name="tasks.check_postings")
def check_postings_task() -> dict:
    settings = get_settings()
    llm = GroqClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )
    skip_after = datetime.now(timezone.utc) - _SKIP_WITHIN

    with _db() as db:
        apps = (
            db.query(Application)
            .filter(
                Application.status.notin_(
                    [ApplicationStatus.withdrawn, ApplicationStatus.rejected]
                )
            )
            .all()
        )

    checked = skipped = 0
    for app in apps:
        checked_at = app.posting_checked_at
        if checked_at is not None:
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            if checked_at > skip_after:
                skipped += 1
                continue

        online = _check_one(app.url, llm)

        with _db() as db:
            fresh = db.get(Application, app.id)
            if fresh is not None:
                fresh.posting_online = online
                fresh.posting_checked_at = datetime.now(timezone.utc)
                db.commit()

        checked += 1
        time.sleep(_RATE_LIMIT_SLEEP)

    return {"checked": checked, "skipped": skipped}
```

- [ ] **Step 4: Update celery_app.py to include check_postings and configure Beat**

Replace the contents of `backend/app/tasks/celery_app.py`:

```python
from celery import Celery

from app.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "applicator",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["app.tasks.pipeline", "app.tasks.check_postings"],
    )
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True
    app.conf.worker_prefetch_multiplier = 1
    app.conf.timezone = "UTC"
    app.conf.beat_schedule = {
        "check-postings-every-6h": {
            "task": "tasks.check_postings",
            "schedule": 21600.0,
        },
    }
    return app


celery_app = make_celery()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/unit/test_check_postings.py -v
```
Expected: all PASSED

- [ ] **Step 6: Run full suite**

```bash
cd backend && python -m pytest -x -q
```
Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add backend/app/tasks/check_postings.py backend/app/tasks/celery_app.py backend/tests/unit/test_check_postings.py
git commit -m "feat(tasks): online status check with Celery Beat, heuristic + LLM fallback"
```

---

## Task 5: Frontend API Layer

**Files:**
- Create: `frontend/src/api/labels.ts`
- Modify: `frontend/src/api/applications.ts`

- [ ] **Step 1: Create frontend/src/api/labels.ts**

```typescript
import { api } from "./client";

export type Label = {
  id: string;
  name: string;
  color: string;
  is_auto: boolean;
};

export const labels = {
  list: () => api<Label[]>("/api/labels"),
  create: (body: { name: string; color: string }) =>
    api<Label>("/api/labels", { method: "POST", body: JSON.stringify(body) }),
  assign: (appId: string, labelId: string) =>
    api<unknown>(`/api/applications/${appId}/labels/${labelId}`, { method: "POST" }),
  remove: (appId: string, labelId: string) =>
    api<unknown>(`/api/applications/${appId}/labels/${labelId}`, { method: "DELETE" }),
};
```

- [ ] **Step 2: Update frontend/src/api/applications.ts**

Update the `JobPosting` type — add `required_documents` after `language`:
```typescript
required_documents: string[] | null;
```

Update the `Application` type — add after `job_posting_dirty`:
```typescript
posting_online: boolean | null;
labels: import("./labels").Label[];
```

Since the import would be circular if labels.ts imports from applications.ts, define `Label` inline in the `Application` type. Change the import approach — add `Label` as an inline type in `applications.ts`:

```typescript
export type Label = {
  id: string;
  name: string;
  color: string;
  is_auto: boolean;
};
```

Then update `Application`:
```typescript
posting_online: boolean | null;
labels: Label[];
```

And update `JobPosting`:
```typescript
required_documents: string[] | null;
```

Also update `labels.ts` to import `Label` from `applications.ts` to avoid duplication:

```typescript
import { api } from "./client";
import type { Label } from "./applications";

export type { Label };

export const labels = {
  list: () => api<Label[]>("/api/labels"),
  create: (body: { name: string; color: string }) =>
    api<Label>("/api/labels", { method: "POST", body: JSON.stringify(body) }),
  assign: (appId: string, labelId: string) =>
    api<unknown>(`/api/applications/${appId}/labels/${labelId}`, { method: "POST" }),
  remove: (appId: string, labelId: string) =>
    api<unknown>(`/api/applications/${appId}/labels/${labelId}`, { method: "DELETE" }),
};
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | head -30
```
Expected: no TypeScript errors (build may fail on other warnings, but type errors = 0)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/labels.ts frontend/src/api/applications.ts
git commit -m "feat(fe-api): Label type, labels API client, posting_online + required_documents types"
```

---

## Task 6: Frontend — Link Display + Online Badge

**Files:**
- Modify: `frontend/src/components/StatusBadge.tsx`
- Modify: `frontend/src/pages/ApplicationsList.tsx`
- Modify: `frontend/src/pages/ApplicationDetail.tsx`

- [ ] **Step 1: Add OnlineBadge to StatusBadge.tsx**

Append to the end of `frontend/src/components/StatusBadge.tsx`:

```tsx
export function OnlineBadge({ online }: { online: boolean | null }) {
  if (online === null || online === undefined) return null;
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
        online ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
      }`}
    >
      {online ? "Online" : "Offline"}
    </span>
  );
}
```

- [ ] **Step 2: Update ApplicationsList.tsx to show link icon and online badge**

Replace the `<li>` block in `ApplicationsList.tsx`:

```tsx
import { JobStateBadge, StatusBadge, OnlineBadge } from "../components/StatusBadge";

// Inside the map:
<li key={a.id} className="p-3 flex items-center gap-3 hover:bg-slate-50">
  <Link to={`/applications/${a.id}`} className="flex-1 truncate min-w-0">
    <div className="font-medium truncate">{a.job_posting?.title ?? a.url}</div>
    <div className="text-sm text-slate-500 flex items-center gap-1">
      {a.job_posting?.company}
      {a.job_posting?.location && (
        <span className="text-slate-400">· {a.job_posting.location}</span>
      )}
    </div>
  </Link>
  <a
    href={a.url}
    target="_blank"
    rel="noopener noreferrer"
    onClick={(e) => e.stopPropagation()}
    className="text-slate-400 hover:text-slate-600 flex-shrink-0"
    title="Open original posting"
  >
    ↗
  </a>
  <OnlineBadge online={a.posting_online} />
  <JobStateBadge state={a.job_state} />
  <StatusBadge status={a.status} />
</li>
```

- [ ] **Step 3: Add URL link to ApplicationDetail.tsx header**

In `ApplicationDetail.tsx`, find where the job state and status badges are rendered (around line 57+). Add a URL link near the top of the detail view. Locate the return block and add after the `<h1>` or title area:

```tsx
<a
  href={a.url}
  target="_blank"
  rel="noopener noreferrer"
  className="text-sm text-blue-600 hover:underline flex items-center gap-1"
>
  View original posting ↗
</a>
```

Place it where the job title/company header section is. Also import and render `OnlineBadge` near the status badges:

```tsx
import { JobStateBadge, StatusBadge, OnlineBadge } from "../components/StatusBadge";

// Near status badges:
<OnlineBadge online={a.posting_online} />
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | head -30
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatusBadge.tsx frontend/src/pages/ApplicationsList.tsx frontend/src/pages/ApplicationDetail.tsx
git commit -m "feat(fe): link display, online status badge in list and detail views"
```

---

## Task 7: Frontend — Labels UI

**Files:**
- Create: `frontend/src/components/LabelChip.tsx`
- Create: `frontend/src/components/LabelEditor.tsx`
- Modify: `frontend/src/pages/ApplicationsList.tsx`
- Modify: `frontend/src/pages/ApplicationDetail.tsx`

- [ ] **Step 1: Create LabelChip.tsx**

```tsx
// frontend/src/components/LabelChip.tsx
type Props = {
  label: { name: string; color: string };
  onRemove?: () => void;
};

export function LabelChip({ label, onRemove }: Props) {
  return (
    <span
      className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-medium text-white"
      style={{ backgroundColor: label.color }}
    >
      {label.name}
      {onRemove && (
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemove(); }}
          className="ml-0.5 hover:opacity-75 leading-none"
          aria-label={`Remove ${label.name}`}
        >
          ×
        </button>
      )}
    </span>
  );
}
```

- [ ] **Step 2: Create LabelEditor.tsx**

```tsx
// frontend/src/components/LabelEditor.tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { labels as labelsApi } from "../api/labels";
import type { Label } from "../api/applications";
import { LabelChip } from "./LabelChip";

const DEFAULT_COLORS = [
  "#6366f1", "#3b82f6", "#10b981", "#f59e0b",
  "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6",
];

type Props = {
  appId: string;
  assigned: Label[];
};

export function LabelEditor({ appId, assigned }: Props) {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [colorPick, setColorPick] = useState(DEFAULT_COLORS[0]);
  const [creating, setCreating] = useState(false);

  const allLabels = useQuery({ queryKey: ["labels"], queryFn: labelsApi.list });

  const assign = useMutation({
    mutationFn: (labelId: string) => labelsApi.assign(appId, labelId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", appId] });
      setSearch("");
    },
  });

  const remove = useMutation({
    mutationFn: (labelId: string) => labelsApi.remove(appId, labelId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", appId] }),
  });

  const create = useMutation({
    mutationFn: (name: string) => labelsApi.create({ name, color: colorPick }),
    onSuccess: (newLabel) => {
      qc.invalidateQueries({ queryKey: ["labels"] });
      assign.mutate(newLabel.id);
      setCreating(false);
      setSearch("");
    },
  });

  const assignedIds = new Set(assigned.map((l) => l.id));
  const filtered = (allLabels.data ?? []).filter(
    (l) =>
      !assignedIds.has(l.id) &&
      l.name.toLowerCase().includes(search.toLowerCase()),
  );
  const exactMatch = (allLabels.data ?? []).some(
    (l) => l.name.toLowerCase() === search.toLowerCase(),
  );

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {assigned.map((lbl) => (
          <LabelChip
            key={lbl.id}
            label={lbl}
            onRemove={() => remove.mutate(lbl.id)}
          />
        ))}
      </div>
      <div className="relative">
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setCreating(false); }}
          placeholder="Add label…"
          className="w-full border rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        {search && (
          <div className="absolute z-10 mt-1 w-full bg-white border rounded shadow-md text-sm">
            {filtered.map((l) => (
              <button
                key={l.id}
                onClick={() => assign.mutate(l.id)}
                className="w-full text-left px-3 py-1.5 hover:bg-slate-50 flex items-center gap-2"
              >
                <span
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ backgroundColor: l.color }}
                />
                {l.name}
              </button>
            ))}
            {!exactMatch && search.trim() && (
              <button
                onClick={() => setCreating(true)}
                className="w-full text-left px-3 py-1.5 hover:bg-slate-50 text-blue-600"
              >
                Create "{search.trim()}"
              </button>
            )}
          </div>
        )}
      </div>
      {creating && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-500">Color:</span>
          {DEFAULT_COLORS.map((c) => (
            <button
              key={c}
              onClick={() => setColorPick(c)}
              className={`w-5 h-5 rounded-full border-2 ${colorPick === c ? "border-slate-700" : "border-transparent"}`}
              style={{ backgroundColor: c }}
              aria-label={c}
            />
          ))}
          <button
            onClick={() => create.mutate(search.trim())}
            disabled={create.isPending}
            className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Create
          </button>
          <button
            onClick={() => setCreating(false)}
            className="text-xs text-slate-500 hover:text-slate-700"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Update applications.list to accept labelIds, then rewrite ApplicationsList.tsx**

First update `frontend/src/api/applications.ts` — replace the `list` function:

```typescript
list: (labelIds?: string[]) => {
  const params = labelIds?.length
    ? "?" + labelIds.map((id) => `label_ids=${id}`).join("&")
    : "";
  return api<Application[]>(`/api/applications${params}`);
},
```

Then replace the full contents of `frontend/src/pages/ApplicationsList.tsx`:

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { Application } from "../api/applications";
import { applications } from "../api/applications";
import { labels as labelsApi } from "../api/labels";
import { AddApplicationForm } from "../components/AddApplicationForm";
import { JobStateBadge, StatusBadge, OnlineBadge } from "../components/StatusBadge";
import { LabelChip } from "../components/LabelChip";

export default function ApplicationsList() {
  const [filterLabelIds, setFilterLabelIds] = useState<string[]>([]);

  const allLabels = useQuery({ queryKey: ["labels"], queryFn: labelsApi.list });

  const { data, isLoading } = useQuery<Application[]>({
    queryKey: ["applications", filterLabelIds],
    queryFn: () => applications.list(filterLabelIds),
    refetchInterval: (q) => {
      const arr = q.state.data;
      if (!arr) return false;
      return arr.some((a) => !["ready", "failed"].includes(a.job_state)) ? 2000 : false;
    },
  });

  const toggleLabel = (id: string) =>
    setFilterLabelIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">Applications</h1>
      <AddApplicationForm />
      {(allLabels.data ?? []).length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {(allLabels.data ?? []).map((lbl) => (
            <button
              key={lbl.id}
              onClick={() => toggleLabel(lbl.id)}
              className={`rounded-full transition-shadow ${
                filterLabelIds.includes(lbl.id) ? "ring-2 ring-offset-1 ring-slate-700" : ""
              }`}
            >
              <LabelChip label={lbl} />
            </button>
          ))}
        </div>
      )}
      {isLoading && <div>Loading…</div>}
      <ul className="divide-y border rounded bg-white">
        {(data ?? []).map((a: Application) => (
          <li key={a.id} className="p-3 flex items-center gap-3 hover:bg-slate-50">
            <Link to={`/applications/${a.id}`} className="flex-1 truncate min-w-0">
              <div className="font-medium truncate">{a.job_posting?.title ?? a.url}</div>
              <div className="text-sm text-slate-500 flex items-center gap-1">
                {a.job_posting?.company}
                {a.job_posting?.location && (
                  <span className="text-slate-400">· {a.job_posting.location}</span>
                )}
              </div>
              {a.labels.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {a.labels.map((lbl) => (
                    <LabelChip key={lbl.id} label={lbl} />
                  ))}
                </div>
              )}
            </Link>
            <a
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-slate-400 hover:text-slate-600 flex-shrink-0"
              title="Open original posting"
            >
              ↗
            </a>
            <OnlineBadge online={a.posting_online} />
            <JobStateBadge state={a.job_state} />
            <StatusBadge status={a.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Add LabelEditor to ApplicationDetail.tsx**

Import and render `LabelEditor` below the job state section in `ApplicationDetail.tsx`:

```tsx
import { LabelEditor } from "../components/LabelEditor";

// Inside the return, after the status/badge row, add:
<div className="mt-3">
  <div className="text-xs text-slate-500 mb-1 font-medium uppercase tracking-wide">Labels</div>
  <LabelEditor appId={a.id} assigned={a.labels} />
</div>
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | head -40
```
Fix any type errors before continuing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/LabelChip.tsx frontend/src/components/LabelEditor.tsx frontend/src/pages/ApplicationsList.tsx frontend/src/pages/ApplicationDetail.tsx frontend/src/api/applications.ts
git commit -m "feat(fe): label chips, filter, label editor with create/assign/remove"
```

---

## Task 8: Frontend — Required Documents Display

**Files:**
- Modify: `frontend/src/components/JobPostingPanel.tsx`

- [ ] **Step 1: Add required_documents display to JobPostingPanel.tsx**

Locate where the component renders job posting fields. After the existing `LIST_FIELDS` rendering block, add a required documents section. Find the JSX that maps over `LIST_FIELDS` and after it add:

```tsx
{jp?.required_documents && jp.required_documents.length > 0 && (
  <div className="mt-3">
    <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
      Required documents
    </div>
    <div className="flex flex-wrap gap-1">
      {jp.required_documents.map((doc) => (
        <span
          key={doc}
          className="px-2 py-0.5 bg-slate-100 text-slate-700 text-xs rounded-full capitalize"
        >
          {doc.replace(/_/g, " ")}
        </span>
      ))}
    </div>
  </div>
)}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/JobPostingPanel.tsx
git commit -m "feat(fe): required documents display in job posting panel"
```

---

## Post-Implementation

- [ ] **Run full backend test suite one final time**

```bash
cd backend && python -m pytest -q
```
Expected: all PASSED, 0 failures

- [ ] **Run alembic upgrade on dev DB**

```bash
cd backend && alembic upgrade head
```
Expected: migration `f9e1b2c3d4a5` applied successfully

- [ ] **Verify Celery Beat config is loaded**

```bash
cd backend && python -c "from app.tasks.celery_app import celery_app; print(celery_app.conf.beat_schedule)"
```
Expected: shows `check-postings-every-6h` entry
