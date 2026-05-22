# Pre-Application Inquiry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-user editable LLM prompt and an "Inquiry" panel on the application detail page that drafts a short pre-application email asking about home-office policy and/or 80% (Mon–Thu) availability when the job posting does not address those topics.

**Architecture:** Extend the existing extractor to set two boolean flags on `JobPosting`. Add an `inquiry_prompt_template` table (one row per user) and three new columns on `Application` (`inquiry_subject`, `inquiry_body`, `inquiry_sent_at`). New backend module `app/inquiry/` builds a system+user prompt and calls the existing Groq LLM client. New endpoints under `/api/applications/{id}/inquiry/*` and `/api/settings/inquiry-prompt`. Frontend gets a new `InquiryPanel` on the detail page and a new `SettingsInquiryPrompt` page.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, Groq LLM via existing `LLMClient` protocol, React + TanStack Query + react-router, Tailwind, Pytest + testcontainers, Playwright.

---

## File Structure

### Backend — new files
- `backend/app/inquiry/__init__.py` — `draft(...)` function (LLM call + parse)
- `backend/app/inquiry/schemas.py` — `InquiryEmail` Pydantic model
- `backend/app/inquiry/prompts.py` — `DEFAULT_TEMPLATE` (system prompt) + `user_prompt(...)` builder
- `backend/app/api/inquiry_prompt.py` — `GET`/`PUT /api/settings/inquiry-prompt`
- `backend/alembic/versions/<new>_pre_application_inquiry.py` — schema migration
- `backend/tests/unit/test_inquiry_prompts.py`
- `backend/tests/unit/test_inquiry_draft.py`
- `backend/tests/integration/test_inquiry_endpoints.py`
- `backend/tests/integration/test_inquiry_prompt_endpoint.py`

### Backend — modified files
- `backend/app/extractor/schemas.py` — add `mentions_home_office_policy`, `mentions_part_time` bool fields
- `backend/app/extractor/prompts.py` — extend SYSTEM string with flag instructions
- `backend/app/pipeline/extract.py` — copy two new fields to `JobPosting`
- `backend/app/db/models.py` — add `InquiryPromptTemplate`, new `Application` cols, new `JobPosting` cols
- `backend/app/api/applications.py` — extend `JobPostingOut` + `ApplicationOut`; add `draft`/`PATCH inquiry`/`mark-sent` endpoints
- `backend/app/main.py` — register `inquiry_prompt_api.router`
- `backend/tests/unit/test_extractor.py` — assert flags round-trip
- `backend/tests/unit/test_pipeline_extract.py` — assert flags persisted

### Frontend — new files
- `frontend/src/api/inquiry.ts` — typed client for settings prompt
- `frontend/src/components/InquiryPanel.tsx` — panel on application detail
- `frontend/src/pages/SettingsInquiryPrompt.tsx` — settings page

### Frontend — modified files
- `frontend/src/api/applications.ts` — add new types + methods
- `frontend/src/pages/ApplicationDetail.tsx` — mount `InquiryPanel`
- `frontend/src/App.tsx` — add settings route + nav link

---

## Task 1: Extend extractor schema with two boolean flags (unit-test first)

**Files:**
- Modify: `backend/app/extractor/schemas.py`
- Modify: `backend/app/extractor/prompts.py`
- Test: `backend/tests/unit/test_extractor.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_extractor.py`:

```python
def test_extract_parses_inquiry_flags():
    payload = {
        "language": "de",
        "mentions_home_office_policy": True,
        "mentions_part_time": False,
    }
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    result = extract("blob", llm)
    assert result.mentions_home_office_policy is True
    assert result.mentions_part_time is False


def test_extract_inquiry_flags_default_to_false():
    payload = {"language": "de"}
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    result = extract("blob", llm)
    assert result.mentions_home_office_policy is False
    assert result.mentions_part_time is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/unit/test_extractor.py -v
```
Expected: both new tests FAIL with `ValidationError` / `AttributeError` (fields not defined yet).

- [ ] **Step 3: Add the two fields to `ExtractedJobPosting`**

In `backend/app/extractor/schemas.py`, append before the closing of the class (after `suggested_labels`):

```python
    mentions_home_office_policy: bool = Field(
        default=False,
        description=(
            "True iff the posting explicitly states a home office / remote / "
            "hybrid policy with frequency or percentage (e.g. 'Homeoffice "
            "möglich', '2 Tage pro Woche remote', 'fully remote', "
            "'hybrid 60/40'). False if home office is not mentioned at all "
            "or only vaguely implied."
        ),
    )
    mentions_part_time: bool = Field(
        default=False,
        description=(
            "True iff the posting explicitly mentions part-time availability "
            "(e.g. 'Teilzeit möglich', '80%', 'part-time'). False if only "
            "Vollzeit / full-time is mentioned or nothing is said about it."
        ),
    )
```

- [ ] **Step 4: Extend the extractor SYSTEM prompt**

Replace `SYSTEM` in `backend/app/extractor/prompts.py` with:

