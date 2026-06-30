# Detailed application statistics — design

Date: 2026-06-30

## Goal

Extend the Stats page with deeper analytics. Primary ask: how many declines and when.
Plus outcome breakdown, funnel conversion %, velocity, ghost rate, interview win rate.

## Decline semantics (decided)

Three negative outcomes tracked **separately** everywhere — never merged into one bucket:

- `rejected` — company said no
- `withdrawn` — user pulled out
- `discarded` — user trashed it (already has reason breakdown in `/api/stats/funnel`)

## Approach

Transition-analysis service over the existing `ApplicationEvent` log. No schema change,
no backfill. The event listener in `backend/app/db/events.py` already writes a
`status_change` row (`from_value`, `to_value`, `occurred_at`) on every status update, so
"when did declines happen" and time-between-stages are answerable from current data.

Rejected alternatives:
- Cramming all metrics into existing `/api/stats/funnel` — `stats.py` already computes 6
  metrics in one function; doubling it makes it unmaintainable.
- Pre-aggregated stats table — premature for a personal tracker; adds write-path
  complexity + a backfill migration for no real benefit.

## Data caveat

The event listener fires only on status **updates**, not initial insert. Apps created
already in `applied` have no `status_change` event. Like existing `weekly_volume`, new
metrics fall back to `Application.created_at` when no event exists. Very old apps may have
thinner transition data — acceptable.

## Backend

New module `backend/app/services/stats_detail.py` with focused pure functions (one per
metric group), exposed via one new endpoint:

`GET /api/stats/detail` — optional `from` / `to` (filter on `created_at`, matching
`/funnel`), `ghost_days` (default 21).

Response shape:

```
outcomes        { active, accepted, offer, rejected, withdrawn, discarded, total }
declines_weekly [{ week, rejected, withdrawn, discarded }]      # ISO-week buckets
decline_timeline[{ app_id, company, role, kind, occurred_at, stage_reached }]  # recent ~25
rejection_stage [{ stage, count }]                              # furthest stage before decline
velocity        { applied_to_response_h, response_to_interview_h,
                  interview_to_offer_h, offer_to_decision_h }   # mean + median each
ghost           { count, threshold_days }
interview       { reached, won, lost, win_rate }
```

`/api/stats/funnel` is left untouched. Conversion % is derived frontend-side from the
funnel counts already returned.

## Metric definitions

1. **Outcomes split** — counts by current status among non-deleted apps. Donut/stacked bar.
2. **Declines weekly (3 series)** — bucket `ApplicationEvent` `status_change` rows by
   `occurred_at` ISO week, grouped by `to_value` in {rejected, withdrawn, discarded}.
   Fallback `created_at` if no event. Stacked chart.
3. **Decline timeline** — recent ~25 decline events: when, which app (company/role), kind,
   and furthest stage reached before the decline. List.
4. **Rejection-stage** — per declined app, furthest funnel stage reached before the decline
   (applied / responded / interview / offer), by walking that app's event sequence. Bar —
   shows *where* applications are lost.
5. **Conversion %** — applied→responded→interview→offer→accepted rates. Overlay % labels on
   the existing funnel bars. Frontend-only derivation.
6. **Velocity** — mean + median hours between milestones (applied→first response→interview
   →offer→decision), from `ApplicationEvent` plus the first incoming `Interaction`. KPI tiles.
7. **Ghost rate** — apps in the applied-set with zero incoming interaction whose `applied`
   event is ≥ `ghost_days` old. Count tile.
8. **Interview win rate** — apps that reached interview; won = subsequently offer/accepted,
   lost = subsequently rejected. `win_rate = won / (won + lost)`. Tile.

Cadence trend (apps/week last-4 vs prior-4) derived frontend-side from existing
`weekly_volume` — minor indicator, no backend work.

## Frontend

Extend `frontend/src/pages/Stats.tsx`. Existing content unchanged at top. Three new
sections below (layout approved via mockup):

- **Outcomes & conversion** — donut (1) + funnel bars with conversion % labels (5)
- **Declines** — weekly stacked chart (2) + rejection-stage bar (4) + recent decline list (3)
- **Velocity & health** — tiles for time-in-stage (6), ghost rate (7), interview win rate (8)

New API wrapper `frontend/src/api/statsDetail.ts`, typed to the response above.

## Testing

Backend unit tests per pure function with seeded `ApplicationEvent` rows, covering empty /
single-app / missing-event (created-already-applied) cases. Given the testcontainers
enum-drift note, include a DB-free or migration-level check if any enum is touched (none
expected here).
