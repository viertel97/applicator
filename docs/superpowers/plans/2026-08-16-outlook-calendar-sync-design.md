# Design: Outlook "Interviews" calendar → app → Google Calendar

**Date:** 2026-08-16
**Status:** Approved (design)

## Problem

Interview invitations arrive at an Outlook.com mailbox. The user adds them to an
Outlook **calendar** directly (via `.ics` in the Outlook app). They want those
appointments to (1) appear in **this app** as interviews and (2) land on their
**Google Calendar** (their main calendar) — without manually forwarding mail
(not always possible; risks organizer notification) and without a Google write
integration.

## Flow

```
Outlook "Interviews" calendar  (user adds events here, source of truth)
      │  MS Graph Calendar API (poll + delta)
      ▼
   THIS app  (stores each as an Interaction, channel=interview)
      │  existing ICS feed at a URL
      ▼
 Google Calendar  (subscribed to the feed URL, auto-polls)
```

One-way fan-out: Outlook is the source; the app and Google Calendar are mirrors.
The app never writes back to Outlook.

**Known caveat (accepted):** Google refreshes subscribed URL feeds on its own
schedule (often hours, up to ~24h). Acceptable because interviews are booked
days out.

## Already built — reused as-is (no new work)

- **ICS output feed** — `app/calendar_feed/ics.py` + `app/api/calendar.py`. Google
  Calendar subscribes to this URL. Output half is done.
- **Fuzzy matcher** — `app/email_ingest/interview_match.py`
  (`match_application(sender, subject, body, candidates)`). Reused for calendar
  events: organizer email → `sender`, event title → `subject`, body preview →
  `body`.
- **Interview storage** — interviews are `Interaction` rows
  (`channel="interview"`, `occurred_at`=start, `ends_at`, `location`,
  `interview_stage`, `needs_review`). Needs-review queue + confirm/reassign modal
  already exist.
- **`InteractionCreatedFrom.graph_sync`** — enum value already reserved (no enum
  drift).
- **MS OAuth login** — `app/auth/ms_oauth.py` + `app/api/auth.py`. Refresh token
  already stored Fernet-encrypted on `User.ms_refresh_token_encrypted`. Config
  keys `ms_tenant_id / ms_client_id / ms_client_secret / ms_redirect_uri` exist;
  `Settings.oauth_enabled` gates it.

## New work (intake only)

### 1. OAuth scope bump
- `ms_oauth.MSConfig.scopes`: add `Calendars.Read` and `offline_access` to the
  existing `("User.Read",)`. Requires one re-login to re-consent.
- Add `acquire_token_by_refresh_token(cfg, refresh_token)` to mint an access
  token from the stored encrypted refresh token (MSAL confidential client).

### 2. Graph client — `app/calendar_sync/graph.py`
- Resolve the target calendar by display name: `GET /me/calendars`, match
  `displayName == settings.outlook_calendar_name` (default `"Interviews"`).
- Delta-sync its events: `GET /me/calendars/{id}/events/delta`. Follow
  `@odata.nextLink` pages; persist the final `@odata.deltaLink` for the next
  incremental pull.
- On `410 Gone` (expired delta link) → drop the stored link and do a full
  re-sync.
- Respect `429` `Retry-After` (surface for Celery retry).

### 3. Schema (one migration)
- Add to `Interaction`:
  - `external_source: str | None` (e.g. `"ms_graph"`)
  - `external_id: str | None` (Graph event id)
  - Unique constraint / dedupe on `(external_source, external_id)` for
    idempotent upsert.
- New table `CalendarSyncState`: `id`, `user_id` (FK), `calendar_id`,
  `delta_link` (Text, nullable), `updated_at`. Holds one row per synced
  calendar.
- Add a **migration test / DB-free test** for the new columns + table (per the
  testcontainers-masks-enum-drift lesson — integration tests build schema from
  models, not migrations).

### 4. Sync service — `app/calendar_sync/sync.py` (idempotent)
For each changed event returned by the delta query:
- **created / updated** → upsert an `Interaction` keyed on
  `(external_source, external_id)`:
  - `occurred_at` = event start (UTC), `ends_at` = event end,
    `location` = `location.displayName` or `onlineMeeting.joinUrl`,
    `subject` = event subject, `body` = `bodyPreview`,
    `channel = interview`, `created_from = graph_sync`.
  - **On first insert:** run the fuzzy matcher over the user's applications;
    set `application_id` to the best candidate and `needs_review = True`.
    Mirrors the email-webhook ingest path exactly.
  - **On update:** refresh time/location/subject fields; keep the existing
    `application_id` link.
- **@removed (cancelled)** → delete the linked `Interaction`. Existing
  `ON DELETE CASCADE` removes its `interview_scheduled` timeline note.
- Re-runs converge (idempotent).

**Unmatched events:** still created with a best-guess `application_id` and
`needs_review = True`, so they surface in the existing review queue for manual
reassignment — same behavior as the email-webhook path.

### 5. Celery beat task
- `tasks.sync_outlook_calendar`, added to `celery_app.beat_schedule`, every
  ~10 min (600s). Reuses existing Celery infra (`app/tasks/celery_app.py`).
- Skips cleanly when `Settings.oauth_enabled` is false or no refresh token is
  stored.

### 6. Config
- Add `outlook_calendar_name: str = "Interviews"` to `Settings`.

## Error handling
- Token refresh / consent revoked → log + surface state in settings; task no-ops
  rather than crashing.
- Graph `429` → respect `Retry-After` (Celery retry).
- Delta link `410 Gone` → reset stored link, full re-sync.
- Event missing a start time → skip.

## Testing
- **Unit:** event → `Interaction` mapping; `@removed` → delete; idempotent
  upsert on `(external_source, external_id)`; scopes include `Calendars.Read`.
- **Integration:** fake Graph client returning delta pages → sync creates /
  updates / deletes `Interaction`s and wires the matcher correctly.
- **Migration / DB-free:** new columns + `CalendarSyncState` table present.

## Out of scope (YAGNI)
- Push (change-notification) webhooks — polling only.
- Write-back to Outlook (one-way).
- Multiple calendars.
- Recurring-event expansion — recurring interviews are rare; masters are treated
  as single occurrences (flagged).
- Google Calendar write API — the existing ICS subscription covers output.
