# Contact Extraction + Missing-Field Backfill — Design Spec
Date: 2026-05-20

## Motivation

Before submitting an application the user wants to contact the company to
ask about 80% workload and remote/flexibility. Today only an unstructured
`contact_person` name and an `application_email` are extracted, often
incomplete. Older `JobPosting` rows also miss fields that have since been
added to the extractor (e.g. `required_documents`).

This spec covers two linked changes:

1. Replace the loose `contact_person` + `application_email` fields with a
   structured `contact` block (name, role, email, phone).
2. Add a backfill mechanism that, on every backend restart, re-runs a
   targeted LLM pass to fill empty fields on existing `JobPosting` rows
   without overwriting non-null values, and without retrying fields that
   were already attempted.

---

## 1. Data Model Changes

### `JobPosting` — column changes

Remove:
- `contact_person: str | None`
- `application_email: str | None`

Add:
```
contact             JSON      nullable  -- {name?, role?, email?, phone?}
backfill_attempts   JSON      NOT NULL DEFAULT '{}'  -- {field_name: ISO timestamp}
```

`contact` shape (all keys optional, any subset may be null/absent):
```json
{
  "name":  "Jane Doe",
  "role":  "Head of Engineering",
  "email": "jane@example.com",
  "phone": "+49 30 1234567"
}
```

`contact` is `null` when no contact info present at all. Empty object `{}`
is normalized to `null` on write.

### Migration

Single Alembic migration:

1. Add `contact JSON NULL` to `job_posting`.
2. Add `backfill_attempts JSON NOT NULL DEFAULT '{}'` to `job_posting`.
3. Data copy:
   - For each row with non-null `contact_person` and/or `application_email`,
     set `contact = {"name": contact_person, "email": application_email}`
     omitting null sub-fields.
4. Drop `contact_person`, `application_email` columns.

Downgrade reverses (recreate columns, copy back `name`/`email`, drop new
columns).

---

## 2. Extractor Schema Changes

`backend/app/extractor/schemas.py`:

```python
class ContactInfo(BaseModel):
    name:  str | None = None
    role:  str | None = None
    email: str | None = None
    phone: str | None = None


class ExtractedJobPosting(BaseModel):
    # ... existing fields ...
    contact: ContactInfo | None = None
    # remove: contact_person, application_email
```

Prompt update: instruct LLM to populate `contact` from byline,
"Ansprechpartner", recruiter signature, sidebar, or mailto links. Phone
numbers from `tel:` links or signature lines. Leave the whole block
`null` if nothing identifiable.

Generator/pipeline code that reads `contact_person` / `application_email`
updates to read from `job_posting.contact`.

---

## 3. Backfill Subsystem

### Eligible fields

```
contact, salary, deadline, tech_stack, benefits, required_documents,
work_mode, seniority, requirements, description
```

Not backfilled: `title`, `company`, `location`, `language` — these
succeed on the initial extract or signal a broken posting.

### Trigger

FastAPI `lifespan` startup hook enqueues a single Celery task
`tasks.backfill_missing` (no args). Task is idempotent — if a previous
run is still in-flight, the new enqueue is a no-op (use a Redis lock
keyed `backfill:lock` with 1 hour TTL).

### Scan query

Select `JobPosting` rows where:
- `raw_text` is non-empty AND
- at least one eligible field is null AND that field name is not a key in
  `backfill_attempts`.

Iterate in stable order (e.g. `created_at ASC`).

### Per-row processing

For each row:

1. Compute `missing = [f for f in ELIGIBLE if getattr(jp, f) is None
   and f not in jp.backfill_attempts]`. Skip if empty.
2. Call `extract_fields(jp.raw_text, missing, llm)` (see §4).
3. For each field in result:
   - If returned value is non-null AND DB column is still null, write it.
4. Stamp `backfill_attempts[field] = utcnow().isoformat()` for **every**
   field in `missing`, regardless of result. Re-assign the JSON column so
   SQLAlchemy detects the change.
5. Commit.
6. Sleep 1.0 s before next row (rate limit).

### Failure handling

- LLM call raises → log warning, do NOT stamp `backfill_attempts`, move on.
  The next restart will retry.
- Invalid JSON / schema mismatch → log warning, stamp attempts to avoid
  poison loop, move on.

