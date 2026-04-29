# Async Pipeline + URL-Only Intake — Design

Date: 2026-04-29
Branch: `feat/applicator-mvp`

## Goal

Allow users to add a job application by URL alone (no CV/Anschreiben required up front) and process the pipeline asynchronously via Celery + Redis. Extracted job information is editable. Generation runs only on explicit user action once variants are attached.

## Motivation

Current state:
- `POST /api/applications` requires defaults for CV and Anschreiben — blocks "I just want to track this URL" flow.
- Pipeline runs in FastAPI `BackgroundTasks` — dies with the API process, no retries, no cross-stage observability, no decoupling.
- Pipeline is monolithic (`Pipeline.run`); cannot re-run a single stage (e.g., re-extract without re-crawling, regenerate without re-extracting).

Users want to drop a URL, see extracted info, edit it, and trigger generation when ready.

## Architecture

### Containers (`docker-compose.yml`)

- `redis` — broker + result backend (image `redis:7-alpine`)
- `worker` — reuses `./backend` image, runs `celery -A app.tasks.celery_app worker --loglevel=info`, depends on `db` (healthy) + `redis`
- `api` — unchanged role; enqueues tasks via Celery `chain` / `apply_async` instead of `BackgroundTasks`
- `db`, `web` — unchanged

### Code layout

```
backend/app/
  pipeline/                    # pure functions, no Celery
    __init__.py
    crawl.py                   # fetch URL, save raw.html, return FetchResult
    extract.py                 # LLM extract → ExtractedJobPosting → upsert JobPosting
    generate.py                # render generated_md + DOCX
  tasks/
    __init__.py
    celery_app.py              # Celery() factory, broker/backend from settings
    pipeline.py                # crawl_task, extract_task, generate_task
  pipeline.py                  # DELETE (replaced by package)
```

Tasks are thin wrappers: load `Application` by id, call pure pipeline function with a session, set `job_state` transitions, persist. Pure functions are unit-testable without Celery.

### State machine

```
pending ──▶ crawling ──▶ extracting ──▶ extracted ──▶ generating ──▶ ready
                                              │
                                              ▼
                                          failed (failed_stage = crawl|extract|generate)
```

- `extracted` is a new terminal state when no variants are attached. Awaits explicit `POST /generate`.
- `ready` is the existing terminal state after generation.
- `failed` is single-state but augmented with `failed_stage` for retry routing.

### Schema migration (Alembic)

1. `Application.cv_variant_id` → nullable
2. `Application.anschreiben_variant_id` → nullable
3. `Application.failed_stage` → new nullable `Enum('crawl', 'extract', 'generate')`
4. `Application.job_posting_dirty` → new `Boolean` not null, default `false`
5. `JobState` Postgres enum gains `extracted` value via `ALTER TYPE job_state ADD VALUE 'extracted'`

## API changes

### Modified

`POST /api/applications` (status 202)
- Body: `{ url: HttpUrl, cv_variant_id?: UUID, anschreiben_variant_id?: UUID }`
- Variants now fully optional. **No default fallback.** If user wants defaults applied, they pick variants in UI explicitly.
- Validates ownership when variants present.
- Enqueues `chain(crawl_task.s(app_id), extract_task.s())`. Generation is **not** chained.
- 409 on duplicate URL hash (unchanged).

`POST /api/applications/{aid}/retry`
- Routes by `failed_stage`:
  - `crawl` → re-enqueues `chain(crawl_task.s, extract_task.s)`
  - `extract` → re-enqueues `extract_task.s` only
  - `generate` → re-enqueues `generate_task.s` (requires variants present)
- If state is `ready` (success retry), re-runs full chain `crawl → extract`. Generation must be triggered separately.
- 409 if pipeline currently running.

### New

`PATCH /api/applications/{aid}/job-posting`
- Body: any subset of `{title, company, location, description, requirements, contact_person, application_email, deadline, salary, tech_stack, seniority, work_mode, benefits, language}`
- Updates `JobPosting` row in place. 404 if no `JobPosting` yet.
- 409 if `job_state` ∈ `{crawling, extracting, generating}`.
- If `generated_md` exists, sets `job_posting_dirty = true` (drives the regenerate banner).
- Returns `ApplicationOut`.