```python
SYSTEM = (
    "You extract structured data from job postings. "
    "Return ONLY JSON matching the schema. "
    "If a field is not present, leave it null or empty list. "
    "Detect the posting language as ISO 639-1. "
    "For required_documents, only use the exact values listed in the schema. "
    "For suggested_labels, only pick from the exact values listed in the schema. "
    "Always include one company-size bucket when determinable. "
    "Set mentions_home_office_policy=true only if the posting explicitly "
    "mentions a home office / remote / hybrid policy with a clear frequency "
    "or percentage. Set mentions_part_time=true only if the posting explicitly "
    "mentions part-time / Teilzeit availability or a percentage <100%. "
    "Otherwise both flags are false."
)
```

- [ ] **Step 5: Run extractor tests to verify they pass**

```bash
cd backend && pytest tests/unit/test_extractor.py -v
```
Expected: PASS (both new + existing tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/extractor/schemas.py backend/app/extractor/prompts.py backend/tests/unit/test_extractor.py
git commit -m "feat(extractor): mentions_home_office_policy / mentions_part_time flags"
```

---

## Task 2: Add DB columns for new flags + inquiry persistence + prompt template

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/alembic/versions/<rev>_pre_application_inquiry.py`

- [ ] **Step 1: Add ORM columns / model**

In `backend/app/db/models.py`:

a) Inside `class JobPosting`, after `required_documents`, add:

```python
    mentions_home_office_policy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mentions_part_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
```

b) Inside `class Application`, after `posting_checked_at`, add:

```python
    inquiry_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    inquiry_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    inquiry_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

c) After the existing `AnschreibenVariant` class, add a new model:

```python
class InquiryPromptTemplate(Base):
    __tablename__ = "inquiry_prompt_template"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), unique=True)
    source_md: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Generate a revision id**

Find the current head:

```bash
cd backend && uv run alembic heads
```

Note the head revision (currently `f9e1b2c3d4a5`). Pick a new id, e.g. `b7c8d9e0f1a2`.

- [ ] **Step 3: Create the migration file**

Create `backend/alembic/versions/b7c8d9e0f1a2_pre_application_inquiry.py`:

```python
"""pre-application inquiry: flags + persistence + prompt template

Revision ID: b7c8d9e0f1a2
Revises: f9e1b2c3d4a5
Create Date: 2026-05-22 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "f9e1b2c3d4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_posting",
        sa.Column("mentions_home_office_policy", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "job_posting",
        sa.Column("mentions_part_time", sa.Boolean(), nullable=True),
    )
    op.add_column("application", sa.Column("inquiry_subject", sa.Text(), nullable=True))
    op.add_column("application", sa.Column("inquiry_body", sa.Text(), nullable=True))
    op.add_column("application", sa.Column("inquiry_sent_at", sa.DateTime(), nullable=True))
    op.create_table(
        "inquiry_prompt_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_md", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("inquiry_prompt_template")
    op.drop_column("application", "inquiry_sent_at")
    op.drop_column("application", "inquiry_body")
    op.drop_column("application", "inquiry_subject")
    op.drop_column("job_posting", "mentions_part_time")
    op.drop_column("job_posting", "mentions_home_office_policy")
```

- [ ] **Step 4: Verify alembic loads the migration without errors**

```bash
cd backend && uv run alembic heads
```
Expected: prints `b7c8d9e0f1a2 (head)`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/b7c8d9e0f1a2_pre_application_inquiry.py
git commit -m "feat(db): inquiry columns + inquiry_prompt_template table"
```

---

## Task 3: Pipeline persists the two new flags

**Files:**
- Modify: `backend/app/pipeline/extract.py`
- Test: `backend/tests/unit/test_pipeline_extract.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_pipeline_extract.py`:

```python
def test_run_extract_persists_inquiry_flags():
    payload = {
        "title": "Dev",
        "company": "Acme",
        "language": "de",
        "mentions_home_office_policy": True,
        "mentions_part_time": False,
    }
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None
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
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))

    run_extract(db, app, "x" * 1000, "/tmp/raw.html", llm)

    assert captured["jp"].mentions_home_office_policy is True
    assert captured["jp"].mentions_part_time is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && pytest tests/unit/test_pipeline_extract.py::test_run_extract_persists_inquiry_flags -v
```
Expected: FAIL (`AttributeError` — `JobPosting` got unexpected keyword).

- [ ] **Step 3: Wire the fields in `run_extract`**

In `backend/app/pipeline/extract.py`, inside the `JobPosting(...)` constructor call (currently ends with `required_documents=job.required_documents,`), add two more arguments:

```python
        required_documents=job.required_documents,
        mentions_home_office_policy=job.mentions_home_office_policy,
        mentions_part_time=job.mentions_part_time,
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && pytest tests/unit/test_pipeline_extract.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/extract.py backend/tests/unit/test_pipeline_extract.py
git commit -m "feat(pipeline): persist inquiry flags onto JobPosting"
```

---

## Task 4: Inquiry module — schemas, prompts, draft function

**Files:**
- Create: `backend/app/inquiry/__init__.py`
- Create: `backend/app/inquiry/schemas.py`
- Create: `backend/app/inquiry/prompts.py`
- Test: `backend/tests/unit/test_inquiry_prompts.py`
- Test: `backend/tests/unit/test_inquiry_draft.py`

- [ ] **Step 1: Write failing prompt-builder tests**

Create `backend/tests/unit/test_inquiry_prompts.py`:

```python
from app.extractor.schemas import ExtractedJobPosting
from app.inquiry.prompts import DEFAULT_TEMPLATE, user_prompt


