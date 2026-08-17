# Webhook Log: Review & Reject Created Interview — Implementation Plan

**Goal:** On the Webhook log page, show which interview/interaction a webhook created, and let the user reject (hard-delete) that interview.

**Decisions (from user):**
- Reject = hard-delete the created `Interaction` (reuse existing `DELETE /api/interactions/{id}`). The webhook row remains in the log; after deletion it reads as "created → interview removed".
- Existing (pre-change) webhook rows: best-effort match their interaction by heuristic so they also show/reject.

**Architecture:** Add a nullable `created_interaction_id` FK (`ON DELETE SET NULL`) to `webhook_request`, populated on the handler's `created` path. A resolver returns the created interaction for a webhook row: FK if set, else a best-effort match for old rows (application + `created_from=email_webhook` + subject). Detail endpoint returns a `created_interaction` object. Reject is frontend-only: call the existing interaction delete; `ON DELETE SET NULL` unlinks the row.

**Tech:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, Postgres (testcontainers), React + TanStack Query.

Current head before this work: `a4b5c6d7e8f9` (webhook_request table).

---

## Task W1: `created_interaction_id` FK column + migration

**Files:** `backend/app/db/models.py` (WebhookRequest), new migration, `backend/tests/unit/test_webhook_request_model.py` + `test_webhook_request_migration.py` (extend).

- Model: add to `WebhookRequest`:
  ```python
  created_interaction_id: Mapped[uuid.UUID | None] = mapped_column(
      ForeignKey("interaction.id", ondelete="SET NULL"), nullable=True, index=True
  )
  ```
- Migration (down_revision `a4b5c6d7e8f9`): `add_column` + `create_foreign_key(..., ondelete="SET NULL")` + `create_index`; downgrade reverses.
- Tests: model column present + nullable; migration-guard asserts a migration adds `created_interaction_id` with `ondelete`/`SET NULL`.

## Task W2: Handler populates the link on the created path

**Files:** `backend/app/api/webhooks.py`, integration test.

- On the `created` path, after `db.add(it)` add `db.flush()` to assign `it.id`, then `rec["created_interaction_id"] = it.id`. (Add `created_interaction_id` to the `rec` dict defaults as `None`.)
- Integration test: a created webhook writes a row whose `created_interaction_id` equals the created interaction's id.

## Task W3: Resolve helper + detail schema + SET-NULL behavior

**Files:** `backend/app/api/webhooks.py`, integration tests.

- `CreatedInteraction(BaseModel)`: id, application_id, display_id, company, starts_at (UtcDateTime from occurred_at), ends_at (UtcDateTime|None), location (str|None), interview_stage (str|None), needs_review (bool).
- `_resolve_created_interaction(db, user, row) -> CreatedInteraction | None`:
  - If `row.created_interaction_id`: load Interaction join Application (+ outerjoin JobPosting) filtered `Application.user_id == user.id`; None if missing/not owned.
  - Elif `row.status == "created"` and `row.matched_application_id`: best-effort — Interaction where `application_id == matched_application_id`, `created_from == email_webhook`, `Application.user_id == user.id`, and (if a subject is derivable from raw_body) `subject == derived_subject`; order by `created_at desc` limit 1.
  - Else None. Company via the calendar `_company` logic (jp.company or url host).
- Extend `WebhookRequestDetail` with `created_interaction: CreatedInteraction | None = None`; populate in `get_webhook_request`.
- Tests: (a) new created row → detail.created_interaction populated (FK path); (b) old row (FK null, matching interaction exists) → populated (heuristic); (c) ignored row → null; (d) after `DELETE /api/interactions/{id}`, refetch detail → created_interaction null AND row.status still "created" (verifies ON DELETE SET NULL).

## Task W4: Frontend — show created interview + Reject

**Files:** `frontend/src/api/webhooks.ts`, `frontend/src/pages/SettingsWebhooks.tsx`.

- api: add `CreatedInteraction` type; extend `WebhookRequestDetail` with `created_interaction: CreatedInteraction | null`. Reject reuses `interactions.remove(id)` from `../api/interactions`.
- DetailModal: when `created_interaction` present, render a block (company + display_id link to `/applications/{application_id}`, interview_stage, start/end time, location, a needs_review badge) and a **Reject interview** button. On click → confirm → `interactions.remove(ci.id)` → invalidate `["webhook-request", id]`, `["webhook-requests"]`, `["calendar-interviews"]`, `["calendar-review-count"]`. For a `created` row with no `created_interaction`, show "Interview removed".
- Typecheck + build via raw binaries.
