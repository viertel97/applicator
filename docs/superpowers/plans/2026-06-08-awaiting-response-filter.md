# Awaiting-Response Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Awaiting reply" filter to the applications list showing apps the user has contacted but not yet heard back from.

**Architecture:** Backend computes a derived `awaiting_response: bool` on `ApplicationOut` (latest interaction is outbound AND status not closed). Frontend adds a toggle chip that filters the already-fetched list client-side, like the existing status/docs/search filters. No DB migration.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + TanStack Query + TypeScript (frontend), pytest (backend tests), `node --test` (frontend unit tests).

**Definition:** An application is *awaiting a response* when (1) its status is not in `{offer, rejected, accepted, withdrawn, discarded}` AND (2) its most recent interaction (any channel, by `occurred_at`) exists and has `direction = out`. No interactions → not awaiting. Inbound wins `occurred_at` ties.

**Spec:** `docs/superpowers/specs/2026-06-08-awaiting-response-filter-design.md`

---

## File Structure

- `backend/app/api/applications.py` — add `CLOSED_STATUSES`, `_compute_awaiting`, `awaiting_response` field on `ApplicationOut`, wire into `list_apps` + `get_app`.
- `backend/tests/integration/test_applications_awaiting.py` — new test module for the flag.
- `frontend/src/api/applications.ts` — add `awaiting_response` to `Application` type.
- `frontend/src/lib/filterDiagnostics.ts` — add `awaitingOnly` to `FilterState`, filter + diagnose logic.
- `frontend/src/lib/filterDiagnostics.test.ts` — extend helpers + tests.
- `frontend/src/components/FilterEmptyState.tsx` — copy for the `awaiting` reason.
- `frontend/src/pages/ApplicationsList.tsx` — toggle chip, state, persistence, wiring.

---

## Task 1: Backend `awaiting_response` flag

**Files:**
- Modify: `backend/app/api/applications.py`
- Test: `backend/tests/integration/test_applications_awaiting.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_applications_awaiting.py`:

```python
from datetime import datetime, timedelta

from app.db.models import (
    Application, ApplicationStatus, Interaction, InteractionChannel,
    InteractionDirection,
)


def _app(db, user, slug, status=ApplicationStatus.applied):
    a = Application(user_id=user.id, url=f"https://x.test/{slug}",
                    url_hash=f"h{slug}", status=status)
    db.add(a)
    db.commit()
    return a


def _flag(client, aid):
    rows = client.get("/api/applications").json()
    return next(r for r in rows if r["id"] == str(aid))["awaiting_response"]


def test_outbound_latest_is_awaiting(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "out")
    db_session.add(Interaction(application_id=a.id,
                               direction=InteractionDirection.out,
                               channel=InteractionChannel.mail))
    db_session.commit()
    assert _flag(client, a.id) is True


def test_inbound_latest_not_awaiting(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "in")
    now = datetime.utcnow()
    db_session.add_all([
        Interaction(application_id=a.id, direction=InteractionDirection.out,
                    channel=InteractionChannel.mail,
                    occurred_at=now - timedelta(days=2)),
        Interaction(application_id=a.id, direction=InteractionDirection.in_,
                    channel=InteractionChannel.mail,
                    occurred_at=now - timedelta(days=1)),
    ])
    db_session.commit()
    assert _flag(client, a.id) is False


def test_no_interactions_not_awaiting(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "none")
    assert _flag(client, a.id) is False


def test_closed_status_not_awaiting(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "rej", status=ApplicationStatus.rejected)
    db_session.add(Interaction(application_id=a.id,
                               direction=InteractionDirection.out,
                               channel=InteractionChannel.mail))
    db_session.commit()
    assert _flag(client, a.id) is False


def test_get_app_carries_flag(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "single")
    db_session.add(Interaction(application_id=a.id,
                               direction=InteractionDirection.out,
                               channel=InteractionChannel.mail))
    db_session.commit()
    body = client.get(f"/api/applications/{a.id}").json()
    assert body["awaiting_response"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_applications_awaiting.py -v`
Expected: FAIL — `KeyError: 'awaiting_response'` (field not on response yet).

- [ ] **Step 3: Add `CLOSED_STATUSES` constant**

In `backend/app/api/applications.py`, after `_BUSY_STATES` (line ~32):

```python
CLOSED_STATUSES = {
    ApplicationStatus.offer,
    ApplicationStatus.rejected,
    ApplicationStatus.accepted,
    ApplicationStatus.withdrawn,
    ApplicationStatus.discarded,
}
```

- [ ] **Step 4: Add `_compute_awaiting` helper**

Add near the other module-level helpers (e.g. after `_load_owned`, line ~180). Imports `Interaction` locally to match the file's existing pattern:

```python
def _compute_awaiting(db: Session, apps: list[Application]) -> set[uuid.UUID]:
    from app.db.models import Interaction
    open_ids = [a.id for a in apps if a.status not in CLOSED_STATUSES]
    if not open_ids:
        return set()
    rows = (
        db.query(
            Interaction.application_id,
            Interaction.direction,
            Interaction.occurred_at,
        )
        .filter(Interaction.application_id.in_(open_ids))
        .all()
    )
    # latest interaction per app; inbound wins ties on occurred_at
    latest: dict[uuid.UUID, tuple[datetime, bool]] = {}
    for app_id, direction, occurred_at in rows:
        is_out = direction == InteractionDirection.out
        cur = latest.get(app_id)
        if cur is None or occurred_at > cur[0] or (occurred_at == cur[0] and not is_out):
            latest[app_id] = (occurred_at, is_out)
    return {aid for aid, (_, is_out) in latest.items() if is_out}
```

Add `InteractionDirection` to the existing `from app.db.models import (...)` block (line ~16-26).

- [ ] **Step 5: Add the field to `ApplicationOut`**

In the `ApplicationOut` class (line ~97), add after `notes`:

```python
    awaiting_response: bool = False
```

Change the `from_orm_row` signature (line ~120) and add the field to the constructor call:

```python
    @classmethod
    def from_orm_row(cls, app: Application, awaiting: bool = False) -> "ApplicationOut":
        return cls(
            ...
            notes=app.notes,
            awaiting_response=awaiting,
        )
```

- [ ] **Step 6: Wire into `list_apps`**

Replace the return in `list_apps` (line ~224-225):

```python
    rows = q.order_by(Application.created_at.desc()).all()
    awaiting = _compute_awaiting(db, rows)
    return [ApplicationOut.from_orm_row(r, awaiting=r.id in awaiting) for r in rows]
```

- [ ] **Step 7: Wire into `get_app`**

Replace the return in `get_app` (line ~234):

```python
    app = _load_owned(db, aid, user)
    awaiting = _compute_awaiting(db, [app])
    return ApplicationOut.from_orm_row(app, awaiting=app.id in awaiting)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_applications_awaiting.py -v`
Expected: PASS (5 tests).

- [ ] **Step 9: Run the broader app test module to check for regressions**

Run: `cd backend && pytest tests/integration/test_applications.py tests/integration/test_timeline_api.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/api/applications.py backend/tests/integration/test_applications_awaiting.py
git commit -m "feat(applications): awaiting_response flag on application output"
```

---

## Task 2: Frontend filter logic + type

**Files:**
- Modify: `frontend/src/api/applications.ts`
- Modify: `frontend/src/lib/filterDiagnostics.ts`
- Test: `frontend/src/lib/filterDiagnostics.test.ts`

- [ ] **Step 1: Extend the test helpers and add failing tests**

In `frontend/src/lib/filterDiagnostics.test.ts`:

Add `awaiting_response` to the `app()` helper's returned object (after `job_posting: jp,`):

```ts
    awaiting_response: o.awaiting ?? false,
```

And add `awaiting?: boolean;` to the `app()` parameter type (the `o: { ... }` object).

Add `awaitingOnly: false,` to the `fs()` defaults object (alongside `filterLabelIds: []`).

Add these tests at the end of the file:

```ts
test("applyFilters awaitingOnly keeps only awaiting apps", () => {
  const data = [app({ awaiting: true }), app({ awaiting: false })];
  const out = applyFilters(data, fs({ awaitingOnly: true }));
  assert.equal(out.length, 1);
  assert.equal(out[0].awaiting_response, true);
});

test("awaiting filter empties list -> awaiting", () => {
  const data = [app({ awaiting: false })];
  assert.equal(diagnoseEmpty(data, fs({ awaitingOnly: true })), "awaiting");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test:unit`
Expected: FAIL — `awaitingOnly` not on `FilterState` type / `applyFilters` ignores it.

- [ ] **Step 3: Add `awaiting_response` to the `Application` type**

In `frontend/src/api/applications.ts`, in the `Application` type (after `notes: string | null;`, line ~70):

```ts
  awaiting_response: boolean;
```

- [ ] **Step 4: Extend `FilterState`, `applyFilters`, `EmptyReason`, `diagnoseEmpty`**

In `frontend/src/lib/filterDiagnostics.ts`:

Add to `FilterState`:

```ts
  awaitingOnly: boolean;
```

In `applyFilters`, add before `if (!matchesSearch(...))`:

```ts
    if (f.awaitingOnly && !a.awaiting_response) return false;
```

Add `"awaiting"` to the `EmptyReason` union (before `"mixed"`).

In `diagnoseEmpty`, add to the `relaxations` array (after the `search` entry):

```ts
    { kind: "awaiting", state: { ...f, awaitingOnly: false } },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test:unit`
