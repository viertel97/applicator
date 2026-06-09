# Stats Applied-Count Fix + Inquiry Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Stats "Weekly volume" chart count real applications (not every non-draft app), stop discarded from inflating applied, and add a separate weekly "inquiries" (question-mail) series.

**Architecture:** Define one `APPLIED_SET` of statuses that mean "really submitted". Weekly applied/discarded use a hybrid rule: the real `status_change` event week when present, else current-status membership bucketed by `created_at` (covers apps created before the event recorder existed on 2026-05-27). Inquiry mails get a dedicated `InteractionCreatedFrom.inquiry_sent` marker, counted by send week. The weekly computation is extracted into a pure, unit-testable helper.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (Postgres), Alembic, pytest (+ testcontainers for integration), React + Recharts + TypeScript.

**Spec:** `docs/superpowers/specs/2026-06-09-stats-applied-fix-and-inquiry-tracking-design.md`

---

## File Structure

- `backend/app/db/models.py` — add `InteractionCreatedFrom.inquiry_sent` member.
- `backend/alembic/versions/c2f4a6b8d0e1_interaction_created_from_inquiry_sent.py` — NEW single-purpose enum migration.
- `backend/app/api/applications.py` — `mark_inquiry_sent` tags the interaction `inquiry_sent`.
- `backend/app/services/stats.py` — `APPLIED_SET` constant, pure `_weekly_volume(...)` helper, `WeeklyVolume.inquiries`, funnel endpoint wiring, totals/funnel "applied" re-pointed to `APPLIED_SET`.
- `backend/tests/unit/test_inquiry_sent_enum_migration.py` — NEW DB-free guard: model member + migration ADD VALUE exist.
- `backend/tests/unit/test_weekly_volume.py` — NEW DB-free unit tests for `_weekly_volume`.
- `backend/tests/integration/test_inquiry_mark_sent.py` — NEW: mark-sent tags `inquiry_sent` (needs Docker).
- `backend/tests/integration/test_stats_funnel.py` — extend with applied-definition + inquiry weekly assertions (needs Docker).
- `frontend/src/api/stats.ts` — `WeeklyVolume.inquiries: number`.
- `frontend/src/pages/Stats.tsx` — 4th `<Line dataKey="inquiries">`.

**Test runner notes:**
- Unit tests are DB-free: `cd backend && .venv/bin/pytest tests/unit/<file> -v`
- Integration tests use testcontainers (real Postgres) and **require Docker**. If Docker is unavailable in this environment, hand the integration-test commands to the user to run in their terminal. Command: `cd backend && .venv/bin/pytest tests/integration/<file> -v`

---

## Task 1: Add `inquiry_sent` enum member + migration (DB-free guard)

**Files:**
- Create: `backend/tests/unit/test_inquiry_sent_enum_migration.py`
- Modify: `backend/app/db/models.py:98-102` (the `InteractionCreatedFrom` enum)
- Create: `backend/alembic/versions/c2f4a6b8d0e1_interaction_created_from_inquiry_sent.py`

Context: the integration harness builds the schema from models via `Base.metadata.create_all` (see `tests/integration/conftest.py:93`), so a missing migration is invisible there. This DB-free test guards both the model member and the migration source, mirroring `tests/unit/test_interaction_enum_binding.py`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_inquiry_sent_enum_migration.py`:

```python
"""Guards the inquiry_sent enum value against model/migration drift.

The integration harness builds the schema from models (create_all), so a
missing Alembic migration is invisible there. These DB-free checks assert both
the model member exists and that a migration adds the Postgres enum value, so
production deploys don't break on an unknown 'inquiry_sent'.
"""
from pathlib import Path

from app.db.models import InteractionCreatedFrom

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_model_has_inquiry_sent_member():
    assert InteractionCreatedFrom.inquiry_sent.value == "inquiry_sent"


def test_a_migration_adds_inquiry_sent_value():
    texts = [p.read_text() for p in VERSIONS.glob("*.py")]
    assert any(
        "inquiry_sent" in t and "ADD VALUE" in t and "interactioncreatedfrom" in t
        for t in texts
    ), "no Alembic migration ADDs 'inquiry_sent' to interactioncreatedfrom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_inquiry_sent_enum_migration.py -v`
Expected: FAIL — `AttributeError: inquiry_sent` on the model test, and the migration test fails (no such migration).

- [ ] **Step 3a: Add the model member**

In `backend/app/db/models.py`, the `InteractionCreatedFrom` enum becomes:

```python
class InteractionCreatedFrom(str, enum.Enum):
    manual = "manual"
    inquiry_migration = "inquiry_migration"
    graph_sync = "graph_sync"
    eml_import = "eml_import"
    inquiry_sent = "inquiry_sent"
```

- [ ] **Step 3b: Create the migration**

Create `backend/alembic/versions/c2f4a6b8d0e1_interaction_created_from_inquiry_sent.py`:

```python
"""add inquiry_sent to interactioncreatedfrom enum

Single-purpose migration: a newly added Postgres enum value is only usable
after the adding transaction commits, so this migration does nothing but
ADD VALUE and must NOT be combined with code that consumes 'inquiry_sent'.

Revision ID: c2f4a6b8d0e1
Revises: f2a3b4c5d6e7
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "c2f4a6b8d0e1"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE interactioncreatedfrom ADD VALUE IF NOT EXISTS 'inquiry_sent'"
    )


def downgrade() -> None:
    # Postgres cannot drop a single enum value; no-op.
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_inquiry_sent_enum_migration.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Verify alembic history is linear (single head)**

Run: `cd backend && .venv/bin/alembic heads`
Expected: a single head line ending `c2f4a6b8d0e1 (head)`. If two heads appear, fix `down_revision`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/c2f4a6b8d0e1_interaction_created_from_inquiry_sent.py backend/tests/unit/test_inquiry_sent_enum_migration.py
git commit -m "feat(crm): add inquiry_sent interaction marker + migration"
```

---

## Task 2: `mark_inquiry_sent` tags interactions `inquiry_sent`

**Files:**
- Modify: `backend/app/api/applications.py:700-710` (the `Interaction(...)` in `mark_inquiry_sent`)
- Test: `backend/tests/integration/test_inquiry_mark_sent.py` (NEW, needs Docker)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_inquiry_mark_sent.py`:

```python
from app.db.models import Application, Interaction, InteractionCreatedFrom


def test_mark_sent_tags_interaction_as_inquiry_sent(client, db_session, auth_user):
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/inq", url_hash="hinq")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)

    r = client.post(
        f"/api/applications/{a.id}/inquiry/mark-sent",
        json={"subject": "Frage", "body": "Hallo"},
    )
    assert r.status_code == 200

    it = db_session.query(Interaction).filter_by(application_id=a.id).one()
    assert it.created_from == InteractionCreatedFrom.inquiry_sent
    assert it.direction.value == "out"
    assert it.channel.value == "mail"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/integration/test_inquiry_mark_sent.py -v`
Expected: FAIL — `created_from` is `InteractionCreatedFrom.manual`, not `inquiry_sent`.

- [ ] **Step 3: Change the marker**

In `backend/app/api/applications.py`, inside `mark_inquiry_sent`, the `Interaction(...)` construction changes its last argument:

```python
    interaction = Interaction(
        application_id=app_row.id,
        occurred_at=now,
        direction=InteractionDirection.out,
        channel=InteractionChannel.mail,
        subject=body.subject,
        body=body.body,
        contact_name=_contact.get("name"),
        contact_handle=_contact.get("email"),
        created_from=InteractionCreatedFrom.inquiry_sent,
    )
```

(`InteractionCreatedFrom` is already imported at the top of `mark_inquiry_sent`'s local import block.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/integration/test_inquiry_mark_sent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/applications.py backend/tests/integration/test_inquiry_mark_sent.py
git commit -m "feat(inquiry): tag sent question-mails with inquiry_sent marker"
```

---

## Task 3: Pure `_weekly_volume` helper + `APPLIED_SET` + schema field

**Files:**
- Modify: `backend/app/services/stats.py` (add constant, schema field, helper)
- Test: `backend/tests/unit/test_weekly_volume.py` (NEW, DB-free)

This task adds the helper and constant but does NOT yet wire them into the endpoint (Task 4). The helper is pure: it reads attributes off model instances, no DB.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_weekly_volume.py`:

```python
import uuid
from datetime import datetime, timezone

from app.db.models import (
    Application, ApplicationEvent, ApplicationEventKind, ApplicationStatus,
    Interaction, InteractionChannel, InteractionCreatedFrom, InteractionDirection,
)
from app.services.stats import _weekly_volume


def _app(status, created_at, aid=None):
    return Application(
        id=aid or uuid.uuid4(),
        user_id=uuid.uuid4(),
        url="u", url_hash="h",
        status=status, created_at=created_at,
    )


def _ev(aid, to_value, occurred_at):
    return ApplicationEvent(
        application_id=aid, kind=ApplicationEventKind.status_change,
        to_value=to_value, occurred_at=occurred_at,
    )


