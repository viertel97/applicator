# Multiple Interview Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show which interview round an application is in (round + stage + upcoming/done) at a glance on the list and detail views, with a structured interview stage picked when logging each interview.

**Architecture:** Interviews are already `Interaction` rows (`channel='interview'`, `occurred_at`, notes). We add ONE nullable enum column `interview_stage` to `Interaction`, derive round/timing on read (no stored round number, no new application status), attach an `interview_summary` object to the application read schema, and surface it in the UI. Round = position of an interview among the app's interview interactions ordered by `occurred_at`; `next` = earliest upcoming (`occurred_at >= now`), `last` = latest past.

**Tech Stack:** Backend — Python, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, Pydantic v2, pytest + testcontainers. Frontend — React 18, TypeScript, TanStack Query, `node --test` unit tests.

**Environment notes (from prior sessions):**
- Run backend tests with the venv python, sandbox off: `backend/.venv/bin/python -m pytest ...` (`uv run` is broken here).
- testcontainers works for integration tests. Integration harness builds schema from models (`create_all`), so a missing migration is invisible there — enum changes MUST also get a DB-free unit test (see Task 2).
- Run frontend unit tests with `npm run test:unit` (`node --test 'src/**/*.test.ts'`). Verify TypeScript with the raw `node_modules/.bin/tsc` (rtk masks tsc output).

Current Alembic head: **`a3b4c5d6e7f8`** (verified via `alembic heads`). The new migration chains from it.

---

## File Structure

**Backend**
- `backend/app/db/models.py` — add `InterviewStage` enum + `Interaction.interview_stage` column (Task 1)
- `backend/alembic/versions/b4c5d6e7f8a9_interaction_interview_stage.py` — NEW migration (Task 2)
- `backend/app/api/interactions.py` — accept/return `interview_stage` (Task 3)
- `backend/app/api/applications.py` — `InterviewSummary` schema, `_compute_interview_summaries`, wire into list/detail + timeline (Task 4)
- `backend/tests/unit/test_interview_stage_enum.py` — NEW DB-free enum/binding + migration test (Tasks 1, 2)
- `backend/tests/integration/test_interview_summary.py` — NEW API test (Tasks 3, 4)

**Frontend**
- `frontend/src/api/interactions.ts` — `InterviewStage` type, add field to `Interaction`/`CreateInteractionInput` (Task 5)
- `frontend/src/api/applications.ts` — `InterviewSummary` type, add `interview_summary` to `Application` (Task 5)
- `frontend/src/lib/interviewSummary.ts` — NEW `STAGE_LABEL` + `formatInterviewSummary` (Task 6)
- `frontend/src/lib/interviewSummary.test.ts` — NEW unit test (Task 6)
- `frontend/src/components/StatusBadge.tsx` — optional `summary` prop (Task 7)
- `frontend/src/pages/ApplicationsList.tsx` + `frontend/src/pages/ApplicationDetail.tsx` — pass `summary` (Task 7)
- `frontend/src/components/InteractionLogModal.tsx` — stage dropdown (Task 8)
- `frontend/src/components/ActivityTimeline.tsx` — stage label (Task 9)

---

## Task 1: Backend — `InterviewStage` enum + `Interaction.interview_stage` column

**Files:**
- Modify: `backend/app/db/models.py` (add enum near the other interaction enums ~line 92; add column to `Interaction` ~line 352)
- Test: `backend/tests/unit/test_interview_stage_enum.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_interview_stage_enum.py`:

```python
"""Guards InterviewStage model/migration drift (DB-free).

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. These checks assert the model
member set and that the column persists enum *values* (not member names).
"""
from sqlalchemy.dialects import postgresql

from app.db.models import Interaction, InterviewStage


def test_interview_stage_members_exact():
    assert [m.value for m in InterviewStage] == [
        "phone_screen",
        "technical",
        "onsite",
        "hr",
        "final",
        "other",
    ]


def test_interview_stage_string_backed():
    assert InterviewStage.technical == "technical"
    assert isinstance(InterviewStage.technical, str)


def test_column_binds_enum_values_not_member_names():
    col_type = Interaction.__table__.c.interview_stage.type
    bind = col_type.bind_processor(postgresql.dialect())
    assert bind(InterviewStage.phone_screen) == "phone_screen"
    assert bind(InterviewStage.hr) == "hr"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_interview_stage_enum.py -v`
