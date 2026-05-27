# Mini-CRM Design

**Date**: 2026-05-27
**Status**: Approved
**Scope**: Turn the application detail page into a tiny CRM for a single user. Track every touchpoint per application across channels, structure discard reasons for stats, surface a unified timeline, and add a funnel/response-rate page.

## Goals

- Log every interaction (mail, LinkedIn, phone, portal, ...) per application with direction and timestamp.
- Replace the freetext "notes for responses" workaround with structured, queryable data.
- Make discard reasons dynamic (user-editable labels) yet stable for stats (immutable slugs).
- Auto-prompt to discard when an incoming interaction is tagged as a rejection.
- Provide a unified activity timeline per application (status changes + interactions + interviews).
- Provide a funnel / response-rate stats page.

## Non-Goals (deferred)

- Contacts/people table (recruiter/hiring-manager records reused across apps).
- Follow-up reminders / snooze with Telegram pings.
- MS Graph inbox auto-sync (use existing `ms_refresh_token_encrypted`).
- Per-channel reusable templates.
- Telegram bot quick-log commands.

## Data Model

### New table: `interaction`

| column                | type                  | notes                                                                                  |
|-----------------------|-----------------------|----------------------------------------------------------------------------------------|
| id                    | uuid pk               |                                                                                        |
| application_id        | fk application(id)    | indexed                                                                                |
| occurred_at           | datetime, not null    | when the message happened; user-editable; default `now()`                              |
| direction             | enum(out, in)         |                                                                                        |
| channel               | enum                  | `mail, linkedin, phone, portal, xing, other`                                           |
| subject               | text, nullable        | mail subject / call topic                                                              |
| body                  | text, nullable        | message body or call notes                                                             |
| contact_name          | text, nullable        | freetext (Contacts table = future)                                                     |
| contact_handle        | text, nullable        | email / LinkedIn URL / phone                                                           |
| sentiment             | enum, nullable        | `positive, neutral, negative, rejection`; only meaningful for direction=in             |
| created_from          | enum                  | `manual, inquiry_migration, graph_sync` (future); default `manual`                     |
| created_at            | datetime              | `server_default now()`                                                                 |
| updated_at            | datetime              | `server_default now(), onupdate now()`                                                 |

Indexes: `application_id`, `(application_id, occurred_at DESC)`.

### New table: `discard_reason`

| column      | type                  | notes                                                          |
|-------------|-----------------------|----------------------------------------------------------------|
| id          | uuid pk               |                                                                |
| user_id     | fk user(id)           |                                                                |
| slug        | string(64), not null  | stable identifier for stats; immutable after create            |
| label       | string(200), not null | display name; user-editable                                    |
| is_system   | bool, default false   | seeded vs user-created                                         |
| is_archived | bool, default false   | hide from picker, keep historical references intact            |
| sort_order  | int, default 0        |                                                                |
| created_at  | datetime              |                                                                |

Unique constraint: `(user_id, slug)`.

**Seeded slugs (per user, on first login or migration)**:
`no_reply, rejected, withdrew_self, location, salary, tech_mismatch, seniority, posting_offline, duplicate, other`.

### New table: `application_event`

| column          | type             | notes                                                  |
|-----------------|------------------|--------------------------------------------------------|
| id              | uuid pk          |                                                        |
| application_id  | fk application   | indexed                                                |
| kind            | enum             | `status_change, created, inquiry_generated, interview_scheduled, ...` (extensible) |
| from_value      | string, nullable | e.g. previous status                                   |
| to_value        | string, nullable | e.g. new status                                        |
| meta            | json, nullable   | arbitrary extras                                       |
| occurred_at     | datetime         | indexed desc                                           |

Written transactionally via SQLAlchemy `before_flush` session event for any tracked attribute change. Initial scope: status changes only; other kinds added as call sites are wired.

### Changes to `application`

- ADD `discard_reason_id` (fk `discard_reason.id`, nullable)
- ADD `discard_interaction_id` (fk `interaction.id`, nullable) — the rejection mail/message that triggered the discard
- RENAME `discard_reason` (text) → `discard_note` (text) — freetext detail field kept alongside structured reason
- DROP `inquiry_subject`, `inquiry_body`, `inquiry_sent_at` (backfilled into `interaction`)