def _job(**kw) -> ExtractedJobPosting:
    base = {"language": "de", "title": "Dev", "company": "Acme"}
    base.update(kw)
    return ExtractedJobPosting(**base)


def test_default_template_is_non_empty_string():
    assert isinstance(DEFAULT_TEMPLATE, str) and len(DEFAULT_TEMPLATE) > 0


def test_user_prompt_includes_only_home_office_when_only_ho_missing():
    p = user_prompt(
        job=_job(), language="de", ask_home_office=True, ask_part_time=False,
    )
    assert "Home Office" in p or "home office" in p.lower()
    assert "80" not in p and "Teilzeit" not in p


def test_user_prompt_includes_only_part_time_when_only_pt_missing():
    p = user_prompt(
        job=_job(), language="de", ask_home_office=False, ask_part_time=True,
    )
    assert "80" in p or "Teilzeit" in p
    assert "Home Office" not in p and "home office" not in p.lower()


def test_user_prompt_includes_both_when_both_missing():
    p = user_prompt(
        job=_job(), language="en", ask_home_office=True, ask_part_time=True,
    )
    text = p.lower()
    assert ("home office" in text or "homeoffice" in text)
    assert ("80" in p or "teilzeit" in text or "part-time" in text)


def test_user_prompt_carries_language_and_company():
    p = user_prompt(
        job=_job(company="Acme GmbH"), language="en",
        ask_home_office=True, ask_part_time=False,
    )
    assert "Acme GmbH" in p
    assert "en" in p
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && pytest tests/unit/test_inquiry_prompts.py -v
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `backend/app/inquiry/schemas.py`**

```python
from pydantic import BaseModel


class InquiryEmail(BaseModel):
    subject: str
    body: str
```

- [ ] **Step 4: Create `backend/app/inquiry/prompts.py`**

```python
from app.extractor.schemas import ExtractedJobPosting


DEFAULT_TEMPLATE = (
    "Du hilfst dem Bewerber, eine kurze, höfliche Vorab-Mail an den "
    "Ansprechpartner einer Stellenausschreibung zu schreiben. Ziel: zwei "
    "offene Punkte vor der eigentlichen Bewerbung klären.\n\n"
    "Regeln:\n"
    "- Maximal acht Sätze.\n"
    "- Nur die im Nutzer-Prompt explizit genannten Fragen stellen, keine "
    "  weiteren Themen.\n"
    "- Höflicher, professioneller Ton; keine Selbstvermarktung, kein CV-Pitch.\n"
    "- Am Ende fragen, ob eine Bewerbung unter diesen Bedingungen willkommen "
    "  ist.\n"
    "- Antwort als JSON {\"subject\": \"...\", \"body\": \"...\"}.\n"
    "- Sprache exakt an die im Nutzer-Prompt angegebene Zielsprache anpassen "
    "  (z.B. 'de' oder 'en')."
)

_HO_TOPIC_DE = (
    "Wie viele Tage Home Office pro Woche sind möglich, unter der "
    "Voraussetzung, dass Kundenprojekte und sonstige Anforderungen erfüllt "
    "sind?"
)
_HO_TOPIC_EN = (
    "How many days of home office per week are possible, assuming customer "
    "projects and other requirements are met?"
)
_PT_TOPIC_DE = (
    "Wäre eine 80%-Stelle (Montag bis Donnerstag) grundsätzlich denkbar?"
)
_PT_TOPIC_EN = (
    "Would an 80% position (Monday to Thursday) be possible in principle?"
)


def _topic_lines(language: str, ask_ho: bool, ask_pt: bool) -> list[str]:
    lang = (language or "de").lower()
    out: list[str] = []
    if ask_ho:
        out.append(_HO_TOPIC_EN if lang == "en" else _HO_TOPIC_DE)
    if ask_pt:
        out.append(_PT_TOPIC_EN if lang == "en" else _PT_TOPIC_DE)
    return out


def user_prompt(
    *,
    job: ExtractedJobPosting,
    language: str,
    ask_home_office: bool,
    ask_part_time: bool,
) -> str:
    topics = _topic_lines(language, ask_home_office, ask_part_time)
    bullet_block = "\n".join(f"- {t}" for t in topics)
    return (
        f"Zielsprache: {language}\n"
        f"Stelle: {job.title or 'unbekannt'} bei {job.company or 'unbekannt'}\n"
        f"Ansprechpartner: {job.contact_person or 'unbekannt'}\n\n"
        f"Fragen, die in der Mail vorkommen MUESSEN (in dieser Reihenfolge):\n"
        f"{bullet_block}"
    )
```

- [ ] **Step 5: Verify prompt tests pass**

```bash
cd backend && pytest tests/unit/test_inquiry_prompts.py -v
```
Expected: PASS.

- [ ] **Step 6: Write failing test for `draft()`**

Create `backend/tests/unit/test_inquiry_draft.py`:

