# Applicator — Design Spec

**Date:** 2026-04-29
**Owner:** Janik (solo)
**Status:** Draft for review

## Goal

A self-hosted web application that streamlines applying to jobs. The user pastes a job posting URL; the system crawls the page, extracts structured information via an LLM, and generates a tailored Anschreiben (cover letter) based on a stored CV and a default Anschreiben template. The user reviews, refines via chat, downloads as DOCX, and tracks the application through its lifecycle (applied, interviews, rejection/offer/acceptance).

## Scope

**In scope (MVP):**
- Microsoft OAuth2 login (single user)
- Paste URL → crawl → extract → generate → review → download DOCX
- Versioned CV variants and Anschreiben templates with `is_default`
- Chat-style refinement of generated Anschreiben
- Application status tracking with multiple interviews per application
- Configurable LLM provider (default: Groq + gpt-oss)
- Postgres-backed persistence

**Out of scope (MVP):**
- Multi-user support (schema is FK-ready but no UI for it)
- OneDrive integration (MS refresh token stored encrypted to enable later)
- Browser extension (URL paste covers MVP)
- Email submission, follow-up reminders, Notion/Excel export

## Non-Goals

- High-throughput batch processing — single-user, low-volume
- Complex job-board integrations — generic HTML crawl + LLM extraction handles all sites
- Mobile app

## Stack

- **Backend:** FastAPI (Python 3.12+), SQLAlchemy 2.0, Alembic, httpx, Playwright (Chromium), python-docx, msal, pydantic-settings
- **Frontend:** React + Vite + TypeScript, TanStack Query, React Router, Tailwind, shadcn/ui, `@uiw/react-md-editor`
- **LLM:** Provider-abstract client; default Groq via OpenAI-compatible SDK pointed at Groq's endpoint, model `gpt-oss`
- **DB:** Postgres 16
- **Async work:** FastAPI `BackgroundTasks` (no Redis/Celery in MVP)
- **Deploy:** docker-compose (api + db + frontend served by nginx)

## Architecture

```
┌──────────────┐    HTTPS    ┌─────────────────────────────────────┐
│ React SPA    │ ──────────► │ FastAPI                              │
│ (Vite/TS)    │ ◄────────── │  ├─ Auth router (MS OAuth2)          │
└──────────────┘             │  ├─ Applications router              │
                              │  ├─ Documents router (CV/Anschr.)   │
                              │  ├─ Chat-refine router (LLM)        │
                              │  ├─ Interviews router                │
                              │  ├─ BackgroundTasks pipeline         │
                              │  ├─ Crawler (httpx → Playwright)    │
                              │  ├─ LLM client (Groq default)       │
                              │  └─ DOCX renderer (python-docx)     │
                              └─────────────┬───────────────────────┘
                                            │
                                  ┌─────────▼─────────┐
                                  │ Postgres 16       │
                                  │ + local fs (data) │
                                  └───────────────────┘
```

### Module Boundaries

Each unit single-responsibility, testable in isolation with fakes.

- `crawler/` — fetch URL → raw HTML/text. No LLM, no DB.
- `extractor/` — text → structured `JobPosting` via LLM. Pure function (LLM injected).
- `generator/` — `JobPosting` + CV variant + Anschreiben variant + language → markdown draft. Pure (LLM injected).
- `renderer/` — markdown → DOCX via python-docx + template. Pure.
- `llm/` — provider-abstract client. `GroqClient` default; interface allows swap.
- `auth/` — Microsoft OAuth2 flow + session middleware.
- `pipeline.py` — orchestrates crawl → extract → generate → render. Updates `job_state` per step.
- `api/` — routers, dependency-injected services.
- `db/` — SQLAlchemy models + Alembic migrations.

## Data Model

