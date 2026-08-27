# Calendar Event Suggestions — staged review before interviews

**Date:** 2026-08-27
**Status:** Approved, ready for implementation plan

## Problem

Outlook calendar events pulled via MS Graph delta-sync are currently
force-created as interview `Interaction`s the moment they arrive: each is
best-guess matched to an application, flagged `needs_review=True`, and shown on
the Calendar (orange chip) before the user has confirmed anything. Two gaps:

1. **No overview** of what was pulled — only a review *count* badge exists, no
   list showing "these events came from the calendar and here's the match."
2. **No real gate** — events become live interviews with a forced match even
   when the match is weak, because the `Interaction.application_id` FK is
   non-null and `match_application` always returns a best candidate.

## Goal

Pulled events land in a **staging** store and surface as reviewable items in
the existing **Suggestions** tab. Nothing becomes a real interview until the
user confirms. Confirmed interviews stay **live-linked** to Outlook (later
changes keep syncing). Dismissed events never resurface.

## Decisions (from brainstorming)

- **Where reviewed:** the existing `/suggestions` tab gets a new "Calendar
  interviews" section (alongside the current offline-posting suggestions).
- **Apply model:** *staged until confirm* — pulled events do NOT become
  interviews or appear on the Calendar until confirmed.
- **Post-confirm:** *stay live-linked* — the promoted `Interaction` keeps its
  `external_id`; later Outlook edits update it, cancellation removes it.
- **Confirm requires an application** — an unmatched event cannot be promoted
  without the user picking an app.
- **Overview scope:** pending list only. No confirmed/dismissed history view
  (YAGNI).

## Data model — new `CalendarSuggestion` table

One row per pulled Outlook event, keyed on `(user_id, external_source,
external_id)`. Serves as both the staging store and the tombstone that keeps
re-syncs idempotent (a full 410 re-sync must not resurrect dismissed/confirmed
events).

| field | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → user | |
| `external_source` | str | `ms_graph` |
| `external_id` | str | Graph event id; unique per `(user_id, external_source)` |
| `status` | enum `CalendarSuggestionStatus` | `pending` / `confirmed` / `dismissed` |
| `subject` | str \| null | event snapshot |
| `starts_at` | datetime (naive UTC) | |
| `ends_at` | datetime \| null | |
| `location` | str \| null | displayName or online-meeting join URL |
| `body` | str \| null | `bodyPreview` |
| `organizer_email` | str | used for matching |
| `suggested_application_id` | uuid FK → application, **nullable** | best-guess, or null |
| `match_score` | float \| null | confidence, for UI display |
| `interaction_id` | uuid FK → interaction, nullable | set on confirm |
| `created_at`, `updated_at` | datetime | |

The nullable application FK is the point of staging: unmatched events wait here
with no forced link; the user picks the app at confirm time.

## Sync becomes a state machine (`app/calendar_sync/sync.py`)

`sync_calendar_events` is rewritten to project delta events into
`CalendarSuggestion` rows instead of `Interaction`s. Per event, look up the
suggestion by `external_id`:

- **none** → create `pending`. Run `match_application` to prefill
  `suggested_application_id` + `match_score`. Prefill with the best candidate
  whenever any application exists (mirrors current matcher behavior — no new
  confidence threshold); `suggested_application_id` is null only when the user
  has no applications at all. The user can always reassign at confirm.
- **pending** → refresh snapshot fields (time moved, subject changed, etc.).
- **confirmed** → **live-link**: update the linked `Interaction`
  (occurred_at / ends_at / location / subject / body), mirroring today's
  update behavior.
- **dismissed** → ignore (do nothing).
- **`@removed`** (cancellation) →
  - pending: delete the suggestion
  - confirmed: delete the linked `Interaction` (ON DELETE CASCADE removes its
    `interview_scheduled` timeline note, as today)
  - dismissed: nothing

Because `status` persists, a full re-sync (410 → full delta) cannot resurrect
dismissed or confirmed events.

Stats dict returned by sync updated to reflect suggestion outcomes
(e.g. `created` / `updated` / `deleted` / `skipped` over suggestions and, for
confirmed events, interaction updates).

## API (`app/api/calendar.py`)

- `GET /api/calendar/suggestions` → pending list. Each item: id, subject,
  starts_at, ends_at, location, organizer, `suggested_application` (display_id
  + company or null), `match_score`.
- `POST /api/calendar/suggestions/{id}/confirm` — body optional
  `application_id` to override/assign the match. Resolves the target app
  (override → else `suggested_application_id`); **400 if none resolved**.
  Creates the real `Interaction`:
  - `channel=interview`, `direction=in_`, `needs_review=False`,
    `created_from=graph_sync`, `external_source=ms_graph`,
    `external_id=<event id>` (kept for live-link),
    time/location/subject/body from the suggestion.
  - plus `ApplicationEvent(kind=interview_scheduled, interaction_id=...)`.
  - sets `suggestion.status=confirmed`, `suggestion.interaction_id`.
- `POST /api/calendar/suggestions/{id}/dismiss` → `status=dismissed`,
  idempotent.

Graph events no longer auto-create `needs_review` interviews. The existing
`needs_review` + `InterviewReviewModal` + `review-count` flow remains for the
**email/webhook** ingest path (unchanged).

## Frontend — Suggestions tab

New "Calendar interviews" section on `/suggestions`, rendered alongside the
existing offline-posting suggestions.

```
• Acme · 2026-09-01 10:00–10:45 · Teams
  matched → App #42 (0.9)   [confirm] [reassign ▾] [dismiss]
• Globex · 2026-09-03 14:00
  unmatched                 [pick app ▾ → confirm] [dismiss]
```

- confirm → `POST .../confirm` (with chosen `application_id` when reassigning
  or picking for an unmatched item).
- dismiss → `POST .../dismiss`.
- `useSuggestionsCount` extended to include the pending calendar count so the
  nav badge reflects both suggestion kinds.

## Migration + tests

- **Alembic:** new `calendar_suggestion` table + `calendarsuggestionstatus`
  enum type; nullable FKs to `application` and `interaction`.
- **Tests:**
  - sync state-machine: all five branches (none/pending/confirmed/dismissed/
    `@removed`) including live-link update of a confirmed interview and
    cancellation removal.
  - idempotency: a full re-sync does not resurrect dismissed or confirmed
    events.
  - confirm endpoint: promotes to Interaction + ApplicationEvent, keeps
    `external_id`, sets suggestion status; 400 when no app resolvable.
  - dismiss endpoint: marks dismissed, idempotent.
  - **migration / DB-free enum test:** the integration suite builds schema from
    models, which would mask a missing-enum migration; add a test that exercises
    the enum against the migration (see prior enum-drift lesson).
- **No backfill:** calendar sync has never succeeded for the current user
  (mailbox 404 — see auth note below), so there are zero existing `graph_sync`
  interviews to migrate.

## Out of scope / notes

- The MS Graph mailbox auth issue (personal vs org identity, `MS_TENANT_ID`
  should be `consumers`/`common`, app-registration account type) is a separate
  operational fix, tracked elsewhere. This spec assumes sync can eventually
  pull events; it does not depend on the auth fix to be implemented and tested
  (tests drive the sync with injected event dicts).
- Confirmed/dismissed history view: deferred (YAGNI).