`notes` (long-form per-app freetext) is kept as-is.

## API Surface

All under existing session auth (`get_current_user`). User-scoping enforced via app/reason ownership checks.

### Interactions — `backend/app/api/interactions.py` (new router)

```
GET    /api/applications/{id}/interactions          → list, ordered occurred_at desc
POST   /api/applications/{id}/interactions          → create
PATCH  /api/interactions/{interaction_id}           → edit any field except application_id/created_from
DELETE /api/interactions/{interaction_id}           → hard delete (solo user, no audit need)
```

POST/PATCH request body:
```json
{
  "occurred_at": "2026-05-27T10:30:00Z",
  "direction": "out",
  "channel": "linkedin",
  "subject": null,
  "body": "Pinged recruiter about timeline",
  "contact_name": "Anna Müller",
  "contact_handle": "linkedin.com/in/...",
  "sentiment": null
}
```

POST response when `sentiment=rejection`:
```json
{
  "interaction": { ... },
  "suggest_discard": { "reason_slug": "rejected", "interaction_id": "..." }
}
```
No server-side auto-mutation; the frontend renders the prompt and the user confirms.

### Discard reasons — `backend/app/api/discard_reasons.py` (new router)

```
GET    /api/discard-reasons                         → list (excludes archived; ?include_archived=1)
POST   /api/discard-reasons                         → {label, slug?} — slug auto-derived (snake_case) if absent
PATCH  /api/discard-reasons/{id}                    → {label?, is_archived?, sort_order?} (slug immutable)
DELETE /api/discard-reasons/{id}                    → 409 if referenced by any application; suggest archive
```

Auto-slug rule: lowercase, ASCII-only, non-alphanumerics → `_`, collapse repeated `_`, trim, truncate to 64. On collision append `_2`, `_3`, ...

### Application discard — extend existing `PATCH /api/applications/{id}`

Accepts new fields:
- `discard_reason_id` (uuid, optional)
- `discard_interaction_id` (uuid, optional)
- `discard_note` (text, optional) — was `discard_reason`

When `status` transitions to `discarded`, none of these are required; UI nudges to provide them.

### Timeline — `GET /api/applications/{id}/timeline`

Server-side merge of: `application_event` rows + `interaction` rows + `interview` rows. Returns one unified list sorted by `occurred_at` desc:

```json
[
  { "kind": "interaction", "at": "...", "data": { ...interaction fields... } },
  { "kind": "interview",   "at": "...", "data": { ...interview fields... } },
  { "kind": "event",       "at": "...", "data": { "kind": "status_change", "from": "draft", "to": "applied" } }
]
```

### Stats — `GET /api/stats/funnel?from=&to=`

Single JSON blob, computed by `backend/app/services/stats.py` with raw SQL aggregations. Recomputed per request (solo user, <1k apps).

```json
{
  "totals": { "applications": 87, "applied": 62, "discarded": 41, "active": 28 },
  "funnel": [
    { "stage": "created",   "count": 87 },
    { "stage": "applied",   "count": 62 },
    { "stage": "responded", "count": 24 },
    { "stage": "interview", "count": 9 },
    { "stage": "offer",     "count": 2 },
    { "stage": "accepted",  "count": 1 }
  ],
  "response_rate_by_channel": [
    { "channel": "mail",     "outgoing": 45, "responses": 12, "rate": 0.27 },
    { "channel": "linkedin", "outgoing": 18, "responses": 9,  "rate": 0.50 }
  ],
  "avg_time_to_reply_hours": { "mail": 96.3, "linkedin": 18.1 },
  "discard_breakdown": [
    { "slug": "no_reply", "label": "No reply", "count": 18 },
    { "slug": "rejected", "label": "Rejected", "count": 12 }
  ],
  "weekly_volume": [
    { "week": "2026-W18", "applied": 8, "discarded": 3, "responses": 2 }
  ]
}
```

