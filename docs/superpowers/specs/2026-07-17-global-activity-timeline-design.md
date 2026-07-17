# Global Activity Timeline

**Date:** 2026-07-17
**Status:** Approved

## Problem

Activity is only visible per-application (`ActivityTimeline.tsx` + `GET /api/applications/{aid}/timeline`). There is no single view showing, across all applications, when applications were sent and when interactions/status changes happened. The user wants one chronological view of everything they've done.

## Scope

A read-only cross-application timeline, added as a **tab on the existing Stats page**. Grouped by day, filterable by activity type, each row links to its application. No schema changes.

Out of scope: date-range pickers, company/text search, editing entries from this view, export.

## Data model

Every timeline row derives from existing data and carries a `category` used for filtering:

| Category (`category`) | Source | `at` timestamp | Notes |
|---|---|---|---|
| `application` | one row per `Application` | `created_at` | represents "application sent / logged" |
| `interaction` | `Interaction` rows | `occurred_at` | email/call/linkedin/interview |
| `status` | `ApplicationEvent` (status_change) with `to_value` NOT in the discard set | `occurred_at` | e.g. draft→applied, applied→interview |
| `discard` | `ApplicationEvent` (status_change) with `to_value` in `{rejected, discarded, withdrawn}` | `occurred_at` | rejections / discards / withdrawals |

Rationale for using `created_at` for "application sent": status-change events are recorded only on UPDATE (`session.dirty` in `app/db/events.py`), never on INSERT. A freshly-created `applied` application therefore has no event. `created_at` is the reliable signal for when an application entered the tracker.

The four categories are non-overlapping: creation comes from `Application.created_at`; later transitions come from `ApplicationEvent`.

## Backend

### New endpoint

`GET /api/timeline` (in `backend/app/api/applications.py`, same router).

Returns `list[GlobalTimelineRow]` sorted by `at` descending, aggregated across all of the user's non-deleted applications.

```python
class GlobalTimelineRow(BaseModel):
    category: str          # "application" | "interaction" | "status" | "discard"
    at: datetime
    application_id: str
    company: str | None    # from JobPosting
    title: str | None      # role/title from JobPosting
    status: str            # current application status (for context/badge)
    data: dict             # category-specific payload
```

`data` payload by category:
- `application`: `{}` (label is company/title + "Application created")
- `interaction`: `{direction, channel, subject, interview_stage}` (mirror the per-app timeline interaction fields, minus body — keep the global view compact)
- `status` / `discard`: `{kind, from, to}`

### Query strategy

1. Load the user's non-deleted applications (id, status, created_at) once; build an `app_id -> (company, title, status)` lookup by joining/left-joining `JobPosting`.
2. One query for all `Interaction` rows whose `application_id` is in the owned set.
3. One query for all `ApplicationEvent` rows whose `application_id` is in the owned set.
4. Emit one `application` row per owned app; classify each event into `status`/`discard`; assemble, sort reverse-chron, return.

No N+1: three bounded queries total, filtered to owned application ids.

### Ownership

All rows scoped to the authenticated user's applications only (deleted_at is null). Interactions/events for other users' apps must never appear — enforced by filtering on the owned id set.

## Frontend

### Stats page tabs

`Stats.tsx` gains a lightweight tab bar with two tabs:
- **Overview** — current Stats content, unchanged.
- **Timeline** — new `GlobalTimeline` component.

Tab state is local component state (no routing change needed).

### `GlobalTimeline` component

- Fetches `/api/timeline` via react-query (`queryKey: ["global-timeline"]`).
- New API binding in `frontend/src/api/interactions.ts` (or a small `timeline` module extension): `timeline.getGlobal()` → `GlobalTimelineRow[]`.
- **Grouping:** rows grouped under day headers using local time — "Today", "Yesterday", else localized date (e.g. `15 Jul 2026`). Reverse-chronological groups and rows.
- **Filter chips:** four toggle chips — Applications, Interactions, Status, Discards — each mapping to a `category`. All on by default; toggling hides that category client-side. When a filter empties a day group, that group header is not rendered. When everything is filtered out, show an empty-state hint.
- **Row content:** icon + one-line description + company · title + relative/absolute time. Whole row clickable → navigates to `/applications/{application_id}` (the app detail route).
- **Empty state:** "No activity yet." when the endpoint returns zero rows.

### Shared row rendering

The per-app `ActivityTimeline.tsx` has `iconFor` / `describe` helpers for interaction and event rows. Extract the reusable parts into a small helper module (e.g. `frontend/src/lib/timelineRender.ts`) so both the per-app and global timelines render interactions/events consistently. The global view adds handling for the `application` category ("Application created") and the company/title label; the per-app view keeps its body-expansion behavior.

## Testing

Backend:
- Endpoint returns rows across multiple applications, correctly categorized (application/interaction/status/discard), sorted reverse-chron.
- Ownership: another user's interactions/events/applications never appear.
- Discard classification: `to_value` in `{rejected, discarded, withdrawn}` → `discard`; other transitions → `status`.

Frontend:
- Grouping: rows bucketed into Today/Yesterday/date correctly.
- Filtering: toggling a category hides its rows; emptied day groups disappear; all-off shows empty state.

## Files touched

- `backend/app/api/applications.py` — new `GlobalTimelineRow` model + `GET /api/timeline`.
- `frontend/src/api/interactions.ts` — `getGlobal()` binding + `GlobalTimelineRow` type.
- `frontend/src/components/GlobalTimeline.tsx` — new.
- `frontend/src/lib/timelineRender.ts` — new, shared icon/describe helpers.
- `frontend/src/components/ActivityTimeline.tsx` — refactor to use shared helpers.
- `frontend/src/pages/Stats.tsx` — tab bar + mount Timeline tab.
- Corresponding test files.
