# Calendar Event Suggestions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pulled Outlook calendar events land in a staging table and surface as reviewable items in the Suggestions tab; nothing becomes a real interview until the user confirms.

**Architecture:** A new `CalendarSuggestion` table stores each pulled event keyed on `(user_id, external_source, external_id)` with a `pending`/`confirmed`/`dismissed` status. `sync_calendar_events` is rewritten from "create Interaction directly" to a state machine that upserts suggestions. A confirm endpoint promotes a suggestion to a live-linked `Interaction` (keeps `external_id`, so later Outlook edits keep syncing); a dismiss endpoint tombstones it. The frontend Suggestions page grows a "Calendar interviews" section.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (Mapped/mapped_column) + Alembic + Postgres; React + TanStack Query + Tailwind; pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-08-27-calendar-suggestions-design.md`

---

## Conventions for every test command

Run backend tests from the `backend/` directory using the venv binary directly (NOT via rtk, which summarizes away real failures), with the sandbox disabled (testcontainers needs the Docker daemon):

```bash
cd backend && .venv/bin/python -m pytest <path> -v
```

Frontend checks:

```bash
cd frontend && npx tsc --noEmit
```

---

## File Structure

**Backend**
- Modify `backend/app/db/models.py` — add `CalendarSuggestionStatus` enum + `CalendarSuggestion` model.
- Create `backend/alembic/versions/e1a2b3c4d5e6_calendar_suggestion.py` — enum type + table (down_revision `d7e8f9a0b1c2`).
- Rewrite `backend/app/calendar_sync/sync.py` — state machine over `CalendarSuggestion`.
- Modify `backend/app/api/calendar.py` — list/confirm/dismiss endpoints.
- Rewrite `backend/tests/integration/test_calendar_sync.py` — suggestion-based sync tests.
- Create `backend/tests/integration/test_calendar_suggestions_api.py` — endpoint tests.
- Create `backend/tests/integration/test_calendar_suggestion_migration.py` — enum/table migration guard.

**Frontend**
- Modify `frontend/src/api/calendar.ts` — `calendarSuggestions` client.
- Modify `frontend/src/pages/Suggestions.tsx` — new "Calendar interviews" section.
- Modify `frontend/src/hooks/useSuggestionsCount.ts` — include pending calendar count.

---

## Task 1: `CalendarSuggestion` model + status enum

**Files:**
- Modify: `backend/app/db/models.py`
- Test: `backend/tests/integration/test_calendar_suggestion_model.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_calendar_suggestion_model.py`:

```python
"""The CalendarSuggestion ORM model is registered with the expected shape."""
from app.db.models import CalendarSuggestion, CalendarSuggestionStatus


def test_status_enum_values():
    assert [s.value for s in CalendarSuggestionStatus] == [
        "pending",
        "confirmed",
        "dismissed",
    ]


def test_table_columns():
    cols = set(CalendarSuggestion.__table__.columns.keys())
    assert {
        "id",
        "user_id",
        "external_source",
        "external_id",
        "status",
        "subject",
        "starts_at",
        "ends_at",
        "location",
        "body",
        "organizer_email",
        "suggested_application_id",
        "match_score",
        "interaction_id",
        "created_at",
        "updated_at",
    } <= cols


def test_unique_constraint_on_external_key():
    names = {c.name for c in CalendarSuggestion.__table__.constraints}
    assert "uq_calsuggestion_external" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_suggestion_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'CalendarSuggestion'`.

- [ ] **Step 3: Add the enum**

In `backend/app/db/models.py`, after the `ApplicationEventKind` enum (around line 122), add:

```python
class CalendarSuggestionStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    dismissed = "dismissed"
```

- [ ] **Step 4: Add the model**

In `backend/app/db/models.py`, after the `CalendarSyncState` class (around line 432), add:

```python
class CalendarSuggestion(Base):
    """A pulled external calendar event staged for user review.

    One row per Outlook event, keyed on (user_id, external_source,
    external_id). Serves as both the staging store (status='pending') and the
    tombstone (confirmed/dismissed) that keeps a full re-sync idempotent — a
    410 re-sync must never resurrect a dismissed or already-confirmed event.
    """

    __tablename__ = "calendar_suggestion"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "external_source",
            "external_id",
            name="uq_calsuggestion_external",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    external_source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CalendarSuggestionStatus] = mapped_column(
        Enum(CalendarSuggestionStatus, name="calendarsuggestionstatus"),
        default=CalendarSuggestionStatus.pending,
        server_default=CalendarSuggestionStatus.pending.value,
        index=True,
    )
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    organizer_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application.id"), nullable=True, index=True
    )
    match_score: Mapped[float | None] = mapped_column(nullable=True)
    interaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interaction.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