def _interaction(occurred_at, direction, created_from=InteractionCreatedFrom.manual):
    return Interaction(
        application_id=uuid.uuid4(), occurred_at=occurred_at,
        direction=direction, channel=InteractionChannel.mail,
        created_from=created_from,
    )


def _by_week(rows):
    return {r.week: r for r in rows}


def test_applied_uses_event_week_when_event_present():
    aid = uuid.uuid4()
    # created in W21, applied event in W23
    app = _app(ApplicationStatus.applied, datetime(2026, 5, 20), aid)
    ev = _ev(aid, "applied", datetime(2026, 6, 1, tzinfo=timezone.utc))  # W23
    rows = _by_week(_weekly_volume([app], [ev], [], []))
    assert rows["2026-W23"].applied == 1
    assert "2026-W21" not in rows or rows["2026-W21"].applied == 0


def test_applied_falls_back_to_created_week_without_event():
    app = _app(ApplicationStatus.applied, datetime(2026, 5, 20))  # W21, no event
    rows = _by_week(_weekly_volume([app], [], [], []))
    assert rows["2026-W21"].applied == 1


def test_pre_apply_statuses_excluded_from_applied():
    apps = [
        _app(ApplicationStatus.draft, datetime(2026, 5, 20)),
        _app(ApplicationStatus.need_call, datetime(2026, 5, 20)),
        _app(ApplicationStatus.apply_direct, datetime(2026, 5, 20)),
    ]
    rows = _by_week(_weekly_volume(apps, [], [], []))
    assert "2026-W21" not in rows or rows["2026-W21"].applied == 0


def test_apply_then_discard_appears_in_both_series():
    aid = uuid.uuid4()
    app = _app(ApplicationStatus.discarded, datetime(2026, 5, 10), aid)
    events = [
        _ev(aid, "applied", datetime(2026, 5, 20, tzinfo=timezone.utc)),    # W21
        _ev(aid, "discarded", datetime(2026, 6, 1, tzinfo=timezone.utc)),   # W23
    ]
    rows = _by_week(_weekly_volume([app], events, [], []))
    assert rows["2026-W21"].applied == 1
    assert rows["2026-W23"].discarded == 1
    # not counted as applied in W23, not discarded in W21
    assert rows["2026-W21"].discarded == 0
    assert rows["2026-W23"].applied == 0


def test_discarded_only_app_not_counted_as_applied():
    app = _app(ApplicationStatus.discarded, datetime(2026, 5, 20))  # W21, no events
    rows = _by_week(_weekly_volume([app], [], [], []))
    assert rows["2026-W21"].discarded == 1
    assert rows["2026-W21"].applied == 0


def test_responses_and_inquiries_bucketed_by_occurred_at():
    resp = _interaction(datetime(2026, 5, 20), InteractionDirection.in_)  # W21
    inq = _interaction(
        datetime(2026, 5, 21), InteractionDirection.out,
        created_from=InteractionCreatedFrom.inquiry_sent,
    )  # W21
    rows = _by_week(_weekly_volume([], [], [resp], [inq]))
    assert rows["2026-W21"].responses == 1
    assert rows["2026-W21"].inquiries == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/unit/test_weekly_volume.py -v`
Expected: FAIL — `ImportError: cannot import name '_weekly_volume'`.

- [ ] **Step 3a: Add `APPLIED_SET` and the `inquiries` schema field**

In `backend/app/services/stats.py`, add `InteractionCreatedFrom`, `ApplicationEvent`, `ApplicationEventKind` to the existing `from app.db.models import (...)` block. Then, after the imports and before `router = APIRouter(...)`, add:

```python
WEEK_FMT = "%G-W%V"

APPLIED_SET = {
    ApplicationStatus.applied,
    ApplicationStatus.offer,
    ApplicationStatus.rejected,
    ApplicationStatus.accepted,
    ApplicationStatus.withdrawn,
}
```

Update the `WeeklyVolume` model to add the field:

```python
class WeeklyVolume(BaseModel):
    week: str
    applied: int
    discarded: int
    responses: int
    inquiries: int