```python
import json

from app.extractor.schemas import ExtractedJobPosting
from app.inquiry import draft
from app.inquiry.schemas import InquiryEmail
from tests.fakes.llm import FakeLLM


def _job(**kw) -> ExtractedJobPosting:
    base = {"language": "de", "title": "Dev", "company": "Acme"}
    base.update(kw)
    return ExtractedJobPosting(**base)


def test_draft_parses_llm_json_into_inquiry_email():
    payload = {"subject": "Frage", "body": "Hallo …"}
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    result = draft(
        job=_job(),
        language="de",
        ask_home_office=True,
        ask_part_time=True,
        system_md="SYS",
        llm=llm,
    )
    assert isinstance(result, InquiryEmail)
    assert result.subject == "Frage"
    assert result.body == "Hallo …"


def test_draft_uses_provided_system_prompt():
    seen = {}

    def handler(messages, schema):
        seen["sys"] = messages[0]["content"]
        return json.dumps({"subject": "s", "body": "b"})

    draft(
        job=_job(),
        language="de",
        ask_home_office=True,
        ask_part_time=False,
        system_md="CUSTOM-SYSTEM-PROMPT",
        llm=FakeLLM(handler=handler),
    )
    assert seen["sys"] == "CUSTOM-SYSTEM-PROMPT"
```

- [ ] **Step 7: Run to verify they fail**

```bash
cd backend && pytest tests/unit/test_inquiry_draft.py -v
```
Expected: FAIL — `draft` not importable.

- [ ] **Step 8: Create `backend/app/inquiry/__init__.py`**

```python
from app.extractor.schemas import ExtractedJobPosting
from app.inquiry.prompts import user_prompt
from app.inquiry.schemas import InquiryEmail
from app.llm.base import LLMClient


def draft(
    *,
    job: ExtractedJobPosting,
    language: str,
    ask_home_office: bool,
    ask_part_time: bool,
    system_md: str,
    llm: LLMClient,
) -> InquiryEmail:
    schema = InquiryEmail.model_json_schema()
    raw = llm.complete(
        [
            {"role": "system", "content": system_md},
            {
                "role": "user",
                "content": user_prompt(
                    job=job,
                    language=language,
                    ask_home_office=ask_home_office,
                    ask_part_time=ask_part_time,
                ),
            },
        ],
        json_schema=schema,
        temperature=0.3,
    )
    return InquiryEmail.model_validate_json(raw)
```

- [ ] **Step 9: Run all inquiry tests**

```bash
cd backend && pytest tests/unit/test_inquiry_prompts.py tests/unit/test_inquiry_draft.py -v
```
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/inquiry backend/tests/unit/test_inquiry_prompts.py backend/tests/unit/test_inquiry_draft.py
git commit -m "feat(inquiry): prompt builder + draft() LLM call"
```

---

## Task 5: Settings endpoint — GET/PUT `/api/settings/inquiry-prompt`

**Files:**
- Create: `backend/app/api/inquiry_prompt.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_inquiry_prompt_endpoint.py`

- [ ] **Step 1: Write failing integration test**

Create `backend/tests/integration/test_inquiry_prompt_endpoint.py`:

```python
from app.inquiry.prompts import DEFAULT_TEMPLATE


def test_get_seeds_default_on_first_call(auth_user):
    client, _ = auth_user
    r = client.get("/api/settings/inquiry-prompt")
    assert r.status_code == 200
    assert r.json()["source_md"] == DEFAULT_TEMPLATE


def test_put_updates_source_md(auth_user):
    client, _ = auth_user
    client.get("/api/settings/inquiry-prompt")
    r = client.put(
        "/api/settings/inquiry-prompt",
        json={"source_md": "custom prompt"},
    )
    assert r.status_code == 200
    assert r.json()["source_md"] == "custom prompt"

    again = client.get("/api/settings/inquiry-prompt")
    assert again.json()["source_md"] == "custom prompt"


def test_get_requires_auth(app_client):
    r = app_client.get("/api/settings/inquiry-prompt")
    assert r.status_code == 401
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && pytest tests/integration/test_inquiry_prompt_endpoint.py -v
```
Expected: FAIL — 404 (endpoint missing).

- [ ] **Step 3: Create `backend/app/api/inquiry_prompt.py`**

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import InquiryPromptTemplate, User
from app.inquiry.prompts import DEFAULT_TEMPLATE

router = APIRouter(prefix="/api/settings/inquiry-prompt", tags=["inquiry-prompt"])


class InquiryPromptOut(BaseModel):
    source_md: str


class InquiryPromptPut(BaseModel):
    source_md: str


def _get_or_seed(db: Session, user: User) -> InquiryPromptTemplate:
    row = db.query(InquiryPromptTemplate).filter_by(user_id=user.id).first()
    if row is None:
        row = InquiryPromptTemplate(user_id=user.id, source_md=DEFAULT_TEMPLATE)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=InquiryPromptOut)
def get_prompt(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    row = _get_or_seed(db, user)
    return InquiryPromptOut(source_md=row.source_md)


@router.put("", response_model=InquiryPromptOut)
def put_prompt(
    body: InquiryPromptPut,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    row = _get_or_seed(db, user)
    row.source_md = body.source_md
    db.commit()
    db.refresh(row)
    return InquiryPromptOut(source_md=row.source_md)
```

- [ ] **Step 4: Mount the router**

In `backend/app/main.py`, add the import next to the other `api` imports:

```python
from app.api import inquiry_prompt as inquiry_prompt_api
```

And inside `create_app` after `app.include_router(labels_api.router)`:

```python
    app.include_router(inquiry_prompt_api.router)
```

- [ ] **Step 5: Run the integration test**

```bash
cd backend && pytest tests/integration/test_inquiry_prompt_endpoint.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/inquiry_prompt.py backend/app/main.py backend/tests/integration/test_inquiry_prompt_endpoint.py
git commit -m "feat(api): editable inquiry prompt template settings endpoint"
```