Note: `match_score` uses `Mapped[float | None]` with no explicit type — SQLAlchemy maps `float` to `Float`. If the linter prefers explicit types, import `Float` from sqlalchemy and use `mapped_column(Float, nullable=True)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_suggestion_model.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/tests/integration/test_calendar_suggestion_model.py
git commit -m "feat(calendar): CalendarSuggestion model + status enum"
```

---

## Task 2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/e1a2b3c4d5e6_calendar_suggestion.py`
- Test: `backend/tests/integration/test_calendar_suggestion_migration.py` (create)

The integration DB fixture builds schema from models (`Base.metadata.create_all`), so a missing migration would NOT fail other tests. This dedicated test upgrades the real migration chain on a fresh container and asserts the table + enum exist — the enum-drift guard.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_calendar_suggestion_migration.py`:

```python
"""Guard: the Alembic chain actually creates calendar_suggestion + its enum.

The db_session fixture builds schema from models, which masks missing
migrations. This test runs `alembic upgrade head` against a fresh container.
"""
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_migration_creates_table_and_enum(pg_container, monkeypatch):
    raw = pg_container.get_connection_url()
    url = raw.replace("postgresql+psycopg2://", "postgresql+psycopg://").replace(
        "postgresql://", "postgresql+psycopg://"
    )
    monkeypatch.setenv("DATABASE_URL", url)

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    try:
        insp = inspect(engine)
        assert "calendar_suggestion" in insp.get_table_names()
        with engine.connect() as conn:
            labels = conn.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'calendarsuggestionstatus' "
                    "ORDER BY e.enumsortorder"
                )
            ).scalars().all()
        assert labels == ["pending", "confirmed", "dismissed"]
    finally:
        # Leave the container clean for other session-scoped users.
        command.downgrade(cfg, "base")
        engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_suggestion_migration.py -v`
Expected: FAIL — either `alembic` can't find the revision, or the assertion on `calendar_suggestion` table fails.

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/e1a2b3c4d5e6_calendar_suggestion.py`:

```python
"""calendar_suggestion: staged Outlook events for review

Revision ID: e1a2b3c4d5e6
Revises: d7e8f9a0b1c2
Create Date: 2026-08-27 00:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    status = postgresql.ENUM(
        "pending", "confirmed", "dismissed",
        name="calendarsuggestionstatus", create_type=False,
    )
    status.create(bind, checkfirst=True)

    op.create_table(
        "calendar_suggestion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"), nullable=False, index=True,
        ),
        sa.Column("external_source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column(
            "status", status, nullable=False, server_default="pending", index=True,
        ),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("organizer_email", sa.Text(), nullable=True),
        sa.Column(
            "suggested_application_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application.id"), nullable=True, index=True,
        ),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column(
            "interaction_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interaction.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "external_source", "external_id",
            name="uq_calsuggestion_external",
        ),
    )


def downgrade() -> None:
    op.drop_table("calendar_suggestion")
    postgresql.ENUM(name="calendarsuggestionstatus").drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_suggestion_migration.py -v`
Expected: 1 passed.

- [ ] **Step 5: Verify the chain has a single head**

Run: `cd backend && .venv/bin/alembic heads`
Expected: exactly one line — `e1a2b3c4d5e6 (head)`.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/e1a2b3c4d5e6_calendar_suggestion.py backend/tests/integration/test_calendar_suggestion_migration.py
git commit -m "feat(calendar): migration for calendar_suggestion table"
```

---

## Task 3: Rewrite `sync_calendar_events` as a suggestion state machine

**Files:**
- Rewrite: `backend/app/calendar_sync/sync.py`
- Rewrite: `backend/tests/integration/test_calendar_sync.py`

Behavior change: sync no longer creates `Interaction`s. Per delta event, keyed on `external_id`:
- **none** → create `pending` suggestion (prefill best-guess match).
- **pending** → refresh snapshot fields.
- **confirmed** → update the live-linked `Interaction` (found by `external_id`).
- **dismissed** → ignore.
- **`@removed`** → pending: delete suggestion · confirmed: delete linked `Interaction` · dismissed: nothing.

Stats keys: `created` (new pending), `updated` (pending refreshed OR confirmed interaction updated), `deleted`, `skipped`.

- [ ] **Step 1: Replace the sync test file**

Replace the entire contents of `backend/tests/integration/test_calendar_sync.py`:

```python
"""Integration tests for the MS Graph → CalendarSuggestion state machine."""
from sqlalchemy import select

from app.calendar_sync.sync import MS_GRAPH, sync_calendar_events
from app.db.models import (
    Application,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    Interaction,
    JobPosting,
)


