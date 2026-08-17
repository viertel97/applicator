# Interview Calendar + Email Ingestion + iCal Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interview-centric calendar to the job-application tracker with a responsive calendar view, forward-to-add email ingestion (inboxbridge.io webhook → LLM parse → auto-attach + review), and a per-user secret-token iCal feed of confirmed interviews.

**Architecture:** Three independent, shippable phases. Phase 1 adds all new DB columns/flag + per-user tokens in one migration and renders manual-entry interviews on a responsive calendar (month grid desktop, agenda list mobile). Phase 2 adds the anonymous token-authed `.ics` feed. Phase 3 adds the inbound-email webhook, LLM extractor, pure-function matcher, and a review/confirm UI. New pure logic (ICS serializer, extractor, matcher, date bucketing) is DB-free and unit-tested; enum changes get a DB-free binding test to catch model/migration drift (testcontainers builds schema from models, not migrations).

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2, Alembic, Postgres 16, `httpx`-based `GroqClient` (OpenAI-compatible LLM), pytest + testcontainers. Frontend — React 18, react-router v6, `@tanstack/react-query` v5, plain `fetch` wrapper (`api<T>`), Tailwind v3 + CSS-var theme tokens, `node:test` unit runner.

---

## File Structure

**Backend — new files:**
- `backend/app/email_ingest/interview_extract.py` — LLM interview-field extractor (DB-free).
- `backend/app/email_ingest/interview_match.py` — pure application matcher.
- `backend/app/calendar_feed/ics.py` — RFC5545 ICS serializer (DB-free). (Package name `calendar_feed` avoids shadowing the stdlib `calendar` module.)
- `backend/app/calendar_feed/__init__.py`
- `backend/app/api/calendar.py` — `GET /api/calendar/interviews`, `GET /api/calendar/{token}.ics`, token read/regenerate endpoints.
- `backend/app/api/webhooks.py` — `POST /api/webhooks/inbound-email/{ingest_token}`.
- `backend/app/services/tokens.py` — lazy token get-or-create + regenerate helpers.
- Alembic migration `backend/alembic/versions/<rev>_interview_calendar.py`.

**Backend — modified files:**
- `backend/app/db/models.py` — `Interaction.location/ends_at/needs_review`, `InteractionCreatedFrom.email_webhook`, `User.ingest_token/calendar_token`.
- `backend/app/api/interactions.py` — extend `InteractionIn`/`InteractionPatch`/`InteractionOut` with `location`, `ends_at`, `needs_review`, and allow `application_id` reassignment on PATCH.
- `backend/app/main.py` — register `calendar` and `webhooks` routers.

**Frontend — new files:**
- `frontend/src/api/calendar.ts` — endpoint module + types.
- `frontend/src/lib/calendarBuckets.ts` (+ `.test.ts`) — pure date bucketing.
- `frontend/src/pages/Calendar.tsx` — responsive calendar page.
- `frontend/src/components/calendar/MonthGrid.tsx`, `AgendaList.tsx`, `InterviewChip.tsx`.
- `frontend/src/components/InterviewReviewModal.tsx` — confirm/reassign dialog.
- `frontend/src/hooks/useReviewCount.ts` — needs-review badge count.
- `frontend/src/pages/settings/CalendarTokens.tsx` — show/regenerate URLs.

**Frontend — modified files:**
- `frontend/src/App.tsx` — add `/calendar` route (+ `/settings/calendar`).
- `frontend/src/components/nav/navItems.ts` — add Calendar nav item.
- `frontend/src/components/nav/DesktopNav.tsx`, `MobileNav.tsx` — review-count badge on Calendar link.

---

# PHASE 1 — Model + Calendar View

## Task 1: Model columns + enum value

**Files:**
- Modify: `backend/app/db/models.py:99-104` (`InteractionCreatedFrom`), `:339-387` (`Interaction`), `:165-172` (`User`)
- Test: `backend/tests/unit/test_interview_calendar_model.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_interview_calendar_model.py
from sqlalchemy.dialects import postgresql
from app.db.models import Interaction, User, InteractionCreatedFrom


def _col_type(model, name):
    return model.__table__.c[name].type


def test_created_from_has_email_webhook_value():
    assert InteractionCreatedFrom.email_webhook.value == "email_webhook"


def test_created_from_binds_values_not_names():
    bind = _col_type(Interaction, "created_from").bind_processor(postgresql.dialect())
    assert bind(InteractionCreatedFrom.email_webhook) == "email_webhook"


def test_interaction_has_new_columns():
    cols = Interaction.__table__.c
    assert "location" in cols and cols["location"].nullable
    assert "ends_at" in cols and cols["ends_at"].nullable
    assert "needs_review" in cols
    assert cols["needs_review"].nullable is False
    assert cols["needs_review"].server_default is not None


def test_user_has_token_columns():
    cols = User.__table__.c
    assert "ingest_token" in cols and cols["ingest_token"].nullable
    assert "calendar_token" in cols and cols["calendar_token"].nullable
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_interview_calendar_model.py -v`
Expected: FAIL (`AttributeError: email_webhook` / missing columns).

- [ ] **Step 3: Edit the models**

In `InteractionCreatedFrom` add the value:
```python
class InteractionCreatedFrom(str, enum.Enum):
    manual = "manual"; inquiry_migration = "inquiry_migration"
    graph_sync = "graph_sync"; eml_import = "eml_import"; inquiry_sent = "inquiry_sent"
    email_webhook = "email_webhook"
```

In `Interaction`, after the `interview_stage` column add:
```python
    location = Column(Text, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    needs_review = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
```

In `User`, after `ms_refresh_token_encrypted` add:
```python
    ingest_token = Column(String(64), nullable=True, unique=True)
    calendar_token = Column(String(64), nullable=True, unique=True)
```
Ensure `Boolean` and `String` are imported at the top of the file (they already are — `Boolean` is used by `Application.job_posting_dirty`, `String` by `User.ms_oid`).

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_interview_calendar_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/unit/test_interview_calendar_model.py
git commit -m "feat(model): interview location/ends_at/needs_review + user tokens + email_webhook enum"
```

## Task 2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<rev>_interview_calendar.py`

- [ ] **Step 1: Generate a revision stub**

Run: `cd backend && ../backend/.venv/bin/python -m alembic revision -m "interview_calendar"` (sandbox off — needs DB URL only for autogenerate, which we are NOT using; a plain `revision` needs no DB). Note the generated filename/rev id. `down_revision` must be `"b4c5d6e7f8a9"` (current head).

- [ ] **Step 2: Write the migration body**

Replace the generated `upgrade`/`downgrade` with (keep the auto-generated `revision`/`down_revision` values):
```python
import sqlalchemy as sa
from alembic import op

# revision identifiers set by the generator; down_revision must be "b4c5d6e7f8a9"

def upgrade() -> None:
    # New enum value (ADD VALUE is transaction-safe on PG12+ as long as we do
    # not USE the value in this migration; we only add columns here).
    op.execute(
        "ALTER TYPE interactioncreatedfrom ADD VALUE IF NOT EXISTS 'email_webhook'"
    )
    op.add_column("interaction", sa.Column("location", sa.Text(), nullable=True))
    op.add_column("interaction", sa.Column("ends_at", sa.DateTime(), nullable=True))
    op.add_column(
        "interaction",
        sa.Column(
            "needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("user", sa.Column("ingest_token", sa.String(64), nullable=True))
    op.add_column("user", sa.Column("calendar_token", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_user_ingest_token", "user", ["ingest_token"])
    op.create_unique_constraint("uq_user_calendar_token", "user", ["calendar_token"])


def downgrade() -> None:
    op.drop_constraint("uq_user_calendar_token", "user", type_="unique")
    op.drop_constraint("uq_user_ingest_token", "user", type_="unique")
    op.drop_column("user", "calendar_token")
    op.drop_column("user", "ingest_token")
    op.drop_column("interaction", "needs_review")
    op.drop_column("interaction", "ends_at")
    op.drop_column("interaction", "location")
    # Postgres cannot drop a single enum value; leave 'email_webhook' in place.
```

