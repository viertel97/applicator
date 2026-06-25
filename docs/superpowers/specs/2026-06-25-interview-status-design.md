# Interview status

**Date:** 2026-06-25
**Status:** Approved (design)

## Problem

The user wants to track job interviews: switch an application's `status` to an
interview state, record when the interview will happen / happened, and add
details for retrospective review (no preparation features).

## Key context

Interview *data* is already modeled in this codebase. A dedicated `Interview`
entity once existed but was deliberately folded into the interaction log
(commit `80eff9b`). Interviews are now `Interaction` rows with
`channel = interview`:

- `occurred_at` — a `datetime` set via a `datetime-local` picker, so it accepts
  past **or** future dates.
- `subject` — repurposed in the UI as "Round / type (e.g. Technical screen)".
- `body` — "Comment (how it went, notes)".
- `sentiment` — outcome (positive / neutral / negative / rejection), shown when
  direction is incoming.

`InteractionLogModal` already special-cases the `interview` channel with those
placeholders. The stats funnel already has an `interview` stage computed from
interactions with `channel = interview` (`stats.py:160`).

**The only genuine gap is a status value.** `ApplicationStatus` has no
`interview` member, so the user cannot switch an application into an interview
state from the status dropdown.

## Approach

Add an `interview` `ApplicationStatus` value and reuse the existing interaction
log for the date and details. No new tables, no new entity, no preparation
features. This matches the prior decision to keep interviews in the interaction
log.

## Design

### 1. Data model — no new schema

- Add `interview = "interview"` to `ApplicationStatus` (`app/db/models.py:29`).
- Interview date + details continue to live in `Interaction(channel=interview)`.
- Migration: `ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'interview'`,
  chained onto current head `c2f4a6b8d0e1`. Identical pattern to the `need_call`
  (`f1a2b3c4d5e6`) and `apply_direct` (`a2b3c4d5e6f7`) migrations. `downgrade` is
  a no-op (Postgres cannot drop an enum value).

### 2. Backend status placement

- Add `ApplicationStatus.interview` to `APPLIED_SET` (`app/services/stats.py:20`).
  An application at interview has necessarily been applied, so it should count in
  the funnel "applied" stage, weekly volume, and `totals.applied`.
- `CLOSED_STATUSES` (`app/api/applications.py:36`) is left unchanged. `interview`
  is an open/active status, so it keeps participating in the "awaiting response"
  computation and is counted in `totals.active` (active = status not in
  {discarded, rejected, withdrawn, accepted}).
- Funnel `interview` stage (`app/services/stats.py:160`): currently counts apps
  with an `interview` interaction. Extend it to also include apps with
  `status == interview`, so an app marked interview without a logged interaction
  still appears in the funnel. Union of the two id sets.
- `update_status` (`app/api/applications.py:298`) needs no new branch; the generic
  path already clears discard fields for non-discarded statuses.
- `check_postings.py:118` (skips withdrawn/rejected from posting checks) is not
  affected.

### 3. Frontend status plumbing

Add `interview` everywhere the status set is enumerated:

- `src/api/applications.ts` — `AppStatus` union.
- `src/pages/ApplicationsList.tsx` — `ALL_STATUSES`, `STATUS_LABEL` ("Interview").
  Not added to `HIDDEN_BY_DEFAULT` (interview is active, shown by default).
- `src/pages/ApplicationDetail.tsx` — `STATUSES`.
- `src/components/StatusBadge.tsx` — `STATUS_CLASS` color (indigo, distinct from
  the existing palette).
- `src/lib/filterDiagnostics.ts` — `ALL_STATUSES`, plus its test array in
  `src/lib/filterDiagnostics.test.ts`.

### 4. UX coupling

In the `ApplicationDetail` status dropdown `onChange` (`ApplicationDetail.tsx:146`):
when the selected status is `interview`, set the status immediately (existing
mutation) **and** open `InteractionLogModal` prefilled with
`{ channel: "interview", direction: "in" }`. Direction `in` makes the
outcome/sentiment field visible for "how it went".

Cancelling the modal leaves the status at `interview` — logging the date and
details is optional and retrospective. This mirrors the existing discard
side-flow, where choosing a status can trigger an auxiliary capture step rather
than blocking the status change.

`InteractionLogModal` is already imported and used on this page, so this is wiring
state (an "open with prefill" trigger), not a new component.

### 5. Testing

- **Migration / DB-free enum test:** assert `interview` is a member of
  `ApplicationStatus` and that the migration adds the value. The integration
  suite builds its schema from the models, not the migrations, so a model-only
  assertion would pass even if the migration were missing — hence an explicit
  migration-aware check.
- **API test:** `PATCH /applications/{id}` with `status=interview` succeeds and the
  application remains open (appears in awaiting/active computations, not in
  `CLOSED_STATUSES`).
- **Stats test:** `interview` is in `APPLIED_SET`; the funnel `interview` stage
  counts an app whose `status == interview` even with no interview interaction,
  and does not double-count one that has both.
- **Frontend:** status lists / label / color include `interview`;
  `filterDiagnostics` test array updated so the exhaustiveness checks stay green.

## Out of scope

- Interview preparation features (agendas, prep notes, reminders).
- A separate interview data entity or dedicated date fields on the application —
  explicitly avoided to honor the fold-into-interaction decision.
- Notifications / scheduling for upcoming interviews.
