# Webhook Request History — Design

**Date:** 2026-08-14
**Status:** Approved (design)

## Goal

When the app receives a request on the inbound-email webhook, persist a full
record of that request so the user can later inspect **what** was received —
raw body, headers, source IP, and the outcome of processing. Surface the
history as a viewable list + detail page in the app.

## Motivation

The `POST /api/webhooks/inbound-email/{ingest_token}` endpoint currently
processes inbound email and either creates a needs-review interview or returns
an "ignored"/error response — but keeps no trace of the request. Debugging why
an email did or did not produce an interview is impossible after the fact. A
persisted audit trail fixes this.

## Scope

- Record **every** inbound request, including failures: bad token (404),
  payload too large (413), unparseable body, no matching application, and
  successful creation.
- Persist: raw body, request headers, source IP, processing outcome
  (status + reason), and matched application id when applicable.
- Provide read API + frontend page to browse and inspect received requests.

Out of scope: retention/pruning policy, replay/re-process, multi-webhook
generalization (only one webhook exists today).

## Backend

### Model — `WebhookRequest` (table `webhook_request`)

| field | type | notes |
|---|---|---|
| `id` | UUID, pk | default uuid4 |
| `user_id` | UUID FK `user.id`, nullable | null when token invalid |
| `ingest_token` | String(64) | token from URL path; stored even if invalid |
| `source_ip` | String(64), nullable | client IP |
| `headers` | JSON, nullable | request headers as a dict |
| `raw_body` | Text, nullable | raw request body (already capped at 512 KB) |
| `status` | String(32) | `created` / `ignored` / `rejected` / `not_found` |
| `reason` | String(200), nullable | detail, e.g. `no match`, `payload too large` |
| `matched_application_id` | UUID FK `application.id`, nullable | set on match |
| `created_at` | DateTime | `server_default=func.now()` |

**No DB enum** for `status`/`reason` — plain strings, to avoid enum-drift
migration friction. Values are a documented convention, validated by tests.

Status → reason mapping:
- `not_found` — bad/unknown ingest token (was HTTP 404)
- `rejected` — `payload too large` (was HTTP 413)
- `ignored` — `unparseable` | `llm unavailable` | `extraction failed` |
  `no applications` | `no match`
- `created` — interview interaction created (reason null)

### Endpoint refactor — `inbound_email`

Wrap the handler body so **exactly one** `WebhookRequest` row is written on
every code path via a `try/finally`:

- Capture `source_ip` (from `request.client.host`) and `headers`
  (`dict(request.headers)`) up front.
- Maintain a mutable record holder (status, reason, matched_application_id,
  user_id, raw_body) updated as the flow progresses.
- In `finally`: persist the `WebhookRequest` row and commit. On the
  success path this commits together with the interaction + event.
- HTTPExceptions (404 bad token, 413 too large) are caught, recorded into the
  holder, then re-raised after the row is written — HTTP status codes and
  response bodies are unchanged from today.

`raw_body`: recorded for every path where the body was read. For the 413
content-length pre-check (body not read), `raw_body` is null and reason is
`payload too large`.

Headers are stored verbatim as received. (No secret redaction — the ingest
token is already in the URL/path, not headers; revisit if auth headers are
ever added.)

### Read API (existing user auth dependency)

- `GET /api/webhooks/requests` — list current user's rows, newest first.
  Returns summary fields: `id`, `created_at`, `status`, `reason`,
  `source_ip`, `matched_application_id`, plus derived `from`/`subject` parsed
  from the stored body when available (best-effort, for the table).
- `GET /api/webhooks/requests/{id}` — full detail: headers + raw_body +
  all summary fields. 404 if not owned by the current user.

Invalid-token rows (`user_id` null) are stored for audit but **not** returned
by the per-user list/detail endpoints.

## Frontend

- `src/api/webhooks.ts` — `listWebhookRequests()`, `getWebhookRequest(id)`,
  mirroring existing api modules (e.g. `calendar.ts`).
- `src/pages/SettingsWebhooks.tsx` — table of received requests
  (time, from, subject, status badge); clicking a row opens a detail modal
  showing headers and raw body (pretty-printed if JSON).
- Route registered in `src/App.tsx` under the Settings section; nav entry in
  `src/components/nav/navItems.ts`.

## Tests

- **Migration test** — `webhook_request` table created with expected columns
  (follows existing migration-test pattern; covers the DB-free/migration gap
  noted for schema changes).
- **Integration** (`test_webhook_api.py`) — a row is written on:
  - `created` (successful match),
  - `ignored` + `no match`,
  - `not_found` (bad token, `user_id` null),
  and the per-user list endpoint returns owned rows only.
- **Model test** — `WebhookRequest` construction / defaults.

## Files touched

- `backend/app/db/models.py` — new model
- `backend/alembic/versions/<rev>_webhook_request.py` — new migration
- `backend/app/api/webhooks.py` — endpoint refactor + read endpoints (+ schemas)
- `backend/tests/...` — migration/integration/model tests
- `frontend/src/api/webhooks.ts` — new
- `frontend/src/pages/SettingsWebhooks.tsx` — new
- `frontend/src/App.tsx`, `frontend/src/components/nav/navItems.ts` — wiring
