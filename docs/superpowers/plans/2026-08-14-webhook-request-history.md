# Webhook Request History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a full audit record of every inbound-email webhook request (raw body, headers, source IP, processing outcome) and surface it as a browsable list + detail page in the app.

**Architecture:** Add a `WebhookRequest` ORM model + Alembic migration. Refactor the `inbound_email` endpoint so a single row is written on every code path via `try/finally` (HTTPExceptions recorded then re-raised, response bodies unchanged). Add two authed read endpoints (list summary + detail). Frontend gets an api module, a Settings page with a table + detail modal, and route/nav wiring.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Alembic, Pydantic v2, Postgres (testcontainers in tests), React + TanStack Query + Tailwind.

---

## Reference facts (verified against the codebase)

- `_uuid` in `models.py` is a module-level `def _uuid() -> uuid.UUID` (line 124) used as `default=_uuid`.
- In `webhooks.py`, `import uuid as _uuid` — there `_uuid` is the **uuid module** (so `_uuid.UUID(app_id)` stays valid). No conflict: the model's `_uuid` lives in `models.py`.
- Model imports already available in `models.py`: `JSON, DateTime, ForeignKey, String, Text, func`, `UUID`, `Mapped`, `mapped_column`, `datetime`, `uuid`.
- Alembic current head: `5606f397a2bf` → new migration's `down_revision`.
- Router already registered: `app/main.py:66 app.include_router(webhooks_api.router)`. No wiring change needed for new endpoints.
- Auth dep: `from app.api.deps import current_user` (session-cookie user).
- UTC datetime serializer: `from app.api.serializers import UtcDateTime`.
- Migration-guard test pattern: `backend/tests/unit/test_posting_offline_migration.py`.
- Integration fixtures: `app_client`, `db_session`, `auth_user` (returns `(client, user)`), in `backend/tests/integration/conftest.py`. Schema is built from models via `create_all` — that is why the migration-guard unit test exists.
- Run backend tests with the venv python (uv is broken in this env):
  `backend/.venv/bin/python -m pytest ...` (run with sandbox off).

## Status/reason convention (documented, validated by tests — NO DB enum)

| status | reason(s) | prior HTTP |
|---|---|---|
| `not_found` | `unknown token` | 404 |
| `rejected` | `payload too large` | 413 |
| `ignored` | `unparseable` \| `llm unavailable` \| `extraction failed` \| `no applications` \| `no match` | 202 |
| `created` | `null` | 202 |

---

## Task 1: `WebhookRequest` model

**Files:**
- Modify: `backend/app/db/models.py` (append new class at end of file)
- Test: `backend/tests/unit/test_webhook_request_model.py` (create)

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/unit/test_webhook_request_model.py`:

```python
from sqlalchemy import inspect

from app.db.models import WebhookRequest


def test_webhook_request_has_expected_columns():
    cols = {c.key for c in inspect(WebhookRequest).columns}
    assert {
        "id",
        "user_id",
        "ingest_token",
        "source_ip",
        "headers",
        "raw_body",
        "status",
        "reason",
        "matched_application_id",
        "created_at",
    } <= cols


def test_webhook_request_tablename():
    assert WebhookRequest.__tablename__ == "webhook_request"


def test_webhook_request_nullability():
    cols = WebhookRequest.__table__.columns
    assert cols["user_id"].nullable is True
    assert cols["matched_application_id"].nullable is True
    assert cols["ingest_token"].nullable is False
    assert cols["status"].nullable is False