- [ ] **Step 3: Verify heads are linear**

Run: `cd backend && ../backend/.venv/bin/python -m alembic heads`
Expected: a single head — the new revision. (Requires `DATABASE_URL` in env/.env pointing at a reachable Postgres. If unreachable in the harness, ask the user to run `alembic upgrade head` in their terminal and confirm; note this in the task handoff.)

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(migration): interview calendar columns + user tokens"
```

## Task 3: Calendar interviews endpoint

**Files:**
- Create: `backend/app/api/calendar.py`
- Modify: `backend/app/main.py:41-68`
- Test: `backend/tests/integration/test_calendar_api.py` (create)

- [ ] **Step 1: Write the failing API test**

```python
# backend/tests/integration/test_calendar_api.py
import uuid
from datetime import datetime, timedelta, timezone

from app.db.models import (
    Application, JobPosting, Interaction, InteractionChannel,
    InteractionDirection, InterviewStage,
)


def _app_with_interview(db, user, *, company, when, needs_review=False):
    app = Application(user_id=user.id, url="https://acme.example/jobs/1",
                      url_hash=uuid.uuid4().hex)
    db.add(app); db.flush()
    db.add(JobPosting(application_id=app.id, raw_text="x", company=company))
    it = Interaction(application_id=app.id, occurred_at=when,
                     direction=InteractionDirection.in_,
                     channel=InteractionChannel.interview,
                     interview_stage=InterviewStage.technical,
                     needs_review=needs_review)
    db.add(it); db.commit()
    return app, it


def test_calendar_interviews_range_filter(app_client, db_session, auth_user):
    now = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
    _app_with_interview(db_session, auth_user, company="Acme", when=now)
    _app_with_interview(db_session, auth_user, company="OldCo",
                        when=now - timedelta(days=90))
    resp = app_client.get(
        "/api/calendar/interviews",
        params={"from": (now - timedelta(days=1)).isoformat(),
                "to": (now + timedelta(days=1)).isoformat()},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["interview_stage"] == "technical"
    assert rows[0]["needs_review"] is False


def test_calendar_interviews_requires_auth(app_client_noauth):
    resp = app_client_noauth.get("/api/calendar/interviews")
    assert resp.status_code == 401
```

If `app_client_noauth` does not exist, use the existing unauthenticated client fixture from `tests/integration/conftest.py` (a `TestClient` with no session cookie); check the fixture names there and adapt.

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/integration/test_calendar_api.py -v` (sandbox off — testcontainers needs Docker)
Expected: FAIL (404, route missing).

- [ ] **Step 3: Implement the endpoint**

```python
# backend/app/api/calendar.py
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import (
    Application, JobPosting, Interaction, InteractionChannel, InterviewStage, User,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class CalendarInterview(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    display_id: int
    company: str
    starts_at: datetime
    ends_at: datetime | None
    location: str | None
    interview_stage: InterviewStage | None
    needs_review: bool


def _company(jp: JobPosting | None, url: str) -> str:
    if jp and jp.company:
        return jp.company
    host = urlparse(url).netloc
    return host or "Unknown"


@router.get("/interviews", response_model=list[CalendarInterview])
def list_interviews(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
):
    stmt = (
        select(Interaction, Application, JobPosting)
        .join(Application, Interaction.application_id == Application.id)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
            Interaction.channel == InteractionChannel.interview,
        )
    )
    if from_ is not None:
        stmt = stmt.where(Interaction.occurred_at >= from_)
    if to is not None:
        stmt = stmt.where(Interaction.occurred_at <= to)
    stmt = stmt.order_by(Interaction.occurred_at.asc())

    out: list[CalendarInterview] = []
    for it, app, jp in db.execute(stmt).all():
        out.append(CalendarInterview(
            id=it.id, application_id=app.id, display_id=app.display_id,
            company=_company(jp, app.url), starts_at=it.occurred_at,
            ends_at=it.ends_at, location=it.location,
            interview_stage=it.interview_stage, needs_review=it.needs_review,
        ))
    return out
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, import and include it next to the other routers:
```python
from app.api import calendar as calendar_api
...
    app.include_router(calendar_api.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/integration/test_calendar_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/calendar.py backend/app/main.py backend/tests/integration/test_calendar_api.py
git commit -m "feat(calendar): GET /api/calendar/interviews range query"
```

## Task 4: Extend interaction schemas with new fields

**Files:**
- Modify: `backend/app/api/interactions.py:40-80` (schemas), `:168-180` (PATCH)
- Test: `backend/tests/integration/test_interactions_api.py` (append) or new `test_interaction_new_fields_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_interaction_new_fields_api.py
from datetime import datetime, timezone


def test_create_interview_with_location_and_ends_at(app_client, db_session, auth_user, make_application):
    app = make_application(db_session, auth_user)  # existing helper; adapt name
    start = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
    resp = app_client.post(
        f"/api/applications/{app.id}/interactions",
        json={"direction": "in", "channel": "interview",
              "occurred_at": start.isoformat(), "ends_at": end.isoformat(),
              "location": "https://meet.example/abc", "interview_stage": "onsite"},
    )
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert body["location"] == "https://meet.example/abc"
    assert body["ends_at"].startswith("2026-09-01T15:00")
    assert body["needs_review"] is False


def test_patch_reassigns_application_and_clears_review(app_client, db_session, auth_user, make_application):
    app_a = make_application(db_session, auth_user)
    app_b = make_application(db_session, auth_user)
    r = app_client.post(f"/api/applications/{app_a.id}/interactions",
                        json={"direction": "in", "channel": "interview"})
    iid = r.json()["id"]
    resp = app_client.patch(f"/api/interactions/{iid}",
                            json={"application_id": str(app_b.id), "needs_review": False})
    assert resp.status_code == 200
    assert resp.json()["application_id"] == str(app_b.id)
```

Use whatever application-creation helper the existing `test_interactions_api.py` uses; if none, create the `Application` inline as in Task 3.

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/integration/test_interaction_new_fields_api.py -v`
Expected: FAIL (`location` not accepted / not returned).

- [ ] **Step 3: Extend the schemas + PATCH**

In `InteractionIn` add:
```python
    location: str | None = None
    ends_at: datetime | None = None
```
In `InteractionPatch` add:
```python
    location: str | None = None
    ends_at: datetime | None = None
    needs_review: bool | None = None
    application_id: uuid.UUID | None = None
```
In `InteractionOut` add:
```python
    location: str | None
    ends_at: datetime | None
    needs_review: bool
```
The create path (`_message_to_interaction` / the POST create handler) must copy `location` and `ends_at` from `InteractionIn` onto the new `Interaction`. Find the POST create handler in `interactions.py` and set `location=body.location, ends_at=body.ends_at` when constructing the row.

The PATCH handler already loops `model_dump(exclude_unset=True)` and `setattr`s — but `application_id` reassignment must re-verify ownership of the *target* application. Update `patch_interaction`:
```python
    it = _own_interaction(db, user, iid)
    data = body.model_dump(exclude_unset=True)
    if "application_id" in data:
        _own_app(db, user, data["application_id"])  # raises 404 if not owned
    for field, val in data.items():
        setattr(it, field, val)
    db.commit(); db.refresh(it)
    return it
```
Confirm `_own_app` exists and accepts `(db, user, app_id)`; if its signature differs, adapt.

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/integration/test_interaction_new_fields_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/interactions.py backend/tests/integration/test_interaction_new_fields_api.py
git commit -m "feat(interactions): location/ends_at/needs_review fields + app reassignment on PATCH"
```

## Task 5: Frontend calendar bucketing helper (pure)

**Files:**
- Create: `frontend/src/lib/calendarBuckets.ts`, `frontend/src/lib/calendarBuckets.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/calendarBuckets.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { groupByDay, monthMatrix } from "./calendarBuckets.ts";

const ev = (id: string, starts_at: string) =>
  ({ id, starts_at } as { id: string; starts_at: string });

test("groupByDay buckets by local calendar day, sorted ascending", () => {
  const rows = [
    ev("b", "2026-09-02T09:00:00Z"),
    ev("a", "2026-09-01T14:00:00Z"),
    ev("c", "2026-09-01T08:00:00Z"),
  ];
  const groups = groupByDay(rows);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].items.map((r) => r.id).join(","), "c,a");
  assert.equal(groups[1].items[0].id, "b");
});

