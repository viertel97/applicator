# Job Enrichment Features — Design Spec
Date: 2026-05-17

## Scope

Four features added to the applicator:

1. **Job link display** — surface `Application.url` as clickable link in UI
2. **Online status check** — periodic background check if position is still active
3. **Labels** — global shared tags, user-managed + LLM auto-suggested, filterable
4. **Submission requirements** — extract required documents during crawl/extract pipeline

---

## 1. Data Model Changes

### `Label` (new table)
```
id           UUID PK
name         String(100) UNIQUE NOT NULL
color        String(7)   NOT NULL  -- hex e.g. "#3b82f6"
is_auto      Boolean     DEFAULT false  -- true = LLM-suggested, false = user-created
created_at   DateTime    server_default=now()
```

### `application_label` (new join table)
```
application_id   UUID FK -> application.id
label_id         UUID FK -> label.id
PRIMARY KEY (application_id, label_id)
```

### `Application` (two new columns)
```
posting_online      Boolean   nullable  -- null = never checked
posting_checked_at  DateTime  nullable
```

### `JobPosting` (one new column)
```
required_documents  JSON  nullable  -- list[str] from fixed vocab
```
Fixed vocab: `["cv", "cover_letter", "portfolio", "references", "certificates", "other"]`

---

## 2. Online Status Check

### Celery Beat schedule
- Task name: `tasks.check_postings`
- Cadence: every 6 hours
- Skip applications where `posting_checked_at > now() - 4h` (restart safety)

### Scope
Applications where `status NOT IN ('withdrawn', 'rejected')`.

### Detection logic (per application)
1. Fetch URL via `HybridFetcher`
2. **Heuristic** (fast path):
   - HTTP 404 / 410 → `posting_online = False`
   - Keyword scan (case-insensitive) on response text:
     ```
     "stelle nicht mehr verfügbar", "position filled", "job no longer available",
     "diese stelle wurde", "anzeige abgelaufen", "no longer accepting",
     "position has been filled"
     ```
     Match → `posting_online = False`
   - HTTP 200 + no keywords → `posting_online = True`
3. **LLM fallback**: only when heuristic is inconclusive (e.g. non-200/404 status, fetch error after retry). Short prompt: "Is this page still an active job posting? Answer yes or no."
4. Write `posting_online` + `posting_checked_at = now()`, commit.

### Rate limiting
- 1 request/sec maximum across the batch (sleep between iterations)

### Failure handling
- Fetch error → log, leave `posting_online` unchanged, update `posting_checked_at`

---

## 3. Labels

### Backend API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/labels` | List all global labels |
| `POST` | `/api/labels` | Create label `{name, color}` |
| `POST` | `/api/applications/{id}/labels/{label_id}` | Assign label to application |
| `DELETE` | `/api/applications/{id}/labels/{label_id}` | Remove label from application |

`GET /api/applications` gains optional query param `?label_ids=uuid,uuid,...` — returns applications that have ANY of the specified labels (OR logic).

`ApplicationOut` response shape gains `labels: list[LabelOut]`.

### Auto-labeling (during extract)
- Fixed candidate set passed to LLM in extract prompt:
  `["Startup", "Konzern", "Remote", "Hybrid", "Finance", "Tech", "Agency", "Consulting", "NGO", "Public Sector"]`
- LLM returns subset that applies to the posting
- Each suggested label: upsert into `label` table with `is_auto=True` (skip if name already exists), then assign to application

### Frontend

**Application list:**
- Colored label chips rendered per row
- Multi-select label filter in list header — filters applications to those matching selected labels

**Application detail:**
- Label editor below job posting header
- Type-ahead search over existing labels (GET /api/labels filtered client-side)
- Create new label inline (name + color picker)
- Remove assigned label with × button

---

## 4. Submission Requirements

### Extraction
- Add `required_documents` field to extractor Pydantic schema (`list[str] | None`)
- Update extract prompt: instruct LLM to identify required documents from fixed vocab:
  `cv`, `cover_letter`, `portfolio`, `references`, `certificates`, `other`
- Stored in `JobPosting.required_documents`

### Frontend
- Application detail: icon row near document section
- Each required document type shown as a small badge (e.g. "CV", "Cover Letter")

---

## 5. Job Link Display

No backend changes needed — `Application.url` already stored.

### Frontend
- **Application list**: small external link icon (↗) next to company name, links to `application.url`, opens in new tab
- **Application detail**: clickable URL displayed in header area near title/company

---

## 6. Migration

One Alembic migration covering:
- New `label` table
- New `application_label` join table
- `ALTER TABLE application ADD COLUMN posting_online BOOLEAN`
- `ALTER TABLE application ADD COLUMN posting_checked_at TIMESTAMP`
- `ALTER TABLE job_posting ADD COLUMN required_documents JSON`

---

## 7. Out of Scope

- Per-user label visibility (all labels are global)
- Label deletion (avoid orphan cleanup complexity for now)
- Notification on status change (badge display only)
- Configurable check interval per application