`PATCH /api/applications/{aid}/variants`
- Body: `{ cv_variant_id?: UUID|null, anschreiben_variant_id?: UUID|null }` — null clears.
- Ownership-checked. No task enqueued.
- 409 if `job_state` ∈ `{generating}`.

`POST /api/applications/{aid}/generate`
- Requires both `cv_variant_id` and `anschreiben_variant_id` set (else 400).
- Requires `JobPosting` row exists (else 400 — extraction must have completed at least once).
- Requires `job_state` ∈ `{extracted, ready, failed}` (else 409). When `failed`, additionally requires `failed_stage='generate'` — failures earlier in the chain go through `POST /retry`.
- Enqueues `generate_task.s(aid)`.
- Clears `job_posting_dirty`, `failed_stage`, `job_error`. Sets state to `generating`.
- Returns 202 + `ApplicationOut`.

### Response shape

`ApplicationOut` adds:
- `cv_variant_id: UUID|None`
- `anschreiben_variant_id: UUID|None`
- `failed_stage: 'crawl'|'extract'|'generate'|None`
- `job_posting_dirty: bool`

## Frontend changes

### Add-application form

- URL field required.
- CV + Anschreiben variant pickers optional, labelled "Skip — add later".
- Submit posts whatever is filled.

### Application detail page

- **JobPosting section**: each field becomes editable; one "Save changes" button per section calls `PATCH /job-posting`. Save disabled while pipeline running.
- **Variants section**: two dropdowns sourced from existing variant lists; calls `PATCH /variants` on change.
- **Generate button**: shown when state ∈ `{extracted, failed, ready}` and both variants set. Tooltip explains disabled reasons. Calls `POST /generate`.
- **Regenerate banner**: when `job_posting_dirty=true` and `generated_md` exists, shows above DOCX section with "Regenerate" button (also calls `POST /generate`).
- **Status pill**: renders `JobState`; for `failed`, appends `failed_stage`.
- Polling unchanged — already covers all state transitions.

## Error handling

- Each Celery task wraps work in try/except. On exception: `job_state=failed`, `failed_stage=<stage>`, `job_error=str(e)[:1000]`, commit, then re-raise so Celery records the traceback.
- `crawl_task` only: `autoretry_for=(httpx.HTTPError, TimeoutError)`, `max_retries=2`, `default_retry_delay=10`. Extract/generate are not auto-retried (LLM cost, non-determinism — user-driven retry only).
- Chain halts on failure naturally (Celery default).
- Enqueue path: if Redis broker is unreachable, FastAPI returns 503 with a clear message; the `Application` row is rolled back to avoid orphan `pending` rows.

## Idempotency

- `crawl_task` overwrites `raw.html` on retry.
- `extract_task` deletes prior `JobPosting` row before inserting new (allows clean re-extract).
- `generate_task` overwrites `generated_md` and DOCX file.

## Testing

### Unit

- `pipeline/crawl.py`, `pipeline/extract.py`, `pipeline/generate.py` — tested as pure functions with a session fixture. Existing `Pipeline.run` tests adapt by calling these directly.

### Task-level

- Test settings set `CELERY_TASK_ALWAYS_EAGER=True` and `CELERY_TASK_EAGER_PROPAGATES=True`. Tasks run sync inline, no broker needed.
- Existing pipeline integration tests rewrite as `chain(crawl_task.s(id), extract_task.s()).apply()`.

### New API tests

- `POST /applications` URL-only: pipeline reaches `extracted`, no DOCX, `generated_md` is null.
- `PATCH /job-posting`: updates persist, sets `job_posting_dirty=true` when `generated_md` exists.
- `PATCH /variants`: ownership rejection, clearing variants, partial update.
- `POST /generate`: 400 without variants, 409 while running, happy path → `ready`.
- `POST /retry` for each `failed_stage`: re-enqueues correct task subset.

### E2E (Playwright)

- URL-only add → wait for `extracted` → edit a field → attach variants → click Generate → DOCX downloads.

## Out of scope

- Beat / scheduled jobs.
- Multi-tenant Celery routing.
- Webhook/event push to frontend (polling stays).
- Cancellation of running tasks.
- Migration of existing applications' `failed` rows to populate `failed_stage` retroactively (left null; retry path handles null as "rerun full chain").

## Open follow-ups (not blocking this spec)

- Consider replacing polling with SSE once stage progress matters more.
- Consider Celery Flower for local observability in `docker-compose.override.yml`.