Expected: FAIL with `ImportError: cannot import name 'InterviewStage'`

- [ ] **Step 3: Add the enum**

In `backend/app/db/models.py`, after the `InteractionCreatedFrom` enum (ends ~line 104), add:

```python
class InterviewStage(str, enum.Enum):
    phone_screen = "phone_screen"
    technical = "technical"
    onsite = "onsite"
    hr = "hr"
    final = "final"
    other = "other"
```

- [ ] **Step 4: Add the column**

In the `Interaction` class in `backend/app/db/models.py`, immediately after the `sentiment` column (ends ~line 354), add:

```python
    interview_stage: Mapped[InterviewStage | None] = mapped_column(
        # Only meaningful when channel == 'interview'. Persist enum values,
        # not member names, to match the migration-created Postgres type.
        Enum(
            InterviewStage,
            name="interviewstage",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_interview_stage_enum.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/tests/unit/test_interview_stage_enum.py
git commit -m "feat(models): add InterviewStage enum + Interaction.interview_stage"
```

---

## Task 2: Backend — Alembic migration for `interview_stage`

**Files:**
- Create: `backend/alembic/versions/b4c5d6e7f8a9_interaction_interview_stage.py`
- Test: `backend/tests/unit/test_interview_stage_enum.py` (append)

- [ ] **Step 1: Add the failing migration test**

Append to `backend/tests/unit/test_interview_stage_enum.py`:

```python
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_migration_adds_interview_stage_column():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        "interview_stage" in t
        and "interviewstage" in t
        and "add_column" in t
        for t in texts
    ), "no Alembic migration adds interaction.interview_stage"


def test_migration_chains_from_head():
    p = VERSIONS / "b4c5d6e7f8a9_interaction_interview_stage.py"
    assert p.exists()
    text = p.read_text()
    assert 'revision: str = "b4c5d6e7f8a9"' in text
    assert '"a3b4c5d6e7f8"' in text  # down_revision = current head
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_interview_stage_enum.py -k migration -v`
Expected: FAIL (`test_migration_chains_from_head` — file does not exist; `test_migration_adds_interview_stage_column` — no match)

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/b4c5d6e7f8a9_interaction_interview_stage.py`:

```python
"""interaction interview_stage

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-12 00:00:00.000000

Adds a nullable structured interview stage to interaction rows. Only set when
channel == 'interview'; existing interview rows keep interview_stage = NULL.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    stage = postgresql.ENUM(
        "phone_screen", "technical", "onsite", "hr", "final", "other",
        name="interviewstage", create_type=False,
    )
    stage.create(bind, checkfirst=True)
    op.add_column(
        "interaction",
        sa.Column("interview_stage", stage, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interaction", "interview_stage")
    postgresql.ENUM(name="interviewstage").drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_interview_stage_enum.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Verify migrations still form a single head**

Run: `.venv/bin/python -m alembic heads`
Expected: single line `b4c5d6e7f8a9 (head)`

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/b4c5d6e7f8a9_interaction_interview_stage.py backend/tests/unit/test_interview_stage_enum.py
git commit -m "feat(db): migration adds interaction.interview_stage"
```

---

## Task 3: Backend — interaction API accepts/returns `interview_stage`

**Files:**
- Modify: `backend/app/api/interactions.py` (`InteractionIn` ~line 37, `InteractionPatch` ~line 48, `InteractionOut` ~line 59, `create_interaction` ~line 131, import ~line 10)
- Test: `backend/tests/integration/test_interview_summary.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_interview_summary.py`:

```python
from app.db.models import Application


def _make_app(db_session, user, slug):
    a = Application(user_id=user.id, url=f"https://x.test/{slug}", url_hash=slug)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def test_create_and_read_interview_stage(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "istage")
    r = client.post(
        f"/api/applications/{a.id}/interactions",
        json={
            "direction": "in",
            "channel": "interview",
            "subject": "Screen",
            "interview_stage": "technical",
            "occurred_at": "2026-07-01T10:00:00+00:00",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["interaction"]["interview_stage"] == "technical"
```

Note: mirror the existing fixtures used in `backend/tests/integration/test_interactions_api.py` (`client`, `db_session`, `auth_user`). If those fixture names differ, match that file exactly.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/test_interview_summary.py::test_create_and_read_interview_stage -v`
Expected: FAIL — response has no `interview_stage` key (KeyError) or field is dropped.

- [ ] **Step 3: Add `interview_stage` to the schemas and create path**

In `backend/app/api/interactions.py`:

Add to the model import block (~line 10-19), alongside `InteractionSentiment`:

```python
    InterviewStage,
```

Add the field to `InteractionIn` (after `sentiment`, ~line 45):

```python
    interview_stage: InterviewStage | None = None
```

Add the same field to `InteractionPatch` (after `sentiment`, ~line 56):

```python
    interview_stage: InterviewStage | None = None
```

Add the same field to `InteractionOut` (after `sentiment`, ~line 69):

```python
    interview_stage: InterviewStage | None
```

In `create_interaction`, add to the `Interaction(...)` constructor (after `sentiment=body.sentiment,`, ~line 140):

```python
        interview_stage=body.interview_stage,
```

(`patch_interaction` already sets every field via `model_dump(exclude_unset=True)`, so it needs no change.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/integration/test_interview_summary.py::test_create_and_read_interview_stage -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/interactions.py backend/tests/integration/test_interview_summary.py
git commit -m "feat(api): interaction endpoints accept interview_stage"
```

---

## Task 4: Backend — `interview_summary` derivation + attach to `ApplicationOut`

**Files:**
- Modify: `backend/app/api/applications.py` (add schemas + `_compute_interview_summaries`; extend `ApplicationOut`/`from_orm_row`; wire into `list_apps`, `get_app`; add `interview_stage` to `get_timeline` data)
- Test: `backend/tests/integration/test_interview_summary.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_interview_summary.py`:

```python
def _log_interview(client, aid, occurred_at, stage=None):
    body = {"direction": "in", "channel": "interview", "occurred_at": occurred_at}
    if stage:
        body["interview_stage"] = stage
    r = client.post(f"/api/applications/{aid}/interactions", json=body)
    assert r.status_code == 200, r.text


def _set_status(client, aid, status):
    r = client.patch(f"/api/applications/{aid}", json={"status": status})
    assert r.status_code == 200, r.text


def test_summary_none_when_not_interview_status(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "s1")
    _log_interview(client, a.id, "2026-07-01T10:00:00+00:00", "technical")
    # status is default 'draft'
    got = client.get(f"/api/applications/{a.id}").json()
    assert got["interview_summary"] is None


def test_summary_none_when_no_interviews(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "s2")
    _set_status(client, a.id, "interview")
    got = client.get(f"/api/applications/{a.id}").json()
    assert got["interview_summary"] is None


def test_summary_upcoming_and_past_rounds(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "s3")
    _set_status(client, a.id, "interview")
    _log_interview(client, a.id, "2020-01-01T10:00:00+00:00", "phone_screen")  # R1 past
    _log_interview(client, a.id, "2999-01-01T10:00:00+00:00", "technical")     # R2 future
    s = client.get(f"/api/applications/{a.id}").json()["interview_summary"]
    assert s["rounds_logged"] == 2
    assert s["next"]["round"] == 2
    assert s["next"]["stage"] == "technical"
    assert s["last"]["round"] == 1
    assert s["last"]["stage"] == "phone_screen"


def test_summary_present_in_list(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "s4")
    _set_status(client, a.id, "interview")
    _log_interview(client, a.id, "2020-01-01T10:00:00+00:00", "onsite")
    rows = client.get("/api/applications").json()
    row = next(r for r in rows if r["id"] == str(a.id))
    assert row["interview_summary"]["last"]["round"] == 1
    assert row["interview_summary"]["last"]["stage"] == "onsite"
    assert row["interview_summary"]["next"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_interview_summary.py -v`
Expected: the four new tests FAIL — response has no `interview_summary` key.

- [ ] **Step 3: Add the summary schemas**

In `backend/app/api/applications.py`, immediately before `class ApplicationOut` (~line 120), add:

```python
class InterviewRoundRef(BaseModel):
    round: int
    stage: str | None
    at: datetime


class InterviewSummary(BaseModel):
    rounds_logged: int
    next: InterviewRoundRef | None = None
    last: InterviewRoundRef | None = None
```

- [ ] **Step 4: Add the field to `ApplicationOut` and `from_orm_row`**

In `ApplicationOut`, add after `awaiting_response: bool = False` (~line 142):

```python
    interview_summary: InterviewSummary | None = None
```

Change the `from_orm_row` signature (~line 145) to accept the summary:

```python
    @classmethod
    def from_orm_row(
        cls,
        app: Application,
        awaiting: bool = False,
        interview_summary: "InterviewSummary | None" = None,
    ) -> "ApplicationOut":
```

Add to the `cls(...)` return kwargs (after `awaiting_response=awaiting,`, ~line 174):

```python
            interview_summary=interview_summary,
```

- [ ] **Step 5: Add the derivation helper**

In `backend/app/api/applications.py`, after `_compute_awaiting` (~line 230), add:

```python
def _compute_interview_summaries(
    db: Session, apps: list[Application]
) -> dict[uuid.UUID, InterviewSummary]:
    from app.db.models import Interaction, InteractionChannel
    ids = [a.id for a in apps if a.status == ApplicationStatus.interview]
    if not ids:
        return {}
    rows = (
        db.query(Interaction)
        .filter(
            Interaction.application_id.in_(ids),
            Interaction.channel == InteractionChannel.interview,
        )
        .order_by(Interaction.application_id, Interaction.occurred_at.asc())
        .all()
    )
    by_app: dict[uuid.UUID, list[Interaction]] = {}
    for it in rows:
        by_app.setdefault(it.application_id, []).append(it)
    # occurred_at is stored naive-UTC (see create_interaction), so compare
    # against a naive-UTC now to avoid aware/naive comparison errors.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out: dict[uuid.UUID, InterviewSummary] = {}
    for app_id, items in by_app.items():
        rounds = list(enumerate(items, start=1))  # (round, interaction), asc
        upcoming = [(r, it) for r, it in rounds if it.occurred_at >= now]
        past = [(r, it) for r, it in rounds if it.occurred_at < now]

        def _ref(pair):
            r, it = pair
            stage = it.interview_stage.value if it.interview_stage else None
            return InterviewRoundRef(round=r, stage=stage, at=it.occurred_at)

        out[app_id] = InterviewSummary(
            rounds_logged=len(items),
            next=_ref(upcoming[0]) if upcoming else None,   # earliest upcoming
            last=_ref(past[-1]) if past else None,          # latest past
        )
    return out
```

- [ ] **Step 6: Wire into `list_apps` and `get_app`**

In `list_apps` (~line 273-275), replace the return block with:

```python
    rows = q.order_by(Application.created_at.desc()).all()
    awaiting = _compute_awaiting(db, rows)
    summaries = _compute_interview_summaries(db, rows)
    return [
        ApplicationOut.from_orm_row(
            r, awaiting=r.id in awaiting, interview_summary=summaries.get(r.id)
        )
        for r in rows
    ]
```

In `get_app` (~line 284-286), replace with:

```python
    app = _load_owned(db, aid, user)
    awaiting = _compute_awaiting(db, [app])
    summaries = _compute_interview_summaries(db, [app])
    return ApplicationOut.from_orm_row(
        app, awaiting=app.id in awaiting, interview_summary=summaries.get(app.id)
    )
```

- [ ] **Step 7: Expose `interview_stage` on the timeline row (for the UI in Task 9)**

In `get_timeline`, in the interaction `data={...}` dict (~line 369-378), add after the `sentiment` line:

```python
                "interview_stage": it.interview_stage.value if it.interview_stage else None,
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/integration/test_interview_summary.py -v`
Expected: PASS (all 5 tests). Also run the existing suite to catch regressions in the read schema:
`.venv/bin/python -m pytest tests/integration/test_applications.py -v` → PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/api/applications.py backend/tests/integration/test_interview_summary.py
git commit -m "feat(api): derive interview_summary (round/stage/timing) on read"
```

---

## Task 5: Frontend — API types

**Files:**
- Modify: `frontend/src/api/interactions.ts` (~line 4-5, `Interaction` type ~line 7, `CreateInteractionInput` ~line 29)
- Modify: `frontend/src/api/applications.ts` (`Application` type ~line 52)

- [ ] **Step 1: Add the `InterviewStage` type + interaction fields**

In `frontend/src/api/interactions.ts`, after the `Channel` type (~line 4), add:

```typescript
export type InterviewStage = "phone_screen" | "technical" | "onsite" | "hr" | "final" | "other";
```

Add `interview_stage: InterviewStage | null;` to the `Interaction` type (after `sentiment`, ~line 17).

Add `interview_stage?: InterviewStage | null;` to `CreateInteractionInput` (after `sentiment`, ~line 37).

- [ ] **Step 2: Add the `InterviewSummary` type + application field**

In `frontend/src/api/applications.ts`, after the `AppStatus` type (~line 3), add:

```typescript
export type InterviewStage = "phone_screen" | "technical" | "onsite" | "hr" | "final" | "other";

export type InterviewRoundRef = {
  round: number;
  stage: InterviewStage | null;
  at: string;
};

export type InterviewSummary = {
  rounds_logged: number;
  next: InterviewRoundRef | null;
  last: InterviewRoundRef | null;
};
```

Add to the `Application` type (after `discard_interaction_id`, ~line 74):

```typescript
  interview_summary: InterviewSummary | null;
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && ./node_modules/.bin/tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/interactions.ts frontend/src/api/applications.ts
git commit -m "feat(types): add InterviewStage + interview_summary API types"
```

---

## Task 6: Frontend — `formatInterviewSummary` helper + test

**Files:**
- Create: `frontend/src/lib/interviewSummary.ts`
- Test: `frontend/src/lib/interviewSummary.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/interviewSummary.test.ts`:

```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { formatInterviewSummary } from "./interviewSummary.ts";

test("upcoming round shows round + stage + upcoming", () => {
  const s = {
    rounds_logged: 2,
    next: { round: 2, stage: "technical" as const, at: "2999-01-02T10:00:00" },
    last: { round: 1, stage: "phone_screen" as const, at: "2020-01-01T10:00:00" },
  };
  const out = formatInterviewSummary(s);
  assert.match(out, /^interview · R2 Technical · upcoming /);
});

test("past-only round shows round + stage + done", () => {
  const s = {
    rounds_logged: 1,
    next: null,
    last: { round: 1, stage: "onsite" as const, at: "2020-01-01T10:00:00" },
  };
  assert.equal(formatInterviewSummary(s), "interview · R1 Onsite · done");
});

test("missing stage omits the stage segment", () => {
  const s = {
    rounds_logged: 1,
    next: null,
    last: { round: 1, stage: null, at: "2020-01-01T10:00:00" },
  };
  assert.equal(formatInterviewSummary(s), "interview · R1 · done");
});

test("empty summary falls back to plain interview", () => {
  const s = { rounds_logged: 0, next: null, last: null };
  assert.equal(formatInterviewSummary(s), "interview");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit`
Expected: FAIL — cannot resolve `./interviewSummary.ts`.

- [ ] **Step 3: Write the helper**

Create `frontend/src/lib/interviewSummary.ts`:

```typescript
import type { InterviewStage, InterviewSummary } from "../api/applications";

export const STAGE_LABEL: Record<InterviewStage, string> = {
  phone_screen: "Phone screen",
  technical: "Technical",
  onsite: "Onsite",
  hr: "HR",
  final: "Final",
  other: "Other",
};

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// Prefer the next upcoming interview; otherwise describe the latest past one.
export function formatInterviewSummary(summary: InterviewSummary): string {
  const ref = summary.next ?? summary.last;
  if (!ref) return "interview";
  const stage = ref.stage ? ` ${STAGE_LABEL[ref.stage]}` : "";
  const timing = summary.next ? ` · upcoming ${shortDate(ref.at)}` : " · done";
  return `interview · R${ref.round}${stage}${timing}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit`
Expected: PASS (4 new tests pass; existing lib tests still pass).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/interviewSummary.ts frontend/src/lib/interviewSummary.test.ts
git commit -m "feat(frontend): formatInterviewSummary badge helper"
```

---

## Task 7: Frontend — `StatusBadge` summary prop + wire into list/detail

**Files:**
- Modify: `frontend/src/components/StatusBadge.tsx` (~line 1, 30-39)
- Modify: `frontend/src/pages/ApplicationsList.tsx` (~line 544)
- Modify: `frontend/src/pages/ApplicationDetail.tsx` (~line 133)

- [ ] **Step 1: Add the `summary` prop to `StatusBadge`**

In `frontend/src/components/StatusBadge.tsx`, change the imports (~line 1) to:

```typescript
import type { AppStatus, FailedStage, InterviewSummary, JobState } from "../api/applications";
import { formatInterviewSummary } from "../lib/interviewSummary";
```

Replace the `StatusBadge` component (~line 30-39) with:

```typescript
export function StatusBadge({
  status,
  title,
  summary,
}: {
  status: AppStatus;
  title?: string;
  summary?: InterviewSummary | null;
}) {
  const label =
    status === "interview" && summary ? formatInterviewSummary(summary) : status;
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_CLASS[status]}`}
      title={title}
    >
      {label}
    </span>
  );
}
```

- [ ] **Step 2: Pass the summary in the list**

In `frontend/src/pages/ApplicationsList.tsx` (~line 544), update the `<StatusBadge>` usage:

```tsx
            <StatusBadge
              status={a.status}
              summary={a.interview_summary}
              title={a.discard_reason_id ? reasonMap[a.discard_reason_id] : undefined}
            />
```

- [ ] **Step 3: Pass the summary in the detail page**

In `frontend/src/pages/ApplicationDetail.tsx` (~line 133), update the usage (`a` is the loaded application):

```tsx
          <StatusBadge status={a.status} summary={a.interview_summary} />
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && ./node_modules/.bin/tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatusBadge.tsx frontend/src/pages/ApplicationsList.tsx frontend/src/pages/ApplicationDetail.tsx
git commit -m "feat(frontend): show interview round/stage on status badge"
```

---

## Task 8: Frontend — stage dropdown in `InteractionLogModal`

**Files:**
- Modify: `frontend/src/components/InteractionLogModal.tsx` (imports ~line 4, state ~line 33, reset ~line 102, stage `<select>` near the subject input ~line 146, create payload ~line 207)

- [ ] **Step 1: Add the stage type import + `STAGE_LABEL`**

In `frontend/src/components/InteractionLogModal.tsx`, extend the interactions import (~line 4) to include the type:

```typescript
import {
  interactions, type CreateInteractionInput, type Channel, type Direction, type Sentiment,
  type InterviewStage,
} from "../api/interactions";
```

Add near the top-level `CHANNELS` constant (~line 17):

```typescript
import { STAGE_LABEL } from "../lib/interviewSummary";

const STAGES: InterviewStage[] = ["phone_screen", "technical", "onsite", "hr", "final", "other"];
```

(Place the `import` line with the other imports at the top of the file, not next to the constant.)

- [ ] **Step 2: Add stage state**

After the `sentiment` state (~line 33), add:

```typescript
  const [interviewStage, setInterviewStage] = useState<InterviewStage | "">("");
```

Add to `reset()` (~line 102-106):

```typescript
    setInterviewStage("");
```

- [ ] **Step 3: Render the stage dropdown for interviews**

In `frontend/src/components/InteractionLogModal.tsx`, immediately before the subject `<input>` block (`{(channel === "mail" || channel === "interview") && (` ~line 146), add:

```tsx
            {channel === "interview" && (
              <select
                value={interviewStage}
                onChange={(e) => setInterviewStage(e.target.value as InterviewStage | "")}
                className="border rounded px-2 py-1 text-sm w-full mb-2"
              >
                <option value="">Stage (optional)</option>
                {STAGES.map((s) => (
                  <option key={s} value={s}>{STAGE_LABEL[s]}</option>
                ))}
              </select>
            )}
```

- [ ] **Step 4: Include the stage in the create payload**

In the Save button's `create.mutate({...})` call (~line 207-211), add `interview_stage`:

```tsx
                      onClick={() => create.mutate({
                        direction, channel, subject: subject || null, body: body || null,
                        contact_name: contactName || null, contact_handle: contactHandle || null,
                        sentiment, occurred_at: new Date(occurredAt).toISOString(),
                        interview_stage: channel === "interview" ? (interviewStage || null) : null,
                      })}
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd frontend && ./node_modules/.bin/tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InteractionLogModal.tsx
git commit -m "feat(frontend): pick interview stage when logging an interview"
```

---

## Task 9: Frontend — stage label in `ActivityTimeline`

**Files:**
- Modify: `frontend/src/components/ActivityTimeline.tsx` (imports ~line 3, `describe` ~line 13-25)

- [ ] **Step 1: Show round-stage label for interview rows**

In `frontend/src/components/ActivityTimeline.tsx`, extend the import (~line 3):

```typescript
import { timeline, type Interaction, type TimelineRow } from "../api/interactions";
import { STAGE_LABEL } from "../lib/interviewSummary";
```

Replace the interview branch inside `describe` (~line 16-18) with:

```typescript
    if (it.channel === "interview") {
      const stage = it.interview_stage ? STAGE_LABEL[it.interview_stage] : null;
      const tail = stage ?? it.subject;
      return `Interview${tail ? ` — ${tail}` : ""}`;
    }
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && ./node_modules/.bin/tsc -b --noEmit`
Expected: no errors. (`Interaction.interview_stage` exists from Task 5.)

- [ ] **Step 3: Run the frontend unit suite once more**

Run: `cd frontend && npm run test:unit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ActivityTimeline.tsx
git commit -m "feat(frontend): label interview timeline rows with stage"
```

---

## Final Verification

- [ ] Backend: `cd backend && .venv/bin/python -m pytest tests/unit/test_interview_stage_enum.py tests/integration/test_interview_summary.py tests/integration/test_applications.py tests/integration/test_interactions_api.py -v` → all PASS
- [ ] Backend: `.venv/bin/python -m alembic heads` → single head `b4c5d6e7f8a9`
- [ ] Frontend: `cd frontend && ./node_modules/.bin/tsc -b --noEmit` → no errors
- [ ] Frontend: `cd frontend && npm run test:unit` → all PASS
- [ ] Manual smoke (run app per the `run` skill): set an application to `interview`, log an interview with a future date + "Technical" stage → list badge reads `interview · R1 Technical · upcoming <date>`; log a second earlier past interview → `last` reflects the past round; timeline rows show the stage label.

## Notes / Pitfalls

- **tz comparison:** `occurred_at` is stored naive-UTC. `_compute_interview_summaries` compares against `datetime.now(timezone.utc).replace(tzinfo=None)`. Do NOT compare a naive DB value against an aware `now` — it raises `TypeError`.
- **Enum drift:** the schema in integration tests is built from models, so the migration in Task 2 is only guarded by the DB-free unit test. Keep both in sync if the stage set changes.
- **No new application status:** round/stage/timing are all derived on read. Status stays flat `interview`. Do not add enum values to `ApplicationStatus`.
- **Migration id collision:** if `b4c5d6e7f8a9` already exists (rebased branch), pick a fresh 12-char id and update Task 2's test assertion to match.