def _app(db, user, *, url="https://acme.example/jobs/1", company="Acme GmbH"):
    a = Application(user_id=user.id, url=url, url_hash=url[-64:].rjust(64, "x"))
    db.add(a)
    db.flush()
    db.add(JobPosting(application_id=a.id, raw_text="x", company=company))
    db.commit()
    db.refresh(a)
    return a


def _event(eid="e1", **over):
    ev = {
        "id": eid,
        "subject": "Interview with Acme",
        "bodyPreview": "See you then",
        "start": {"dateTime": "2026-08-20T10:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-08-20T11:00:00.0000000", "timeZone": "UTC"},
        "location": {"displayName": "Zoom"},
        "organizer": {"emailAddress": {"address": "hr@acme.example", "name": "HR"}},
    }
    ev.update(over)
    return ev


def _get_suggestion(db, eid="e1"):
    return db.execute(
        select(CalendarSuggestion).where(CalendarSuggestion.external_id == eid)
    ).scalar_one()


def test_new_event_creates_pending_suggestion(db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)

    stats = sync_calendar_events(db_session, user, [_event()])

    assert stats["created"] == 1
    s = _get_suggestion(db_session)
    assert s.status == CalendarSuggestionStatus.pending
    assert s.external_source == MS_GRAPH
    assert s.subject == "Interview with Acme"
    assert s.location == "Zoom"
    assert s.starts_at.hour == 10 and s.ends_at.hour == 11
    assert s.suggested_application_id == app.id  # matched by organizer domain
    # No interview is created yet.
    assert db_session.execute(select(Interaction)).scalar_one_or_none() is None


