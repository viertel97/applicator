# Outlook Sync Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the user a Settings sub-page that shows whether the Outlook calendar connection is working (latest run health + manual "Sync now") and lists every event ever pulled from Outlook (all statuses), mirroring the existing Webhook log page.

**Architecture:** Health of the latest sync is stamped on `User` (six `outlook_last_*` columns) on *every* sync exit path — including the pre-calendar failures (`no_token`, `token_refresh_failed`, `no_calendar`) that `CalendarSyncState` cannot capture. `sync_user_calendar` gains a `trigger` label and records health on skip/success/error. Three new endpoints (`sync-status`, `sync-now`, `entries`) back a new React page.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (Mapped/mapped_column) + Alembic + Postgres; React + TanStack Query + Tailwind + react-router; pytest + testcontainers.

**Source spec:** `docs/superpowers/specs/2026-08-27-outlook-sync-visibility-design.md`

---

## Environment / test harness (read once, applies to every backend step)

Backend tests use testcontainers (need Docker) and MUST run with the **sandbox disabled** and **NOT via rtk** (rtk masks pytest/compiler output — verified project quirk). The worktree has no local `.venv`; reuse the repo venv, forcing the worktree code onto `PYTHONPATH` so it wins over any editable install:

```bash
cd <WORKTREE>/backend
PYTHONPATH="<WORKTREE>/backend" /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest <test-path> -p no:cacheprovider -q
```

Replace `<WORKTREE>` with the absolute worktree path (`git rev-parse --show-toplevel`). If Docker is not running, the integration tests error at container startup — ask the user to start Docker rather than skipping.

Frontend type-check uses the **raw** compiler binary (the rtk hook masks `npx tsc` errors). First `npm install` in the worktree (node_modules is gitignored, not copied into the worktree):

```bash
cd <WORKTREE>/frontend && npm install
node_modules/typescript/bin/tsc --noEmit
```

Commit after each task's reviews pass. Conventional-commit messages.

---

## File Structure

**Backend**
- `backend/app/db/models.py` — add six `outlook_last_*` columns to `User`.
- `backend/alembic/versions/f3a4b5c6d7e8_user_outlook_health.py` (new) — add the six nullable columns to `user` (down_revision = current head `e1a2b3c4d5e6`, confirmed sole head).
- `backend/app/tasks/sync_outlook_calendar.py` — typed token errors, `_record_health`, `trigger` param, health on every path.
- `backend/app/api/calendar.py` — `sync-status`, `sync-now`, `entries` endpoints + response models.
- `backend/tests/integration/test_user_outlook_health_migration.py` (new) — migration guard.
- `backend/tests/integration/test_calendar_sync_health.py` (new) — health stamping on each path.
- `backend/tests/integration/test_calendar_sync_api.py` (new) — the three endpoints.

**Frontend**
- `frontend/src/api/calendar.ts` — `SyncStatus`, `CalendarEntry` types + `syncStatus`/`syncNow`/`entries`.
- `frontend/src/pages/SettingsOutlookSync.tsx` (new) — the page.
- `frontend/src/App.tsx` — route `/settings/outlook`.
- `frontend/src/components/nav/navItems.ts` — nav link.

---

## Task 1: User health columns + Alembic migration + migration guard

**Files:**
- Modify: `backend/app/db/models.py` (User class, after `created_at` ~line 182)
- Create: `backend/alembic/versions/f3a4b5c6d7e8_user_outlook_health.py`
- Test: `backend/tests/integration/test_user_outlook_health_migration.py`

- [ ] **Step 1: Write the failing migration-guard test**

Create `backend/tests/integration/test_user_outlook_health_migration.py` (mirrors `test_calendar_suggestion_migration.py`: `__file__`-relative Config + `DROP SCHEMA public CASCADE` isolation):

```python
"""Guard: the Alembic chain adds the outlook_last_* health columns to user.

The db_session fixture builds schema from models, which masks a missing
migration. This test runs `alembic upgrade head` against a fresh container.
"""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


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


def test_migration_adds_outlook_health_columns(fresh_db):
    engine, url = fresh_db
    cfg = _alembic_cfg(url)

    command.upgrade(cfg, "head")

    cols = {c["name"] for c in inspect(engine).get_columns("user")}
    for name in (
        "outlook_last_sync_at",
        "outlook_last_status",
        "outlook_last_reason",
        "outlook_last_trigger",
        "outlook_last_counts",
        "outlook_last_error",
    ):
        assert name in cols, f"missing column {name}"
```

- [ ] **Step 2: Run the test, verify it fails**

Run (see Environment preamble):
```bash
cd <WORKTREE>/backend
PYTHONPATH="<WORKTREE>/backend" /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_user_outlook_health_migration.py -p no:cacheprovider -q
```
Expected: FAIL — `alembic upgrade head` runs but the columns are absent (AssertionError: missing column outlook_last_sync_at).