```
user
  id PK, ms_oid UNIQUE, email, display_name,
  ms_refresh_token_encrypted, created_at

cv_variant
  id PK, user_id FK, name, source_md, file_path,
  is_default, created_at

anschreiben_variant
  id PK, user_id FK, name, source_md,
  is_default, created_at

application
  id PK, user_id FK,
  url, url_hash UNIQUE,
  status ENUM(draft, applied, offer, rejected, accepted, withdrawn),
  job_posting_id FK NULL,
  cv_variant_id FK,
  anschreiben_variant_id FK,
  generated_md TEXT, generated_docx_path,
  language CHAR(2),
  job_state ENUM(pending, crawling, extracting, generating, ready, failed),
  job_error TEXT,
  created_at, updated_at

job_posting
  id PK, application_id FK,
  raw_text, raw_html_path,
  title, company, location,
  description, requirements,
  contact_person, application_email, deadline, salary,
  tech_stack JSONB, seniority, work_mode, benefits JSONB, language,
  extracted_at

interview
  id PK, application_id FK,
  scheduled_at, kind ENUM(phone, video, onsite, technical, final),
  notes, outcome ENUM(pending, passed, failed, cancelled),
  created_at

chat_message
  id PK, application_id FK,
  role ENUM(user, assistant, system),
  content, created_at

audit_log
  id PK, user_id, action, entity, entity_id,
  payload JSONB, created_at
```

Notes:
- `url_hash` (sha256 of normalized URL) prevents duplicate applications.
- `job_state` is the pipeline state machine (internal); `status` is the user-facing application lifecycle.
- DOCX and raw HTML stored on disk under `data/{user_id}/{application_id}/`; only paths in DB.
- `cv_variant.file_path` points to the user's real DOCX/PDF; `source_md` is the LLM-readable representation.
- `ms_refresh_token_encrypted` uses Fernet with key from `APP_SECRET_KEY` env var.

## Data Flow

### Add Application

```
POST /api/applications {url, cv_variant_id?, anschreiben_variant_id?}
  → normalize url, compute url_hash
  → if exists: 409 with existing application id
  → defaults: cv_variant_id/anschreiben_variant_id from is_default if omitted
  → insert application(job_state=pending, status=draft)
  → BackgroundTasks.add_task(process_application, app_id)
  → 202 + {id, job_state}
```

### Background Pipeline (`process_application`)

```
1. job_state=crawling
   crawler.fetch(url):
     - httpx GET (timeout 10s, realistic UA)
     - if status != 200, len(text) < 500, or JS-only markers detected
       → playwright fetch (headless, wait networkidle)
   → store raw_html_path + raw_text

2. job_state=extracting
   extractor.extract(raw_text) → JobPosting (pydantic)
     - LLM call with structured-output JSON schema
     - language detected and stored
   → insert job_posting

3. job_state=generating
   generator.generate(
     job_posting,
     cv_variant.source_md,
     anschreiben_variant.source_md,
     language,
   )
     - LLM prompt: match CV to requirements, draft Anschreiben in detected language
   → application.generated_md = draft
   → application.language = language

4. renderer.to_docx(generated_md, template) → file_path
   → application.generated_docx_path

5. job_state=ready
```

Failure at any step → `job_state=failed`, `job_error=str(e)`. Frontend exposes a retry button that re-runs the pipeline from step 1.

### Frontend Polling

While `job_state in (pending, crawling, extracting, generating)`, the SPA polls `GET /api/applications/{id}` every 2s.

### Chat Refinement

```
POST /api/applications/{id}/chat {message}
  → load chat_messages history for application
  → build LLM prompt: system + history + current generated_md + new user message
  → LLM call returns: assistant message + updated markdown
  → persist user message, assistant message
  → application.generated_md = updated markdown
  → re-render DOCX
  → return {assistant_message, generated_md}
```

### Status & Interviews

```
PATCH /api/applications/{id} {status}
POST  /api/applications/{id}/interviews {scheduled_at, kind}
PATCH /api/interviews/{id} {outcome, notes, scheduled_at?}
DELETE /api/interviews/{id}
```

## Auth

Microsoft OAuth2 via `msal`.

