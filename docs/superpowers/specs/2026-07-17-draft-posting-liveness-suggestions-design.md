# Draft Posting Liveness Checks & Suggestions Inbox

Date: 2026-07-17
Status: Approved design (pending user spec review)

## Problem

Job postings for applications still in `draft` status may go offline (filled,
expired, removed) before the user acts on them. The user wants the app to
detect this automatically on a schedule and **suggest** action — never mutate
application state on its own. Human-in-the-loop stays: the app flags, the user
decides.

## Existing state (do not rebuild)

A checker already exists and covers most of the mechanism:

- `backend/app/tasks/check_postings.py` — `check_postings_task`.
- `backend/app/tasks/celery_app.py` — Celery beat schedule
  `check-postings-every-6h` (21600s).
- Fetch via `httpx` with browser User-Agent, `follow_redirects=True`.
- Detection: 404/410 → offline; HTTP 200 + keyword match → offline; otherwise
  LLM fallback ("is this still an active job posting?").
- Writes `Application.posting_online` (bool|null) and
  `posting_checked_at` (datetime). Skips re-checking within 4h. Skips
  `withdrawn`/`rejected`.
- Frontend already shows an `OnlineBadge` (green Online / red Offline) on
  `ApplicationsList` and `ApplicationDetail`.

The checker never changes `status` — human-in-the-loop is already satisfied at
the data layer. This spec **enhances** the checker and adds a suggestions
surface; it is not a greenfield build.

## Decisions (locked)

1. **Scope:** check `status == draft` only (was: all except withdrawn/rejected).
2. **403:** treat as offline (alongside 404/410).
3. **Redirect:** flag a redirect to a *different host* or to a bare-root /
   homepage-like path as offline.
4. **Keywords:** add the missing German phrases.
5. **Reason:** store *why* a posting was judged offline.
6. **Suggestions inbox:** a dedicated page listing offline drafts, plus a
   notification count in nav. (Not inline card CTAs.)
7. **Dismiss:** permanent per application; a dismissed suggestion never
   re-surfaces.
8. **No auto-action:** checker only sets flags; status changes only via the
   user's explicit Discard action.

## Data model

Add two nullable columns to `Application` (`backend/app/db/models.py`) + one
Alembic migration in `backend/alembic/versions/`:

- `posting_offline_reason: Mapped[str | None]` (`Text`, nullable) — short
  machine/humanreadable reason, e.g. `http_404`, `http_403`,
  `redirect_offhost`, `redirect_root`, `keyword:bereits besetzt`,
  `llm_inactive`.
- `posting_offline_dismissed_at: Mapped[datetime | None]` (`DateTime`,
  nullable) — set when user dismisses; never auto-cleared.

Set `posting_offline_reason` alongside `posting_online`/`posting_checked_at` in
the task (null it out when a posting is online).

## Checker changes (`check_postings.py`)

- **Query filter:** `Application.status == ApplicationStatus.draft`.
- **`_OFFLINE_STATUSES`:** add `403`.
- **`_OFFLINE_KEYWORDS`:** add `"stellenanzeige konnte nicht gefunden werden"`,
  `"keine stellenanzeige gefunden"`, `"bereits besetzt"`.
- **Redirect detection:** `_default_fetch` returns `(status, text, final_url)`;
  compare `final_url` host + path to the original `app.url`. If host differs, or
  the final path is a bare root (`/`, or a short homepage-like path such as
  `/jobs`, `/karriere`, `/stellenangebote` with no id/slug segment), treat as
  offline with reason `redirect_offhost` / `redirect_root`. Same-host deep
  redirects fall through to keyword/LLM as today.
- **`_heuristic`/`_check_one`:** return `(online: bool|None, reason: str|None)`
  so the reason propagates to the DB write. LLM "no" → reason `llm_inactive`.
- Preserve: 4h skip window, LLM fallback, 6h cadence, flag-only writes.
- Do **not** overwrite `posting_offline_dismissed_at`; leave it to the API.

## API (`backend/app/api/applications.py`)

- **`GET /api/applications/suggestions`** — returns current user's applications
  where `status == draft AND posting_online IS FALSE AND
  posting_offline_dismissed_at IS NULL`. Response items include: id, url, job
  title/company (from `JobPosting` if present), `posting_offline_reason`,
  `posting_checked_at`. Response model follows existing Pydantic `*Out` pattern.
- **`POST /api/applications/{id}/dismiss-offline`** — sets
  `posting_offline_dismissed_at = now(utc)` for the owned application. Idempotent.
- Discard uses the **existing** status/discard flow — no new endpoint.
- Expose the two new fields on the existing application detail/list `*Out`
  models where the frontend needs them (at minimum `posting_offline_reason`).

## Frontend

- **Nav notification** (`components/nav/navItems.ts`, `DesktopNav`,
  `MobileNav`): add a "Suggestions" main-group item at `/suggestions` with a
  small count badge showing the number of open suggestions. Count comes from the
  suggestions endpoint (fetch on load / existing query cache). Badge hidden when
  count is 0.
- **New page** `frontend/src/pages/Suggestions.tsx` + route in `App.tsx`
  (`/suggestions`). Lists each offline draft: title/company, url, human-readable
  reason (map reason code → German label, e.g. `redirect_root` → "Weiterleitung
  zur Startseite", `http_404` → "Seite nicht gefunden"), last-checked time, and
  per-row actions:
  - **Open** — navigate to `ApplicationDetail`.
  - **Discard** — open the existing discard flow (`DiscardReasonPicker` /
    status change). On success the item leaves the list (no longer draft).
  - **Dismiss** — call dismiss endpoint; item leaves the list; count decrements.
- **API client** (`frontend/src/api/applications.ts`): add `getSuggestions()`
  and `dismissOffline(id)`; add `posting_offline_reason` to the application type.
- Existing `OnlineBadge` stays as-is on list/detail.

## Error handling

- Fetch errors / timeouts → inconclusive (`online=None`), no reason, no write —
  same as today.
- 403 with a real body is still treated as offline per decision 2; accepted
  false-positive risk. Reason `http_403` makes it auditable in the inbox, and
  Dismiss lets the user override.
- Dismiss/discard endpoints scope to the authenticated user; 404 on non-owned
  or missing id.

## Testing

- **Task unit tests** (DB-free where possible, per repo convention): inject
  `fetch_fn` returning crafted `(status, text, final_url)`; assert
  `(online, reason)` for: 404, 403, 410, keyword hits (each new German phrase),
  off-host redirect, root redirect, same-host deep redirect → falls to
  keyword/LLM, HTTP 200 clean → online with reason cleared.
- **Scope test:** only `draft` applications are queried; applied/interview/etc.
  are skipped.
- **API tests:** suggestions endpoint returns only offline, non-dismissed draft
  apps for the current user; dismiss endpoint sets the timestamp and removes the
  item from a subsequent suggestions call; ownership enforced.
- **Migration test:** upgrade adds both columns; per the enum-drift memory,
  include a migration-level check rather than relying only on model-built schema.
- **Frontend:** Suggestions page renders rows, reason labels, and the three
  actions; nav badge reflects count and hides at 0.

## Out of scope / YAGNI

- No auto status changes ever.
- No re-surfacing of dismissed suggestions.
- No email/push notifications (in-app count only).
- No change to cron cadence or the 4h skip window.
- No re-check of non-draft applications.