def test_online_meeting_join_url_used_when_no_location(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    ev = _event(location={"displayName": ""}, onlineMeeting={"joinUrl": "https://meet/x"})

    sync_calendar_events(db_session, user, [ev])

    assert _get_suggestion(db_session).location == "https://meet/x"


def test_pending_suggestion_refreshed_on_update(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    original_id = _get_suggestion(db_session).id

    stats = sync_calendar_events(
        db_session,
        user,
        [_event(subject="Rescheduled",
                start={"dateTime": "2026-08-21T14:00:00.0000000", "timeZone": "UTC"},
                end={"dateTime": "2026-08-21T15:00:00.0000000", "timeZone": "UTC"})],
    )

    assert stats["updated"] == 1 and stats["created"] == 0
    db_session.expire_all()
    s = _get_suggestion(db_session)
    assert s.id == original_id  # same row, not a duplicate
    assert s.subject == "Rescheduled" and s.starts_at.day == 21


def test_new_event_without_applications_still_stages_unmatched(db_session, auth_user):
    _, user = auth_user  # no applications

    stats = sync_calendar_events(db_session, user, [_event()])

    assert stats["created"] == 1
    s = _get_suggestion(db_session)
    assert s.suggested_application_id is None  # nothing to match to


def test_event_missing_start_is_skipped(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)

    stats = sync_calendar_events(db_session, user, [_event(start=None)])

    assert stats["skipped"] == 1 and stats["created"] == 0


def test_removed_pending_event_deletes_suggestion(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])

    stats = sync_calendar_events(
        db_session, user, [{"id": "e1", "@removed": {"reason": "deleted"}}]
    )

    assert stats["deleted"] == 1
    assert db_session.execute(
        select(CalendarSuggestion).where(CalendarSuggestion.external_id == "e1")
    ).scalar_one_or_none() is None


def test_dismissed_event_is_not_resurrected(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    s = _get_suggestion(db_session)
    s.status = CalendarSuggestionStatus.dismissed
    db_session.commit()

    # A full re-sync sends the same event again.
    stats = sync_calendar_events(db_session, user, [_event()])

    assert stats["skipped"] == 1 and stats["created"] == 0
    db_session.expire_all()
    assert _get_suggestion(db_session).status == CalendarSuggestionStatus.dismissed


def test_confirmed_event_updates_linked_interaction(db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    s = _get_suggestion(db_session)
    # Simulate confirm: create the live-linked interview + mark confirmed.
    from app.db.models import (
        ApplicationEvent,
        ApplicationEventKind,
        InteractionChannel,
        InteractionCreatedFrom,
        InteractionDirection,
    )
    it = Interaction(
        application_id=app.id,
        occurred_at=s.starts_at,
        ends_at=s.ends_at,
        direction=InteractionDirection.in_,
        channel=InteractionChannel.interview,
        location=s.location,
        subject=s.subject,
        body=s.body,
        needs_review=False,
        created_from=InteractionCreatedFrom.graph_sync,
        external_source=MS_GRAPH,
        external_id=s.external_id,
    )
    db_session.add(it)
    db_session.flush()
    db_session.add(ApplicationEvent(
        application_id=app.id,
        kind=ApplicationEventKind.interview_scheduled,
        interaction_id=it.id,
    ))
    s.status = CalendarSuggestionStatus.confirmed
    s.interaction_id = it.id
    db_session.commit()

    stats = sync_calendar_events(
        db_session, user,
        [_event(start={"dateTime": "2026-08-22T09:00:00.0000000", "timeZone": "UTC"},
                end={"dateTime": "2026-08-22T09:30:00.0000000", "timeZone": "UTC"})],
    )

    assert stats["updated"] == 1
    db_session.expire_all()
    it2 = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it2.occurred_at.day == 22 and it2.ends_at.hour == 9


def test_removed_confirmed_event_deletes_interaction(db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    s = _get_suggestion(db_session)
    from app.db.models import (
        InteractionChannel,
        InteractionCreatedFrom,
        InteractionDirection,
    )
    it = Interaction(
        application_id=app.id, occurred_at=s.starts_at,
        direction=InteractionDirection.in_, channel=InteractionChannel.interview,
        needs_review=False, created_from=InteractionCreatedFrom.graph_sync,
        external_source=MS_GRAPH, external_id=s.external_id,
    )
    db_session.add(it)
    db_session.flush()
    s.status = CalendarSuggestionStatus.confirmed
    s.interaction_id = it.id
    db_session.commit()

    stats = sync_calendar_events(
        db_session, user, [{"id": "e1", "@removed": {"reason": "deleted"}}]
    )

    assert stats["deleted"] == 1
    db_session.expire_all()
    assert db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one_or_none() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_sync.py -v`
Expected: FAIL — `sync_calendar_events` still creates Interactions / has no CalendarSuggestion logic.

- [ ] **Step 3: Rewrite `sync.py`**

Replace the entire contents of `backend/app/calendar_sync/sync.py`:

```python
"""Idempotent projection of MS Graph calendar events into CalendarSuggestions.

Pulled events are STAGED, not applied: each event becomes a CalendarSuggestion
(status='pending') keyed on (external_source, external_id). Confirmation into a
real interview happens elsewhere (the confirm endpoint). Once confirmed, this
sync keeps the linked Interaction in step with Outlook (live-link); once
dismissed, the event is never resurrected. Re-runs converge.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    Interaction,
    JobPosting,
    User,
)
from app.email_ingest.interview_match import Candidate, match_application

MS_GRAPH = "ms_graph"


def _parse_dt(node: dict | None) -> datetime | None:
    """Parse a Graph ``{"dateTime": ...}`` node to naive UTC (whole seconds)."""
    if not node:
        return None
    raw = node.get("dateTime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:19])
    except ValueError:
        return None


def _location(ev: dict) -> str | None:
    loc = (ev.get("location") or {}).get("displayName")
    if loc:
        return loc
    return (ev.get("onlineMeeting") or {}).get("joinUrl")


def _organizer_email(ev: dict) -> str:
    return (ev.get("organizer") or {}).get("emailAddress", {}).get("address", "")


def _candidates(db: Session, user: User) -> list[Candidate]:
    rows = db.execute(
        select(Application, JobPosting)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(Application.user_id == user.id, Application.deleted_at.is_(None))
    ).all()
    return [
        Candidate(application_id=str(a.id), company=(jp.company if jp else None), url=a.url)
        for a, jp in rows
    ]


def _linked_interaction(db: Session, external_id: str) -> Interaction | None:
    return db.execute(
        select(Interaction).where(
            Interaction.external_source == MS_GRAPH,
            Interaction.external_id == external_id,
        )
    ).scalar_one_or_none()


def sync_calendar_events(db: Session, user: User, events: list[dict]) -> dict:
    """Upsert/delete CalendarSuggestions for the given Graph delta events.

    Returns a stats dict: created / updated / deleted / skipped.
    """
    stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
    candidates = None  # lazily computed only when we create a new suggestion

    for ev in events:
        external_id = ev.get("id")
        if not external_id:
            stats["skipped"] += 1
            continue

        existing = db.execute(
            select(CalendarSuggestion).where(
                CalendarSuggestion.user_id == user.id,
                CalendarSuggestion.external_source == MS_GRAPH,
                CalendarSuggestion.external_id == external_id,
            )
        ).scalar_one_or_none()

        # Cancellation.
        if ev.get("@removed") is not None:
            if existing is None:
                stats["skipped"] += 1
            elif existing.status == CalendarSuggestionStatus.pending:
                db.delete(existing)
                stats["deleted"] += 1
            elif existing.status == CalendarSuggestionStatus.confirmed:
                it = _linked_interaction(db, external_id)
                if it is not None:
                    db.delete(it)  # CASCADE removes the timeline note
                db.delete(existing)
                stats["deleted"] += 1
            else:  # dismissed
                stats["skipped"] += 1
            continue

        start = _parse_dt(ev.get("start"))
        if start is None:
            stats["skipped"] += 1
            continue

        end = _parse_dt(ev.get("end"))
        location = _location(ev)
        subject = ev.get("subject")
        body = ev.get("bodyPreview")

        if existing is None:
            if candidates is None:
                candidates = _candidates(db, user)
            app_id, score = match_application(
                sender=_organizer_email(ev),
                subject=subject or "",
                body=body or "",
                candidates=candidates,
            )
            db.add(
                CalendarSuggestion(
                    user_id=user.id,
                    external_source=MS_GRAPH,
                    external_id=external_id,
                    status=CalendarSuggestionStatus.pending,
                    subject=subject,
                    starts_at=start,
                    ends_at=end,
                    location=location,
                    body=body,
                    organizer_email=_organizer_email(ev),
                    suggested_application_id=(
                        uuid.UUID(app_id) if app_id else None
                    ),
                    match_score=score,
                )
            )
            stats["created"] += 1
            continue

        if existing.status == CalendarSuggestionStatus.dismissed:
            stats["skipped"] += 1
            continue

        if existing.status == CalendarSuggestionStatus.pending:
            existing.subject = subject
            existing.starts_at = start
            existing.ends_at = end
            existing.location = location
            existing.body = body
            existing.organizer_email = _organizer_email(ev)
            stats["updated"] += 1
            continue

        # confirmed → live-link: keep the promoted interview in step.
        it = _linked_interaction(db, external_id)
        if it is not None:
            it.occurred_at = start
            it.ends_at = end
            it.location = location
            it.subject = subject
            it.body = body
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

    db.commit()
    return stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_sync.py -v`
Expected: all tests pass.

- [ ] **Step 5: Run the task-level sync test (regression)**

The task in `sync_outlook_calendar.py` calls `sync_calendar_events`; confirm its own tests still pass (stats keys unchanged):
Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_sync.py tests/unit/test_calendar_graph.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/calendar_sync/sync.py backend/tests/integration/test_calendar_sync.py
git commit -m "feat(calendar): sync stages events as suggestions instead of interviews"
```

---

## Task 4: List / confirm / dismiss endpoints

**Files:**
- Modify: `backend/app/api/calendar.py`
- Test: `backend/tests/integration/test_calendar_suggestions_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_calendar_suggestions_api.py`:

```python
"""API tests for calendar suggestion review (list / confirm / dismiss)."""
from sqlalchemy import select

from app.calendar_sync.sync import MS_GRAPH
from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
    JobPosting,
)


def _app(db, user, *, company="Acme GmbH"):
    a = Application(user_id=user.id, url="https://acme.example/1", url_hash="a" * 64)
    db.add(a)
    db.flush()
    db.add(JobPosting(application_id=a.id, raw_text="x", company=company))
    db.commit()
    db.refresh(a)
    return a


def _suggestion(db, user, app=None, *, eid="e1"):
    from datetime import datetime
    s = CalendarSuggestion(
        user_id=user.id,
        external_source=MS_GRAPH,
        external_id=eid,
        status=CalendarSuggestionStatus.pending,
        subject="Interview",
        starts_at=datetime(2026, 9, 1, 10, 0),
        ends_at=datetime(2026, 9, 1, 11, 0),
        location="Zoom",
        suggested_application_id=(app.id if app else None),
        match_score=0.9 if app else 0.0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_list_returns_only_pending(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    _suggestion(db_session, user, app, eid="e1")
    dismissed = _suggestion(db_session, user, app, eid="e2")
    dismissed.status = CalendarSuggestionStatus.dismissed
    db_session.commit()

    r = client.get("/api/calendar/suggestions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["external_id"] == "e1"
    assert data[0]["suggested_application"]["company"] == "Acme GmbH"
    assert data[0]["match_score"] == 0.9


def test_confirm_promotes_to_live_linked_interview(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    s = _suggestion(db_session, user, app)

    r = client.post(f"/api/calendar/suggestions/{s.id}/confirm", json={})
    assert r.status_code == 200

    db_session.expire_all()
    it = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it.application_id == app.id
    assert it.channel == InteractionChannel.interview
    assert it.created_from == InteractionCreatedFrom.graph_sync
    assert it.needs_review is False
    assert it.external_source == MS_GRAPH  # live-linked
    ev = db_session.execute(
        select(ApplicationEvent).where(
            ApplicationEvent.kind == ApplicationEventKind.interview_scheduled
        )
    ).scalar_one()
    assert ev.interaction_id == it.id
    s2 = db_session.get(CalendarSuggestion, s.id)
    assert s2.status == CalendarSuggestionStatus.confirmed
    assert s2.interaction_id == it.id


def test_confirm_with_application_override(client, db_session, auth_user):
    _, user = auth_user
    matched = _app(db_session, user, company="Acme GmbH")
    other = Application(user_id=user.id, url="https://other.example/9", url_hash="o" * 64)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    s = _suggestion(db_session, user, matched)

    r = client.post(
        f"/api/calendar/suggestions/{s.id}/confirm",
        json={"application_id": str(other.id)},
    )
    assert r.status_code == 200

    db_session.expire_all()
    it = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it.application_id == other.id


def test_confirm_unmatched_without_app_is_rejected(client, db_session, auth_user):
    _, user = auth_user
    s = _suggestion(db_session, user, app=None)  # unmatched

    r = client.post(f"/api/calendar/suggestions/{s.id}/confirm", json={})
    assert r.status_code == 400

    db_session.expire_all()
    assert db_session.get(CalendarSuggestion, s.id).status == CalendarSuggestionStatus.pending


def test_dismiss_marks_dismissed(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    s = _suggestion(db_session, user, app)

    r = client.post(f"/api/calendar/suggestions/{s.id}/dismiss")
    assert r.status_code == 200

    db_session.expire_all()
    assert db_session.get(CalendarSuggestion, s.id).status == CalendarSuggestionStatus.dismissed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_suggestions_api.py -v`
Expected: FAIL — endpoints return 404 (routes don't exist).

- [ ] **Step 3: Add the endpoints**

In `backend/app/api/calendar.py`:

First extend the imports from models (the existing import block around line 16):

```python
from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    InteractionChannel,
    InteractionCreatedFrom,
    InteractionDirection,
    InterviewStage,
    JobPosting,
    Interaction,
    User,
)
```

Then, before the `_lookup_by_calendar_token` helper (around line 143), add:

```python
class SuggestedApp(BaseModel):
    id: uuid.UUID
    display_id: int
    company: str


class CalendarSuggestionOut(BaseModel):
    id: uuid.UUID
    external_id: str
    subject: str | None
    starts_at: UtcDateTime
    ends_at: UtcDateTime | None
    location: str | None
    organizer_email: str | None
    match_score: float | None
    suggested_application: SuggestedApp | None


class ConfirmSuggestionIn(BaseModel):
    application_id: uuid.UUID | None = None


def _owned_suggestion(db: Session, sid: uuid.UUID, user: User) -> CalendarSuggestion:
    s = db.execute(
        select(CalendarSuggestion).where(
            CalendarSuggestion.id == sid,
            CalendarSuggestion.user_id == user.id,
        )
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "suggestion not found")
    return s


@router.get("/suggestions", response_model=list[CalendarSuggestionOut])
def list_calendar_suggestions(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> list[CalendarSuggestionOut]:
    rows = db.execute(
        select(CalendarSuggestion, Application, JobPosting)
        .outerjoin(Application, CalendarSuggestion.suggested_application_id == Application.id)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(
            CalendarSuggestion.user_id == user.id,
            CalendarSuggestion.status == CalendarSuggestionStatus.pending,
        )
        .order_by(CalendarSuggestion.starts_at.asc())
    ).all()
    out: list[CalendarSuggestionOut] = []
    for s, app, jp in rows:
        suggested = None
        if app is not None:
            suggested = SuggestedApp(
                id=app.id, display_id=app.display_id, company=_company(jp, app.url)
            )
        out.append(
            CalendarSuggestionOut(
                id=s.id,
                external_id=s.external_id,
                subject=s.subject,
                starts_at=s.starts_at,
                ends_at=s.ends_at,
                location=s.location,
                organizer_email=s.organizer_email,
                match_score=s.match_score,
                suggested_application=suggested,
            )
        )
    return out


@router.post("/suggestions/{sid}/confirm")
def confirm_calendar_suggestion(
    sid: uuid.UUID,
    payload: ConfirmSuggestionIn,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    s = _owned_suggestion(db, sid, user)
    if s.status != CalendarSuggestionStatus.pending:
        raise HTTPException(409, "suggestion already resolved")

    app_id = payload.application_id or s.suggested_application_id
    if app_id is None:
        raise HTTPException(400, "no application to link; pick one to confirm")
    # Ownership check on the chosen application.
    app_row = db.execute(
        select(Application).where(
            Application.id == app_id,
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if app_row is None:
        raise HTTPException(400, "application not found")

    it = Interaction(
        application_id=app_row.id,
        occurred_at=s.starts_at,
        ends_at=s.ends_at,
        direction=InteractionDirection.in_,
        channel=InteractionChannel.interview,
        location=s.location,
        subject=s.subject,
        body=s.body,
        needs_review=False,
        created_from=InteractionCreatedFrom.graph_sync,
        external_source=s.external_source,
        external_id=s.external_id,
    )
    db.add(it)
    db.flush()  # assign it.id for the timeline note
    db.add(
        ApplicationEvent(
            application_id=app_row.id,
            kind=ApplicationEventKind.interview_scheduled,
            interaction_id=it.id,
        )
    )
    s.status = CalendarSuggestionStatus.confirmed
    s.interaction_id = it.id
    db.commit()
    return {"ok": True, "interaction_id": str(it.id)}


@router.post("/suggestions/{sid}/dismiss")
def dismiss_calendar_suggestion(
    sid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    s = _owned_suggestion(db, sid, user)
    if s.status == CalendarSuggestionStatus.pending:
        s.status = CalendarSuggestionStatus.dismissed
        db.commit()
    return {"ok": True}
```

Note: the existing `/{token}.ics` route uses a path param that could shadow `/suggestions`. FastAPI matches literal path segments before parameterized ones, so `/suggestions` and `/suggestions/{sid}/confirm` are matched ahead of `/{token}.ics`. No reordering needed, but keep the new routes above `ics_feed` for clarity.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_calendar_suggestions_api.py -v`
Expected: all pass.

- [ ] **Step 5: Full backend suite (regression)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: green (or pre-existing unrelated failures only).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/calendar.py backend/tests/integration/test_calendar_suggestions_api.py
git commit -m "feat(calendar): list/confirm/dismiss endpoints for calendar suggestions"
```

---

## Task 5: Frontend — Suggestions tab "Calendar interviews" section

**Files:**
- Modify: `frontend/src/api/calendar.ts`
- Modify: `frontend/src/pages/Suggestions.tsx`
- Modify: `frontend/src/hooks/useSuggestionsCount.ts`

- [ ] **Step 1: Add the API client**

In `frontend/src/api/calendar.ts`, add these types and extend the `calendar` object:

```typescript
export type CalendarSuggestion = {
  id: string;
  external_id: string;
  subject: string | null;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  organizer_email: string | null;
  match_score: number | null;
  suggested_application: {
    id: string;
    display_id: number;
    company: string;
  } | null;
};
```

Add inside the `calendar` object (before the closing brace):

```typescript
  suggestions: () => api<CalendarSuggestion[]>("/api/calendar/suggestions"),
  confirmSuggestion: (id: string, application_id?: string) =>
    api<{ ok: boolean; interaction_id: string }>(
      `/api/calendar/suggestions/${id}/confirm`,
      { method: "POST", body: JSON.stringify(application_id ? { application_id } : {}) },
    ),
  dismissSuggestion: (id: string) =>
    api<{ ok: boolean }>(`/api/calendar/suggestions/${id}/dismiss`, { method: "POST" }),
```

- [ ] **Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Add the "Calendar interviews" section to the Suggestions page**

In `frontend/src/pages/Suggestions.tsx`, add imports at the top:

```typescript
import { calendar, type CalendarSuggestion } from "../api/calendar";
```

Add this component above the `export default function Suggestions()`:

```tsx
function fmtRange(startIso: string, endIso: string | null): string {
  const start = new Date(startIso);
  const s = start.toLocaleString();
  if (!endIso) return s;
  const end = new Date(endIso);
  const sameDay = start.toDateString() === end.toDateString();
  return `${s} – ${sameDay ? end.toLocaleTimeString() : end.toLocaleString()}`;
}

function CalendarSuggestionRow({ s }: { s: CalendarSuggestion }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [overrideId, setOverrideId] = useState<string>("");

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["calendar-suggestions"] });
    qc.invalidateQueries({ queryKey: ["suggestions"] });
    qc.invalidateQueries({ queryKey: ["calendar-interviews"] });
  };

  const confirm = useMutation({
    mutationFn: () =>
      calendar.confirmSuggestion(
        s.id,
        overrideId || s.suggested_application?.id || undefined,
      ),
    onSuccess: () => {
      invalidate();
      toast("Interview übernommen");
    },
    onError: () => toast("Bitte zuerst eine Bewerbung wählen"),
  });

  const dismiss = useMutation({
    mutationFn: () => calendar.dismissSuggestion(s.id),
    onSuccess: () => {
      invalidate();
      toast("Vorschlag ausgeblendet");
    },
  });

  const busy = confirm.isPending || dismiss.isPending;
  const appList = useQuery({ queryKey: ["applications"], queryFn: () => applications.list() });

  return (
    <li className="border border-border rounded-lg p-4 bg-surface flex flex-col gap-2">
      <div className="font-semibold text-fg truncate">
        {s.subject ?? "(ohne Titel)"}
      </div>
      <div className="text-sm text-muted">
        {fmtRange(s.starts_at, s.ends_at)}
        {s.location && <span> · {s.location}</span>}
      </div>
      <div className="text-sm">
        {s.suggested_application ? (
          <span className="text-muted">
            Zuordnung → #{s.suggested_application.display_id}{" "}
            {s.suggested_application.company}
            {s.match_score != null && (
              <span className="text-xs"> ({s.match_score.toFixed(1)})</span>
            )}
          </span>
        ) : (
          <span className="text-orange-600">Keine Zuordnung — Bewerbung wählen</span>
        )}
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <select
          className="border border-border rounded px-2 py-1 text-sm bg-surface"
          value={overrideId}
          onChange={(e) => setOverrideId(e.target.value)}
        >
          <option value="">
            {s.suggested_application ? "Vorgeschlagene übernehmen" : "Bewerbung wählen…"}
          </option>
          {appList.data?.map((a) => (
            <option key={a.id} value={a.id}>
              #{a.display_id} {a.company ?? a.url}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="bg-accent text-white rounded px-3 py-1 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => confirm.mutate()}
        >
          Bestätigen
        </button>
        <button
          type="button"
          className="border border-border rounded px-3 py-1 text-sm text-muted hover:text-fg disabled:opacity-50"
          disabled={busy}
          onClick={() => dismiss.mutate()}
        >
          Ausblenden
        </button>
      </div>
    </li>
  );
}

function CalendarSuggestionsSection() {
  const q = useQuery({
    queryKey: ["calendar-suggestions"],
    queryFn: () => calendar.suggestions(),
  });
  if ((q.data?.length ?? 0) === 0) return null;
  return (
    <div className="mb-6">
      <h2 className="text-lg font-semibold text-fg mb-2">Kalender-Interviews</h2>
      <p className="text-sm text-muted mb-3">
        Aus deinem Outlook-Kalender übernommen. Bestätige, um sie als Interview
        zu speichern.
      </p>
      <ul className="flex flex-col gap-3">
        {q.data!.map((s) => (
          <CalendarSuggestionRow key={s.id} s={s} />
        ))}
      </ul>
    </div>
  );
}
```

Then render `<CalendarSuggestionsSection />` inside the `Suggestions` component, right after the intro `<p>` and before the offline-postings block. Replace the return of `Suggestions()`'s opening so the section always renders:

```tsx
  return (
    <div className="max-w-3xl mx-auto p-4 md:p-6">
      <h1 className="text-xl font-bold text-fg mb-1">Vorschläge</h1>
      <p className="text-sm text-muted mb-4">
        Die App ändert nichts von selbst — du entscheidest.
      </p>
      <CalendarSuggestionsSection />
      <h2 className="text-lg font-semibold text-fg mb-2">Offline-Anzeigen</h2>
      {q.isLoading ? (
        <div className="text-muted">Lädt…</div>
      ) : q.isError ? (
        <div className="text-red-600">Konnte Vorschläge nicht laden.</div>
      ) : (q.data?.length ?? 0) === 0 ? (
        <div className="text-muted border border-border rounded-lg p-6 text-center">
          Keine offenen Vorschläge. 🎉
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {q.data!.map((s) => (
            <SuggestionRow key={s.id} s={s} />
          ))}
        </ul>
      )}
    </div>
  );
```

- [ ] **Step 4: Update the nav badge count**

Replace `frontend/src/hooks/useSuggestionsCount.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { applications } from "../api/applications";
import { calendar } from "../api/calendar";

// Nav-badge count: offline-posting suggestions + pending calendar interviews.
// Shares caches with the Suggestions page so actions there update the badge.
export function useSuggestionsCount(): number {
  const offline = useQuery({
    queryKey: ["suggestions"],
    queryFn: () => applications.getSuggestions(),
  });
  const cal = useQuery({
    queryKey: ["calendar-suggestions"],
    queryFn: () => calendar.suggestions(),
  });
  return (offline.data?.length ?? 0) + (cal.data?.length ?? 0);
}
```

- [ ] **Step 5: Verify the frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/calendar.ts frontend/src/pages/Suggestions.tsx frontend/src/hooks/useSuggestionsCount.ts
git commit -m "feat(frontend): calendar interviews section in Suggestions tab"
```

---

## Final verification

- [ ] **Backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Single migration head**

Run: `cd backend && .venv/bin/alembic heads`
Expected: `e1a2b3c4d5e6 (head)`.

- [ ] **Frontend typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

- [ ] **Manual smoke (optional, requires the auth fix + a real Outlook calendar):**
  1. Trigger a sync (`docker compose exec worker python -c "from app.tasks.sync_outlook_calendar import sync_outlook_calendar_task as t; print(t.run())"`).
  2. Open `/suggestions` → "Kalender-Interviews" lists pulled events.
  3. Confirm one → it appears on the Calendar as a real interview and in the ICS feed.
  4. Dismiss another → gone, and a re-sync does not bring it back.
```
