# Outlook Sync Visibility — Design

**Goal:** Give the user a page to (a) see whether the Outlook calendar connection is actually working, and (b) browse every event pulled from Outlook — not just the pending ones. Mirrors the existing "Webhook log" page.

**Problem today:** The webhook log works because every inbound request persists a `WebhookRequest` row (success *and* failure). Calendar sync persists nothing per run — `sync_outlook_calendar_task` returns a stats/skip dict that is only logged. `CalendarSyncState` stores just the delta cursor + `updated_at`. So there is no way to answer "did it run, did it work, and why not." Separately, the `CalendarSuggestion` rows pulled from Outlook are only visible while `pending` (Suggestions tab); confirmed/dismissed ones disappear, so there is no full list of "what came from Outlook."

**Tech stack:** FastAPI + SQLAlchemy 2.0 (Mapped/mapped_column) + Alembic + Postgres; React + TanStack Query + Tailwind + react-router; pytest + testcontainers.

**Decisions locked during brainstorming:**
- Show **both** a connection/run status **and** the list of pulled entries.
- **Latest-only** run status (no per-run history table).
- Include a manual **"Sync now"** trigger.

---

## Architecture

Three backend pieces + one frontend page:

1. **Health fields on `User`** — the latest sync result, written on every sync exit path.
2. **Sync refactor** — `sync_user_calendar` records those fields on success, every skip, and every error; accepts a `trigger` label.
3. **Endpoints** — `sync-now` (manual trigger), `sync-status` (read health), `entries` (all pulled events).
4. **Frontend** — a new Settings sub-page mirroring `SettingsWebhooks.tsx`.

### Why health lives on `User`, not `CalendarSyncState`

`CalendarSyncState` is keyed on `(user_id, calendar_id)` and is only created **after** the calendar is resolved (`sync_outlook_calendar.py:100`). The failures the user most wants to see — `no_token`, `token_refresh_failed`, `no_calendar`, `oauth_disabled` — all occur **before** that row exists, so they cannot be recorded there. `User` is the one entity guaranteed to exist on every path, and it already holds `ms_refresh_token_encrypted`, so the Outlook connection state is coherent there. This keeps "latest-only, no new table" while capturing all failure modes. One Outlook calendar is synced per user (`settings.outlook_calendar_name`), so per-user health == per-connection health.

---

## Data model

Add to `class User(Base)` in `backend/app/db/models.py` (after `created_at`, ~line 182):

```python
outlook_last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
outlook_last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
outlook_last_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
outlook_last_trigger: Mapped[str | None] = mapped_column(String(16), nullable=True)
outlook_last_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
outlook_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Convention (validated by tests, NOT a DB enum — same rationale as `WebhookRequest.status`, avoids enum-drift migration friction):
- `outlook_last_status` ∈ `{"ok", "skipped", "error"}`.
- `outlook_last_reason`: free string; known values `no_token`, `no_calendar`, `oauth_disabled`, `token_refresh_failed`, `rate_limited`, `graph_error`. `null` when status is `ok`.
- `outlook_last_trigger` ∈ `{"scheduled", "manual"}`.
- `outlook_last_counts`: `{"created": int, "updated": int, "deleted": int, "skipped": int}` on `ok`, else `null`.
- `outlook_last_error`: short exception text on `error`, else `null`.

**Alembic migration** adds the six nullable columns to `user` (down_revision = current head `e1a2b3c4d5e6`; the plan must re-confirm the head at implementation time). All nullable → no backfill. Migration-guard test asserts the columns exist after `upgrade head` (the integration DB builds schema from models and would mask a missing migration).

---

## Sync refactor

`backend/app/calendar_sync/` and `backend/app/tasks/sync_outlook_calendar.py`.

Introduce a single helper that stamps the health fields, and call it on every exit:

```python
def _record_health(user, *, status, reason=None, trigger, counts=None, error=None):
    user.outlook_last_sync_at = datetime.utcnow()   # naive UTC, matching how all datetimes are stored in this codebase
    user.outlook_last_status = status
    user.outlook_last_reason = reason
    user.outlook_last_trigger = trigger
    user.outlook_last_counts = counts
    user.outlook_last_error = error