def test_webhook_request_construction_defaults():
    r = WebhookRequest(ingest_token="tok", status="ignored")
    assert r.ingest_token == "tok"
    assert r.status == "ignored"
    assert r.user_id is None
    assert r.matched_application_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_webhook_request_model.py -v` (from `backend/`, sandbox off)
Expected: FAIL with `ImportError: cannot import name 'WebhookRequest'`

- [ ] **Step 3: Append the model to `backend/app/db/models.py`**

Add at the very end of the file (all imports already present):

```python
class WebhookRequest(Base):
    """Audit record of a single inbound-email webhook request.

    Written on EVERY code path (success and failure). status/reason are plain
    strings following a documented convention (NO DB enum) to avoid enum-drift
    migration friction; the values are validated by tests, not the database.
    """

    __tablename__ = "webhook_request"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    # Null when the ingest token did not match a user (bad/unknown token).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id"), nullable=True, index=True
    )
    ingest_token: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    matched_application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_webhook_request_model.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/unit/test_webhook_request_model.py
git commit -m "feat(webhook): add WebhookRequest model"
```

---

## Task 2: Alembic migration + migration-guard test

**Files:**
- Create: `backend/alembic/versions/a4b5c6d7e8f9_webhook_request.py`
- Test: `backend/tests/unit/test_webhook_request_migration.py` (create)

- [ ] **Step 1: Write the failing migration-guard test**

Create `backend/tests/unit/test_webhook_request_migration.py`:

```python
"""Guards the webhook_request table against model/migration drift.

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. This DB-free check asserts a
migration actually creates the table, so production deploys don't break.
"""
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_a_migration_creates_webhook_request_table():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        "create_table" in t and '"webhook_request"' in t for t in texts
    ), "no Alembic migration creates the webhook_request table"


def test_migration_defines_core_columns():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    hit = next(
        t for t in texts if "create_table" in t and '"webhook_request"' in t
    )
    for col in (
        '"ingest_token"',
        '"source_ip"',
        '"headers"',
        '"raw_body"',
        '"status"',
        '"reason"',
        '"matched_application_id"',
    ):
        assert col in hit, f"migration missing column {col}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_webhook_request_migration.py -v`
Expected: FAIL on `test_a_migration_creates_webhook_request_table` (assertion error, no migration yet)

- [ ] **Step 3: Create the migration**

Create `backend/alembic/versions/a4b5c6d7e8f9_webhook_request.py`:

```python
"""webhook_request

Revision ID: a4b5c6d7e8f9
Revises: 5606f397a2bf
Create Date: 2026-08-14 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "5606f397a2bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=True,
        ),
        sa.Column("ingest_token", sa.String(64), nullable=False),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("raw_body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column(
            "matched_application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_webhook_request_user_id", "webhook_request", ["user_id"]
    )
    op.create_index(
        "ix_webhook_request_created_at", "webhook_request", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_request_created_at", table_name="webhook_request")
    op.drop_index("ix_webhook_request_user_id", table_name="webhook_request")
    op.drop_table("webhook_request")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_webhook_request_migration.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Verify the revision graph has a single head**

Run: `backend/.venv/bin/python -m alembic heads` (from `backend/`, sandbox off)
Expected: exactly one head, `a4b5c6d7e8f9 (head)`. If `alembic` env can't connect to a DB, skip this check — the guard test already covers the file.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/a4b5c6d7e8f9_webhook_request.py backend/tests/unit/test_webhook_request_migration.py
git commit -m "feat(webhook): migration for webhook_request table"
```

---

## Task 3: Refactor `inbound_email` to record a row on every path

**Files:**
- Modify: `backend/app/api/webhooks.py` (handler `inbound_email`, lines 66-135; imports)
- Test: `backend/tests/integration/test_webhook_api.py` (add tests)

- [ ] **Step 1: Write the failing integration tests**

Append to `backend/tests/integration/test_webhook_api.py`:

```python
def test_webhook_records_row_on_created(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    _, user = auth_user
    app = _app(db_session, user, "Acme GmbH", "acme.example")
    user.ingest_token = "rectok"; db_session.commit()
    db_session.refresh(user)
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()):
        resp = app_client.post(
            "/api/webhooks/inbound-email/rectok",
            json={"from": "jane@acme.example", "subject": "Interview at Acme", "body_text": "..."},
        )
    assert resp.status_code == 202, resp.text
    row = db_session.query(WebhookRequest).filter_by(ingest_token="rectok").one()
    assert row.status == "created"
    assert row.reason is None
    assert row.user_id == user.id
    assert row.matched_application_id == app.id
    assert row.raw_body is not None
    assert isinstance(row.headers, dict)


def test_webhook_records_row_on_no_match(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    _, user = auth_user
    _app(db_session, user, "Acme GmbH", "acme.example")
    user.ingest_token = "nmtok"; db_session.commit()
    db_session.refresh(user)
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()), \
         patch("app.api.webhooks.match_application", return_value=(None, 0.0)):
        resp = app_client.post(
            "/api/webhooks/inbound-email/nmtok",
            json={"from": "x@y.z", "subject": "s", "body_text": "b"},
        )
    assert resp.status_code == 202, resp.text
    row = db_session.query(WebhookRequest).filter_by(ingest_token="nmtok").one()
    assert row.status == "ignored"
    assert row.reason == "no match"
    assert row.matched_application_id is None


def test_webhook_records_row_on_bad_token(app_client, db_session):
    from app.db.models import WebhookRequest

    resp = app_client.post(
        "/api/webhooks/inbound-email/badtok",
        json={"from": "x@y.z", "subject": "s", "body_text": "b"},
    )
    assert resp.status_code == 404
    row = db_session.query(WebhookRequest).filter_by(ingest_token="badtok").one()
    assert row.status == "not_found"
    assert row.user_id is None
```

Note: `match_application` is already imported at module top (`from app.email_ingest.interview_match import Candidate, match_application`), so `patch("app.api.webhooks.match_application", ...)` is valid.

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest tests/integration/test_webhook_api.py -v`
Expected: the 3 new tests FAIL (no `WebhookRequest` rows written yet); the 3 existing tests still PASS.

- [ ] **Step 3: Rewrite the handler with try/finally**

In `backend/app/api/webhooks.py`, add `WebhookRequest` to the models import block (insert alphabetically near the end of the import list, e.g. after `User`):

```python
    User,
    WebhookRequest,
)
```

Replace the whole `inbound_email` function (currently lines 66-135) with:

```python
@router.post("/inbound-email/{ingest_token}", status_code=202)
async def inbound_email(
    ingest_token: str, request: Request, db: Annotated[Session, Depends(db_dep)],
):
    # Mutable holder — one WebhookRequest row is written from `finally` on
    # EVERY path (success, ignored, and re-raised HTTPExceptions).
    rec: dict = {
        "ingest_token": ingest_token,
        "source_ip": request.client.host if request.client else None,
        "headers": dict(request.headers),
        "raw_body": None,
        "user_id": None,
        "status": "ignored",
        "reason": None,
        "matched_application_id": None,
    }
    try:
        user = _lookup_user(db, ingest_token)  # raises HTTPException(404)
        rec["user_id"] = user.id

        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > _MAX_BODY:
            # Body not read on this pre-check path — raw_body stays null.
            raise HTTPException(413, "payload too large")
        raw = await request.body()
        rec["raw_body"] = raw.decode("utf-8", "replace")
        if len(raw) > _MAX_BODY:
            raise HTTPException(413, "payload too large")

        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            rec["reason"] = "unparseable"
            return {"status": "ignored", "reason": "unparseable"}
        email = InboundEmail.normalize(payload)

        llm = _webhook_llm()
        if llm is None:
            rec["reason"] = "llm unavailable"
            return {"status": "ignored", "reason": "llm unavailable"}
        try:
            extracted = extract_interview(email.subject, email.body_text, llm)
        except Exception:
            rec["reason"] = "extraction failed"
            return {"status": "ignored", "reason": "extraction failed"}

        apps = db.execute(
            select(Application, JobPosting)
            .outerjoin(JobPosting, JobPosting.application_id == Application.id)
            .where(Application.user_id == user.id, Application.deleted_at.is_(None))
        ).all()
        if not apps:
            rec["reason"] = "no applications"
            return {"status": "ignored", "reason": "no applications"}

        candidates = [
            Candidate(application_id=str(a.id), company=(jp.company if jp else None), url=a.url)
            for a, jp in apps
        ]
        app_id, _score = match_application(
            sender=email.from_, subject=email.subject, body=email.body_text,
            candidates=candidates,
        )
        if app_id is None:
            rec["reason"] = "no match"
            return {"status": "ignored", "reason": "no match"}

        stage = None
        if extracted.interview_stage:
            stage = InterviewStage(extracted.interview_stage)

        kwargs = dict(
            application_id=_uuid.UUID(app_id),
            ends_at=extracted.ends_at,
            direction=InteractionDirection.in_,
            channel=InteractionChannel.interview,
            interview_stage=stage,
            location=extracted.location,
            contact_name=extracted.contact_name,
            contact_handle=extracted.contact_handle,
            subject=email.subject,
            body=email.body_text,
            needs_review=True,
            created_from=InteractionCreatedFrom.email_webhook,
        )
        if extracted.starts_at is not None:
            kwargs["occurred_at"] = extracted.starts_at
        it = Interaction(**kwargs)
        db.add(it)
        db.add(ApplicationEvent(
            application_id=_uuid.UUID(app_id),
            kind=ApplicationEventKind.interview_scheduled,
        ))
        rec["status"] = "created"
        rec["matched_application_id"] = _uuid.UUID(app_id)
        # NOTE: no db.commit() here — the `finally` commits the interaction,
        # event, and WebhookRequest together.
        return {"status": "created", "needs_review": True}
    except HTTPException as exc:
        if exc.status_code == 404:
            rec["status"] = "not_found"
            rec["reason"] = "unknown token"
        elif exc.status_code == 413:
            rec["status"] = "rejected"
            rec["reason"] = "payload too large"
        raise
    finally:
        db.add(WebhookRequest(**rec))
        db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest tests/integration/test_webhook_api.py -v`
Expected: all tests PASS (3 original + 3 new). The original `test_webhook_creates_needs_review_interview` still passes because the interaction is now committed in `finally`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/webhooks.py backend/tests/integration/test_webhook_api.py
git commit -m "feat(webhook): record a WebhookRequest on every inbound path"
```