test("monthMatrix returns 6 weeks of 7 days covering the month", () => {
  const weeks = monthMatrix(2026, 8); // 0-based month => September 2026
  assert.equal(weeks.length, 6);
  assert.equal(weeks[0].length, 7);
  const all = weeks.flat();
  assert.ok(all.some((d) => d.getMonth() === 8 && d.getDate() === 1));
  assert.ok(all.some((d) => d.getMonth() === 8 && d.getDate() === 30));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test 'src/lib/calendarBuckets.test.ts'`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the helper**

```ts
// frontend/src/lib/calendarBuckets.ts
export type HasStart = { starts_at: string };
export type DayGroup<T> = { key: string; date: Date; items: T[] };

function dayKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function groupByDay<T extends HasStart>(rows: T[]): DayGroup<T>[] {
  const sorted = [...rows].sort(
    (a, b) => +new Date(a.starts_at) - +new Date(b.starts_at),
  );
  const map = new Map<string, DayGroup<T>>();
  for (const r of sorted) {
    const d = new Date(r.starts_at);
    const key = dayKey(d);
    let g = map.get(key);
    if (!g) {
      g = { key, date: new Date(d.getFullYear(), d.getMonth(), d.getDate()), items: [] };
      map.set(key, g);
    }
    g.items.push(r);
  }
  return [...map.values()];
}

// 6x7 matrix of Date objects; weeks start Monday.
export function monthMatrix(year: number, month: number): Date[][] {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7; // Mon=0
  const start = new Date(year, month, 1 - offset);
  const weeks: Date[][] = [];
  for (let w = 0; w < 6; w++) {
    const row: Date[] = [];
    for (let d = 0; d < 7; d++) {
      row.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7 + d));
    }
    weeks.push(row);
  }
  return weeks;
}

