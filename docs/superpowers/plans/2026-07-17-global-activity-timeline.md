# Global Activity Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cross-application "Timeline" tab to the Stats page that shows, in one chronological, day-grouped, type-filterable view, every application sent, interaction logged, and status change / discard across all of the user's applications.

**Architecture:** One new backend aggregation endpoint `GET /api/timeline` merges three existing data sources (Application.created_at, Interaction, ApplicationEvent) into category-tagged rows, owner-scoped, sorted newest-first. The frontend adds a tab to `Stats.tsx` hosting a new `GlobalTimeline` component that groups rows by day and filters them by category client-side. Pure grouping and row-description logic is extracted into testable helper modules shared with the existing per-app timeline.

**Tech Stack:** FastAPI + SQLAlchemy (backend), pytest + testcontainers (backend tests), React + react-query + react-router (frontend), Node built-in test runner (`node --test`, TypeScript type-stripping) for frontend unit tests.

---

## Key conventions (read before starting)

**Backend tests** live in `backend/tests/integration/`, use testcontainers Postgres. The schema is built from the ORM models via `Base.metadata.create_all` (NOT migrations), so no migration is needed for this feature (no schema change). Run with the project venv python, sandbox OFF:

```
cd backend && .venv/bin/python -m pytest tests/integration/test_global_timeline_api.py -v
```

Fixtures (from `backend/tests/integration/conftest.py`): `client` (authenticated `TestClient`), `db_session` (SQLAlchemy session), `auth_user` (returns `(client, user)`). Status-change `ApplicationEvent` rows are created automatically by a `before_flush` listener (`app/db/events.py`) — but ONLY on UPDATE of an existing Application, never on INSERT. To generate a status event in a test, PATCH the application after creating it.

**Frontend unit tests** use `node --test` via `npm run test:unit` (script: `node --test 'src/**/*.test.ts'`). Follow the existing pattern in `frontend/src/lib/parseCalendarPaste.test.ts`: `import test from "node:test"; import assert from "node:assert/strict";`, import the module under test with an explicit `.ts` extension. Pass a fixed `now: Date` into any time-dependent function so tests are deterministic. Run with sandbox OFF:

```
cd frontend && npm run test:unit
```

Do NOT unit-test React components (the runner has no DOM; Playwright is the only browser harness and crashes in-sandbox). Keep all testable logic in pure `.ts` helpers.

---

## Task 1: Backend `GET /api/timeline` endpoint

**Files:**
- Modify: `backend/app/api/interactions.py` (router prefix is `/api` — this avoids the `/{aid}` UUID-collision that would happen under the `applications.py` router, whose prefix is `/api/applications`)
- Test: `backend/tests/integration/test_global_timeline_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_global_timeline_api.py`:

```python
def test_global_timeline_aggregates_and_scopes(client, db_session, auth_user):
    from app.db.models import Application, JobPosting

    _, user = auth_user

    # App A: gets a job posting + status change to applied + an interaction
    a = Application(user_id=user.id, url="https://x.test/a", url_hash="ha")
    db_session.add(a)
    db_session.commit()
    db_session.add(JobPosting(application_id=a.id, company="Acme", title="Engineer"))
    db_session.commit()
    aid = a.id

    client.patch(f"/api/applications/{aid}", json={"status": "applied"})
    client.post(
        f"/api/applications/{aid}/interactions",
        json={"direction": "out", "channel": "mail", "subject": "Hi"},
    )
    client.patch(f"/api/applications/{aid}", json={"status": "rejected"})

    # App B: only created, never touched
    b = Application(user_id=user.id, url="https://x.test/b", url_hash="hb")
    db_session.add(b)
    db_session.commit()

    r = client.get("/api/timeline")
    assert r.status_code == 200
    rows = r.json()

    cats = [row["category"] for row in rows]
    assert cats.count("application") == 2          # one per app
    assert "interaction" in cats
    assert "status" in cats                        # draft -> applied
    assert "discard" in cats                       # applied -> rejected

    # company/title enrichment present on App A rows
    acme_rows = [row for row in rows if row["application_id"] == str(aid)]
    assert all(row["company"] == "Acme" for row in acme_rows)
    assert all(row["title"] == "Engineer" for row in acme_rows)

    # newest first
    ts = [row["at"] for row in rows]
    assert ts == sorted(ts, reverse=True)


def test_global_timeline_excludes_other_users(client, db_session, auth_user):
    from app.db.models import Application, User

    _, user = auth_user
    other = User(ms_oid="other", email="other@b.c", display_name="O")
    db_session.add(other)
    db_session.flush()
    db_session.add(Application(user_id=other.id, url="https://x.test/o", url_hash="ho"))
    db_session.commit()

    r = client.get("/api/timeline")
    assert r.status_code == 200
    assert r.json() == []


def test_global_timeline_excludes_deleted_apps(client, db_session, auth_user):
    from datetime import datetime, timezone
    from app.db.models import Application

    _, user = auth_user
    a = Application(
        user_id=user.id, url="https://x.test/d", url_hash="hd",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(a)
    db_session.commit()

    r = client.get("/api/timeline")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_global_timeline_api.py -v`
