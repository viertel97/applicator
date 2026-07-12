# Multiple Interview Tracking — Design

**Date:** 2026-07-12
**Status:** Approved for planning

## Problem

The `interview` application status is flat. It tells you "in interviewing mode" but not
*where* you are — it makes a difference whether you are before the first interview or
after the second. Today interviews are already logged as `Interaction` rows
(`channel='interview'`, `occurred_at`, free-text `subject`/`body`), but there is no
structured interview stage, no round awareness, and no at-a-glance display of round
position.

## Goal

1. **Primary:** Show *which round* you are in, at a glance, on both the application list
   and detail (without opening the app).
2. Let the user pick a structured interview **stage** (phone / technical / onsite / …)
   when logging an interview.
3. Support the real workflow: log an interview **when the invitation arrives** (future
   date) and **optionally** add notes after it happens.

## Non-Goals

- No new `ApplicationStatus` enum values. Status stays flat `interview`; round info is
  **derived**, not stored as status.
- No dedicated `interview` table (the old one was folded into `Interaction` in migration
  `d5e6f7a8b9c0` and stays that way).
- No mandatory outcome field. "How it went" is optional free text; existing `sentiment`
  covers gut outcome if the user wants it.
- No reminders/notifications for upcoming interviews (out of scope; timing is display-only).

## Approach

Interviews are already `Interaction` rows and `occurred_at` already accepts future dates,
so the model is ~80% there. We add one structured field, derive round/timing on read, and
surface it in the UI. Round is **auto-derived** (no manual counter).

---

## Section 1 — Data Model (backend)

Add ONE nullable enum column to `Interaction` (`backend/app/db/models.py`):

- `interview_stage`: enum `InterviewStage` = `phone_screen`, `technical`, `onsite`, `hr`,
  `final`, `other`. Nullable. Only meaningful when `channel='interview'`.

Reuse existing columns:
- `occurred_at` — interview date/time. `>= now` ⇒ **upcoming**, `< now` ⇒ **done**.
- `body` — optional "what was asked / how it went".
- `sentiment` — optional gut outcome (already `positive/neutral/negative/rejection`).
- `subject` — stays as an optional free label (unchanged).

**Round** = the 1-based position of an interview among the application's `interview`
interactions ordered by `occurred_at` ascending. Log a 2nd interview ⇒ it is R2. No stored
round number.

**Migration:** one Alembic revision that
1. creates the `interviewstage` Postgres enum type, and
2. adds the nullable `interview_stage` column to `interaction`.

Follow the existing enum convention in the model (`Enum(InterviewStage,
name="interviewstage", values_callable=lambda e: [m.value for m in e])`) so persisted
values match the migration-created type. Per project note, integration tests build the
schema from models — add a DB-free/migration check when touching enums.

## Section 2 — Derived Summary + API

Backend computes a small `interview_summary` object and attaches it to the application
read schema (Pydantic) in **both** the list and detail responses. The list needs it so the
badge renders without fetching each app's timeline.

```
interview_summary: {
  rounds_logged: int,                    # count of channel='interview' interactions
  next: { round: int, stage: str|null, at: datetime } | null,  # earliest upcoming (occurred_at >= now)
  last: { round: int, stage: str|null, at: datetime } | null,  # latest past (occurred_at < now)
} | null   # null when status != 'interview' OR no interviews logged
```

- Computed in the application serializer from the interaction rows (rounds numbered by
  `occurred_at` asc; `next`/`last` split on `now`).
- List endpoint must load interview interactions efficiently (eager-load / aggregate;
  avoid N+1). Detail already loads the timeline.
- `POST`/`PATCH` on interactions accepts the new optional `interview_stage` field.
- No new endpoints.

## Section 3 — Frontend

Files: `frontend/src/components/InteractionLogModal.tsx`, `StatusBadge.tsx`,
`ActivityTimeline.tsx`, `api/applications.ts`, `api/interactions.ts`, list + detail pages.

1. **InteractionLogModal:** when `channel === 'interview'`, show a **stage dropdown**
   (the 6 `InterviewStage` options) alongside the date. `subject` remains an optional free
   label. Persists `interview_stage`.
2. **Badge (list + detail):** when `interview_summary` is present, render an enriched
   label instead of plain `Interview`:
   - upcoming exists → `Interview · R{next.round} {stage} · upcoming {shortDate}`
   - only past → `Interview · R{last.round} {stage} · done`
   - status `interview` but nothing logged → plain `Interview` (fallback)
   Keeps the existing indigo color.
3. **ActivityTimeline:** interview rows show `R{n} · {stage}` (fall back to `subject` when
   no stage) instead of raw subject.
4. Shared helper `formatInterviewSummary(summary)` producing the badge string, used by
   both list and detail so the wording stays identical.
5. Add `InterviewStage` type + `interview_summary` type to the frontend API types.

## Data Flow

1. Invitation arrives → user logs interview: date (future), stage, optional subject.
2. Backend stores `Interaction(channel='interview', occurred_at, interview_stage, …)`.
3. On list/detail read, backend derives `interview_summary` from the app's interview rows.
4. Frontend badge shows round + stage + upcoming/done; timeline lists each round.
5. After the interview, user optionally edits the row to add `body`/`sentiment`.

## Testing

- **Backend unit:** `interview_summary` derivation — 0 interviews (null), 1 upcoming
  (next=R1, last=null), 1 past (last=R1, next=null), mixed past+future (correct round
  numbering and next/last split), status != interview (null).
- **Migration/enum:** DB-free check that `InterviewStage` model enum matches the migration
  (per the enum-drift note).
- **API:** create/patch interaction with `interview_stage`; list response includes
  `interview_summary`; no N+1 on the list query.
- **Frontend:** `formatInterviewSummary` for each branch (upcoming / past-only / empty
  fallback); stage dropdown appears only for interview channel.

## Rollout

Single migration, backward compatible (new column nullable, new summary is additive).
Existing interview interactions get `interview_stage = null` and still produce a valid
summary (round numbers work, stage shows as blank/`other` in display).