**Response definitions** (intentionally different):
- `response_rate_by_channel.responses[channel]` = count of applications with ≥1 incoming interaction on that channel whose `occurred_at` is strictly after the earliest outgoing interaction on the same channel for that application. The same-channel + ordering rule prevents cross-channel inflation (e.g. mail-out + linkedin-in doesn't count as a mail response).
- `funnel.stage=responded` = count of applications with ≥1 incoming interaction on any channel, regardless of ordering. Looser by design: the funnel measures "did this app generate any reply?" while channel rates measure per-channel effectiveness.

## Frontend

### `ApplicationDetail.tsx` — restructure into 3 collapsible panels

1. **Job posting** — existing top section, unchanged.
2. **Activity** (new) — replaces the current scattered notes/inquiry sections:
   - Tab header: `Timeline | Interactions | Notes`
   - **Timeline tab** — chronological feed, newest first. Cards per entry with kind-specific icons. Interaction cards inline-editable (pencil icon). `+ Log interaction` button at top opens modal.
   - **Interactions tab** — same data filtered to interactions, table-style for scanning.
   - **Notes tab** — existing `notes` textarea for long-form thoughts; no migration.
3. **Documents & Inquiry** — existing CV/Anschreiben/inquiry generator unchanged in shape. The "Send inquiry" action also creates an outgoing `mail` interaction with the subject/body prefilled from the inquiry draft. The standalone `inquiry_sent_at` toggle is removed.

### Log-interaction modal

```
[ direction: out/in toggle ]   [ channel: dropdown ]
[ occurred_at: datetime picker, default now ]
[ contact_name ]  [ contact_handle ]
[ subject (only when channel=mail) ]
[ body (textarea, markdown) ]
[ sentiment: none/positive/neutral/negative/rejection ]   ← only shown when direction=in
[ Save ] [ Save & discard app ]                           ← second button only shown when sentiment=rejection
```

`Save & discard app` opens a follow-up sheet: discard-reason picker (with seeded reasons + inline "Add new..."), optional `discard_note` freetext, `discard_interaction_id` prefilled to the just-created interaction.

### Discard reason picker (reusable component)

- Combobox: type-to-search, ordered by `sort_order`.
- `+ Add new reason` inline → small modal asks for label, auto-derives slug, POSTs, selects the new reason.
- Archived reasons hidden by default; toggle to show.

### `SettingsDiscardReasons.tsx` (new settings page)

- Table: drag-handle | label (inline-editable) | slug (readonly) | archive toggle | usage count.
- Add-new-reason button.
- Delete enabled only when usage count = 0; otherwise disabled with "archive instead" tooltip.

### `ApplicationsList.tsx` — minor additions

- New filter chip: filter by discard reason (only enabled when status filter = discarded).
- Discarded status badge shows reason label on hover.

### Stats page — `frontend/src/pages/Stats.tsx` (new route `/stats`)

Charts via **recharts** (new dependency).

- Top row: 4 KPI cards — active count, overall response rate, avg time-to-reply, interview conversion %.
- Funnel: horizontal `BarChart` with counts and drop-off % annotations.
- Channel comparison: small table (recharts overkill for 2–5 rows).
- Discard breakdown: horizontal `BarChart` sorted desc; click row → navigates to ApplicationsList filtered to those discards.
- Weekly volume: `LineChart` showing applied / discarded / responses series.

## Migration & Rollout

### Single alembic revision

1. Create `interaction` table (with indexes).
2. Create `discard_reason` table (with unique `(user_id, slug)`).
3. Create `application_event` table (with indexes).
4. Add columns to `application`: `discard_reason_id`, `discard_interaction_id`.
5. Rename `application.discard_reason` → `application.discard_note`.
6. Data backfill (raw SQL via `op.execute`):
   - For each `user`: insert the 10 system discard reasons (slugs + default labels, `is_system=true`).
   - For each `application` where `inquiry_sent_at IS NOT NULL`: insert one `interaction` row (direction=out, channel=mail, occurred_at=`inquiry_sent_at`, subject=`inquiry_subject`, body=`inquiry_body`, created_from=`inquiry_migration`).
   - For each `application` where status=`discarded` AND `discard_note` matches a seeded label case-insensitively: set `discard_reason_id` to the matching reason. Unmatched OR NULL `discard_note`: leave `discard_reason_id` NULL; any existing text in `discard_note` is preserved.
   - For each `application`: insert one `application_event` row (kind=`created`, occurred_at=`application.created_at`).
7. Drop columns: `inquiry_subject`, `inquiry_body`, `inquiry_sent_at`.
8. Downgrade: drop new tables, drop new columns, restore old columns as nullable (backfill data loss for inquiry fields is accepted; documented in revision docstring).

**Pre-deploy**: take a manual DB backup. The migration is destructive (drops 3 columns).

### SQLAlchemy event hook for status changes

In a new module `backend/app/db/events.py`, register a `before_flush` session event that:
- Iterates `session.dirty` for `Application` instances.
- Detects changed `status` via `sqlalchemy.inspect(obj).attrs.status.history`.
- Appends one `ApplicationEvent(kind='status_change', from_value=old, to_value=new, occurred_at=now())` to the session.

No write on unchanged status. Wired at app startup in `app/main.py`.

### No feature flag

Solo user. Hard switch at deploy.

## Testing

### Backend (pytest)

- `test_interactions_api.py` — CRUD, auth boundaries (other user 404), `suggest_discard` payload appears only when `sentiment=rejection`.
- `test_discard_reasons_api.py` — auto-slug derivation, archive vs delete, 409 on delete-when-referenced, seed-on-new-user.
- `test_application_events.py` — event row written on status change, none written when status unchanged, backfill produces one `created` row per app.
- `test_stats_funnel.py` — cross-channel response is NOT counted (mail-out + linkedin-in → 0 for both channels), discard breakdown groups by slug, weekly volume buckets correctly across week boundaries.
- `test_migration.py` — apply migration to a temp DB pre-seeded with inquiry-sent apps and discarded apps; assert backfill produces expected rows.

### Frontend

- Playwright spec `interaction-log.spec.ts`: log-modal → save → row appears in timeline → tag as rejection on a new incoming interaction → discard prompt → confirm → app status = discarded with reason+link.

## File Inventory

**New backend files**:
- `backend/app/api/interactions.py`
- `backend/app/api/discard_reasons.py`
- `backend/app/services/stats.py`
- `backend/app/db/events.py`
- `backend/alembic/versions/<hash>_mini_crm.py`
- `backend/tests/test_interactions_api.py`
- `backend/tests/test_discard_reasons_api.py`
- `backend/tests/test_application_events.py`
- `backend/tests/test_stats_funnel.py`
- `backend/tests/test_migration.py` (or extend existing migration test)

**Modified backend files**:
- `backend/app/db/models.py` — new models, FK additions, column rename
- `backend/app/api/applications.py` — accept new discard fields, add timeline endpoint
- `backend/app/main.py` — register new routers + event hook

**New frontend files**:
- `frontend/src/api/interactions.ts`
- `frontend/src/api/discardReasons.ts`
- `frontend/src/api/stats.ts`
- `frontend/src/pages/Stats.tsx`
- `frontend/src/pages/SettingsDiscardReasons.tsx`
- `frontend/src/components/InteractionLogModal.tsx`
- `frontend/src/components/DiscardReasonPicker.tsx`
- `frontend/src/components/ActivityTimeline.tsx`
- `frontend/e2e/interaction-log.spec.ts`

**Modified frontend files**:
- `frontend/src/pages/ApplicationDetail.tsx` — restructure into 3 panels, integrate timeline
- `frontend/src/pages/ApplicationsList.tsx` — discard-reason filter chip
- `frontend/src/api/applications.ts` — extend discard payload
- `frontend/package.json` — add `recharts`
- routing config — `/stats`, `/settings/discard-reasons`

## Open Questions

None at design time. Future iterations track: contacts table, reminders, MS Graph sync, templates, Telegram quick-log.
