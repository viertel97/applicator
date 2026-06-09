# Stats: fix "applied" count + track inquiry mails separately

**Date:** 2026-06-09
**Status:** Design approved, pending spec review

## Problem

The Stats "Weekly volume" chart reports wrong numbers. For 2026-W21 it showed
`applied: 31, discarded: 10, responses: 1` — but the user submitted zero real
applications that week.

Root cause is in `backend/app/services/stats.py` (`funnel` endpoint), weekly
volume block (lines ~168-183):

```python
for a in apps:
    wk = a.created_at.strftime("%G-W%V")
    if a.status != ApplicationStatus.draft:      # bug 1
        weekly[wk]["applied"] += 1
    if a.status == ApplicationStatus.discarded:
        weekly[wk]["discarded"] += 1
```

1. **"applied" = "not draft".** Counts every app past `draft`. But
   `need_call`, `apply_direct`, and `discarded` are NOT submitted applications.
   `need_call` / `apply_direct` are pre-apply states; `discarded` is thrown away.
2. **Bucketed by `created_at`.** Shows the app's *creation* week, not the week it
   became applied. `responses` buckets by interaction `occurred_at` (real event
   time) — mismatched semantics across series.
3. **Discarded double-counts.** Conditions aren't mutually exclusive, so the 10
   discarded also sit inside the 31 "applied".

The same "applied = not draft" definition also lives in `totals["applied"]`
(line ~187) and the funnel "applied" stage (line ~103), which feed the page's
response-rate and interview-conversion KPIs — so those are wrong too.

Separately: sending an inquiry ("question") mail is a distinct process step the
user wants tracked on its own, not folded into "applied". Today
`mark_inquiry_sent` (`backend/app/api/applications.py:683`) only writes an
outgoing `Interaction` with `created_from=manual` — indistinguishable from any
other logged outgoing mail.

## Key constraint

The `status_change` event recorder (`backend/app/db/events.py`, `before_flush`
listener) only landed **2026-05-27** (commit `854b2dd`). Apps that transitioned
in W20/W21 (~May 11-24) have **no** status-change events. A purely event-based
"applied" count would show empty for exactly the weeks under review.

## Decisions

- **Applied definition: hybrid.** Use the real `status_change` → `applied` event
  week when present; fall back to current-status membership (bucketed by
  `created_at`) for older apps with no events. (User-selected.)
- **Inquiry display: 4th line** on the existing Weekly volume chart, alongside
  applied / discarded / responses. (User-selected.)

## Design

### Shared definition

```python
APPLIED_SET = {
    ApplicationStatus.applied,
    ApplicationStatus.offer,
    ApplicationStatus.rejected,
    ApplicationStatus.accepted,
    ApplicationStatus.withdrawn,
}
```

These statuses mean the application was actually submitted. `draft`,
`need_call`, `apply_direct`, `discarded` are excluded.

### 1. Weekly volume — extract a pure helper

Pull the weekly computation out of the `funnel` endpoint into a testable pure
function in `stats.py`:

```python
def _weekly_volume(
    apps: list[Application],
    status_events: list[ApplicationEvent],   # kind == status_change
    in_interactions: list[Interaction],      # direction == in
    inquiry_interactions: list[Interaction], # created_from == inquiry_sent
) -> list[WeeklyVolume]:
    ...
```

The endpoint gathers the inputs and calls the helper.

**applied (hybrid), per app:**
- earliest `status_change` event with `to_value == "applied"` → bucket that
  event's `occurred_at` week.
- else if `app.status in APPLIED_SET` → bucket `created_at` week.
- else → not counted.

**discarded (hybrid), per app:**
- earliest `status_change` event with `to_value == "discarded"` → bucket that
  event's `occurred_at` week.
- else if `app.status == discarded` → bucket `created_at` week.
- else → not counted.

applied and discarded are independent series. An app that was applied then later
discarded legitimately appears in both, in its respective event weeks. No
double-count *within* a series (each app contributes at most once per series:
event-week XOR created-week).