```

Change `sync_user_calendar(db, user, settings, *, graph=None, trigger="scheduled")`:
- On `no_token` (access token is None) → `_record_health(status="skipped", reason="no_token")`, commit, return `{"skipped": "no_token"}` (unchanged return shape).
- On `no_calendar` → `_record_health(status="skipped", reason="no_calendar")`, commit, return `{"skipped": "no_calendar"}`.
- On success → `_record_health(status="ok", counts=stats)` alongside the existing `state.delta_link = delta_link`, commit, return `stats`.
- Wrap the Graph/token calls so exceptions are recorded:
  - `GraphRateLimited` → record `status="error", reason="rate_limited", error=str(exc)`, commit, then **re-raise** (the Celery task still needs to `self.retry`). The manual endpoint catches it (below) and returns the recorded health rather than retrying.
  - Any other `Exception` → record `status="error", reason="graph_error", error=<short str>`, commit, then re-raise. (For the scheduled task this surfaces as before; for manual it is caught.)
- `token_refresh_failed`: `_access_token` currently returns `None` and logs on refresh failure, which is indistinguishable from `no_token` at the call site. Refactor `_access_token` to distinguish "no token stored" from "refresh failed" (e.g. return a small result object or raise a typed error) so health can record `no_token` vs `token_refresh_failed` correctly.

The task loop (`sync_outlook_calendar_task`) passes `trigger="scheduled"` and is otherwise unchanged (it already loops users and returns the per-user dict). `oauth_disabled` is handled at the task level (returns early); the **manual endpoint** records/returns `oauth_disabled` itself (see below), so scheduled runs need no health row for the global-disabled case.

Health writes must not break sync idempotency — they are plain column assignments committed in the same transaction as the existing `db.commit()`.

---

## Endpoints

Extend `backend/app/api/calendar.py` (reuse existing `router`, `db_dep`, `current_user`, `UtcDateTime`, `_company`).

### `GET /api/calendar/sync-status`
Returns the current user's health:
```
SyncStatusOut {
  last_sync_at: UtcDateTime | null
  last_status: str | null
  last_reason: str | null
  last_trigger: str | null
  last_counts: { created:int, updated:int, deleted:int, skipped:int } | null
  last_error: str | null
  oauth_enabled: bool          # from settings, so the UI can explain a disabled integration
}
```

### `POST /api/calendar/sync-now`
Runs a sync for the current user **synchronously** and returns the resulting `SyncStatusOut`.
- If `settings.oauth_enabled` is false → record/return `status="skipped", reason="oauth_disabled"` (still persist to `User` so the page shows it), 200.
- Else call `sync_user_calendar(db, user, settings, trigger="manual")` inside a `try/except` that catches `GraphRateLimited` and generic `Exception` (health already recorded inside the helper) and returns the persisted `SyncStatusOut` with HTTP 200 (a failed *connection* is a successful *diagnostic* — the page shows the red status; we do not 500). Re-read the user's health fields after the call and return them.
- This is a real MS Graph call. It is the point of the button.

### `GET /api/calendar/entries`
Returns **all** `CalendarSuggestion` rows for the user (every status), newest first (`starts_at desc`, or `created_at desc` — pick `starts_at desc` for calendar relevance):
```
CalendarEntryOut {
  id, external_id, subject, starts_at, ends_at, location, organizer_email,
  status: "pending" | "confirmed" | "dismissed",
  match_score: float | null,
  suggested_application: { id, display_id, company } | null,
  interaction_id: uuid | null
}
```
The existing `GET /api/calendar/suggestions` (pending-only, for the Suggestions tab) is unchanged.

---

## Frontend

New page `frontend/src/pages/SettingsOutlookSync.tsx`, mirroring `SettingsWebhooks.tsx` structure/classes.

**API client** — extend `frontend/src/api/calendar.ts`:
- `syncStatus()` → `GET /api/calendar/sync-status`
- `syncNow()` → `POST /api/calendar/sync-now`
- `entries()` → `GET /api/calendar/entries`
- types `SyncStatus`, `CalendarEntry`.

**Page layout:**
1. **Connection card** (top): heading "Outlook-Verbindung". Shows last-sync time (`toLocaleString`), a status badge (green `ok` / grey `skipped` / red `error`), the reason + `last_error` text, and the counts. A **"Jetzt synchronisieren"** button calls `syncNow()`; on success it invalidates `["outlook-sync-status"]`, `["calendar-entries"]`, `["calendar-suggestions"]`, `["suggestions"]` and shows the returned status. Disabled while pending. When `oauth_enabled` is false, show an explanatory line ("Outlook-Integration ist deaktiviert").
2. **Entries table** (below): query `["calendar-entries"]`. Columns: Zeit (`starts_at`), Betreff (subject), Zuordnung (`#display_id company` or "—"), Status badge (Ausstehend / Bestätigt / Ausgeblendet). Empty state "Noch keine Kalender-Einträge übernommen."