Expected: FAIL — `GET /api/timeline` returns 404 / 422 (route not defined) or assertion errors.

- [ ] **Step 3: Write the endpoint**

In `backend/app/api/interactions.py`, add near the other route definitions (after the imports and the existing models; `Application` is already imported, add `ApplicationEvent` and `JobPosting` to the model import block from `app.db.models`):

```python
_DISCARD_TO_VALUES = {"rejected", "discarded", "withdrawn"}


class GlobalTimelineRow(BaseModel):
    category: str  # "application" | "interaction" | "status" | "discard"
    at: datetime
    application_id: str
    company: str | None
    title: str | None
    status: str
    data: dict


@router.get("/timeline", response_model=list[GlobalTimelineRow])
def global_timeline(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    apps = (
        db.query(Application)
        .filter(Application.user_id == user.id, Application.deleted_at.is_(None))
        .all()
    )
    if not apps:
        return []
    app_ids = [a.id for a in apps]

    postings = {
        p.application_id: p
        for p in db.query(JobPosting).filter(JobPosting.application_id.in_(app_ids))
    }
    status_by_id = {a.id: a.status.value for a in apps}

    def _meta(aid):
        p = postings.get(aid)
        return (p.company if p else None, p.title if p else None)

    rows: list[GlobalTimelineRow] = []

    for a in apps:
        company, title = _meta(a.id)
        rows.append(GlobalTimelineRow(
            category="application", at=a.created_at, application_id=str(a.id),
            company=company, title=title, status=a.status.value, data={},
        ))

    for it in db.query(Interaction).filter(Interaction.application_id.in_(app_ids)):
        company, title = _meta(it.application_id)
        rows.append(GlobalTimelineRow(
            category="interaction", at=it.occurred_at,
            application_id=str(it.application_id),
            company=company, title=title, status=status_by_id[it.application_id],
            data={
                "direction": it.direction.value,
                "channel": it.channel.value,
                "subject": it.subject,
                "interview_stage": it.interview_stage.value if it.interview_stage else None,
            },
        ))

    for ev in db.query(ApplicationEvent).filter(ApplicationEvent.application_id.in_(app_ids)):
        company, title = _meta(ev.application_id)
        category = "discard" if ev.to_value in _DISCARD_TO_VALUES else "status"
        rows.append(GlobalTimelineRow(
            category=category, at=ev.occurred_at,
            application_id=str(ev.application_id),
            company=company, title=title, status=status_by_id[ev.application_id],
            data={"kind": ev.kind.value, "from": ev.from_value, "to": ev.to_value},
        ))

    rows.sort(key=lambda r: r.at, reverse=True)
    return rows
```

