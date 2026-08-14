# Interview Calendar + Email Ingestion + iCal Export — Design

**Date:** 2026-08-13
**Status:** Approved (design)

## Goal

Give the job-application tracker a calendar centered on interviews, with three
capabilities:

1. **Calendar view** of upcoming interviews (responsive: month grid on desktop,
   agenda list on mobile).
2. **Forward-to-add ingestion**: forward an interview-invite email to a
   dedicated address (via inboxbridge.io), which POSTs a webhook to the backend.
   The backend LLM-parses it, auto-attaches it to the best-guess application,
   and flags it for review.
3. **iCal export**: a per-user secret-token `.ics` feed of *confirmed*
   interviews, subscribable from Google Calendar (auto-refreshed by Google).

## Context / existing building blocks

- Interviews are already modeled as
  `Interaction(channel=interview, interview_stage, occurred_at)` attached to an
  `Application` (`backend/app/db/models.py`). `occurred_at` already accepts
  future timestamps.
- `Interaction.created_from` enum + `InteractionCreatedFrom` already exists.
- `.eml` LLM import path exists (`backend/app/email_ingest/parser.py`,
  `llm_split.py`, `api/interactions.py::import_eml`) — reuse its LLM client and
  module structure for the new extractor.
- Telegram bot (`bot/bot.py`) and a bot-authenticated endpoint pattern
  (`api/bot.py`, `BOT_API_KEY`) exist — a model for token-authenticated inbound
  requests.
- Frontend is React + TS (`frontend/src/`), mobile-heavy (see `open_tasks.txt`),
  with an existing `InteractionLogModal`, `parseCalendarPaste.ts`, and a
  `GlobalTimeline`.

## Decisions (locked during brainstorming)

- Ingestion path: **B — real email forwarding via inboxbridge.io webhook** (no
  IMAP polling).
- Matching: **auto-attach best-guess application, but mark unconfirmed** until
  the user reviews; review lets the user reassign the application.
- Calendar contents: **interviews only** for v1 (deadlines/reminders are later
  follow-ups).
- Layout: **responsive hybrid** — month grid on desktop, agenda list on mobile.
- iCal feed: **confirmed interviews only** (nothing tentative reaches Google
  Calendar).
- Interview fields: **add `location` + `ends_at`** (nullable).

## 1. Data model changes

`Interaction` (new nullable columns + flag):
- `location: str | None` — address or meeting/video link. LLM-filled.
- `ends_at: datetime | None` — end time. Null ⇒ calendar/iCal default to
  `occurred_at + 60 min`.
- `needs_review: bool` — default `false`, server_default `"false"`.
  Webhook-created interviews start `true`.

`InteractionCreatedFrom`: add value `email_webhook`. Persist enum *values* (not
names) to match the existing migration-created Postgres type, consistent with
the current `values_callable` pattern.

`User` (two nullable secret tokens, generated lazily on first use):
- `ingest_token: str | None` — authenticates + identifies the user for the
  inbound-email webhook URL.
- `calendar_token: str | None` — authenticates the anonymous `.ics` feed URL.

Tokens are URL-safe random strings; regenerating a token invalidates the old URL
(useful if a token leaks). One Alembic migration covers all of the above.

## 2. Ingestion: forward → interview

**Endpoint:** `POST /api/webhooks/inbound-email/{ingest_token}`
- Resolve `ingest_token` → `User`; 404/401 on unknown token. No session
  required (inboxbridge/Google cannot send a cookie).
- Payload: sender, subject, text and/or HTML body (exact shape per
  inboxbridge.io — normalize into `from`, `subject`, `body_text`).

**Pipeline:**
1. **LLM extract** interview fields from subject + body:
   `starts_at`, `ends_at`/duration, `location`/link, `interview_stage`,
   interviewer name/handle. New extractor module under `app/email_ingest/`
   (e.g. `interview_extract.py`) reusing the existing LLM client. Deterministic,
   DB-free, unit-testable with a mocked LLM.
2. **Match application** — score candidates by sender-domain and company-name
   similarity against `JobPosting.company` / `Application` for that user; pick
   the top candidate. Matcher is a pure function (inputs: parsed email +
   candidate list) returning `(application_id, score)` — unit-testable without a
   DB.
3. **Create** `Interaction`:
   - `channel = interview`, `needs_review = true`,
     `created_from = email_webhook`.
   - `application_id` = best-guess match.
   - `occurred_at`, `ends_at`, `location`, `interview_stage`, `contact_name`,
     `contact_handle` from extraction.
   - `subject` = email subject; `body` = original email text (audit trail).
   - Emit an `ApplicationEvent(kind=interview_scheduled)` (existing enum value).

