# Awaiting-Response Filter — Design

## Problem

The applications list has filters for status, discard reason, required docs, labels,
and free-text search. None of them answer the everyday question: *"Which companies
have I contacted and am still waiting to hear back from?"*

Today "I sent a mail" is not a status. It is recorded as an `Interaction` row
(`direction=out`, `channel=mail`) created by inquiry *mark-sent*, manual interaction
entry, or `.eml` import. Replies are `Interaction` rows with `direction=in`. The
list endpoint (`ApplicationOut`) ships no interaction data, so the frontend cannot
filter on this today.

## Goal

Add an "Awaiting reply" filter to the applications list that shows only the
applications where the user has sent something and has not yet received a reply.

## Definition

An application is **awaiting a response** when **both** hold:

1. Its status is **not** closed/answered, i.e. not in
   `{offer, rejected, accepted, withdrawn, discarded}`.
2. Its **most recent** interaction (any channel, ordered by `occurred_at`) exists
   and has `direction = out`.

Consequences:

- No interactions at all → **not** awaiting (you must have sent something).
- A reply (`direction=in`) that is the latest interaction → not awaiting.
- A follow-up sent after their reply (latest is `out` again) → awaiting again.
  This naturally handles back-and-forth threads.
- Channel-agnostic: mail, linkedin, phone all count — matches the user's choice of
  "sent anything, no reply".
- Tie-break: if the maximum `occurred_at` is shared by an inbound and an outbound
  row, **inbound wins** (a reply clears the flag). This is a defensive edge case;
  same-timestamp interactions are not expected in practice.

## Approach

Chosen: **backend computes a boolean, frontend toggles client-side.**

The list endpoint computes `awaiting_response: bool` per application and includes it
on `ApplicationOut`. The frontend adds a toggle chip that filters the already-fetched
list client-side, exactly like the existing status / docs / search filters.

Rationale:
- The flag needs latest-interaction direction, which lives in the DB. Computing one
  bool server-side is cheaper than shipping interaction data to the client.
- Toggling stays instant and reuses the cached list (no refetch), matching the feel
  of every other client-side filter. Only the label filter goes server-side.
- The flag is reusable later (e.g. a row badge) without new endpoints.

Rejected:
- **Server query param `?awaiting=true`** — forces a refetch per toggle, breaks the
  instant-toggle feel, not reusable as a badge.
- **Client fetches per-app interactions** — N+1 requests.

## Backend changes (`backend/app/api/applications.py`)

- Module constant:
  `CLOSED_STATUSES = {ApplicationStatus.offer, .rejected, .accepted, .withdrawn, .discarded}`.
- `_compute_awaiting(db, apps: list[Application]) -> set[uuid.UUID]`:
  - Collect ids of `apps`.
  - One query: `(application_id, direction, occurred_at)` from `Interaction`
    filtered by `application_id IN ids`.
  - Reduce to the latest interaction direction per application (max `occurred_at`;
    inbound wins ties).
  - Awaiting set = apps whose latest direction is `out` **and** whose status is not
    in `CLOSED_STATUSES`.
- `ApplicationOut`:
  - New field `awaiting_response: bool`.
  - `from_orm_row(cls, app, awaiting: bool = False)` sets it.
- `list_apps`: after loading `rows`, call `_compute_awaiting(db, rows)` once, then
  `ApplicationOut.from_orm_row(r, awaiting=(r.id in awaiting_set))`.
- `get_app`: compute via `_compute_awaiting(db, [app])` so the single-row response is
  also correct (cheap, one app).

No DB migration — purely derived.

## Frontend changes

**`frontend/src/api/applications.ts`**
- Add `awaiting_response: boolean` to the `Application` type.

**`frontend/src/lib/filterDiagnostics.ts`**
- `FilterState`: add `awaitingOnly: boolean`.
- `applyFilters`: `if (f.awaitingOnly && !a.awaiting_response) return false;`.
- `EmptyReason`: add `"awaiting"`.
- `diagnoseEmpty`: add relaxation `{ kind: "awaiting", state: { ...f, awaitingOnly: false } }`.

**`frontend/src/components/FilterEmptyState.tsx`**
- `COPY.awaiting = { message: "No applications are awaiting a reply.", fix: "Show all" }`.

**`frontend/src/pages/ApplicationsList.tsx`**
- New constant `AWAITING_FILTER_KEY = "applicator.awaitingFilter"`.
- `awaitingOnly` state, initialised from `localStorage` (default `false`), with a
  toggle helper that persists.
- Render a toggle chip in the status-filter row (reuse the existing chip styling;
  active state highlighted like the docs/labels chips).
- Include `awaitingOnly` in the memoised `filterState`.
- `handleFix`: `case "awaiting": setAwaitingOnly(false); persist; break;` and reset it
  in the `"mixed"` case.

## Testing

**Backend** (extend the applications-list test module):
- Outbound is latest interaction → `awaiting_response = true`.
- Inbound is latest interaction → `false`.
- Latest interaction outbound but status closed (e.g. `rejected`) → `false`.
- No interactions → `false`.

**Frontend** (`frontend/src/lib/filterDiagnostics.test.ts`):
- Update the `fs()` helper default with `awaitingOnly: false`.
- Update the `app()` helper to set `awaiting_response` (default `false`,
  overridable).
- `applyFilters` drops non-awaiting rows when `awaitingOnly` is on.
- `diagnoseEmpty` returns `"awaiting"` when the awaiting filter alone empties the list.

## Out of scope

- A row/detail badge for awaiting state (the flag makes it trivial later).
- Sorting by time-since-last-contact.
- Notifications / reminders for stale awaiting applications.