---

## Task 4: Read API — list + detail endpoints

**Files:**
- Modify: `backend/app/api/webhooks.py` (add imports, schemas, 2 endpoints)
- Test: `backend/tests/integration/test_webhook_api.py` (add tests)

- [ ] **Step 1: Write the failing integration tests**

Append to `backend/tests/integration/test_webhook_api.py`:

```python
def test_list_requests_returns_owned_rows_only(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    client, user = auth_user
    # Owned row.
    db_session.add(WebhookRequest(
        ingest_token="own", user_id=user.id, status="ignored", reason="no match",
        raw_body='{"from": "jane@acme.example", "subject": "Hi"}',
    ))
    # Invalid-token row (user_id null) — must NOT appear in per-user list.
    db_session.add(WebhookRequest(
        ingest_token="bad", user_id=None, status="not_found", reason="unknown token",
    ))
    db_session.commit()

    resp = client.get("/api/webhooks/requests")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "ignored"
    assert r["reason"] == "no match"
    assert r["from"] == "jane@acme.example"
    assert r["subject"] == "Hi"


def test_get_request_detail_and_ownership(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    client, user = auth_user
    owned = WebhookRequest(
        ingest_token="own", user_id=user.id, status="created",
        headers={"x-test": "1"}, raw_body='{"from": "a@b.c"}',
    )
    other = WebhookRequest(ingest_token="oth", user_id=None, status="not_found")
    db_session.add_all([owned, other]); db_session.commit()
    db_session.refresh(owned); db_session.refresh(other)

    ok = client.get(f"/api/webhooks/requests/{owned.id}")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["headers"] == {"x-test": "1"}
    assert body["raw_body"] == '{"from": "a@b.c"}'
    assert body["from"] == "a@b.c"

    # Not owned → 404.
    denied = client.get(f"/api/webhooks/requests/{other.id}")
    assert denied.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest tests/integration/test_webhook_api.py -k "requests" -v`