Edge cases: no confident match still attaches to the best candidate but stays
`needs_review` (user can reassign); if there are zero applications, respond 202
and log — do not create an orphan (the model requires `application_id`).

## 3. Review / confirm flow

- Interviews with `needs_review = true` render with a "Needs review" badge on the
  calendar and contribute to a small review-count indicator (mirrors the
  existing suggestions-count hook pattern).
- A confirm dialog (reusing `InteractionLogModal` patterns) lets the user edit
  `starts_at`/`ends_at`/`location`/`interview_stage` **and reassign the
  application** if the guess was wrong.
- Confirming sets `needs_review = false`. Only then does the interview enter the
  iCal feed.
- Endpoint: `PATCH /interactions/{iid}` already exists; extend it to accept the
  new fields + `needs_review` and (for reassignment) `application_id`.

## 4. Calendar view (responsive hybrid)

**Backend:** `GET /api/calendar/interviews?from=&to=` (session-authed) → list of
interviews across all of the user's applications:
`{ id, application_id, display_id, company, starts_at, ends_at, location,
interview_stage, needs_review }`. `company` resolved from
`JobPosting.company` (fallback: application URL host).

**Frontend:** new "Calendar" route/tab.
- **Desktop (wide):** month grid; each day cell shows interview chips
  (`HH:MM company`), color-hinted by stage.
- **Mobile (narrow):** agenda list grouped by day, upcoming first.
- Responsive switch is CSS/layout-driven (media query / container width) — no
  new heavy calendar dependency; date bucketing is a small pure helper
  (`lib/calendarBuckets.ts`) with unit tests.
- Unconfirmed interviews are visually faded + badged. Tapping an interview opens
  the owning application's detail.

## 5. iCal feed

**Endpoint:** `GET /api/calendar/{calendar_token}.ics` (anonymous, token-authed).
- Includes **confirmed** interviews only: `channel=interview`,
  `needs_review=false`, not soft-deleted, for the token's user.
- One `VEVENT` per interview:
  - `UID` = interaction id (stable across refreshes; edits update in place).
  - `DTSTART` = `occurred_at`; `DTEND` = `ends_at` or `occurred_at + 60 min`.
  - `SUMMARY` = `"{company} · {interview_stage}"`.
  - `LOCATION` = `location`.
  - `DESCRIPTION` = subject/notes + deep link to the application in the app.
  - `STATUS:CONFIRMED`; `DTSTAMP`/`LAST-MODIFIED` from `updated_at`.
- Emit valid `VCALENDAR` with `PRODID`, `VERSION:2.0`, UTC timestamps, and
  RFC5545 line folding/escaping. Prefer a small serializer (hand-built or the
  `icalendar` lib) — decide at implementation time; keep it DB-free/unit-tested.
- User subscribes once in Google Calendar via "From URL"; Google re-fetches on
  its own cadence.

## 6. Security / tokens

- `ingest_token` and `calendar_token` are unguessable, per-user, revocable.
- Webhook endpoint: constant-time token comparison; rate-limit / size-limit the
  payload; ignore/segregate unparseable emails rather than 500-ing.
- iCal endpoint is read-only and exposes only confirmed interview
  summaries/locations for that one user.
- Surface both URLs (and a "regenerate" action) somewhere in settings/UI.

## 7. Testing

- **Unit (DB-free):** LLM interview extractor (mocked LLM), application matcher
  scoring, ICS serialization for a known interview set, calendar date-bucketing
  helper. Aligns with the enum-drift/testcontainers notes: add DB-free +
  migration coverage where enums change.
- **API:** webhook happy-path and bad/unknown token; confirm/reassign via PATCH;
  `.ics` output for a known confirmed set (and exclusion of unconfirmed);
  `/calendar/interviews` range filtering.
- **Frontend:** calendar render (month vs agenda breakpoints), unconfirmed
  styling, date-bucketing unit tests.

## 8. Phasing (independent, shippable increments)

1. **Model + calendar view** — migration (all new columns/flag) + manual-entry
   interviews visible on the responsive calendar. Uses existing manual
   interaction creation. Immediately useful.
2. **iCal feed** — `calendar_token` + `.ics` endpoint; subscribe from Google.
3. **Webhook ingestion + review flow** — `ingest_token` + inbound-email webhook
   + LLM extractor + matcher + review/confirm UI. The "forward and forget" magic.

## Out of scope (v1)

- Deadlines and follow-up reminders on the calendar.
- Application-less standalone calendar events.
- Two-way sync / writing back to Google Calendar (feed is read-only).
- IMAP polling.