---

## Task 6: Application endpoints — draft / patch / mark-sent + extended response

**Files:**
- Modify: `backend/app/api/applications.py`
- Test: `backend/tests/integration/test_inquiry_endpoints.py`

- [ ] **Step 1: Extend `JobPostingOut` + `ApplicationOut`**

In `backend/app/api/applications.py`, inside `JobPostingOut`, append:

```python
    mentions_home_office_policy: bool | None = None
    mentions_part_time: bool | None = None
```

Inside `ApplicationOut`, append (after `job_posting: JobPostingOut | None`):

```python
    inquiry_subject: str | None
    inquiry_body: str | None
    inquiry_sent_at: datetime | None
```

Add an import at the top:

```python
from datetime import datetime
```

And update `ApplicationOut.from_orm_row` to include the new fields:

```python
            inquiry_subject=app.inquiry_subject,
            inquiry_body=app.inquiry_body,
            inquiry_sent_at=app.inquiry_sent_at,
```

- [ ] **Step 2: Write failing integration tests**

Create `backend/tests/integration/test_inquiry_endpoints.py`:

```python
import json
import uuid

from app.db.models import Application, JobPosting, JobState
from app.inquiry.prompts import DEFAULT_TEMPLATE


def _make_app(db_session, user, *, ho=False, pt=False, email="hr@acme.test"):
    a = Application(
        user_id=user.id,
        url="https://x.test/u",
        url_hash="h" * 64,
        job_state=JobState.extracted,
        language="de",
    )
    db_session.add(a)
    db_session.flush()
    jp = JobPosting(
        application_id=a.id,
        raw_text="x",
        title="Dev",
        company="Acme",
        application_email=email,
        language="de",
        mentions_home_office_policy=ho,
        mentions_part_time=pt,
    )
    db_session.add(jp)
    db_session.commit()
    return a


def _patch_llm(monkeypatch, payload):
    from app.api import applications as apps_module

    def fake_llm():
        from tests.fakes.llm import FakeLLM
        return FakeLLM(handler=lambda m, s: json.dumps(payload))

    monkeypatch.setattr(apps_module, "_inquiry_llm", fake_llm)


def test_draft_creates_inquiry_when_both_flags_false(
    auth_user, db_session, monkeypatch,
):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)
    _patch_llm(monkeypatch, {"subject": "Frage", "body": "Hallo …"})

    r = client.post(f"/api/applications/{a.id}/inquiry/draft")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["subject"] == "Frage"
    assert data["body"] == "Hallo …"
    assert data["recipient"] == "hr@acme.test"

    # ApplicationOut now exposes the saved values
    g = client.get(f"/api/applications/{a.id}").json()
    assert g["inquiry_subject"] == "Frage"
    assert g["inquiry_body"] == "Hallo …"


def test_draft_rejected_when_both_flags_true(
    auth_user, db_session, monkeypatch,
):
    client, user = auth_user
    a = _make_app(db_session, user, ho=True, pt=True)
    _patch_llm(monkeypatch, {"subject": "x", "body": "x"})

    r = client.post(f"/api/applications/{a.id}/inquiry/draft")
    assert r.status_code == 400


def test_patch_updates_subject_and_body(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)
    _patch_llm(monkeypatch, {"subject": "s", "body": "b"})
    client.post(f"/api/applications/{a.id}/inquiry/draft")

    r = client.patch(
        f"/api/applications/{a.id}/inquiry",
        json={"subject": "edited", "body": "edited body"},
    )
    assert r.status_code == 200
    assert r.json()["subject"] == "edited"
    g = client.get(f"/api/applications/{a.id}").json()
    assert g["inquiry_subject"] == "edited"
    assert g["inquiry_body"] == "edited body"


def test_mark_sent_sets_timestamp(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)
    _patch_llm(monkeypatch, {"subject": "s", "body": "b"})
    client.post(f"/api/applications/{a.id}/inquiry/draft")

    r = client.post(f"/api/applications/{a.id}/inquiry/mark-sent")
    assert r.status_code == 200
    assert r.json()["sent_at"] is not None

    g = client.get(f"/api/applications/{a.id}").json()
    assert g["inquiry_sent_at"] is not None


def test_draft_seeds_default_prompt_when_missing(auth_user, db_session, monkeypatch):
    client, user = auth_user
    a = _make_app(db_session, user, ho=False, pt=False)

    seen = {}

    def fake_llm():
        from tests.fakes.llm import FakeLLM

        def handler(messages, schema):
            seen["sys"] = messages[0]["content"]
            return json.dumps({"subject": "s", "body": "b"})

        return FakeLLM(handler=handler)

    from app.api import applications as apps_module
    monkeypatch.setattr(apps_module, "_inquiry_llm", fake_llm)

    client.post(f"/api/applications/{a.id}/inquiry/draft")
    assert seen["sys"] == DEFAULT_TEMPLATE


def test_draft_404_when_other_user(auth_user, db_session, monkeypatch):
    client, _ = auth_user
    r = client.post(f"/api/applications/{uuid.uuid4()}/inquiry/draft")
    assert r.status_code == 404
```

- [ ] **Step 3: Run to verify failure**