**responses:** unchanged — incoming interactions bucketed by `occurred_at`.

**inquiries (new):** outgoing interactions with `created_from == inquiry_sent`,
bucketed by `occurred_at` week.

Week key stays ISO: `dt.strftime("%G-W%V")`.

### 2. Data fetch in `funnel`

Add a query for status-change events for the in-scope apps:

```python
status_events = (
    db.query(ApplicationEvent)
      .filter(ApplicationEvent.application_id.in_(aids),
              ApplicationEvent.kind == ApplicationEventKind.status_change,
              ApplicationEvent.to_value.in_(("applied", "discarded")))
      .all() if aids else []
)
```

Inquiry interactions can be filtered from a query on the in-scope apps with
`direction == out` and `created_from == inquiry_sent` (or reuse `out_rows`
already fetched for channel rates and filter in Python).

### 3. Schema

`WeeklyVolume` gains `inquiries: int`. The weekly `defaultdict` factory adds
`"inquiries": 0`.

### 4. Totals + funnel consistency

Re-point to `APPLIED_SET` (point-in-time, status-only — no events needed):
- `totals["applied"]` = `sum(1 for a in apps if a.status in APPLIED_SET)`
- funnel "applied" stage count = same.

This auto-corrects the Stats.tsx response-rate and interview-conversion
denominators, which read `totals.applied`.

### 5. Inquiry marker

- Add enum member `InteractionCreatedFrom.inquiry_sent = "inquiry_sent"` in
  `backend/app/db/models.py`.
- New **single-purpose** alembic migration adding the Postgres enum value,
  mirroring `e1f2a3b4c5d6_interaction_created_from_eml_import.py`:
  ```python
  op.execute(
      "ALTER TYPE interactioncreatedfrom ADD VALUE IF NOT EXISTS 'inquiry_sent'"
  )
  ```
  `down_revision = "f2a3b4c5d6e7"` (current head). Must not be combined with code
  that consumes the value in the same transaction (Postgres requires the
  ADD VALUE to commit first).
- `mark_inquiry_sent` (`applications.py:709`) sets
  `created_from=InteractionCreatedFrom.inquiry_sent` instead of `manual`.

### 6. Frontend

`frontend/src/pages/Stats.tsx` weekly chart: add a 4th line.

```tsx
<Line type="monotone" dataKey="inquiries" stroke="#d97706" />
```

Amber `#d97706` — distinct from applied (blue `#2563eb`), discarded
(red `#dc2626`), responses (green `#16a34a`). The `stats` API type for
`WeeklyVolume` gains `inquiries: number`.

## Testing

- **Unit tests for `_weekly_volume`** (pure function, no DB):
  - app with `status_change` → applied event counts in the event's week, not the
    created week.
  - applied-set app with no events (pre-listener) counts in its created week.
  - `need_call` / `apply_direct` / `draft` apps excluded from applied.
  - apply-then-discard (two events) appears in applied week AND discarded week.
  - discarded-only app (current status discarded, no applied event) counts in
    discarded, not applied.
  - inquiry interaction counted in `inquiries` by `occurred_at` week; a plain
    `manual` outgoing mail is not.
- **Migration / enum test.** Per the project's standing lesson, integration test
  schema is built from models and would mask a missing migration. Add a test
  (run against a migrated DB, or a DB-free assertion on the migration) verifying
  `inquiry_sent` is a valid value of the `interactioncreatedfrom` Postgres type.

## Accepted limitations

- Inquiry mails sent before the `inquiry_sent` marker existed can't be
  retro-tagged → historical inquiry counts undercount until enough new ones
  accrue.
- An app applied *before* 2026-05-27 (no event) and later discarded drops out of
  "applied" (current status discarded, no applied event). Rare; accepted.

## Out of scope

- Backfilling historical `status_change` events or an `applied_at` column.
- Any change to how `responses` is computed.
- Distinguishing historical inquiry mails from other logged outgoing mails.