Expected: FAIL with 404 / route-not-found (endpoints don't exist yet).

- [ ] **Step 3: Add imports, schemas, helper, and endpoints**

In `backend/app/api/webhooks.py`:

Change the pydantic import (currently `from pydantic import BaseModel`) to:

```python
from pydantic import BaseModel, Field
```

Add these imports near the other `from app...` imports (top of file):

```python
from app.api.deps import current_user, db_dep
from app.api.serializers import UtcDateTime
```

(`db_dep` is already imported on the existing `from app.api.deps import db_dep` line — merge them into the single line above and delete the old one so `db_dep` is not imported twice.)

Add the schemas + helper right after the `InboundEmail` class:

```python
class WebhookRequestSummary(BaseModel):
    id: uuid.UUID
    created_at: UtcDateTime
    status: str
    reason: str | None = None
    source_ip: str | None = None
    matched_application_id: uuid.UUID | None = None
    # Best-effort, parsed from the stored body for the table view.
    from_: str | None = Field(default=None, alias="from")
    subject: str | None = None

    model_config = {"populate_by_name": True}


class WebhookRequestDetail(WebhookRequestSummary):
    headers: dict | None = None
    raw_body: str | None = None


def _derive_from_subject(raw_body: str | None) -> tuple[str | None, str | None]:
    """Best-effort extract of from/subject from a stored JSON body."""
    if not raw_body:
        return None, None
    try:
        payload = json.loads(raw_body)
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    frm = payload.get("from") or payload.get("sender")
    return frm, payload.get("subject")
```

Note on `uuid`: the module is imported as `import uuid as _uuid`. Add a plain `import uuid` at the top as well so the annotations `uuid.UUID` in the schemas resolve. (Alternatively use `_uuid.UUID`, but `import uuid` reads cleaner for type annotations.) Add near the top imports:

```python
import uuid
```

Add the two endpoints at the END of the file (after `inbound_email`):

```python
@router.get("/requests", response_model=list[WebhookRequestSummary])
def list_webhook_requests(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> list[WebhookRequestSummary]:
    rows = db.execute(
        select(WebhookRequest)
        .where(WebhookRequest.user_id == user.id)
        .order_by(WebhookRequest.created_at.desc())
    ).scalars().all()
    out: list[WebhookRequestSummary] = []
    for r in rows:
        frm, subj = _derive_from_subject(r.raw_body)
        out.append(WebhookRequestSummary(
            id=r.id,
            created_at=r.created_at,
            status=r.status,
            reason=r.reason,
            source_ip=r.source_ip,
            matched_application_id=r.matched_application_id,
            from_=frm,
            subject=subj,
        ))
    return out


@router.get("/requests/{req_id}", response_model=WebhookRequestDetail)
def get_webhook_request(
    req_id: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> WebhookRequestDetail:
    r = db.get(WebhookRequest, req_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "not found")
    frm, subj = _derive_from_subject(r.raw_body)
    return WebhookRequestDetail(
        id=r.id,
        created_at=r.created_at,
        status=r.status,
        reason=r.reason,
        source_ip=r.source_ip,
        matched_application_id=r.matched_application_id,
        from_=frm,
        subject=subj,
        headers=r.headers,
        raw_body=r.raw_body,
    )
```

Route note: `/requests` and `/requests/{req_id}` do not collide with `/inbound-email/{ingest_token}`. FastAPI matches the static `/requests` prefix before the `{req_id}` param path, so ordering is safe.

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest tests/integration/test_webhook_api.py -v`
Expected: all PASS. Confirm `response_model` emits the `from` alias (FastAPI defaults `response_model_by_alias=True`), so `r["from"]` is present.

- [ ] **Step 5: Run the full webhook + migration test set**

Run: `backend/.venv/bin/python -m pytest tests/integration/test_webhook_api.py tests/unit/test_webhook_request_model.py tests/unit/test_webhook_request_migration.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/webhooks.py backend/tests/integration/test_webhook_api.py
git commit -m "feat(webhook): list + detail read endpoints for request history"
```

---

## Task 5: Frontend api module

**Files:**
- Create: `frontend/src/api/webhooks.ts`

- [ ] **Step 1: Create the api module**

Create `frontend/src/api/webhooks.ts` (mirrors `frontend/src/api/calendar.ts`, uses the shared `api` client):

```ts
import { api } from "./client";

export type WebhookRequestSummary = {
  id: string;
  created_at: string;
  status: string;
  reason: string | null;
  source_ip: string | null;
  matched_application_id: string | null;
  from: string | null;
  subject: string | null;
};

export type WebhookRequestDetail = WebhookRequestSummary & {
  headers: Record<string, string> | null;
  raw_body: string | null;
};

export const listWebhookRequests = () =>
  api<WebhookRequestSummary[]>("/api/webhooks/requests");

export const getWebhookRequest = (id: string) =>
  api<WebhookRequestDetail>(`/api/webhooks/requests/${id}`);
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit` (sandbox off; rtk masks tsc — use the raw node binary if output looks summarized)
Expected: no new type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/webhooks.ts
git commit -m "feat(webhook): frontend api module for request history"
```

---

## Task 6: Frontend page + route + nav wiring

**Files:**
- Create: `frontend/src/pages/SettingsWebhooks.tsx`
- Modify: `frontend/src/App.tsx` (import + route)
- Modify: `frontend/src/components/nav/navItems.ts` (nav entry)

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/SettingsWebhooks.tsx`:

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getWebhookRequest,
  listWebhookRequests,
  type WebhookRequestSummary,
} from "../api/webhooks";

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "created"
      ? "bg-emerald-100 text-emerald-700"
      : status === "not_found" || status === "rejected"
        ? "bg-rose-100 text-rose-700"
        : "bg-amber-100 text-amber-700";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${tone}`}>
      {status}
    </span>
  );
}