- [ ] **Step 3: Add the columns to the `User` model**

In `backend/app/db/models.py`, inside `class User(Base)`, immediately after the `created_at` line (~182):

```python
    outlook_last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outlook_last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    outlook_last_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outlook_last_trigger: Mapped[str | None] = mapped_column(String(16), nullable=True)
    outlook_last_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outlook_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

(`JSON`, `Text`, `String`, `DateTime` are already imported at the top of the file.)

- [ ] **Step 4: Write the migration**

Create `backend/alembic/versions/f3a4b5c6d7e8_user_outlook_health.py`:

```python
"""user outlook_last_* health columns

Revision ID: f3a4b5c6d7e8
Revises: e1a2b3c4d5e6
Create Date: 2026-08-27 00:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("outlook_last_sync_at", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("outlook_last_status", sa.String(16), nullable=True))
    op.add_column("user", sa.Column("outlook_last_reason", sa.String(64), nullable=True))
    op.add_column("user", sa.Column("outlook_last_trigger", sa.String(16), nullable=True))
    op.add_column("user", sa.Column("outlook_last_counts", sa.JSON(), nullable=True))
    op.add_column("user", sa.Column("outlook_last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in (
        "outlook_last_error",
        "outlook_last_counts",
        "outlook_last_trigger",
        "outlook_last_reason",
        "outlook_last_status",
        "outlook_last_sync_at",
    ):
        op.drop_column("user", col)
```

Before writing, re-confirm the head is still `e1a2b3c4d5e6`:
```bash
cd <WORKTREE>/backend
PYTHONPATH="<WORKTREE>/backend" /Users/Janik/private/code/applicator/backend/.venv/bin/python -m alembic heads
```
Expected: a single head `e1a2b3c4d5e6`. If it differs, set `down_revision` to the reported head.

- [ ] **Step 5: Run the test, verify it passes**

Run the same pytest command as Step 2. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/f3a4b5c6d7e8_user_outlook_health.py backend/tests/integration/test_user_outlook_health_migration.py
git commit -m "feat(calendar): user outlook_last_* health columns + migration"
```

---

## Task 2: Sync refactor — typed token errors, `_record_health`, health on every path

**Files:**
- Modify: `backend/app/tasks/sync_outlook_calendar.py`
- Test: `backend/tests/integration/test_calendar_sync_health.py`

**Status/reason convention (from spec):** `outlook_last_status ∈ {"ok","skipped","error"}`. Skipped reasons: `no_token`, `no_calendar`, `oauth_disabled`. Error reasons: `token_refresh_failed`, `rate_limited`, `graph_error`. `outlook_last_counts` set only on `ok`; `outlook_last_error` set only on `error`. `outlook_last_trigger ∈ {"scheduled","manual"}`.

**Decision (locked):** `token_refresh_failed` is a broken *connection* the user must act on → `status="error"` (red badge), but the function still *returns* a skip-shaped dict `{"skipped": "token_refresh_failed"}` (no exception, no Celery retry — a revoked consent won't fix itself on retry). The return dict is internal/logging only; the user-facing signal is the health status.

- [ ] **Step 1: Write the failing health tests**

Create `backend/tests/integration/test_calendar_sync_health.py`:

```python
"""User.outlook_last_* health is stamped on every sync exit path."""
import pytest

from app.calendar_sync.graph import GraphRateLimited
from app.config import get_settings
from app.db.models import Application, JobPosting
from app.tasks import sync_outlook_calendar as mod
from app.tasks.sync_outlook_calendar import sync_user_calendar


class FakeGraph:
    """Scriptable GraphClient stand-in (mirrors test_sync_outlook_calendar_task)."""

    def __init__(self, calendar_id="cal-1", events=None, delta="delta-A", raise_exc=None):
        self.calendar_id = calendar_id
        self.events = events or []
        self.delta = delta
        self.raise_exc = raise_exc

    def resolve_calendar_id(self, name):
        return self.calendar_id

    def delta_events(self, calendar_id, delta_link=None):
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.events, self.delta


def _app(db, user):
    a = Application(user_id=user.id, url="https://acme.example/j", url_hash="a" * 64)
    db.add(a)
    db.flush()
    db.add(JobPosting(application_id=a.id, raw_text="x", company="Acme GmbH"))
    db.commit()
    return a


def _event(eid="e1"):
    return {
        "id": eid,
        "subject": "Acme interview",
        "bodyPreview": "hi",
        "start": {"dateTime": "2026-08-20T10:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-08-20T11:00:00.0000000", "timeZone": "UTC"},
        "organizer": {"emailAddress": {"address": "hr@acme.example"}},
    }


def test_ok_records_counts_and_status(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    graph = FakeGraph(events=[_event()], delta="delta-A")

    stats = sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="manual")

    db_session.refresh(user)
    assert user.outlook_last_status == "ok"
    assert user.outlook_last_reason is None
    assert user.outlook_last_trigger == "manual"
    assert user.outlook_last_error is None
    assert user.outlook_last_counts["created"] == stats["created"]
    assert user.outlook_last_sync_at is not None


def test_no_calendar_records_skipped(db_session, auth_user):
    _, user = auth_user
    graph = FakeGraph(calendar_id=None)

    result = sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="scheduled")

    assert result == {"skipped": "no_calendar"}
    db_session.refresh(user)
    assert user.outlook_last_status == "skipped"
    assert user.outlook_last_reason == "no_calendar"
    assert user.outlook_last_trigger == "scheduled"
    assert user.outlook_last_counts is None


def test_graph_exception_records_error_and_reraises(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    graph = FakeGraph(raise_exc=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="scheduled")

    db_session.refresh(user)
    assert user.outlook_last_status == "error"
    assert user.outlook_last_reason == "graph_error"
    assert "boom" in user.outlook_last_error
    assert user.outlook_last_counts is None


def test_rate_limited_records_error_and_reraises(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    graph = FakeGraph(raise_exc=GraphRateLimited(30))

    with pytest.raises(GraphRateLimited):
        sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="scheduled")

    db_session.refresh(user)
    assert user.outlook_last_status == "error"
    assert user.outlook_last_reason == "rate_limited"


def test_no_token_records_skipped(db_session, auth_user):
    _, user = auth_user
    user.ms_refresh_token_encrypted = None
    db_session.commit()

    # graph=None → goes through _access_token, which raises NoOutlookToken.
    result = sync_user_calendar(db_session, user, get_settings(), graph=None, trigger="manual")

    assert result == {"skipped": "no_token"}
    db_session.refresh(user)
    assert user.outlook_last_status == "skipped"
    assert user.outlook_last_reason == "no_token"


def test_token_refresh_failed_records_error(db_session, auth_user, monkeypatch):
    _, user = auth_user
    user.ms_refresh_token_encrypted = "encrypted-blob"
    db_session.commit()

    # Stub decrypt + Graph token call so refresh "fails" (no access_token).
    monkeypatch.setattr(mod, "decrypt", lambda *a, **k: "refresh-token")
    monkeypatch.setattr(
        mod, "acquire_token_by_refresh_token",
        lambda *a, **k: {"error": "invalid_grant", "error_description": "consent revoked"},
    )

    result = sync_user_calendar(db_session, user, get_settings(), graph=None, trigger="manual")

    assert result == {"skipped": "token_refresh_failed"}
    db_session.refresh(user)
    assert user.outlook_last_status == "error"
    assert user.outlook_last_reason == "token_refresh_failed"
    assert user.outlook_last_error  # non-empty message
```

- [ ] **Step 2: Run the tests, verify they fail**

```bash
cd <WORKTREE>/backend
PYTHONPATH="<WORKTREE>/backend" /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_calendar_sync_health.py -p no:cacheprovider -q
```
Expected: FAIL — `sync_user_calendar` has no `trigger` kwarg / does not stamp `outlook_last_*` / no `NoOutlookToken`.

- [ ] **Step 3: Refactor `_access_token` to distinguish the two token failures**

In `backend/app/tasks/sync_outlook_calendar.py`, add typed errors and change `_access_token` to raise instead of returning `None`. Also add the `datetime` import.

Replace the import block near the top — add `from datetime import datetime`:

```python
from __future__ import annotations

import logging
from datetime import datetime
```

Add exception classes above `_ms_config` (after `logger = ...`):

```python
class NoOutlookToken(Exception):
    """User has no stored Outlook refresh token (never connected)."""


class TokenRefreshFailed(Exception):
    """A refresh token exists but Graph declined to mint an access token."""
```

Replace the whole `_access_token` function:

```python
def _access_token(db: Session, user: User, settings: Settings) -> str:
    """Mint a Graph access token from the user's stored refresh token.

    Raises NoOutlookToken when nothing is stored, TokenRefreshFailed when the
    refresh is rejected (revoked consent). Rotates the stored refresh token if
    Graph issues a new one.
    """
    if not user.ms_refresh_token_encrypted:
        raise NoOutlookToken()
    refresh = decrypt(user.ms_refresh_token_encrypted, settings.app_secret_key)
    token = acquire_token_by_refresh_token(_ms_config(settings), refresh)
    access = token.get("access_token")
    if not access:
        msg = token.get("error_description") or token.get("error") or "token refresh failed"
        logger.warning(
            "calendar sync: token refresh failed for user %s: %s", user.id, msg
        )
        raise TokenRefreshFailed(str(msg))
    new_refresh = token.get("refresh_token")
    if new_refresh:
        user.ms_refresh_token_encrypted = encrypt(new_refresh, settings.app_secret_key)
    return access
```

- [ ] **Step 4: Add `_record_health` and stamp it on every path in `sync_user_calendar`**

Add the helper above `sync_user_calendar`:

```python
def _record_health(
    user: User,
    *,
    status: str,
    trigger: str,
    reason: str | None = None,
    counts: dict | None = None,
    error: str | None = None,
) -> None:
    # naive UTC, matching how all datetimes are stored in this codebase
    user.outlook_last_sync_at = datetime.utcnow()
    user.outlook_last_status = status
    user.outlook_last_reason = reason
    user.outlook_last_trigger = trigger
    user.outlook_last_counts = counts
    user.outlook_last_error = error
```

Replace the entire `sync_user_calendar` function body:

```python
def sync_user_calendar(
    db: Session,
    user: User,
    settings: Settings,
    *,
    graph: GraphClient | None = None,
    trigger: str = "scheduled",
) -> dict:
    """Sync one user's Outlook calendar. `graph` is injectable for tests.

    Records latest-run health on `user` on every exit path (skip/ok/error).
    """
    if graph is None:
        try:
            access = _access_token(db, user, settings)
        except NoOutlookToken:
            _record_health(user, status="skipped", reason="no_token", trigger=trigger)
            db.commit()
            return {"skipped": "no_token"}
        except TokenRefreshFailed as exc:
            _record_health(
                user, status="error", reason="token_refresh_failed",
                trigger=trigger, error=str(exc),
            )
            db.commit()
            return {"skipped": "token_refresh_failed"}
        graph = GraphClient(access)

    try:
        calendar_id = graph.resolve_calendar_id(settings.outlook_calendar_name)
        if calendar_id is None:
            logger.info(
                "calendar sync: calendar %r not found for user %s",
                settings.outlook_calendar_name, user.id,
            )
            _record_health(user, status="skipped", reason="no_calendar", trigger=trigger)
            db.commit()
            return {"skipped": "no_calendar"}

        state = _get_or_create_state(db, user, calendar_id)
        try:
            events, delta_link = graph.delta_events(calendar_id, state.delta_link)
        except DeltaExpired:
            logger.info(
                "calendar sync: delta link expired for user %s, full re-sync", user.id
            )
            state.delta_link = None
            events, delta_link = graph.delta_events(calendar_id, None)
    except GraphRateLimited as exc:
        _record_health(
            user, status="error", reason="rate_limited", trigger=trigger, error=str(exc)
        )
        db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 - record then re-raise for the task
        _record_health(
            user, status="error", reason="graph_error",
            trigger=trigger, error=str(exc)[:500],
        )
        db.commit()
        raise

    stats = sync_calendar_events(db, user, events)
    state.delta_link = delta_link
    _record_health(user, status="ok", trigger=trigger, counts=stats)
    db.commit()
    return stats
```

Note: `except GraphRateLimited` is listed *before* `except Exception` so the rate-limit reason wins (GraphRateLimited subclasses GraphError → Exception). `DeltaExpired` is handled by the inner try; any GraphRateLimited/other error raised by the re-sync call still propagates to the outer handlers.

The task loop `sync_outlook_calendar_task` is unchanged — it calls `sync_user_calendar(db, user, settings)` which now defaults `trigger="scheduled"`.

- [ ] **Step 5: Run the tests, verify they pass**

Run the Step 2 command. Expected: PASS (6 tests).

- [ ] **Step 6: Run the existing sync task tests to confirm no regression**

```bash
cd <WORKTREE>/backend
PYTHONPATH="<WORKTREE>/backend" /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_sync_outlook_calendar_task.py -p no:cacheprovider -q
```
Expected: PASS (existing 5 tests still green — they inject `graph`, default `trigger` applies).

- [ ] **Step 7: Commit**

```bash
git add backend/app/tasks/sync_outlook_calendar.py backend/tests/integration/test_calendar_sync_health.py
git commit -m "feat(calendar): record latest sync health on User for every path"
```

---

## Task 3: Endpoints — `sync-status`, `sync-now`, `entries`

**Files:**
- Modify: `backend/app/api/calendar.py`
- Test: `backend/tests/integration/test_calendar_sync_api.py`

- [ ] **Step 1: Write the failing endpoint tests**

Create `backend/tests/integration/test_calendar_sync_api.py`:

```python
"""API tests for Outlook sync visibility: sync-status, sync-now, entries."""
from datetime import datetime

from app.calendar_sync.sync import MS_GRAPH
from app.db.models import (
    Application,
    CalendarSuggestion,
    CalendarSuggestionStatus,
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


def _suggestion(db, user, app=None, *, eid, status):
    s = CalendarSuggestion(
        user_id=user.id,
        external_source=MS_GRAPH,
        external_id=eid,
        status=status,
        subject="Interview",
        starts_at=datetime(2026, 9, 1, 10, 0),
        ends_at=datetime(2026, 9, 1, 11, 0),
        location="Zoom",
        organizer_email="hr@acme.example",
        suggested_application_id=(app.id if app else None),
        match_score=0.9 if app else None,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_sync_status_returns_health_and_oauth_flag(client, db_session, auth_user):
    _, user = auth_user
    user.outlook_last_sync_at = datetime(2026, 8, 27, 9, 0)
    user.outlook_last_status = "ok"
    user.outlook_last_trigger = "scheduled"
    user.outlook_last_counts = {"created": 1, "updated": 0, "deleted": 0, "skipped": 0}
    db_session.commit()

    r = client.get("/api/calendar/sync-status")
    assert r.status_code == 200
    data = r.json()
    assert data["last_status"] == "ok"
    assert data["last_counts"]["created"] == 1
    assert "oauth_enabled" in data


def test_entries_returns_all_statuses(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    _suggestion(db_session, user, app, eid="e1", status=CalendarSuggestionStatus.pending)
    _suggestion(db_session, user, app, eid="e2", status=CalendarSuggestionStatus.confirmed)
    _suggestion(db_session, user, None, eid="e3", status=CalendarSuggestionStatus.dismissed)

    r = client.get("/api/calendar/entries")
    assert r.status_code == 200
    data = r.json()
    statuses = {row["status"] for row in data}
    assert statuses == {"pending", "confirmed", "dismissed"}
    ext = next(row for row in data if row["external_id"] == "e1")
    assert ext["suggested_application"]["company"] == "Acme GmbH"


def test_sync_now_oauth_disabled_returns_skipped_200(client, db_session, auth_user, monkeypatch):
    from app.api import calendar as cal_mod

    class _S:
        oauth_enabled = False

    monkeypatch.setattr(cal_mod, "get_settings", lambda: _S())

    r = client.post("/api/calendar/sync-now")
    assert r.status_code == 200
    data = r.json()
    assert data["last_status"] == "skipped"
    assert data["last_reason"] == "oauth_disabled"
    assert data["last_trigger"] == "manual"


def test_sync_now_runs_sync_and_returns_health(client, db_session, auth_user, monkeypatch):
    from app.api import calendar as cal_mod
    from app.tasks.sync_outlook_calendar import _record_health

    class _S:
        oauth_enabled = True

    monkeypatch.setattr(cal_mod, "get_settings", lambda: _S())

    def _fake_sync(db, user, settings, *, trigger):
        _record_health(
            user, status="ok", trigger=trigger,
            counts={"created": 2, "updated": 0, "deleted": 0, "skipped": 0},
        )
        db.commit()
        return {"created": 2}

    monkeypatch.setattr(cal_mod, "sync_user_calendar", _fake_sync)

    r = client.post("/api/calendar/sync-now")
    assert r.status_code == 200
    data = r.json()
    assert data["last_status"] == "ok"
    assert data["last_trigger"] == "manual"
    assert data["last_counts"]["created"] == 2


def test_sync_now_broken_connection_returns_200_not_500(client, db_session, auth_user, monkeypatch):
    from app.api import calendar as cal_mod
    from app.tasks.sync_outlook_calendar import _record_health

    class _S:
        oauth_enabled = True

    monkeypatch.setattr(cal_mod, "get_settings", lambda: _S())

    def _boom(db, user, settings, *, trigger):
        _record_health(
            user, status="error", reason="graph_error", trigger=trigger, error="boom",
        )
        db.commit()
        raise RuntimeError("boom")

    monkeypatch.setattr(cal_mod, "sync_user_calendar", _boom)

    r = client.post("/api/calendar/sync-now")
    assert r.status_code == 200  # a failed connection is a successful diagnostic
    data = r.json()
    assert data["last_status"] == "error"
    assert data["last_reason"] == "graph_error"
```

- [ ] **Step 2: Run the tests, verify they fail**

```bash
cd <WORKTREE>/backend
PYTHONPATH="<WORKTREE>/backend" /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration/test_calendar_sync_api.py -p no:cacheprovider -q
```
Expected: FAIL — endpoints 404 (not yet defined).

- [ ] **Step 3: Add imports to `backend/app/api/calendar.py`**

Extend the existing imports. Add after the `from app.calendar_feed.ics import ...` line:

```python
from app.calendar_sync.graph import GraphRateLimited
from app.config import Settings, get_settings
from app.tasks.sync_outlook_calendar import _record_health, sync_user_calendar
```

(`datetime` and `CalendarSuggestion`/`CalendarSuggestionStatus`/`Application`/`JobPosting` are already imported.)

- [ ] **Step 4: Add response models + `sync-status` + `sync-now`**

Append to `backend/app/api/calendar.py` (after the existing suggestion endpoints, before `_lookup_by_calendar_token`):

```python
class SyncCounts(BaseModel):
    created: int
    updated: int
    deleted: int
    skipped: int


class SyncStatusOut(BaseModel):
    last_sync_at: UtcDateTime | None
    last_status: str | None
    last_reason: str | None
    last_trigger: str | None
    last_counts: SyncCounts | None
    last_error: str | None
    oauth_enabled: bool


def _sync_status_out(user: User, settings: Settings) -> SyncStatusOut:
    return SyncStatusOut(
        last_sync_at=user.outlook_last_sync_at,
        last_status=user.outlook_last_status,
        last_reason=user.outlook_last_reason,
        last_trigger=user.outlook_last_trigger,
        last_counts=user.outlook_last_counts,
        last_error=user.outlook_last_error,
        oauth_enabled=settings.oauth_enabled,
    )


@router.get("/sync-status", response_model=SyncStatusOut)
def get_sync_status(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> SyncStatusOut:
    return _sync_status_out(user, get_settings())


@router.post("/sync-now", response_model=SyncStatusOut)
def sync_now(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> SyncStatusOut:
    settings = get_settings()
    if not settings.oauth_enabled:
        _record_health(user, status="skipped", reason="oauth_disabled", trigger="manual")
        db.commit()
        db.refresh(user)
        return _sync_status_out(user, settings)
    try:
        sync_user_calendar(db, user, settings, trigger="manual")
    except Exception:  # noqa: BLE001 - health is recorded inside; report it, don't 500
        db.rollback()
    db.refresh(user)
    return _sync_status_out(user, settings)
```

Note: `SyncStatusOut.last_counts` is a Pydantic model but `user.outlook_last_counts` is a plain `dict` from the JSON column — Pydantic validates the dict into `SyncCounts` automatically.

- [ ] **Step 5: Add the `entries` endpoint**

Append after the code from Step 4:

```python
class CalendarEntryOut(BaseModel):
    id: uuid.UUID
    external_id: str
    subject: str | None
    starts_at: UtcDateTime
    ends_at: UtcDateTime | None
    location: str | None
    organizer_email: str | None
    status: str
    match_score: float | None
    suggested_application: SuggestedApp | None
    interaction_id: uuid.UUID | None


@router.get("/entries", response_model=list[CalendarEntryOut])
def list_calendar_entries(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> list[CalendarEntryOut]:
    rows = db.execute(
        select(CalendarSuggestion, Application, JobPosting)
        .outerjoin(Application, CalendarSuggestion.suggested_application_id == Application.id)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(CalendarSuggestion.user_id == user.id)
        .order_by(CalendarSuggestion.starts_at.desc())
    ).all()
    out: list[CalendarEntryOut] = []
    for s, app, jp in rows:
        suggested = None
        if app is not None:
            suggested = SuggestedApp(
                id=app.id, display_id=app.display_id, company=_company(jp, app.url)
            )
        out.append(
            CalendarEntryOut(
                id=s.id,
                external_id=s.external_id,
                subject=s.subject,
                starts_at=s.starts_at,
                ends_at=s.ends_at,
                location=s.location,
                organizer_email=s.organizer_email,
                status=s.status.value,
                match_score=s.match_score,
                suggested_application=suggested,
                interaction_id=s.interaction_id,
            )
        )
    return out
```

- [ ] **Step 6: Run the tests, verify they pass**

Run the Step 2 command. Expected: PASS (5 tests).

- [ ] **Step 7: Guard against circular import**

`app.api.calendar` now imports from `app.tasks.sync_outlook_calendar`. Confirm the app still boots:
```bash
cd <WORKTREE>/backend
PYTHONPATH="<WORKTREE>/backend" /Users/Janik/private/code/applicator/backend/.venv/bin/python -c "from app.main import app; print('ok')"
```
Expected: `ok`. If an ImportError appears, move the `sync_user_calendar`/`_record_health` import to function-local inside `sync_now`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/calendar.py backend/tests/integration/test_calendar_sync_api.py
git commit -m "feat(calendar): sync-status, sync-now, entries endpoints"
```

---

## Task 4: Frontend API client

**Files:**
- Modify: `frontend/src/api/calendar.ts`

- [ ] **Step 1: Add types + methods**

In `frontend/src/api/calendar.ts`, add these types after the existing `CalendarSuggestion` type:

```typescript
export type SyncCounts = {
  created: number;
  updated: number;
  deleted: number;
  skipped: number;
};

export type SyncStatus = {
  last_sync_at: string | null;
  last_status: "ok" | "skipped" | "error" | null;
  last_reason: string | null;
  last_trigger: "scheduled" | "manual" | null;
  last_counts: SyncCounts | null;
  last_error: string | null;
  oauth_enabled: boolean;
};

export type CalendarEntry = {
  id: string;
  external_id: string;
  subject: string | null;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  organizer_email: string | null;
  status: "pending" | "confirmed" | "dismissed";
  match_score: number | null;
  suggested_application: {
    id: string;
    display_id: number;
    company: string;
  } | null;
  interaction_id: string | null;
};
```

Add these three methods to the `calendar` object (after `dismissSuggestion`):

```typescript
  syncStatus: () => api<SyncStatus>("/api/calendar/sync-status"),
  syncNow: () => api<SyncStatus>("/api/calendar/sync-now", { method: "POST" }),
  entries: () => api<CalendarEntry[]>("/api/calendar/entries"),
```

- [ ] **Step 2: Type-check**

```bash
cd <WORKTREE>/frontend && npm install
node_modules/typescript/bin/tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/calendar.ts
git commit -m "feat(frontend): calendar sync-status/sync-now/entries API client"
```

---

## Task 5: Frontend page + route + nav

**Files:**
- Create: `frontend/src/pages/SettingsOutlookSync.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/nav/navItems.ts`

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/SettingsOutlookSync.tsx` (mirrors `SettingsWebhooks.tsx` structure/classes):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  calendar,
  type CalendarEntry,
  type SyncStatus,
} from "../api/calendar";

function StatusBadge({ status }: { status: string | null }) {
  const tone =
    status === "ok"
      ? "bg-emerald-100 text-emerald-700"
      : status === "error"
        ? "bg-rose-100 text-rose-700"
        : "bg-amber-100 text-amber-700";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${tone}`}>
      {status ?? "—"}
    </span>
  );
}

const ENTRY_STATUS_LABEL: Record<CalendarEntry["status"], string> = {
  pending: "Ausstehend",
  confirmed: "Bestätigt",
  dismissed: "Ausgeblendet",
};

function EntryStatusBadge({ status }: { status: CalendarEntry["status"] }) {
  const tone =
    status === "confirmed"
      ? "bg-emerald-100 text-emerald-700"
      : status === "dismissed"
        ? "bg-rose-100 text-rose-700"
        : "bg-amber-100 text-amber-700";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${tone}`}>
      {ENTRY_STATUS_LABEL[status]}
    </span>
  );
}

function ConnectionCard() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["outlook-sync-status"],
    queryFn: () => calendar.syncStatus(),
  });
  const sync = useMutation({
    mutationFn: () => calendar.syncNow(),
    onSuccess: (data: SyncStatus) => {
      qc.setQueryData(["outlook-sync-status"], data);
      qc.invalidateQueries({ queryKey: ["calendar-entries"] });
      qc.invalidateQueries({ queryKey: ["calendar-suggestions"] });
      qc.invalidateQueries({ queryKey: ["suggestions"] });
    },
  });

  const s = q.data;
  return (
    <div className="border border-border rounded p-4 space-y-3 mb-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Outlook-Verbindung</h2>
        <button
          type="button"
          disabled={sync.isPending || (s ? !s.oauth_enabled : false)}
          onClick={() => sync.mutate()}
          className="px-3 py-1 rounded text-sm font-medium bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-50"
        >
          {sync.isPending ? "Synchronisiere…" : "Jetzt synchronisieren"}
        </button>
      </div>
      {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
      {s && !s.oauth_enabled && (
        <p className="text-sm text-muted">Outlook-Integration ist deaktiviert.</p>
      )}
      {s && (
        <div className="space-y-1 text-sm">
          <div className="flex gap-2 items-center">
            <StatusBadge status={s.last_status} />
            {s.last_reason && <span className="text-muted">{s.last_reason}</span>}
            {s.last_trigger && (
              <span className="text-muted">· {s.last_trigger}</span>
            )}
          </div>
          <div className="text-muted">
            Letzte Synchronisation:{" "}
            {s.last_sync_at ? new Date(s.last_sync_at).toLocaleString() : "—"}
          </div>
          {s.last_counts && (
            <div className="text-muted">
              +{s.last_counts.created} · ~{s.last_counts.updated} · −
              {s.last_counts.deleted} · {s.last_counts.skipped} übersprungen
            </div>
          )}
          {s.last_error && (
            <div className="text-rose-600 text-xs break-words">{s.last_error}</div>
          )}
        </div>
      )}
      {sync.isError && (
        <p className="text-xs text-red-600">Synchronisation fehlgeschlagen.</p>
      )}
    </div>
  );
}

function EntriesTable() {
  const q = useQuery({
    queryKey: ["calendar-entries"],
    queryFn: () => calendar.entries(),
  });
  return (
    <div>
      <h2 className="text-lg font-semibold mb-3">Kalender-Einträge</h2>
      {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
      {q.data && q.data.length === 0 && (
        <div className="text-muted text-sm">
          Noch keine Kalender-Einträge übernommen.
        </div>
      )}
      {q.data && q.data.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 pr-2">Zeit</th>
              <th className="py-2 pr-2">Betreff</th>
              <th className="py-2 pr-2">Zuordnung</th>
              <th className="py-2 pr-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((e: CalendarEntry) => (
              <tr key={e.id} className="border-b border-border">
                <td className="py-2 pr-2 whitespace-nowrap">
                  {new Date(e.starts_at).toLocaleString()}
                </td>
                <td className="py-2 pr-2">{e.subject ?? "—"}</td>
                <td className="py-2 pr-2">
                  {e.suggested_application ? (
                    <Link
                      to={`/applications/${e.suggested_application.id}`}
                      className="text-accent hover:underline"
                    >
                      #{e.suggested_application.display_id}{" "}
                      {e.suggested_application.company}
                    </Link>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="py-2 pr-2">
                  <EntryStatusBadge status={e.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function SettingsOutlookSync() {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Outlook sync</h1>
      <ConnectionCard />
      <EntriesTable />
    </div>
  );
}
```

- [ ] **Step 2: Wire the route in `frontend/src/App.tsx`**

Add the import alongside the other page imports (after the `SettingsWebhooks` import, line ~12):

```tsx
import SettingsOutlookSync from "./pages/SettingsOutlookSync";
```

Add the route block right after the `/settings/webhooks` `<Route>` (ends ~line 123), mirroring it:

```tsx
      <Route
        path="/settings/outlook"
        element={
          <ProtectedShell>
            <SettingsOutlookSync />
          </ProtectedShell>
        }
      />
```

- [ ] **Step 3: Add the nav link in `frontend/src/components/nav/navItems.ts`**

Add after the `/settings/webhooks` entry (last item in `NAV_ITEMS`):

```typescript
  { to: "/settings/outlook", label: "Outlook sync", group: "settings" },
```

- [ ] **Step 4: Type-check**

```bash
cd <WORKTREE>/frontend
node_modules/typescript/bin/tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SettingsOutlookSync.tsx frontend/src/App.tsx frontend/src/components/nav/navItems.ts
git commit -m "feat(frontend): Outlook sync visibility page + route + nav"
```

---

## Final verification (after all tasks)

- [ ] Full backend calendar test sweep:
```bash
cd <WORKTREE>/backend
PYTHONPATH="<WORKTREE>/backend" /Users/Janik/private/code/applicator/backend/.venv/bin/python -m pytest tests/integration -k "calendar or sync_outlook or outlook_health" -p no:cacheprovider -q
```
Expected: all green.

- [ ] Frontend type-check clean: `cd <WORKTREE>/frontend && node_modules/typescript/bin/tsc --noEmit`.

- [ ] Final code review of the whole branch, then superpowers:finishing-a-development-branch.

---

## Self-Review (completed against the spec)

**Spec coverage:**
- Health fields on `User` (six columns) → Task 1. ✓
- Alembic migration + migration guard → Task 1. ✓
- `_record_health` + `trigger` param + record on no_token/no_calendar/ok/rate_limited/graph_error → Task 2. ✓
- Distinguish `no_token` vs `token_refresh_failed` (typed `_access_token`) → Task 2. ✓
- `sync-status` / `sync-now` (200 on broken connection, oauth_disabled path) / `entries` (all statuses, `starts_at desc`) → Task 3. ✓
- Frontend API client types + methods → Task 4. ✓
- Page (connection card + entries table), route, nav → Task 5. ✓
- Testing per spec (migration guard, sync health, endpoints, raw tsc) → Tasks 1–5. ✓

**Type consistency:** `_record_health(user, *, status, trigger, reason=None, counts=None, error=None)` — same signature used in Task 2 impl and Task 3 tests/endpoint. `SyncStatusOut`/`SyncStatus`, `CalendarEntryOut`/`CalendarEntry` field names match front↔back. `status.value` yields the string the frontend union expects.

**Known deviations from spec (intentional, documented):**
- `token_refresh_failed` uses `status="error"` (red, actionable) while still *returning* a skip-shaped dict — documented at the top of Task 2. Spec listed it among error-reasons, so this matches intent.
- Reused `_record_health` from the tasks module inside the `sync-now` `oauth_disabled` branch (DRY) instead of inlining the six assignments.

**Out of scope (per spec, not built):** per-run history table, raw Graph JSON storage, retention/pruning, entries pagination, multi-calendar.