```bash
cd backend && pytest tests/integration/test_inquiry_endpoints.py -v
```
Expected: FAIL — endpoints missing.

- [ ] **Step 4: Add the endpoints + LLM indirection**

In `backend/app/api/applications.py`:

a) Add imports near the top (keep alphabetical-ish with existing imports):

```python
from app.db.models import InquiryPromptTemplate
from app.inquiry import draft as inquiry_draft
from app.inquiry.prompts import DEFAULT_TEMPLATE
from app.llm.base import LLMClient
from app.llm.groq import GroqClient
```

b) Add a helper near the other `_start_*` helpers (so tests can `monkeypatch._inquiry_llm`):

```python
def _inquiry_llm() -> LLMClient:
    s = get_settings()
    return GroqClient(api_key=s.llm_api_key, model=s.llm_model, base_url=s.llm_base_url)
```

Also add `from app.config import get_settings` if not already imported (it isn't — replace the existing `from app.config import Settings` line with `from app.config import Settings, get_settings`).

c) Add Pydantic models for the new requests/responses (right after `class StatusUpdate`):

```python
class InquiryPatch(BaseModel):
    subject: str
    body: str


class InquiryDraftOut(BaseModel):
    subject: str
    body: str
    recipient: str | None
    sent_at: datetime | None = None


class InquiryMarkSentOut(BaseModel):
    sent_at: datetime
```

d) Add three endpoints at the bottom of the file (before the labels routes is fine, or after — keep grouped):

```python
def _build_inquiry_job(app_row: Application):
    from app.extractor.schemas import ExtractedJobPosting

    jp = app_row.job_posting
    return ExtractedJobPosting(
        title=jp.title,
        company=jp.company,
        location=jp.location,
        contact_person=jp.contact_person,
        language=jp.language or "de",
    )


def _ensure_inquiry_prompt(db: Session, user: User) -> str:
    row = db.query(InquiryPromptTemplate).filter_by(user_id=user.id).first()
    if row is None:
        row = InquiryPromptTemplate(user_id=user.id, source_md=DEFAULT_TEMPLATE)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row.source_md


@router.post("/{aid}/inquiry/draft", response_model=InquiryDraftOut)
def draft_inquiry(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if app_row.job_posting is None:
        raise HTTPException(400, "no job posting yet")
    ask_ho = not bool(app_row.job_posting.mentions_home_office_policy)
    ask_pt = not bool(app_row.job_posting.mentions_part_time)
    if not ask_ho and not ask_pt:
        raise HTTPException(400, "Posting covers both topics.")
    system_md = _ensure_inquiry_prompt(db, user)
    try:
        email = inquiry_draft(
            job=_build_inquiry_job(app_row),
            language=app_row.job_posting.language or app_row.language or "de",
            ask_home_office=ask_ho,
            ask_part_time=ask_pt,
            system_md=system_md,
            llm=_inquiry_llm(),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"draft failed: {exc}") from exc
    app_row.inquiry_subject = email.subject
    app_row.inquiry_body = email.body
    db.commit()
    db.refresh(app_row)
    return InquiryDraftOut(
        subject=email.subject,
        body=email.body,
        recipient=app_row.job_posting.application_email,
        sent_at=app_row.inquiry_sent_at,
    )


@router.patch("/{aid}/inquiry", response_model=InquiryDraftOut)
def patch_inquiry(
    aid: uuid.UUID,
    body: InquiryPatch,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    app_row.inquiry_subject = body.subject
    app_row.inquiry_body = body.body
    db.commit()
    db.refresh(app_row)
    return InquiryDraftOut(
        subject=app_row.inquiry_subject or "",
        body=app_row.inquiry_body or "",
        recipient=(app_row.job_posting.application_email if app_row.job_posting else None),
        sent_at=app_row.inquiry_sent_at,
    )


@router.post("/{aid}/inquiry/mark-sent", response_model=InquiryMarkSentOut)
def mark_inquiry_sent(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    from datetime import datetime as _dt
    app_row = _load_owned(db, aid, user)
    app_row.inquiry_sent_at = _dt.utcnow()
    db.commit()
    db.refresh(app_row)
    return InquiryMarkSentOut(sent_at=app_row.inquiry_sent_at)
```

- [ ] **Step 5: Run the integration tests**

```bash
cd backend && pytest tests/integration/test_inquiry_endpoints.py -v
```
Expected: PASS.

- [ ] **Step 6: Run the full backend test suite to catch regressions**

```bash
cd backend && pytest
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/applications.py backend/tests/integration/test_inquiry_endpoints.py
git commit -m "feat(api): inquiry draft/patch/mark-sent endpoints"
```

---

## Task 7: Frontend types + API client

**Files:**
- Modify: `frontend/src/api/applications.ts`
- Create: `frontend/src/api/inquiry.ts`

- [ ] **Step 1: Extend `JobPosting` and `Application` types**

In `frontend/src/api/applications.ts`:

Inside the `JobPosting` type, after `required_documents`, add:

```ts
  mentions_home_office_policy: boolean | null;
  mentions_part_time: boolean | null;
```

Inside the `Application` type, after `job_posting`, add:

```ts
  inquiry_subject: string | null;
  inquiry_body: string | null;
  inquiry_sent_at: string | null;
```

- [ ] **Step 2: Add inquiry methods on the `applications` object**

Inside the `applications = { ... }` object, before the closing brace, add:

```ts
  draftInquiry: (id: string) =>
    api<{ subject: string; body: string; recipient: string | null; sent_at: string | null }>(
      `/api/applications/${id}/inquiry/draft`,
      { method: "POST" },
    ),
  patchInquiry: (id: string, body: { subject: string; body: string }) =>
    api<{ subject: string; body: string; recipient: string | null; sent_at: string | null }>(
      `/api/applications/${id}/inquiry`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  markInquirySent: (id: string) =>
    api<{ sent_at: string }>(
      `/api/applications/${id}/inquiry/mark-sent`,
      { method: "POST" },
    ),
```

- [ ] **Step 3: Create `frontend/src/api/inquiry.ts`**

```ts
import { api } from "./client";

export type InquiryPrompt = { source_md: string };

export const inquiryPrompt = {
  get: () => api<InquiryPrompt>("/api/settings/inquiry-prompt"),
  put: (source_md: string) =>
    api<InquiryPrompt>("/api/settings/inquiry-prompt", {
      method: "PUT",
      body: JSON.stringify({ source_md }),
    }),
};
```

- [ ] **Step 4: Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/applications.ts frontend/src/api/inquiry.ts
git commit -m "feat(frontend): inquiry types + API client"
```

---

## Task 8: Settings page — `SettingsInquiryPrompt`

**Files:**
- Create: `frontend/src/pages/SettingsInquiryPrompt.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the page**

`frontend/src/pages/SettingsInquiryPrompt.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { inquiryPrompt } from "../api/inquiry";

export default function SettingsInquiryPrompt() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["inquiry-prompt"],
    queryFn: () => inquiryPrompt.get(),
  });
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (q.data && !dirty) setDraft(q.data.source_md);
  }, [q.data, dirty]);

  const save = useMutation({
    mutationFn: (s: string) => inquiryPrompt.put(s),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["inquiry-prompt"] });
    },
  });

  if (q.isLoading) return <div className="p-6">Loading…</div>;
  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-2">Pre-application inquiry prompt</h1>
      <p className="text-sm text-slate-500 mb-3">
        System prompt used when drafting the pre-application email. The body of
        the email is built automatically and only includes the topics not
        already covered by the posting (home office, 80% Mon–Thu).
      </p>
      <textarea
        className="border rounded p-2 w-full font-mono text-sm"
        rows={18}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          setDirty(true);
        }}
      />
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate(draft)}
        >
          Save
        </button>
        {save.isError && (
          <span className="text-rose-600 text-sm">
            {(save.error as Error).message}
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add the route + nav link in `App.tsx`**

a) Add the import at the top of `frontend/src/App.tsx` next to other settings page imports:

```tsx
import SettingsInquiryPrompt from "./pages/SettingsInquiryPrompt";
```

b) Inside `Nav()` add a nav item before the LLM one:

```tsx
      {item("/settings/inquiry-prompt", "Inquiry prompt")}