```

- [ ] **Step 3b: Add the pure helper**

In `backend/app/services/stats.py`, add this function (place it above the `funnel` endpoint):

```python
def _weekly_volume(
    apps: list[Application],
    status_events: list[ApplicationEvent],
    in_interactions: list[Interaction],
    inquiry_interactions: list[Interaction],
) -> list[WeeklyVolume]:
    # earliest status_change event per app for applied / discarded
    applied_at: dict[uuid.UUID, datetime] = {}
    discarded_at: dict[uuid.UUID, datetime] = {}
    for ev in status_events:
        if ev.to_value == "applied":
            cur = applied_at.get(ev.application_id)
            if cur is None or ev.occurred_at < cur:
                applied_at[ev.application_id] = ev.occurred_at
        elif ev.to_value == "discarded":
            cur = discarded_at.get(ev.application_id)
            if cur is None or ev.occurred_at < cur:
                discarded_at[ev.application_id] = ev.occurred_at

    weekly: dict[str, dict[str, int]] = defaultdict(lambda: {
        "applied": 0, "discarded": 0, "responses": 0, "inquiries": 0,
    })

    for a in apps:
        if a.id in applied_at:
            weekly[applied_at[a.id].strftime(WEEK_FMT)]["applied"] += 1
        elif a.status in APPLIED_SET:
            weekly[a.created_at.strftime(WEEK_FMT)]["applied"] += 1

        if a.id in discarded_at:
            weekly[discarded_at[a.id].strftime(WEEK_FMT)]["discarded"] += 1
        elif a.status == ApplicationStatus.discarded:
            weekly[a.created_at.strftime(WEEK_FMT)]["discarded"] += 1

    for it in in_interactions:
        weekly[it.occurred_at.strftime(WEEK_FMT)]["responses"] += 1
    for it in inquiry_interactions:
        weekly[it.occurred_at.strftime(WEEK_FMT)]["inquiries"] += 1

    return [WeeklyVolume(week=w, **vals) for w, vals in sorted(weekly.items())]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/unit/test_weekly_volume.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stats.py backend/tests/unit/test_weekly_volume.py
git commit -m "feat(stats): pure weekly-volume helper with hybrid applied rule"
```

---

## Task 4: Wire helper into the funnel endpoint + align totals/funnel

**Files:**
- Modify: `backend/app/services/stats.py` (funnel endpoint body)
- Test: `backend/tests/integration/test_stats_funnel.py` (extend, needs Docker)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_stats_funnel.py`:

```python
def test_applied_excludes_pre_apply_and_discarded(client, db_session, auth_user):
    from app.db.models import ApplicationStatus
    _, u = auth_user
    for i, st in enumerate([
        ApplicationStatus.need_call,
        ApplicationStatus.apply_direct,
        ApplicationStatus.discarded,
        ApplicationStatus.draft,
    ]):
        db_session.add(Application(
            user_id=u.id, url=f"https://x.test/p{i}", url_hash=f"hp{i}", status=st,
        ))
    db_session.add(Application(
        user_id=u.id, url="https://x.test/ap", url_hash="hap",
        status=ApplicationStatus.applied,
    ))
    db_session.commit()
    body = client.get("/api/stats/funnel").json()
    # only the one applied app counts
    assert body["totals"]["applied"] == 1
    stages = {s["stage"]: s["count"] for s in body["funnel"]}
    assert stages["applied"] == 1
    total_weekly_applied = sum(w["applied"] for w in body["weekly_volume"])
    total_weekly_discarded = sum(w["discarded"] for w in body["weekly_volume"])
    assert total_weekly_applied == 1
    assert total_weekly_discarded == 1  # discarded not also counted as applied


def test_weekly_inquiries_counted(client, db_session, auth_user):
    from app.db.models import (
        ApplicationStatus, Interaction, InteractionChannel,
        InteractionCreatedFrom, InteractionDirection,
    )
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/wi", url_hash="hwi",
                    status=ApplicationStatus.need_call)
    db_session.add(a); db_session.commit(); db_session.refresh(a)
    db_session.add_all([
        Interaction(application_id=a.id, direction=InteractionDirection.out,
                    channel=InteractionChannel.mail,
                    created_from=InteractionCreatedFrom.inquiry_sent),
        Interaction(application_id=a.id, direction=InteractionDirection.out,
                    channel=InteractionChannel.mail,
                    created_from=InteractionCreatedFrom.manual),
    ])
    db_session.commit()
    body = client.get("/api/stats/funnel").json()
    total_inquiries = sum(w["inquiries"] for w in body["weekly_volume"])
    assert total_inquiries == 1  # only the inquiry_sent one
    # need_call app is not an application
    assert body["totals"]["applied"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/integration/test_stats_funnel.py -v`
Expected: FAIL — `weekly_volume` rows have no `inquiries` key / `totals.applied` counts non-draft (would be 4 not 1).

- [ ] **Step 3a: Re-point funnel "applied" stage and totals to `APPLIED_SET`**

In `backend/app/services/stats.py`, the funnel "applied" stage line changes:

```python
        FunnelStage(stage="applied",
                    count=sum(1 for a in apps if a.status in APPLIED_SET)),
```

And in the `totals` dict:

```python
        "applied": sum(1 for a in apps if a.status in APPLIED_SET),
```

- [ ] **Step 3b: Fetch status events + inquiry interactions and call the helper**

Replace the inline weekly block (the `# weekly volume: ISO week ...` loop through `weekly_volume = [...]`) with:

```python
    # weekly volume via pure helper (hybrid applied/discarded)
    status_events: list[ApplicationEvent] = (
        db.query(ApplicationEvent)
          .filter(ApplicationEvent.application_id.in_(aids),
                  ApplicationEvent.kind == ApplicationEventKind.status_change,
                  ApplicationEvent.to_value.in_(("applied", "discarded")))
          .all() if aids else []
    )
    inquiry_rows = [
        it for it in out_rows
        if it.created_from == InteractionCreatedFrom.inquiry_sent
    ]
    weekly_volume = _weekly_volume(apps, status_events, in_rows, inquiry_rows)
```

(`out_rows` and `in_rows` are already fetched earlier in the endpoint.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/integration/test_stats_funnel.py -v`
Expected: PASS (all tests in file).

- [ ] **Step 5: Run the full backend suite for regressions**

Run: `cd backend && .venv/bin/pytest tests/unit -v` (DB-free, always runnable)
and, if Docker available: `cd backend && .venv/bin/pytest -q`
Expected: PASS / no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/stats.py backend/tests/integration/test_stats_funnel.py
git commit -m "fix(stats): real applied count + weekly inquiries via helper"
```

---

## Task 5: Frontend — inquiries line on Weekly volume

**Files:**
- Modify: `frontend/src/api/stats.ts` (the `weekly_volume` type)
- Modify: `frontend/src/pages/Stats.tsx:106-122` (weekly chart)

No JS test framework covers this trivial chart change; verification is a TypeScript typecheck plus a visual check in the running app.

- [ ] **Step 1: Add `inquiries` to the API type**

In `frontend/src/api/stats.ts`, the `weekly_volume` member type becomes:

```ts
  weekly_volume: { week: string; applied: number; discarded: number; responses: number; inquiries: number }[];
```

- [ ] **Step 2: Add the chart line**

In `frontend/src/pages/Stats.tsx`, inside the weekly `<LineChart>`, after the `responses` line add:

```tsx
              <Line type="monotone" dataKey="inquiries" stroke="#d97706" />
```

So the four lines read applied (`#2563eb`), discarded (`#dc2626`), responses (`#16a34a`), inquiries (`#d97706`).

- [ ] **Step 3: Typecheck**

Run (raw tsc — rtk can mask tsc errors, and sandbox off is required for the node binary):
`cd frontend && node node_modules/typescript/bin/tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Visual check**

Bring up the app (rebuild the Docker image first if running via compose — the app is served from the built image, not live source) and open Stats. Confirm a 4th amber "inquiries" line renders in Weekly volume and the legend shows it. If Docker build is blocked in this environment, ask the user to rebuild + bring up, then verify.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/stats.ts frontend/src/pages/Stats.tsx
git commit -m "feat(stats): show weekly inquiries line on volume chart"
```

---

## Self-Review

- **Spec coverage:** APPLIED_SET (§Shared) → Task 3/4; hybrid applied & discarded (§1) → Task 3 helper + Task 4 wiring; responses unchanged → preserved in helper; inquiries series (§1, §6) → Task 1/2/3/4/5; totals+funnel consistency (§4) → Task 4 Step 3a; inquiry marker + migration (§5) → Task 1/2; tests incl. enum-migration guard (§Testing) → Task 1 + Task 3 + Task 4. All spec sections mapped.
- **Placeholder scan:** none — every code/step is concrete.
- **Type consistency:** `_weekly_volume(apps, status_events, in_interactions, inquiry_interactions)` signature identical in Task 3 definition and Task 4 call site (positional `apps, status_events, in_rows, inquiry_rows`). `WeeklyVolume.inquiries` added in Task 3, consumed in Task 4 assertions and Task 5 type. `InteractionCreatedFrom.inquiry_sent` defined Task 1, used Task 2/4. Migration revision `c2f4a6b8d0e1` / down_revision `f2a3b4c5d6e7` consistent.

## Accepted limitations (from spec)
- Inquiry mails sent before the marker can't be retro-tagged (undercount until new ones accrue).
- An app applied before 2026-05-27 (no event) then discarded drops from applied. Rare.