Expected: PASS (all existing + 2 new).

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: no errors (this will surface that `ApplicationsList.tsx` must supply `awaitingOnly` in its `filterState` — fixed in Task 3; if `tsc` errors only there, that is expected and resolved next task).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/applications.ts frontend/src/lib/filterDiagnostics.ts frontend/src/lib/filterDiagnostics.test.ts
git commit -m "feat(filter): awaitingOnly filter logic and Application flag"
```

---

## Task 3: Frontend toggle chip + empty-state copy

**Files:**
- Modify: `frontend/src/components/FilterEmptyState.tsx`
- Modify: `frontend/src/pages/ApplicationsList.tsx`

- [ ] **Step 1: Add empty-state copy**

In `frontend/src/components/FilterEmptyState.tsx`, add to the `COPY` record (after the `labels` entry):

```ts
  awaiting: { message: "No applications are awaiting a reply.", fix: "Show all" },
```

- [ ] **Step 2: Add the storage key and state to `ApplicationsList`**

In `frontend/src/pages/ApplicationsList.tsx`, add a constant beside the other keys (line ~21-23):

```ts
const AWAITING_FILTER_KEY = "applicator.awaitingFilter";
```

Add state beside `filterDocs` (line ~200):

```ts
  const [awaitingOnly, setAwaitingOnly] = useState<boolean>(
    () => localStorage.getItem(AWAITING_FILTER_KEY) === "true",
  );

  const toggleAwaiting = () =>
    setAwaitingOnly((v) => {
      localStorage.setItem(AWAITING_FILTER_KEY, String(!v));
      return !v;
    });
```

- [ ] **Step 3: Include `awaitingOnly` in `filterState`**

Update the `filterState` `useMemo` (line ~222-225):

```ts
  const filterState: FilterState = useMemo(
    () => ({ hiddenStatuses, reasonFilter, filterDocs, query, filterLabelIds, awaitingOnly }),
    [hiddenStatuses, reasonFilter, filterDocs, query, filterLabelIds, awaitingOnly],
  );
```

- [ ] **Step 4: Handle the `awaiting` fix and reset in `mixed`**

In `handleFix`, add a case (after the `labels` case):

```ts
      case "awaiting":
        setAwaitingOnly(false);
        localStorage.setItem(AWAITING_FILTER_KEY, "false");
        break;
```

In the `"mixed"` case body, add before the closing `break;`:

```ts
        setAwaitingOnly(false);
        localStorage.setItem(AWAITING_FILTER_KEY, "false");
```

- [ ] **Step 5: Render the toggle chip**

In the docs-filter row `<div className="flex flex-wrap gap-1.5 mb-3">` (line ~338), add the chip as the first child inside the div, before the `{ALL_DOCS.map(...)}`:

```tsx
        <button
          type="button"
          onClick={toggleAwaiting}
          className={`text-xs px-2 py-0.5 rounded border transition-colors ${
            awaitingOnly
              ? "bg-sky-100 text-sky-800 border-sky-300"
              : "bg-white text-slate-400 border-slate-200 hover:border-slate-400"
          }`}
        >
          Awaiting reply
        </button>
```

- [ ] **Step 6: Typecheck and unit tests**

Run: `cd frontend && npx tsc -b && npm run test:unit`
Expected: no type errors; all unit tests pass.

- [ ] **Step 7: Manual verification in browser**

Run the app (rebuild the Docker image per project workflow, then `docker compose up`). In the applications list:
- Seed an app with a sent inquiry / outbound interaction → toggle "Awaiting reply" → only that app shows.
- Add an inbound interaction (or import a reply `.eml`) → toggle again → app disappears.
- Mark an awaiting app `rejected` → it drops out of the awaiting set.
- Toggle on with no awaiting apps → empty-state shows "No applications are awaiting a reply." with a working "Show all" button.
- Reload the page → toggle state persists.

State explicitly if the browser cannot be exercised in this environment.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/FilterEmptyState.tsx frontend/src/pages/ApplicationsList.tsx
git commit -m "feat(filter): awaiting-reply toggle chip on applications list"
```

---

## Self-Review Notes

- **Spec coverage:** definition (Task 1 logic), backend flag + `_compute_awaiting` + both endpoints (Task 1), `Application` type (Task 2), `FilterState`/`applyFilters`/`EmptyReason`/`diagnoseEmpty` (Task 2), `FilterEmptyState` copy (Task 3), `ApplicationsList` chip + state + persistence + `handleFix` (Task 3), backend tests (Task 1), frontend tests (Task 2). All spec sections mapped.
- **Type consistency:** `awaiting_response` (snake_case API field) vs `awaitingOnly` (camelCase filter state) used consistently across tasks. `_compute_awaiting` returns `set[uuid.UUID]`; callers test membership with `r.id in awaiting`.
- **No migration:** field is derived; confirmed no model/DB change.