```

c) Add a route inside the `<Routes>` block (place it next to the other `/settings/*` routes):

```tsx
      <Route
        path="/settings/inquiry-prompt"
        element={
          <ProtectedShell>
            <SettingsInquiryPrompt />
          </ProtectedShell>
        }
      />
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/SettingsInquiryPrompt.tsx frontend/src/App.tsx
git commit -m "feat(frontend): inquiry prompt settings page"
```

---

## Task 9: Detail page — `InquiryPanel`

**Files:**
- Create: `frontend/src/components/InquiryPanel.tsx`
- Modify: `frontend/src/pages/ApplicationDetail.tsx`

- [ ] **Step 1: Create the panel**

`frontend/src/components/InquiryPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";
import type { Application } from "../api/applications";

type Props = { app: Application };

function mailto(to: string | null, subject: string, body: string): string {
  const params = new URLSearchParams();
  params.set("subject", subject);
  params.set("body", body);
  return `mailto:${to ?? ""}?${params.toString()}`;
}

export function InquiryPanel({ app }: Props) {
  const qc = useQueryClient();
  const jp = app.job_posting;
  const ho = jp?.mentions_home_office_policy === true;
  const pt = jp?.mentions_part_time === true;
  const bothCovered = ho && pt;
  const pipelineReady = ["extracted", "ready"].includes(app.job_state);
  const hasDraft = app.inquiry_subject != null || app.inquiry_body != null;

  const [subject, setSubject] = useState(app.inquiry_subject ?? "");
  const [body, setBody] = useState(app.inquiry_body ?? "");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!dirty) {
      setSubject(app.inquiry_subject ?? "");
      setBody(app.inquiry_body ?? "");
    }
  }, [app.inquiry_subject, app.inquiry_body, dirty]);

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["application", app.id] });

  const draft = useMutation({
    mutationFn: () => applications.draftInquiry(app.id),
    onSuccess: () => {
      setDirty(false);
      invalidate();
    },
  });
  const save = useMutation({
    mutationFn: () => applications.patchInquiry(app.id, { subject, body }),
    onSuccess: () => {
      setDirty(false);
      invalidate();
    },
  });
  const markSent = useMutation({
    mutationFn: () => applications.markInquirySent(app.id),
    onSuccess: invalidate,
  });

  if (!jp || !pipelineReady) {
    return (
      <div className="bg-white border rounded p-3 mt-4 text-slate-500 text-sm">
        Pre-application inquiry will appear after extraction.
      </div>
    );
  }

  if (bothCovered && !hasDraft) {
    return (
      <div className="bg-white border rounded p-3 mt-4 text-slate-500 text-sm">
        Posting covers home office and part-time — no inquiry needed.
      </div>
    );
  }

  const onDraft = () => {
    if (hasDraft && !confirm("Overwrite the current draft?")) return;
    draft.mutate();
  };

  return (
    <div className="bg-white border rounded p-3 mt-4">
      <div className="flex items-center mb-2">
        <h2 className="font-semibold flex-1">Pre-application inquiry</h2>
        {app.inquiry_sent_at && (
          <span className="text-xs bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded">
            Sent {new Date(app.inquiry_sent_at).toLocaleDateString()}
          </span>
        )}
      </div>

      {!hasDraft ? (
        <button
          type="button"
          className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
          disabled={draft.isPending}
          onClick={onDraft}
        >
          Draft inquiry
        </button>
      ) : (
        <>
          <label className="block text-xs uppercase text-slate-500 mt-1">Subject</label>
          <input
            className="border rounded px-2 py-1 w-full"
            value={subject}
            onChange={(e) => {
              setSubject(e.target.value);
              setDirty(true);
            }}
          />
          <label className="block text-xs uppercase text-slate-500 mt-2">Body</label>
          <textarea
            className="border rounded px-2 py-1 w-full font-mono text-sm"
            rows={10}
            value={body}
            onChange={(e) => {
              setBody(e.target.value);
              setDirty(true);
            }}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
              disabled={!dirty || save.isPending}
              onClick={() => save.mutate()}
            >
              Save
            </button>
            <a
              href={mailto(jp.application_email, subject, body)}
              className={`px-3 py-1 rounded border ${
                jp.application_email ? "border-blue-600 text-blue-700" : "border-slate-300 text-slate-400 pointer-events-none"
              }`}
              title={jp.application_email ? "" : "No recipient on file"}
            >
              Open in mail
            </a>
            <button
              type="button"
              className="bg-emerald-600 text-white px-3 py-1 rounded disabled:opacity-50"
              disabled={markSent.isPending}
              onClick={() => markSent.mutate()}
            >
              Mark sent
            </button>
            <button
              type="button"
              className="bg-slate-200 text-slate-800 px-3 py-1 rounded disabled:opacity-50"
              disabled={draft.isPending}
              onClick={onDraft}
            >
              Regenerate
            </button>
          </div>
          {(save.isError || draft.isError || markSent.isError) && (
            <div className="text-rose-600 text-sm mt-2">
              {(save.error || draft.error || markSent.error as Error)?.toString()}
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Mount on `ApplicationDetail`**

In `frontend/src/pages/ApplicationDetail.tsx`:

a) Add the import next to the other component imports:

```tsx
import { InquiryPanel } from "../components/InquiryPanel";
```

b) Inside the JSX, just after the closing `</div>` of the JobPosting card (the `<div className="bg-white border rounded p-3">` block), add:

```tsx
        <InquiryPanel app={a} />
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/InquiryPanel.tsx frontend/src/pages/ApplicationDetail.tsx
git commit -m "feat(frontend): InquiryPanel on application detail"
```

---

## Task 10: Verification — full backend test run + manual UI smoke

**Files:** none

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && pytest
```
Expected: all PASS.

- [ ] **Step 2: Run frontend type-check + build**

```bash
cd frontend && npx tsc --noEmit && npx vite build
```
Expected: both succeed without errors.

- [ ] **Step 3: Bring up the stack and smoke-test the UI**

```bash
docker compose up --build -d
```

Open http://localhost:8080 and:

1. Verify the nav shows "Inquiry prompt".
2. Visit `/settings/inquiry-prompt` — page loads with the default template seeded; edit and save; reload — value persisted.
3. Add a new application whose posting omits both topics (or backfill flags to false in DB). Wait until extraction finishes.
4. Open the detail page — `InquiryPanel` shows a "Draft inquiry" button.
5. Click it — subject/body populate, mailto link looks well-formed (URL-encoded subject/body).
6. Edit body, click Save, reload — edits persist.
7. Click "Mark sent" — green "Sent {date}" badge appears, panel becomes read-only.
8. Add an application whose posting mentions both topics — panel shows the "Posting covers home office and part-time" hint instead of a button.

- [ ] **Step 4: Tear down**

```bash
docker compose down
```

- [ ] **Step 5: Final commit (only if any small fix was required during smoke test)**

Otherwise the feature is complete and the prior commits already cover it.

---

## Self-review notes

- Every spec requirement maps to a task: schema flags (T1) → DB cols + migration (T2) → pipeline persistence (T3) → inquiry module (T4) → settings endpoint (T5) → app endpoints (T6) → frontend types (T7) → settings page (T8) → InquiryPanel (T9) → verification (T10).
- Field names are consistent across backend/frontend: `mentions_home_office_policy`, `mentions_part_time`, `inquiry_subject`, `inquiry_body`, `inquiry_sent_at`, `source_md`.
- No placeholders. Each code step has full code; each test step has full test code; each command step has the exact command and expected outcome.
- `_inquiry_llm` is exposed as a module-level helper specifically so tests can monkeypatch it without touching Groq.
- Legacy postings with null flags are treated as `false` (UI button enabled), matching the design doc.