**Wiring:**
- Route in `frontend/src/App.tsx`: `path="/settings/outlook"` → `<SettingsOutlookSync />` (mirror the `/settings/webhooks` route block).
- Nav in `frontend/src/components/nav/navItems.ts`: `{ to: "/settings/outlook", label: "Outlook sync", group: "settings" }`.

Reuse a small `StatusBadge` (map status/entry-status → tone) as in `SettingsWebhooks.tsx`; no shared extraction needed unless trivial.

---

## Testing

Backend (venv binary directly, sandbox disabled — testcontainers needs Docker; NOT via rtk):
- **Migration guard** (`test_user_outlook_health_migration.py`): `upgrade head` on a fresh container, assert the six `user` columns exist. Follow the sibling migration-test convention (`__file__`-relative Config + `DROP SCHEMA public CASCADE` isolation) used by `test_calendar_suggestion_migration.py`.
- **Sync health** (extend `test_calendar_sync.py` or a new `test_calendar_sync_health.py`): with an injected `GraphClient`, assert `User.outlook_last_*` is stamped correctly on: `no_token`, `no_calendar`, `ok` (counts match stats + status ok + reason null + trigger), and a Graph exception (`status="error"`, reason recorded, error text set, exception re-raised). Distinguish `no_token` vs `token_refresh_failed`.
- **Endpoints** (`test_calendar_sync_api.py`): `sync-status` returns health + `oauth_enabled`; `sync-now` with a stubbed/injected graph updates and returns health (and the `oauth_disabled` path returns skipped without 500); `entries` returns pending+confirmed+dismissed rows (not filtered like `/suggestions`).

Frontend: raw `tsc` (`frontend/node_modules/typescript/bin/tsc --noEmit`, NOT `npx tsc` — the rtk hook masks compiler errors).

---

## Out of scope (YAGNI)

- Per-run history table (explicitly chose latest-only).
- Storing raw Graph event JSON per run (the entries table already shows what arrived).
- Retention/pruning, pagination on entries (the volume is small; add later if needed).
- Multi-calendar support (one configured calendar per user).

---

## File structure

**Backend**
- Modify `backend/app/db/models.py` — six `outlook_last_*` columns on `User`.
- Create `backend/alembic/versions/<rev>_user_outlook_health.py` — add columns (down_revision = head `e1a2b3c4d5e6`, re-confirm at build time).
- Modify `backend/app/tasks/sync_outlook_calendar.py` — `_record_health`, `trigger` param, distinguish token-refresh failure, record on every path.
- Modify `backend/app/api/calendar.py` — `sync-status`, `sync-now`, `entries` endpoints + response models.
- Create `backend/tests/integration/test_user_outlook_health_migration.py`.
- Create/extend `backend/tests/integration/test_calendar_sync_health.py` (sync health) and `test_calendar_sync_api.py` (endpoints).

**Frontend**
- Modify `frontend/src/api/calendar.ts` — `syncStatus`, `syncNow`, `entries` + types.
- Create `frontend/src/pages/SettingsOutlookSync.tsx`.
- Modify `frontend/src/App.tsx` — route.
- Modify `frontend/src/components/nav/navItems.ts` — nav link.