export function eventsForDay<T extends HasStart>(rows: T[], day: Date): T[] {
  const key = dayKey(day);
  return rows.filter((r) => dayKey(new Date(r.starts_at)) === key);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test 'src/lib/calendarBuckets.test.ts'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/calendarBuckets.ts frontend/src/lib/calendarBuckets.test.ts
git commit -m "feat(calendar): pure date-bucketing helper with tests"
```

## Task 6: Frontend calendar API module

**Files:**
- Create: `frontend/src/api/calendar.ts`

- [ ] **Step 1: Implement the module (no test — thin API binding)**

```ts
// frontend/src/api/calendar.ts
import { api } from "./client";
import type { InterviewStage } from "./interactions";

export type CalendarInterview = {
  id: string;
  application_id: string;
  display_id: number;
  company: string;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  interview_stage: InterviewStage | null;
  needs_review: boolean;
};

export type CalendarTokens = {
  ingest_url: string | null;
  calendar_url: string | null;
};

export const calendar = {
  interviews: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    const qs = q.toString();
    return api<CalendarInterview[]>(`/api/calendar/interviews${qs ? `?${qs}` : ""}`);
  },
  tokens: () => api<CalendarTokens>("/api/calendar/tokens"),
  regenerate: (kind: "ingest" | "calendar") =>
    api<CalendarTokens>(`/api/calendar/tokens/regenerate?kind=${kind}`, { method: "POST" }),
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/calendar.ts
git commit -m "feat(calendar): frontend API module"
```

## Task 7: Calendar page (responsive month grid + agenda)

**Files:**
- Create: `frontend/src/pages/Calendar.tsx`, `frontend/src/components/calendar/MonthGrid.tsx`, `AgendaList.tsx`, `InterviewChip.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/nav/navItems.ts`

- [ ] **Step 1: Build `InterviewChip.tsx`**

```tsx
// frontend/src/components/calendar/InterviewChip.tsx
import { useNavigate } from "react-router-dom";
import type { CalendarInterview } from "../../api/calendar";

const STAGE_COLOR: Record<string, string> = {
  phone_screen: "bg-blue-500", technical: "bg-violet-500", onsite: "bg-amber-500",
  hr: "bg-teal-500", final: "bg-emerald-600", other: "bg-slate-500",
};

export function InterviewChip({ ev }: { ev: CalendarInterview }) {
  const nav = useNavigate();
  const time = new Date(ev.starts_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dot = STAGE_COLOR[ev.interview_stage ?? "other"] ?? "bg-slate-500";
  return (
    <button
      onClick={() => nav(`/applications/${ev.application_id}`)}
      className={`w-full flex items-center gap-1 text-left text-xs px-1 py-0.5 rounded
        hover:bg-surface2 ${ev.needs_review ? "opacity-60" : ""}`}
      title={ev.needs_review ? "Needs review" : undefined}
    >
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
      <span className="truncate">{time} {ev.company}</span>
      {ev.needs_review && <span className="ml-auto text-[10px] text-amber-600">review</span>}
    </button>
  );
}
```

- [ ] **Step 2: Build `MonthGrid.tsx` (desktop) and `AgendaList.tsx` (mobile)**

```tsx
// frontend/src/components/calendar/MonthGrid.tsx
import { monthMatrix, eventsForDay } from "../../lib/calendarBuckets";
import type { CalendarInterview } from "../../api/calendar";
import { InterviewChip } from "./InterviewChip";

export function MonthGrid({ year, month, events }:
  { year: number; month: number; events: CalendarInterview[] }) {
  const weeks = monthMatrix(year, month);
  const dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return (
    <div className="grid grid-cols-7 gap-px bg-border rounded overflow-hidden">
      {dows.map((d) => (
        <div key={d} className="bg-surface px-2 py-1 text-xs font-semibold text-muted">{d}</div>
      ))}
      {weeks.flat().map((day) => {
        const inMonth = day.getMonth() === month;
        const dayEvents = eventsForDay(events, day);
        return (
          <div key={day.toISOString()}
            className={`bg-bg min-h-[5rem] p-1 ${inMonth ? "" : "opacity-40"}`}>
            <div className="text-[11px] text-muted">{day.getDate()}</div>
            <div className="flex flex-col gap-0.5">
              {dayEvents.map((ev) => <InterviewChip key={ev.id} ev={ev} />)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

```tsx
// frontend/src/components/calendar/AgendaList.tsx
import { groupByDay } from "../../lib/calendarBuckets";
import type { CalendarInterview } from "../../api/calendar";
import { InterviewChip } from "./InterviewChip";

export function AgendaList({ events }: { events: CalendarInterview[] }) {
  const groups = groupByDay(events);
  if (groups.length === 0)
    return <p className="text-muted text-sm p-4">No upcoming interviews.</p>;
  return (
    <div className="flex flex-col gap-4">
      {groups.map((g) => (
        <div key={g.key}>
          <h3 className="text-sm font-semibold mb-1">
            {g.date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
          </h3>
          <div className="flex flex-col gap-1">
            {g.items.map((ev) => <InterviewChip key={ev.id} ev={ev} />)}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Build `Calendar.tsx` page (responsive switch via Tailwind `hidden md:block` / `md:hidden`)**

```tsx
// frontend/src/pages/Calendar.tsx
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { calendar } from "../api/calendar";
import { MonthGrid } from "../components/calendar/MonthGrid";
import { AgendaList } from "../components/calendar/AgendaList";

export function Calendar() {
  const [cursor, setCursor] = useState(() => {
    const n = new Date();
    return { year: n.getFullYear(), month: n.getMonth() };
  });
  const range = useMemo(() => {
    const from = new Date(cursor.year, cursor.month - 1, 1).toISOString();
    const to = new Date(cursor.year, cursor.month + 2, 0, 23, 59).toISOString();
    return { from, to };
  }, [cursor]);

  const q = useQuery({
    queryKey: ["calendar-interviews", range.from, range.to],
    queryFn: () => calendar.interviews(range.from, range.to),
  });
  const events = q.data ?? [];

  const shift = (delta: number) =>
    setCursor((c) => {
      const m = c.month + delta;
      return { year: c.year + Math.floor(m / 12), month: ((m % 12) + 12) % 12 };
    });
  const label = new Date(cursor.year, cursor.month, 1)
    .toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-3">
        <h1 className="text-lg font-semibold">Calendar</h1>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => shift(-1)} className="px-2 py-1 rounded hover:bg-surface2">‹</button>
          <span className="text-sm w-36 text-center">{label}</span>
          <button onClick={() => shift(1)} className="px-2 py-1 rounded hover:bg-surface2">›</button>
        </div>
      </div>
      <div className="hidden md:block">
        <MonthGrid year={cursor.year} month={cursor.month} events={events} />
      </div>
      <div className="md:hidden">
        <AgendaList events={events} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire route + nav**

In `frontend/src/App.tsx` add the route (import `Calendar`):
```tsx
<Route path="/calendar" element={<ProtectedShell><Calendar /></ProtectedShell>} />
```
In `frontend/src/components/nav/navItems.ts` add to `NAV_ITEMS` (place before Settings group):
```ts
{ to: "/calendar", label: "Calendar", group: "main" },
```

- [ ] **Step 5: Typecheck + build**

Run: `cd frontend && node_modules/.bin/tsc --noEmit` (raw tsc — rtk masks tsc output; run the binary directly with sandbox off)
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Calendar.tsx frontend/src/components/calendar/ frontend/src/App.tsx frontend/src/components/nav/navItems.ts
git commit -m "feat(calendar): responsive month-grid/agenda calendar page + nav"
```

---

# PHASE 2 — iCal Feed

## Task 8: ICS serializer (pure, DB-free)

**Files:**
- Create: `backend/app/calendar_feed/__init__.py`, `backend/app/calendar_feed/ics.py`
- Test: `backend/tests/unit/test_ics_serializer.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_ics_serializer.py
from datetime import datetime, timezone
from app.calendar_feed.ics import IcsEvent, render_calendar


def _ev(**kw):
    base = dict(
        uid="11111111-1111-1111-1111-111111111111",
        summary="Acme · technical",
        starts_at=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc),
        location="https://meet.example/abc",
        description="Onsite loop\nhttps://app.example/applications/1",
        updated_at=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
    )
    base.update(kw)
    return IcsEvent(**base)


def test_render_wraps_vcalendar_and_vevent():
    out = render_calendar([_ev()])
    assert out.startswith("BEGIN:VCALENDAR\r\n")
    assert out.rstrip().endswith("END:VCALENDAR")
    assert "VERSION:2.0" in out
    assert "PRODID:" in out
    assert "BEGIN:VEVENT\r\n" in out
    assert "UID:11111111-1111-1111-1111-111111111111\r\n" in out
    assert "DTSTART:20260901T140000Z\r\n" in out
    assert "DTEND:20260901T150000Z\r\n" in out
    assert "STATUS:CONFIRMED\r\n" in out
    assert "SUMMARY:Acme \\u00b7 technical".replace("\\u00b7", "·") in out or "SUMMARY:Acme" in out


def test_default_end_is_start_plus_60min():
    out = render_calendar([_ev(ends_at=None)])
    assert "DTEND:20260901T150000Z\r\n" in out


def test_escapes_special_chars_and_folds_long_lines():
    ev = _ev(summary="A, B; C\\D", description="line1\nline2")
    out = render_calendar([ev])
    assert "SUMMARY:A\\, B\\; C\\\\D\r\n" in out
    assert "line1\\nline2" in out
    # 75-octet line folding: every physical line <= 75 chars before CRLF
    for line in out.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75 or line == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_ics_serializer.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the serializer**

```python
# backend/app/calendar_feed/__init__.py
```
```python
# backend/app/calendar_feed/ics.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

PRODID = "-//Applicator//Interview Calendar//EN"


@dataclass
class IcsEvent:
    uid: str
    summary: str
    starts_at: datetime
    ends_at: datetime | None
    location: str | None
    description: str | None
    updated_at: datetime


def _utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    # RFC5545 content-line folding at 75 octets; continuation lines start with a space.
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    out = []
    while len(data) > 75:
        # avoid splitting a multibyte char: back off to a safe boundary
        cut = 75
        while (data[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(data[:cut].decode("utf-8"))
        data = b" " + data[cut:]
    out.append(data.decode("utf-8"))
    return "\r\n".join(out)


def _prop(name: str, value: str) -> str:
    return _fold(f"{name}:{value}")


def render_event(ev: IcsEvent) -> list[str]:
    end = ev.ends_at or (ev.starts_at + timedelta(minutes=60))
    lines = [
        "BEGIN:VEVENT",
        _prop("UID", ev.uid),
        _prop("DTSTAMP", _utc(ev.updated_at)),
        _prop("LAST-MODIFIED", _utc(ev.updated_at)),
        _prop("DTSTART", _utc(ev.starts_at)),
        _prop("DTEND", _utc(end)),
        _prop("SUMMARY", _escape(ev.summary)),
        "STATUS:CONFIRMED",
    ]
    if ev.location:
        lines.append(_prop("LOCATION", _escape(ev.location)))
    if ev.description:
        lines.append(_prop("DESCRIPTION", _escape(ev.description)))
    lines.append("END:VEVENT")
    return lines


def render_calendar(events: list[IcsEvent]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        f"PRODID:{PRODID}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for ev in events:
        lines.extend(render_event(ev))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_ics_serializer.py -v`
Expected: PASS. (If the folding assertion in the test is too strict for the `·` char, adjust the test to check the specific expected fold; keep the serializer correct.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/calendar_feed/ backend/tests/unit/test_ics_serializer.py
git commit -m "feat(ics): RFC5545 VCALENDAR serializer with folding/escaping"
```

## Task 9: Token service (lazy get-or-create + regenerate)

**Files:**
- Create: `backend/app/services/tokens.py`
- Test: `backend/tests/unit/test_token_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_token_service.py
from app.services.tokens import new_token


def test_new_token_is_urlsafe_and_unique():
    a, b = new_token(), new_token()
    assert a != b
    assert len(a) >= 32
    assert all(c.isalnum() or c in "-_" for c in a)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_token_service.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# backend/app/services/tokens.py
from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.db.models import User


def new_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_ingest_token(db: Session, user: User) -> str:
    if not user.ingest_token:
        user.ingest_token = new_token()
        db.commit()
    return user.ingest_token


def ensure_calendar_token(db: Session, user: User) -> str:
    if not user.calendar_token:
        user.calendar_token = new_token()
        db.commit()
    return user.calendar_token


def regenerate(db: Session, user: User, kind: str) -> None:
    if kind == "ingest":
        user.ingest_token = new_token()
    elif kind == "calendar":
        user.calendar_token = new_token()
    else:
        raise ValueError(f"unknown token kind: {kind}")
    db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_token_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tokens.py backend/tests/unit/test_token_service.py
git commit -m "feat(tokens): lazy per-user ingest/calendar token service"
```

## Task 10: `.ics` feed + token endpoints

**Files:**
- Modify: `backend/app/api/calendar.py`
- Test: `backend/tests/integration/test_ics_feed_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_ics_feed_api.py
import uuid
from datetime import datetime, timezone

from app.db.models import (
    Application, JobPosting, Interaction, InteractionChannel,
    InteractionDirection, InterviewStage,
)


def _interview(db, user, *, needs_review):
    app = Application(user_id=user.id, url="https://acme.example/j",
                      url_hash=uuid.uuid4().hex)
    db.add(app); db.flush()
    db.add(JobPosting(application_id=app.id, raw_text="x", company="Acme"))
    db.add(Interaction(application_id=app.id,
                       occurred_at=datetime(2026, 9, 1, 14, tzinfo=timezone.utc),
                       direction=InteractionDirection.in_,
                       channel=InteractionChannel.interview,
                       interview_stage=InterviewStage.technical,
                       needs_review=needs_review))
    db.commit()


def test_ics_feed_includes_confirmed_excludes_review(app_client, db_session, auth_user):
    _interview(db_session, auth_user, needs_review=False)
    _interview(db_session, auth_user, needs_review=True)
    tokens = app_client.get("/api/calendar/tokens").json()
    url = tokens["calendar_url"]
    token = url.rsplit("/", 1)[-1].removesuffix(".ics")
    resp = app_client.get(f"/api/calendar/{token}.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    body = resp.text
    assert body.count("BEGIN:VEVENT") == 1  # only the confirmed one
    assert "SUMMARY:Acme" in body


def test_ics_feed_unknown_token_404(app_client_noauth):
    resp = app_client_noauth.get("/api/calendar/deadbeef.ics")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/integration/test_ics_feed_api.py -v`
Expected: FAIL (routes missing).

- [ ] **Step 3: Add token + feed endpoints to `calendar.py`**

Append to `backend/app/api/calendar.py`:
```python
import hmac
from fastapi import Header, HTTPException, Request, Response
from app.config import get_settings
from app.calendar_feed.ics import IcsEvent, render_calendar
from app.services.tokens import (
    ensure_ingest_token, ensure_calendar_token, regenerate,
)


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("/tokens")
def get_tokens(request: Request, db=Depends(db_dep), user=Depends(current_user)):
    ingest = ensure_ingest_token(db, user)
    cal = ensure_calendar_token(db, user)
    base = _base_url(request)
    return {
        "ingest_url": f"{base}/api/webhooks/inbound-email/{ingest}",
        "calendar_url": f"{base}/api/calendar/{cal}.ics",
    }


@router.post("/tokens/regenerate")
def regenerate_token(kind: str, request: Request, db=Depends(db_dep), user=Depends(current_user)):
    if kind not in ("ingest", "calendar"):
        raise HTTPException(400, "kind must be ingest or calendar")
    regenerate(db, user, kind)
    return get_tokens(request, db, user)


def _lookup_by_calendar_token(db: Session, token: str) -> User:
    row = db.execute(select(User).where(User.calendar_token == token)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not found")
    return row


@router.get("/{token}.ics")
def ics_feed(token: str, request: Request, db: Annotated[Session, Depends(db_dep)]):
    user = _lookup_by_calendar_token(db, token)
    stmt = (
        select(Interaction, Application, JobPosting)
        .join(Application, Interaction.application_id == Application.id)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
            Interaction.channel == InteractionChannel.interview,
            Interaction.needs_review.is_(False),
        )
        .order_by(Interaction.occurred_at.asc())
    )
    base = _base_url(request)
    events: list[IcsEvent] = []
    for it, app, jp in db.execute(stmt).all():
        company = _company(jp, app.url)
        stage = it.interview_stage.value if it.interview_stage else "interview"
        deep = f"{base.replace('/api','')}/applications/{app.id}"
        events.append(IcsEvent(
            uid=str(it.id), summary=f"{company} · {stage}",
            starts_at=it.occurred_at, ends_at=it.ends_at, location=it.location,
            description="\n".join(filter(None, [it.subject, deep])),
            updated_at=it.updated_at,
        ))
    body = render_calendar(events)
    return Response(content=body, media_type="text/calendar; charset=utf-8")
```

Note: the `/{token}.ics` route must be declared so it does not shadow `/interviews` — FastAPI matches literal paths first, so `/interviews` and `/tokens` still resolve correctly. Verify by running the full calendar test module.

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/integration/test_ics_feed_api.py backend/tests/integration/test_calendar_api.py -v`
Expected: PASS (both the feed tests and the earlier interviews test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/calendar.py backend/tests/integration/test_ics_feed_api.py
git commit -m "feat(ics): token endpoints + anonymous .ics feed of confirmed interviews"
```

## Task 11: Settings UI for token URLs

**Files:**
- Create: `frontend/src/pages/settings/CalendarTokens.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/nav/navItems.ts`

- [ ] **Step 1: Build the settings page**

```tsx
// frontend/src/pages/settings/CalendarTokens.tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { calendar } from "../../api/calendar";

function UrlRow({ label, url }: { label: string; url: string | null }) {
  return (
    <div className="mb-3">
      <div className="text-sm font-semibold mb-1">{label}</div>
      <div className="flex gap-2">
        <input readOnly value={url ?? ""} className="flex-1 px-2 py-1 rounded border border-border bg-surface text-xs" />
        <button onClick={() => url && navigator.clipboard.writeText(url)}
          className="px-2 py-1 rounded bg-accent text-accentFg text-xs">Copy</button>
      </div>
    </div>
  );
}

export function CalendarTokens() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["calendar-tokens"], queryFn: () => calendar.tokens() });
  const regen = useMutation({
    mutationFn: (kind: "ingest" | "calendar") => calendar.regenerate(kind),
    onSuccess: (data) => qc.setQueryData(["calendar-tokens"], data),
  });
  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-lg font-semibold mb-4">Calendar & Email</h1>
      <UrlRow label="iCal subscription URL (Google Calendar → From URL)" url={q.data?.calendar_url ?? null} />
      <button onClick={() => regen.mutate("calendar")} className="text-xs text-red-600 mb-6">Regenerate iCal URL</button>
      <UrlRow label="Forward-to-add email webhook URL" url={q.data?.ingest_url ?? null} />
      <button onClick={() => regen.mutate("ingest")} className="text-xs text-red-600">Regenerate webhook URL</button>
      <p className="text-xs text-muted mt-2">Regenerating invalidates the old URL.</p>
    </div>
  );
}
```

- [ ] **Step 2: Wire route + nav (settings group)**

`App.tsx`:
```tsx
<Route path="/settings/calendar" element={<ProtectedShell><CalendarTokens /></ProtectedShell>} />
```
`navItems.ts`:
```ts
{ to: "/settings/calendar", label: "Calendar & Email", group: "settings" },
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && node_modules/.bin/tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/settings/CalendarTokens.tsx frontend/src/App.tsx frontend/src/components/nav/navItems.ts
git commit -m "feat(settings): calendar/webhook token URLs with regenerate"
```

---

# PHASE 3 — Webhook Ingestion + Review Flow

## Task 12: Interview field extractor (LLM, DB-free)

**Files:**
- Create: `backend/app/email_ingest/interview_extract.py`
- Test: `backend/tests/unit/test_interview_extract.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_interview_extract.py
import json
from app.email_ingest.interview_extract import extract_interview, ExtractedInterview


class _FakeLLM:
    def __init__(self, payload): self._payload = payload; self.calls = []
    def complete(self, messages, *, json_schema=None, temperature=0.2):
        self.calls.append((messages, json_schema))
        return json.dumps(self._payload)


def test_extract_parses_fields_and_passes_schema():
    llm = _FakeLLM({
        "starts_at": "2026-09-01T14:00:00Z", "ends_at": "2026-09-01T15:00:00Z",
        "location": "https://meet.example/abc", "interview_stage": "technical",
        "contact_name": "Jane Doe", "contact_handle": "jane@acme.example",
    })
    out = extract_interview("Interview invite", "Let's meet...", llm)
    assert isinstance(out, ExtractedInterview)
    assert out.interview_stage == "technical"
    assert out.location == "https://meet.example/abc"
    assert llm.calls[0][1] is not None  # json_schema was provided


def test_extract_tolerates_nulls():
    llm = _FakeLLM({"starts_at": None, "ends_at": None, "location": None,
                    "interview_stage": None, "contact_name": None, "contact_handle": None})
    out = extract_interview("s", "b", llm)
    assert out.starts_at is None
    assert out.interview_stage is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_interview_extract.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the extractor (reuse `LLMClient` protocol)**

```python
# backend/app/email_ingest/interview_extract.py
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.llm.base import LLMClient

_STAGES = ["phone_screen", "technical", "onsite", "hr", "final", "other"]

_SYSTEM = (
    "You extract structured interview details from a forwarded email. "
    "Return starts_at/ends_at as ISO-8601 UTC (or null if unknown). "
    "location is a physical address or video link. "
    f"interview_stage is one of {_STAGES} or null. "
    "Return null for any field you cannot determine. Do not invent values."
)


class _LlmInterview(BaseModel):
    starts_at: str | None = None
    ends_at: str | None = None
    location: str | None = None
    interview_stage: str | None = None
    contact_name: str | None = None
    contact_handle: str | None = None


class ExtractedInterview(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    interview_stage: str | None = None
    contact_name: str | None = None
    contact_handle: str | None = None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_interview(subject: str, body: str, llm: LLMClient) -> ExtractedInterview:
    raw = llm.complete(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Subject: {subject}\n\n{body}"},
        ],
        json_schema=_LlmInterview.model_json_schema(),
        temperature=0.0,
    )
    parsed = _LlmInterview.model_validate_json(raw)
    stage = parsed.interview_stage if parsed.interview_stage in _STAGES else None
    return ExtractedInterview(
        starts_at=_parse_dt(parsed.starts_at),
        ends_at=_parse_dt(parsed.ends_at),
        location=parsed.location or None,
        interview_stage=stage,
        contact_name=parsed.contact_name or None,
        contact_handle=parsed.contact_handle or None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_interview_extract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/email_ingest/interview_extract.py backend/tests/unit/test_interview_extract.py
git commit -m "feat(ingest): LLM interview-field extractor"
```

## Task 13: Application matcher (pure function)

**Files:**
- Create: `backend/app/email_ingest/interview_match.py`
- Test: `backend/tests/unit/test_interview_match.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_interview_match.py
from app.email_ingest.interview_match import match_application, Candidate


def _cands():
    return [
        Candidate(application_id="a1", company="Acme GmbH", url="https://acme.example/jobs/1"),
        Candidate(application_id="a2", company="Globex", url="https://globex.io/careers/9"),
    ]


def test_matches_by_sender_domain():
    aid, score = match_application(sender="jane@acme.example", subject="Interview",
                                   body="", candidates=_cands())
    assert aid == "a1"
    assert score > 0


def test_matches_by_company_name_in_subject():
    aid, _ = match_application(sender="recruiter@hire.io",
                               subject="Your Globex interview", body="", candidates=_cands())
    assert aid == "a2"


def test_empty_candidates_returns_none():
    aid, score = match_application(sender="x@y.z", subject="", body="", candidates=[])
    assert aid is None
    assert score == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_interview_match.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the matcher**

```python
# backend/app/email_ingest/interview_match.py
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import urlparse


@dataclass
class Candidate:
    application_id: str
    company: str | None
    url: str


def _domain(email_or_url: str) -> str:
    if "@" in email_or_url:
        return email_or_url.rsplit("@", 1)[-1].lower()
    return urlparse(email_or_url).netloc.lower().removeprefix("www.")


def _root(domain: str) -> str:
    parts = domain.split(".")
    return parts[-2] if len(parts) >= 2 else domain


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _score(sender: str, text: str, cand: Candidate) -> float:
    score = 0.0
    sender_root = _root(_domain(sender))
    cand_root = _root(_domain(cand.url))
    if sender_root and sender_root == cand_root:
        score += 1.0
    if cand.company:
        company_norm = _norm(cand.company)
        if company_norm and company_norm in _norm(text):
            score += 0.8
        # token-name in sender domain root, e.g. "acme" in "acme"
        if sender_root and sender_root in company_norm:
            score += 0.5
        score += 0.3 * SequenceMatcher(None, company_norm, _norm(text)).ratio()
    return score


def match_application(*, sender: str, subject: str, body: str, candidates: list[Candidate]):
    if not candidates:
        return None, 0.0
    text = f"{subject} {body}"
    best = max(candidates, key=lambda c: _score(sender, text, c))
    return best.application_id, _score(sender, text, best)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit/test_interview_match.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/email_ingest/interview_match.py backend/tests/unit/test_interview_match.py
git commit -m "feat(ingest): pure application matcher (domain + company similarity)"
```

## Task 14: Inbound-email webhook endpoint

**Files:**
- Create: `backend/app/api/webhooks.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_webhook_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_webhook_api.py
import uuid
from unittest.mock import patch

from app.db.models import Application, JobPosting, Interaction, InteractionChannel
from app.email_ingest.interview_extract import ExtractedInterview


def _app(db, user, company, host):
    app = Application(user_id=user.id, url=f"https://{host}/jobs/1", url_hash=uuid.uuid4().hex)
    db.add(app); db.flush()
    db.add(JobPosting(application_id=app.id, raw_text="x", company=company))
    db.commit()
    return app


def _fake_extract(subject, body, llm):
    from datetime import datetime, timezone
    return ExtractedInterview(starts_at=datetime(2026, 9, 1, 14, tzinfo=timezone.utc),
                              interview_stage="technical", location="https://meet/x",
                              contact_name="Jane", contact_handle="jane@acme.example")


def test_webhook_creates_needs_review_interview(app_client_noauth, db_session, auth_user):
    app = _app(db_session, auth_user, "Acme GmbH", "acme.example")
    token = auth_user.ingest_token or "seed"
    if not auth_user.ingest_token:
        auth_user.ingest_token = token; db_session.commit()
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()):
        resp = app_client_noauth.post(
            f"/api/webhooks/inbound-email/{token}",
            json={"from": "jane@acme.example", "subject": "Interview at Acme", "body_text": "..."},
        )
    assert resp.status_code == 202
    it = db_session.query(Interaction).filter_by(application_id=app.id).one()
    assert it.needs_review is True
    assert it.channel == InteractionChannel.interview
    assert it.location == "https://meet/x"


def test_webhook_unknown_token_404(app_client_noauth):
    resp = app_client_noauth.post("/api/webhooks/inbound-email/nope",
                                  json={"from": "x@y.z", "subject": "s", "body_text": "b"})
    assert resp.status_code == 404


def test_webhook_no_applications_returns_202_no_orphan(app_client_noauth, db_session, auth_user):
    auth_user.ingest_token = "tok2"; db_session.commit()
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()):
        resp = app_client_noauth.post("/api/webhooks/inbound-email/tok2",
                                      json={"from": "x@y.z", "subject": "s", "body_text": "b"})
    assert resp.status_code == 202
    assert db_session.query(Interaction).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/integration/test_webhook_api.py -v`
Expected: FAIL (route missing).

- [ ] **Step 3: Implement the webhook**

```python
# backend/app/api/webhooks.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_dep
from app.config import get_settings
from app.db.models import (
    Application, JobPosting, Interaction, InteractionChannel, InteractionDirection,
    InteractionCreatedFrom, InterviewStage, ApplicationEvent, ApplicationEventKind, User,
)
from app.email_ingest.interview_extract import extract_interview
from app.email_ingest.interview_match import match_application, Candidate

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_MAX_BODY = 512 * 1024  # 512 KB


class InboundEmail(BaseModel):
    from_: str = ""
    subject: str = ""
    body_text: str = ""

    model_config = {"populate_by_name": True}

    # inboxbridge sends "from"; map it
    @classmethod
    def normalize(cls, payload: dict) -> "InboundEmail":
        return cls(
            from_=payload.get("from") or payload.get("sender") or "",
            subject=payload.get("subject") or "",
            body_text=payload.get("body_text") or payload.get("text")
            or payload.get("body") or "",
        )


def _webhook_llm():
    from app.llm.groq import GroqClient
    s = get_settings()
    if not s.llm_api_key:
        return None
    return GroqClient(api_key=s.llm_api_key, model=s.llm_model, base_url=s.llm_base_url)


def _lookup_user(db: Session, token: str) -> User:
    row = db.execute(select(User).where(User.ingest_token == token)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not found")
    return row


@router.post("/inbound-email/{ingest_token}", status_code=202)
async def inbound_email(
    ingest_token: str, request: Request, db: Annotated[Session, Depends(db_dep)],
):
    user = _lookup_user(db, ingest_token)
    raw = await request.body()
    if len(raw) > _MAX_BODY:
        raise HTTPException(413, "payload too large")
    import json
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {"status": "ignored", "reason": "unparseable"}
    email = InboundEmail.normalize(payload)

    llm = _webhook_llm()
    if llm is None:
        return {"status": "ignored", "reason": "llm unavailable"}
    extracted = extract_interview(email.subject, email.body_text, llm)

    apps = db.execute(
        select(Application, JobPosting)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(Application.user_id == user.id, Application.deleted_at.is_(None))
    ).all()
    if not apps:
        return {"status": "ignored", "reason": "no applications"}

    candidates = [
        Candidate(application_id=str(a.id), company=(jp.company if jp else None), url=a.url)
        for a, jp in apps
    ]
    app_id, _score = match_application(
        sender=email.from_, subject=email.subject, body=email.body_text, candidates=candidates,
    )
    stage = None
    if extracted.interview_stage:
        stage = InterviewStage(extracted.interview_stage)

    import uuid as _uuid
    it = Interaction(
        application_id=_uuid.UUID(app_id),
        occurred_at=extracted.starts_at,  # may be None; DB default fills if so
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
    if it.occurred_at is None:
        # occurred_at is NOT NULL with server_default; leave unset so DB fills it
        del it.occurred_at
    db.add(it)
    db.add(ApplicationEvent(application_id=_uuid.UUID(app_id),
                            kind=ApplicationEventKind.interview_scheduled))
    db.commit()
    return {"status": "created", "needs_review": True}
```

Note on `occurred_at`: since the column is NOT NULL with `server_default=func.now()`, passing `None` explicitly would violate the constraint. The `del it.occurred_at` removes the attribute so SQLAlchemy uses the server default. Verify this works against the testcontainer; if `del` on an unset attribute raises, guard with `if extracted.starts_at is None` and construct the row without `occurred_at`.

- [ ] **Step 4: Register router in `main.py`**

```python
from app.api import webhooks as webhooks_api
...
    app.include_router(webhooks_api.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/integration/test_webhook_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/webhooks.py backend/app/main.py backend/tests/integration/test_webhook_api.py
git commit -m "feat(webhook): inbound-email → LLM extract → matched needs-review interview"
```

## Task 15: Review-count hook + badge

**Files:**
- Create: `frontend/src/hooks/useReviewCount.ts`
- Modify: `backend/app/api/calendar.py` (add count endpoint), `frontend/src/api/calendar.ts`, `frontend/src/components/nav/DesktopNav.tsx`, `MobileNav.tsx`

- [ ] **Step 1: Add backend count endpoint**

Append to `backend/app/api/calendar.py`:
```python
@router.get("/review-count")
def review_count(db: Annotated[Session, Depends(db_dep)], user: Annotated[User, Depends(current_user)]):
    from sqlalchemy import func
    n = db.execute(
        select(func.count(Interaction.id))
        .join(Application, Interaction.application_id == Application.id)
        .where(Application.user_id == user.id, Application.deleted_at.is_(None),
               Interaction.channel == InteractionChannel.interview,
               Interaction.needs_review.is_(True))
    ).scalar_one()
    return {"count": int(n)}
```

- [ ] **Step 2: Add frontend binding + hook**

In `frontend/src/api/calendar.ts` add to the `calendar` object:
```ts
  reviewCount: () => api<{ count: number }>("/api/calendar/review-count"),
```
Create `frontend/src/hooks/useReviewCount.ts`:
```ts
import { useQuery } from "@tanstack/react-query";
import { calendar } from "../api/calendar";

export function useReviewCount(): number {
  const q = useQuery({ queryKey: ["calendar-review-count"], queryFn: () => calendar.reviewCount() });
  return q.data?.count ?? 0;
}
```

- [ ] **Step 3: Render badge on Calendar nav link**

In both `DesktopNav.tsx` and `MobileNav.tsx`, mirror the existing `useSuggestionsCount` + `NavCountBadge` usage: call `const reviewCount = useReviewCount();` and, when rendering the item whose `to === "/calendar"`, add `<NavCountBadge count={reviewCount} />`.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && node_modules/.bin/tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/calendar.py frontend/src/api/calendar.ts frontend/src/hooks/useReviewCount.ts frontend/src/components/nav/DesktopNav.tsx frontend/src/components/nav/MobileNav.tsx
git commit -m "feat(review): needs-review count endpoint + Calendar nav badge"
```

## Task 16: Review/confirm modal (edit + reassign)

**Files:**
- Create: `frontend/src/components/InterviewReviewModal.tsx`
- Modify: `frontend/src/components/calendar/InterviewChip.tsx` (open modal instead of navigating when `needs_review`)

- [ ] **Step 1: Build the modal**

```tsx
// frontend/src/components/InterviewReviewModal.tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { interactions, type InterviewStage } from "../api/interactions";
import { applications } from "../api/applications";
import type { CalendarInterview } from "../api/calendar";

const STAGES: InterviewStage[] = ["phone_screen", "technical", "onsite", "hr", "final", "other"];

export function InterviewReviewModal({ ev, open, onClose }:
  { ev: CalendarInterview; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [startsAt, setStartsAt] = useState(ev.starts_at.slice(0, 16));
  const [endsAt, setEndsAt] = useState(ev.ends_at?.slice(0, 16) ?? "");
  const [location, setLocation] = useState(ev.location ?? "");
  const [stage, setStage] = useState<InterviewStage>(ev.interview_stage ?? "other");
  const [appId, setAppId] = useState(ev.application_id);

  const appList = useQuery({ queryKey: ["applications-min"], queryFn: () => applications.list() });

  const save = useMutation({
    mutationFn: () => interactions.patch(ev.id, {
      occurred_at: new Date(startsAt).toISOString(),
      ends_at: endsAt ? new Date(endsAt).toISOString() : null,
      location: location || null, interview_stage: stage,
      application_id: appId, needs_review: false,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calendar-interviews"] });
      qc.invalidateQueries({ queryKey: ["calendar-review-count"] });
      onClose();
    },
  });

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-surface rounded-lg p-4 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-base font-semibold mb-3">Confirm interview</h2>
        <label className="block text-xs mb-2">Starts
          <input type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)}
            className="w-full px-2 py-1 rounded border border-border bg-bg" /></label>
        <label className="block text-xs mb-2">Ends
          <input type="datetime-local" value={endsAt} onChange={(e) => setEndsAt(e.target.value)}
            className="w-full px-2 py-1 rounded border border-border bg-bg" /></label>
        <label className="block text-xs mb-2">Location
          <input value={location} onChange={(e) => setLocation(e.target.value)}
            className="w-full px-2 py-1 rounded border border-border bg-bg" /></label>
        <label className="block text-xs mb-2">Stage
          <select value={stage} onChange={(e) => setStage(e.target.value as InterviewStage)}
            className="w-full px-2 py-1 rounded border border-border bg-bg">
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></label>
        <label className="block text-xs mb-3">Application
          <select value={appId} onChange={(e) => setAppId(e.target.value)}
            className="w-full px-2 py-1 rounded border border-border bg-bg">
            {(appList.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                #{a.display_id} {a.job_posting?.company ?? a.url}
              </option>
            ))}
          </select></label>
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1 rounded text-sm">Cancel</button>
          <button onClick={() => save.mutate()} disabled={save.isPending}
            className="px-3 py-1 rounded bg-accent text-accentFg text-sm">Confirm</button>
        </div>
      </div>
    </div>
  );
}
```

Verify `interactions.patch(id, payload)` exists in `frontend/src/api/interactions.ts`; if the method is named differently (e.g. `update`), use that. Confirm its input type accepts `application_id`, `needs_review`, `location`, `ends_at` — extend the TS `PatchInteractionInput` type there to include these fields (mirror the backend `InteractionPatch`).

- [ ] **Step 2: Open modal from chip when needs_review**

In `InterviewChip.tsx`, add local `useState` for modal open; if `ev.needs_review`, the button opens `<InterviewReviewModal>` instead of navigating. Otherwise keep the navigate behavior.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && node_modules/.bin/tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/InterviewReviewModal.tsx frontend/src/components/calendar/InterviewChip.tsx frontend/src/api/interactions.ts
git commit -m "feat(review): confirm/reassign interview modal from calendar"
```

## Task 17: Full suite + verification

**Files:** none (verification task)

- [ ] **Step 1: Backend unit + integration suites**

Run: `backend/.venv/bin/python -m pytest backend/tests/unit backend/tests/integration -q` (sandbox off; Docker for testcontainers)
Expected: all pass. Pay attention to any enum-drift failures — the DB-free binding test in Task 1 must pass alongside testcontainer tests.

- [ ] **Step 2: Frontend unit tests + typecheck**

Run: `cd frontend && node --test 'src/**/*.test.ts' && node_modules/.bin/tsc --noEmit`
Expected: all pass, no type errors.

- [ ] **Step 3: Migration applies cleanly (user's terminal if Docker blocked in harness)**

Run: `cd backend && ../backend/.venv/bin/python -m alembic upgrade head` against a scratch DB, then `alembic downgrade -1` and back up.
Expected: no errors. If Docker/DB is blocked in the harness, hand off to the user to run and confirm.

- [ ] **Step 4: Manual smoke via the built Docker image**

Per project memory: the app is served from the built image, so rebuild and run before manual checks — in-container `python -c` replays bypass real endpoints. Verify: Calendar tab renders; manual interview shows on grid/agenda; `/api/calendar/<token>.ics` returns a valid `VCALENDAR`; settings page shows both URLs.

- [ ] **Step 5: Final commit / branch is ready for PR**

```bash
git status
```
Then use the `superpowers:finishing-a-development-branch` skill to decide merge/PR.

---

## Notes for the executor

- **Sandbox / tooling:** run Python via `backend/.venv/bin/python` directly with the sandbox off (`uv run` is broken here). Run `tsc`/`node --test` via the raw binaries — the rtk proxy summarizes away real tsc/test errors.
- **Docker in harness:** builds can fail on a keychain credential error; if so, have the user build in their terminal and bring images up with `--no-deps`.
- **Enum drift:** testcontainers builds the schema from models via `Base.metadata.create_all`, not migrations — so the Task 1 DB-free binding test is the real guard that the `email_webhook` value is wired correctly. Do not skip it.
- **Fixture names:** the exact integration fixture names (`app_client`, `app_client_noauth`, `auth_user`, `db_session`, any `make_application` helper) must be confirmed against `backend/tests/integration/conftest.py` before writing each API test; adapt the tests here to the real names.
- **Adapt, don't invent:** where a method name on the frontend API modules differs from what is used here (`interactions.patch`, `applications.list`), use the real one and extend its TS input type to cover the new fields.