Also update the existing model import at the top of the file to include `ApplicationEvent` and `JobPosting` (JobPosting is already imported; add `ApplicationEvent`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_global_timeline_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/interactions.py backend/tests/integration/test_global_timeline_api.py
git commit -m "feat(api): add global activity timeline endpoint"
```

---

## Task 2: Frontend API binding + types

**Files:**
- Modify: `frontend/src/api/interactions.ts`

- [ ] **Step 1: Add the type and binding**

In `frontend/src/api/interactions.ts`, add the type near the existing `TimelineRow`:

```typescript
export type TimelineCategory = "application" | "interaction" | "status" | "discard";

export type GlobalTimelineRow = {
  category: TimelineCategory;
  at: string;
  application_id: string;
  company: string | null;
  title: string | null;
  status: string;
  data: {
    direction?: Direction;
    channel?: Channel;
    subject?: string | null;
    interview_stage?: InterviewStage | null;
    kind?: string;
    from?: string | null;
    to?: string | null;
  };
};
```

Extend the existing `timeline` export object with a `getGlobal` binding:

```typescript
export const timeline = {
  get: (appId: string) =>
    api<TimelineRow[]>(`/api/applications/${appId}/timeline`),
  getGlobal: () => api<GlobalTimelineRow[]>(`/api/timeline`),
};
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. (Per project note: run the raw `tsc` binary with sandbox OFF — do not rely on a proxy that summarizes output.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/interactions.ts
git commit -m "feat(frontend): add global timeline api binding"
```

---

## Task 3: Shared row-render helpers + refactor per-app timeline

**Files:**
- Create: `frontend/src/lib/timelineRender.ts`
- Create: `frontend/src/lib/timelineRender.test.ts`
- Modify: `frontend/src/components/ActivityTimeline.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/timelineRender.test.ts`:

```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { interactionIcon, interactionDescribe, eventDescribe } from "./timelineRender.ts";

test("interaction icon: interview vs outgoing vs incoming", () => {
  assert.equal(interactionIcon({ channel: "interview", direction: "out" }), "🎤");
  assert.equal(interactionIcon({ channel: "mail", direction: "out" }), "→");
  assert.equal(interactionIcon({ channel: "mail", direction: "in" }), "←");
});

test("interaction describe: interview uses stage label", () => {
  assert.equal(
    interactionDescribe({ channel: "interview", direction: "in", subject: null, interview_stage: "technical" }),
    "Interview — Technical",
  );
});

test("interaction describe: mail uses direction verb + subject", () => {
  assert.equal(
    interactionDescribe({ channel: "mail", direction: "out", subject: "Hello", interview_stage: null }),
    "Sent via mail — Hello",
  );
});

test("event describe: status change renders from -> to", () => {
  assert.equal(eventDescribe({ kind: "status_change", from: "draft", to: "applied" }), "Status: draft → applied");
});
```

Note: `"Technical"` must equal `STAGE_LABEL.technical` in `frontend/src/lib/interviewSummary.ts`. Verify that value while implementing; if the label differs, use the actual label in the assertion.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit`
Expected: FAIL — `./timelineRender.ts` does not exist.

- [ ] **Step 3: Implement the helpers**

Create `frontend/src/lib/timelineRender.ts`:

```typescript
import { STAGE_LABEL } from "./interviewSummary";
import type { Channel, Direction, InterviewStage } from "../api/interactions";

type InteractionLike = {
  channel: Channel | string;
  direction: Direction | string;
};

type InteractionDescribeLike = InteractionLike & {
  subject: string | null;
  interview_stage: InterviewStage | string | null;
};

type EventLike = { kind: string; from: string | null; to: string | null };

export function interactionIcon(it: InteractionLike): string {
  if (it.channel === "interview") return "🎤";
  return it.direction === "out" ? "→" : "←";
}

export function interactionDescribe(it: InteractionDescribeLike): string {
  if (it.channel === "interview") {
    const stage = it.interview_stage
      ? STAGE_LABEL[it.interview_stage as InterviewStage]
      : null;
    const tail = stage ?? it.subject;
    return `Interview${tail ? ` — ${tail}` : ""}`;
  }
  const dir = it.direction === "out" ? "Sent" : "Received";
  return `${dir} via ${it.channel}${it.subject ? ` — ${it.subject}` : ""}`;
}

export function eventDescribe(ev: EventLike): string {
  if (ev.kind === "status_change") return `Status: ${ev.from} → ${ev.to}`;
  return ev.kind;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit`
Expected: PASS.

- [ ] **Step 5: Refactor `ActivityTimeline.tsx` to use the helpers**

In `frontend/src/components/ActivityTimeline.tsx`, remove the local `STAGE_LABEL` import and replace the local `iconFor`/`describe` functions so they delegate to the shared helpers:

```typescript
import { interactionIcon, interactionDescribe, eventDescribe } from "../lib/timelineRender";
// (remove: import { STAGE_LABEL } from "../lib/interviewSummary";)

function iconFor(row: TimelineRow) {
  if (row.kind === "interaction") return interactionIcon(row.data);
  return "•";
}

function describe(row: TimelineRow): string {
  if (row.kind === "interaction") return interactionDescribe(row.data);
  return eventDescribe(row.data);
}
```

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/timelineRender.ts frontend/src/lib/timelineRender.test.ts frontend/src/components/ActivityTimeline.tsx
git commit -m "refactor(frontend): extract shared timeline render helpers"
```

---

## Task 4: Day-grouping helper

**Files:**
- Create: `frontend/src/lib/timelineGroup.ts`
- Create: `frontend/src/lib/timelineGroup.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/timelineGroup.test.ts`:

```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { dayLabel, groupByDay } from "./timelineGroup.ts";

const NOW = new Date("2026-07-17T10:00:00");

test("dayLabel returns Today for same calendar day", () => {
  assert.equal(dayLabel("2026-07-17T08:30:00", NOW), "Today");
});

test("dayLabel returns Yesterday for previous calendar day", () => {
  assert.equal(dayLabel("2026-07-16T23:00:00", NOW), "Yesterday");
});

test("dayLabel returns a formatted date for older days", () => {
  const label = dayLabel("2026-07-10T12:00:00", NOW);
  assert.notEqual(label, "Today");
  assert.notEqual(label, "Yesterday");
  assert.match(label, /2026/);
});

test("groupByDay buckets rows newest-day-first, preserving row order within a day", () => {
  const rows = [
    { at: "2026-07-17T09:00:00", id: "a" },
    { at: "2026-07-17T08:00:00", id: "b" },
    { at: "2026-07-16T20:00:00", id: "c" },
  ];
  const groups = groupByDay(rows, NOW);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].label, "Today");
  assert.deepEqual(groups[0].rows.map((r) => r.id), ["a", "b"]);
  assert.equal(groups[1].label, "Yesterday");
  assert.deepEqual(groups[1].rows.map((r) => r.id), ["c"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit`
Expected: FAIL — `./timelineGroup.ts` does not exist.

- [ ] **Step 3: Implement the helper**

Create `frontend/src/lib/timelineGroup.ts`:

```typescript
function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

export function dayLabel(iso: string, now: Date): string {
  const d = new Date(iso);
  const dayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / dayMs);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export type DayGroup<T> = { key: string; label: string; rows: T[] };

export function groupByDay<T extends { at: string }>(
  rows: T[],
  now: Date,
): DayGroup<T>[] {
  const groups: DayGroup<T>[] = [];
  let current: DayGroup<T> | null = null;
  for (const row of rows) {
    const label = dayLabel(row.at, now);
    if (!current || current.label !== label) {
      current = { key: label, label, rows: [] };
      groups.push(current);
    }
    current.rows.push(row);
  }
  return groups;
}
```

Note: `groupByDay` assumes `rows` are already sorted newest-first (the endpoint guarantees this). It groups consecutive same-day rows, so day headers appear in the same descending order as the rows.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/timelineGroup.ts frontend/src/lib/timelineGroup.test.ts
git commit -m "feat(frontend): add timeline day-grouping helper"
```

---

## Task 5: `GlobalTimeline` component

**Files:**
- Create: `frontend/src/components/GlobalTimeline.tsx`

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/GlobalTimeline.tsx`:

```typescript
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { timeline, type GlobalTimelineRow, type TimelineCategory } from "../api/interactions";
import { groupByDay } from "../lib/timelineGroup";
import { interactionIcon, interactionDescribe, eventDescribe } from "../lib/timelineRender";

const FILTERS: { key: TimelineCategory; label: string }[] = [
  { key: "application", label: "Applications" },
  { key: "interaction", label: "Interactions" },
  { key: "status", label: "Status" },
  { key: "discard", label: "Discards" },
];

function iconFor(row: GlobalTimelineRow): string {
  if (row.category === "application") return "📮";
  if (row.category === "interaction") {
    return interactionIcon({ channel: row.data.channel ?? "other", direction: row.data.direction ?? "in" });
  }
  return row.category === "discard" ? "🗑" : "•";
}

function describe(row: GlobalTimelineRow): string {
  if (row.category === "application") return "Application created";
  if (row.category === "interaction") {
    return interactionDescribe({
      channel: row.data.channel ?? "other",
      direction: row.data.direction ?? "in",
      subject: row.data.subject ?? null,
      interview_stage: row.data.interview_stage ?? null,
    });
  }
  return eventDescribe({
    kind: row.data.kind ?? "status_change",
    from: row.data.from ?? null,
    to: row.data.to ?? null,
  });
}

function label(row: GlobalTimelineRow): string {
  return [row.company, row.title].filter(Boolean).join(" · ") || "Untitled application";
}

export function GlobalTimeline() {
  const navigate = useNavigate();
  const [active, setActive] = useState<Set<TimelineCategory>>(
    () => new Set(FILTERS.map((f) => f.key)),
  );

  const q = useQuery({
    queryKey: ["global-timeline"],
    queryFn: () => timeline.getGlobal(),
  });

  function toggle(key: TimelineCategory) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  if (!q.data) return <div className="text-sm text-muted">Loading…</div>;
  if (q.data.length === 0)
    return <div className="text-sm text-muted">No activity yet.</div>;

  const visible = q.data.filter((r) => active.has(r.category));
  const groups = groupByDay(visible, new Date());

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => {
          const on = active.has(f.key);
          return (
            <button
              key={f.key}
              onClick={() => toggle(f.key)}
              className={`text-xs px-2 py-1 rounded border ${
                on ? "bg-fg text-bg" : "text-muted"
              }`}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      {groups.length === 0 ? (
        <div className="text-sm text-muted">Nothing matches the current filters.</div>
      ) : (
        groups.map((g) => (
          <div key={g.key}>
            <div className="text-xs font-semibold text-muted uppercase mb-1">{g.label}</div>
            <ul className="divide-y border rounded">
              {g.rows.map((row, i) => (
                <li
                  key={i}
                  className="p-2 flex gap-3 cursor-pointer hover:bg-surface"
                  onClick={() => navigate(`/applications/${row.application_id}`)}
                >
                  <span className="text-muted w-5 text-center">{iconFor(row)}</span>
                  <div className="flex-1">
                    <div className="text-sm">{describe(row)}</div>
                    <div className="text-xs text-muted">{label(row)}</div>
                  </div>
                  <div className="text-xs text-muted whitespace-nowrap">
                    {new Date(row.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}
```

Note: reuse whatever `bg-surface` / `text-muted` / `text-fg` / `bg-fg` tokens the codebase already uses (they appear in `ActivityTimeline.tsx` and `Stats.tsx`). If a token name differs, match the existing components rather than inventing new classes.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/GlobalTimeline.tsx
git commit -m "feat(frontend): add global timeline component"
```

---

## Task 6: Add Timeline tab to Stats page

**Files:**
- Modify: `frontend/src/pages/Stats.tsx`

- [ ] **Step 1: Wire a tab bar into Stats**

In `frontend/src/pages/Stats.tsx`:

1. Add imports at the top:

```typescript
import { useState } from "react";
import { GlobalTimeline } from "../components/GlobalTimeline";
```

2. Inside the `Stats` page component, introduce tab state and render a tab bar above the existing content. Wrap the current Stats body (charts/KPIs) so it only renders on the "overview" tab, and render `<GlobalTimeline />` on the "timeline" tab:

```typescript
const [tab, setTab] = useState<"overview" | "timeline">("overview");

// ...inside the returned JSX, above the existing content:
<div className="flex gap-2 mb-4">
  {(["overview", "timeline"] as const).map((t) => (
    <button
      key={t}
      onClick={() => setTab(t)}
      className={`text-sm px-3 py-1 rounded border ${
        tab === t ? "bg-fg text-bg" : "text-muted"
      }`}
    >
      {t === "overview" ? "Overview" : "Timeline"}
    </button>
  ))}
</div>

{tab === "timeline" ? <GlobalTimeline /> : (
  /* existing overview content goes here */
)}
```

Adapt the exact JSX nesting to the current structure of `Stats.tsx` (it uses a top-level wrapper; keep the tab bar inside that wrapper so page padding/heading is preserved). The existing charts must remain unchanged on the overview tab. If the file returns early while loading data (e.g. `if (!data) return ...`), place the tab bar and the timeline branch so the Timeline tab is reachable even while overview data is still loading — i.e. render the tab bar before any overview-data early-return, and short-circuit to `<GlobalTimeline />` when `tab === "timeline"`.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual verification**

Run the app (per project `run`/`verify` skills; build the Docker image in your own terminal per project note, then bring up local images). Log in, open Stats, confirm:
- Two tabs (Overview, Timeline) render; Overview is unchanged.
- Timeline shows day headers with entries newest-first.
- Toggling each filter chip hides/shows that category; turning all off shows the "Nothing matches" hint.
- Clicking a row navigates to that application's detail page.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Stats.tsx
git commit -m "feat(frontend): add timeline tab to stats page"
```

---

## Final verification

- [ ] Backend tests pass: `cd backend && .venv/bin/python -m pytest tests/integration/test_global_timeline_api.py -v`
- [ ] Frontend unit tests pass: `cd frontend && npm run test:unit`
- [ ] Frontend typechecks: `cd frontend && npx tsc --noEmit`
- [ ] Existing per-app timeline still works (ActivityTimeline refactor did not change behavior) — spot-check on an application detail page.