### Concurrency / lock

```python
with redis.lock("backfill:lock", timeout=3600, blocking=False) as got:
    if not got:
        return
    run_backfill(...)
```

---

## 4. New Extractor Entrypoint

`backend/app/extractor/__init__.py`:

```python
def extract_fields(
    raw_text: str,
    fields: list[str],
    llm: LLMClient,
) -> dict[str, Any]:
    """Extract a subset of fields. Returns partial dict — keys are the
    requested field names; values may be None if not present in text."""
```

Implementation:

- Build a Pydantic model dynamically with `pydantic.create_model`, copying
  type annotations from `ExtractedJobPosting` for the requested fields
  (including the new `ContactInfo` nested model).
- Reuse `SYSTEM` prompt with a small suffix: "Only fill the fields shown
  in the schema."
- Same LLM call signature as `extract()`.
- Return `model.model_dump(exclude_none=False)` so callers can distinguish
  attempted-but-null from absent.

Test fixture: feed a posting text with known contact line, request
`["contact"]`, assert structured output.

---

## 5. Frontend Changes

`frontend/src/api/applications.ts`:
- `JobPostingOut` type: drop `contact_person`, `application_email`. Add
  `contact: { name?: string; role?: string; email?: string; phone?: string } | null`.

`frontend/src/components/JobPostingPanel.tsx`:
- Remove the `contact_person` and `application_email` rows from `FIELDS`.
- Render a single "Contact" section when `contact` is non-null:
  - Name (plain text)
  - Role (plain text, secondary color)
  - Email as `mailto:` link
  - Phone as `tel:` link
- Hide section entirely if all four sub-fields are null/absent.

No list-view changes.

---

## 6. Backend API

`ApplicationOut.job_posting` reflects new shape automatically through
Pydantic. No new endpoints. No manual backfill trigger in this iteration.

---

## 7. Application Deletion (Soft Delete)

### Data model

`Application` gains one column:
```
deleted_at   DateTime  nullable  -- null = active, non-null = soft-deleted
```

Single Alembic migration adds this column. No cascade changes — related
`JobPosting`, `application_label`, and raw HTML files stay on disk and in
the DB. They are not surfaced because the parent is filtered out.

### Query filter

All read endpoints that list or fetch applications filter
`deleted_at IS NULL` by default. No `?include_deleted` toggle in this
iteration.

### API

| Method | Path | Description |
|--------|------|-------------|
| `DELETE` | `/api/applications/{id}` | Soft delete: set `deleted_at = now()`. Idempotent — returns 204 even if already deleted. Returns 404 only if id never existed. |

No restore endpoint. No hard-delete endpoint.

### Frontend

- **List row:** small trash icon at the end of the row. Click opens a
  confirmation modal ("Delete application to {company}? This hides it
  from your list."). Confirm → `DELETE /api/applications/{id}` → remove
  row from list state.
- **Detail panel:** "Delete" button in the panel header area. Same
  confirm modal. On success → navigate back to list.

Modal text identical in both places. Single shared component.

---

## 8. Out of Scope

- Manual "backfill now" button in UI
- Backfill of `title` / `company` / `location` / `language`
- Retry logic for fields that produced null on first attempt
- Per-application backfill scheduling / cadence beyond startup
- Notification when contact info appears after a backfill run
- Cross-posting deduplication of contacts
- Restore of soft-deleted applications
- Hard-delete endpoint or admin tooling
- Cascade cleanup of orphaned `JobPosting`, labels, raw HTML on delete

---

## 9. Testing

- Unit: `extract_fields` with a fixture posting returns expected partial dict.
- Unit: backfill scan picks correct rows (missing field + not in attempts).
- Unit: backfill writes only non-null results, never overwrites non-null
  DB values, stamps all attempted fields.
- Unit: contact migration copy logic (old `contact_person` →
  `contact.name`, old `application_email` → `contact.email`).
- E2E: posting with structured contact line is extracted end-to-end and
  rendered in detail view.
- Unit: `DELETE /api/applications/{id}` sets `deleted_at`, list endpoint
  no longer returns the row, second DELETE is still 204.
- E2E: delete from list row hides it; delete from detail navigates back
  to list with the row gone.