function prettyBody(raw: string | null): string {
  if (!raw) return "";
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function DetailModal({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["webhook-request", id],
    queryFn: () => getWebhookRequest(id),
  });
  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <div
        className="bg-surface rounded-lg max-w-2xl w-full max-h-[85vh] overflow-auto p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-semibold">Webhook request</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted hover:text-fg"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
        {q.data && (
          <div className="space-y-3 text-sm">
            <div className="flex gap-2 items-center">
              <StatusBadge status={q.data.status} />
              {q.data.reason && (
                <span className="text-muted">{q.data.reason}</span>
              )}
            </div>
            <div className="text-muted">
              {new Date(q.data.created_at).toLocaleString()} · IP{" "}
              {q.data.source_ip ?? "—"}
            </div>
            <div>
              <div className="font-semibold mb-1">Headers</div>
              <pre className="bg-bg rounded p-2 text-xs overflow-auto max-h-40">
                {JSON.stringify(q.data.headers ?? {}, null, 2)}
              </pre>
            </div>
            <div>
              <div className="font-semibold mb-1">Body</div>
              <pre className="bg-bg rounded p-2 text-xs overflow-auto max-h-64">
                {prettyBody(q.data.raw_body)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SettingsWebhooks() {
  const [selected, setSelected] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["webhook-requests"],
    queryFn: () => listWebhookRequests(),
  });

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Webhook log</h1>
      {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
      {q.data && q.data.length === 0 && (
        <div className="text-muted text-sm">No requests received yet.</div>
      )}
      {q.data && q.data.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 pr-2">Time</th>
              <th className="py-2 pr-2">From</th>
              <th className="py-2 pr-2">Subject</th>
              <th className="py-2 pr-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((r: WebhookRequestSummary) => (
              <tr
                key={r.id}
                onClick={() => setSelected(r.id)}
                className="border-b border-border cursor-pointer hover:bg-bg"
              >
                <td className="py-2 pr-2 whitespace-nowrap">
                  {new Date(r.created_at).toLocaleString()}
                </td>
                <td className="py-2 pr-2">{r.from ?? "—"}</td>
                <td className="py-2 pr-2">{r.subject ?? "—"}</td>
                <td className="py-2 pr-2">
                  <StatusBadge status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {selected && (
        <DetailModal id={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
```

Note: Tailwind color tokens (`bg-surface`, `bg-bg`, `text-fg`, `text-muted`, `border-border`) match those used in `SettingsCalendar.tsx`. If `bg-bg` is not a defined token in this project, use `bg-surface` for the `pre` blocks — verify against `frontend/tailwind.config`/existing pages before finalizing.

- [ ] **Step 2: Register the route in `frontend/src/App.tsx`**

Add the import alongside the other page imports:

```tsx
import SettingsWebhooks from "./pages/SettingsWebhooks";
```

Add a route in the same style as `/settings/calendar`:

```tsx
      <Route
        path="/settings/webhooks"
        element={
          <ProtectedShell>
            <SettingsWebhooks />
          </ProtectedShell>
        }
      />
```

- [ ] **Step 3: Add the nav entry in `frontend/src/components/nav/navItems.ts`**

Add to the `NAV_ITEMS` array, in the settings group (after the Calendar & Email entry):

```ts
  { to: "/settings/webhooks", label: "Webhook log", group: "settings" },
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SettingsWebhooks.tsx frontend/src/App.tsx frontend/src/components/nav/navItems.ts
git commit -m "feat(webhook): settings page + route + nav for request history"
```

---

## Task 7: Full verification

- [ ] **Step 1: Run the full backend test suite**

Run: `backend/.venv/bin/python -m pytest -q` (from `backend/`, sandbox off)
Expected: all pass (existing + new webhook tests). Testcontainers Postgres is required and works in this env.

- [ ] **Step 2: Frontend typecheck + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: clean.

- [ ] **Step 3: Manual smoke (optional, if a local stack is up)**

- POST a body to `/api/webhooks/inbound-email/<real ingest token>`, then open `/settings/webhooks` and confirm the row appears with the right status badge and that the detail modal shows headers + pretty-printed body.
- POST to a bad token → 404 still returned, and (as an admin/db check) a `not_found` row exists but is NOT listed for the user.

---

## Self-Review (checked against the spec)

**Spec coverage:**
- Model `WebhookRequest` (all 10 fields, no DB enum) → Task 1. ✅
- Migration creating `webhook_request` → Task 2. ✅
- Endpoint refactor: single row on every path via try/finally, source_ip + headers captured up front, HTTPExceptions recorded then re-raised (unchanged status codes/bodies), success commits together with interaction+event, 413 pre-check leaves raw_body null → Task 3. ✅
- Status→reason convention (`not_found`/`rejected`/`ignored`/`created`) → recorded in handler, validated by tests. ✅
- Read API: `GET /requests` (owned, newest first, summary + derived from/subject), `GET /requests/{id}` (detail, 404 if not owned), invalid-token rows excluded → Task 4. ✅
- Frontend api module (`listWebhookRequests`, `getWebhookRequest`) → Task 5. ✅
- `SettingsWebhooks.tsx` table + detail modal (pretty-printed JSON), route in `App.tsx`, nav entry → Task 6. ✅
- Tests: migration guard (Task 2), integration for created/no-match/not_found + owned-only list (Tasks 3-4), model test (Task 1). ✅

**Out of scope (correctly omitted):** retention/pruning, replay, multi-webhook generalization, secret redaction.

**Type consistency:** `WebhookRequestSummary`/`WebhookRequestDetail` field names match between backend schemas and the frontend TS types; `from` alias used consistently on both sides; `_derive_from_subject` returns `(from, subject)` used identically in both endpoints.