```
GET  /api/auth/login    → redirect to MS authorize URL
GET  /api/auth/callback → exchange code, upsert user, set session cookie
POST /api/auth/logout   → clear session
GET  /api/auth/me       → current user
```

- Session cookie: httponly, secure, samesite=lax. Server-side session store (DB-backed) keyed by random session id.
- All `/api/*` routes except `/auth/*` require an authenticated session via dependency.
- `msal` silent flow refreshes access tokens; refresh token persisted encrypted to enable OneDrive later.

## Frontend

Pages:
- `/login` — Microsoft sign-in button
- `/applications` — list with filter by status, "Add URL" input
- `/applications/:id` — split view:
  - left: extracted job_posting fields (read-only)
  - right: tabs — `Anschreiben` (markdown editor + chat panel + Download DOCX), `Status` (status dropdown + interviews CRUD), `Raw` (raw text/HTML)
- `/settings/cv` — list/upload/edit CV variants, set default
- `/settings/anschreiben` — list/edit Anschreiben templates, set default
- `/settings/llm` — provider/model/api_key (Groq default)

State: TanStack Query for all server state; no global store.

## Error Handling

- **Crawler:** httpx timeout → fallback to Playwright; both fail → `job_state=failed`, error surfaced in UI with retry.
- **LLM:** retry 2× with exponential backoff; structured-output parse failure → one re-prompt with the parse error appended.
- **DOCX render:** failure preserves `generated_md`, sets a warning flag (not full pipeline failure), allows manual retry.
- **Auth:** 401 → SPA redirects to `/login`.
- **All API errors:** structured JSON `{error, code, detail}` with appropriate status codes.

## Testing

- **Unit:** extractor, generator, renderer, crawler — pure functions with fixtures.
- **Fakes:** `FakeLLM` returns canned `JobPosting` and markdown; `FakeBrowser` for Playwright; `FakeFetcher` for httpx.
- **Integration:** real Postgres (testcontainers or compose test profile), real HTTP routes with `FakeLLM` + `FakeBrowser` injected — no real network or LLM calls.
- **E2E:** Playwright test against full stack — single happy path (add URL → ready → download DOCX → set status).
- **TDD:** failing test first per superpowers TDD skill.

## Repository Layout

```
applicator/
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── api/{auth,applications,documents,chat,interviews}.py
│   │   ├── crawler/{__init__,httpx_fetcher,playwright_fetcher}.py
│   │   ├── extractor/{__init__,prompts,schemas}.py
│   │   ├── generator/{__init__,prompts}.py
│   │   ├── renderer/{__init__,docx,template.docx}
│   │   ├── llm/{__init__,groq,base}.py
│   │   ├── auth/{ms_oauth,session}.py
│   │   ├── db/{models,session}.py
│   │   ├── pipeline.py
│   │   ├── config.py
│   │   └── main.py
│   └── tests/{unit,integration,e2e,fakes}
├── frontend/
│   ├── package.json
│   ├── src/{pages,components,api,hooks}
│   └── tests/
├── docker-compose.yml
├── .env.example
└── docs/superpowers/specs/
```

## Configuration

`.env` keys:
- `DATABASE_URL`
- `APP_SECRET_KEY` (Fernet key for session + token encryption)
- `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_REDIRECT_URI`
- `LLM_PROVIDER` (default `groq`), `LLM_MODEL` (default `gpt-oss`), `LLM_API_KEY`, `LLM_BASE_URL`
- `DATA_DIR` (default `./data`)
- `FRONTEND_ORIGIN` (CORS)

## Open Questions for Future Iterations

- OneDrive integration: store generated DOCX in user's OneDrive, edit in Word Online.
- Browser extension: capture URL + raw HTML directly from the active tab to bypass crawl-blocking.
- Pipeline durability: if process restarts mid-pipeline, current `BackgroundTasks` design loses in-flight jobs — re-trigger via UI is acceptable for MVP. Move to Celery + Redis if frequency grows.
- Multi-user UI: schema is FK-ready; only requires routing and admin views.
