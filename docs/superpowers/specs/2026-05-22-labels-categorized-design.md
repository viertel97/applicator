# Categorized Labels — Design Spec
Date: 2026-05-22

## Motivation

The label list in production has grown to ~45 free-form strings —
`AI`, `AI Engineer`, `Frankfurt`, `Konzern`, `Python`, `Senior`,
`PostgreSQL`, `LVM Versicherung`, … — with no structure. Two
consequences:

1. **UI scannability collapses.** The label chip filter shows every
   label in one flat list. Users can't tell at a glance which chips
   are about location vs. role vs. tech stack.
2. **No constraint on the LLM.** The extractor's `suggested_labels`
   field is a flat `list[str]` with a soft enum in the prompt. The
   model drifts: today's list mixes our intended vocabulary
   (`Konzern`, `Tech`, `Remote`) with arbitrary tokens (`Spam
   Detection`, `KI-Anwendungsentwicklung`, `LVM Versicherung`).

We add a fixed `category` enum on every label, force the extractor to
emit labels per category, and group chips by category in the UI.
Existing labels are categorized in a one-shot Celery task on worker
startup.

---

## 1. Data Model

### `LabelCategory` enum

String-backed, lowercase, exactly these 10 members:

| Value          | Use                                              |
|----------------|--------------------------------------------------|
| `role`         | Job role / function (AI Engineer, Data Scientist) |
| `tech`         | Tools, languages, libraries (Python, AWS)        |
| `domain`       | Industry / business area (Finance, Insurance)    |
| `seniority`    | Seniority signal (Senior, Lead, Junior)          |
| `work_mode`    | Remote / Hybrid / Onsite / Full-time / Part-time |
| `location`     | Cities, regions, countries                       |
| `company_size` | Startup / KMU / Mittelstand / Konzern            |
| `language`     | Required language (German, English)              |
| `company`      | Specific employer name                           |
| `other`        | User-created labels, fallback                    |

`other` is **never emitted by the LLM**. It's the default for
user-created labels and the fallback when categorization fails.

### `Label` table — added column

```python
category: Mapped[LabelCategory] = mapped_column(
    Enum(LabelCategory), nullable=False, server_default=LabelCategory.other.value
)
```

Server default lets the Alembic migration add the column on existing
rows without a separate backfill step.

`Label.name` remains globally unique. One name = one row = one
category.

---

## 2. Extractor Schema

Replace flat `suggested_labels: list[str]` with a structured nested
model in `app/extractor/schemas.py`:

```python
class LabelSuggestions(BaseModel):
    role: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    domain: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    company_size: list[str] = Field(
        default_factory=list,
        description="Exactly one of Startup, KMU, Mittelstand, Konzern when determinable.",
    )
    language: list[str] = Field(default_factory=list)
    company: list[str] = Field(default_factory=list)


class ExtractedJobPosting(BaseModel):
    ...
    suggested_labels: LabelSuggestions = Field(default_factory=LabelSuggestions)
```

Per-category fields (not `dict[str, list[str]]`) so Groq's strict JSON
schema mode enforces the exact key set and rejects unknown categories.

### Prompt update

In `app/extractor/prompts.py::SYSTEM`, replace the existing
`suggested_labels` sentence with:

```
For suggested_labels, place each label under the matching category
field (role, tech, domain, seniority, work_mode, location,
company_size, language, company). Leave a category empty if nothing
fits. Pick exactly one company_size bucket when determinable from
explicit headcount or general knowledge of the named company.
```

The `other` category does not exist in this schema — the LLM never
emits it.

---

## 3. Pipeline + Backfill

### Shared upsert (new location)

Move `_upsert_and_assign_labels` out of `app/pipeline/extract.py` into
`app/labels/upsert.py`. New signature:

```python
def upsert_and_assign_labels(
    db: Session,
    app: Application,
    suggestions: LabelSuggestions,
) -> None: ...
```

Iterates the nine emitted categories; for each name calls
`_get_or_create_label(db, name, category)` then appends to
`app.labels` if absent. If a label with that name already exists in
a different category, the existing row wins — its category is not
overwritten by a later extraction. (Avoids ping-pong if two postings
disagree on the bucket.)

`pipeline/extract.py::run_extract` and the backfill processor both
import from this single module.

### Backfill processor (Section 6 refactor)

`pick_missing` is unchanged in semantics: `suggested_labels` is
requested when the parent Application has zero labels and the field
has not been attempted before.

`process_row` routes the `suggested_labels` result through
`upsert_and_assign_labels` (which now expects a `LabelSuggestions`
instance, built from the dict the LLM returned).

`extract_fields` already handles nested-model fields (the existing
`contact` field uses the same machinery); no change required.

### One-shot legacy categorization (`other` → real category)

A new Celery task `tasks.categorize_existing_labels`, registered the
same way `tasks.backfill_missing` is, runs on worker startup:

1. Acquire Redis lock `labels:categorize:lock` (TTL 3600). No-op if
   another run holds it.
2. Query all `Label` rows with `category = 'other'` AND `is_auto = true`
   (skip user-created labels — they own their category).
3. Chunk into batches of ~20 names. For each batch call the Groq
   client with a fixed JSON schema:

   ```json
   {"type": "object", "additionalProperties": false,
    "required": [<names>],
    "properties": {"<name>": {"enum": [...categories without 'other'...]}}}
   ```

   Prompt: *"Categorize each label name below into one of: role,
   tech, domain, seniority, work_mode, location, company_size,
   language, company. Return a JSON object mapping each name to its
   category."*
4. Apply: for each `name → category` pair, `UPDATE label SET category
   = :cat WHERE name = :name AND category = 'other'`.
5. On batch failure (429 surfacing through GroqClient's bounded retry,
   JSON parse error, etc.) log warning and continue with next batch.
   Untouched rows stay `other`; next worker boot retries them.

Single-process Celery worker → the lock is mostly defensive. Task is
idempotent — only touches `category = 'other'` rows.

Why Celery, not the Alembic migration: deploys must not depend on
Groq availability, and the categorization is heavy enough (~3 batches
of 20 = 3 LLM calls) to bother the migration. Worker boot is the
natural retry point.

---

## 4. API

### `LabelOut`

```python
class LabelOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    category: LabelCategory
```

### `LabelCreate` (POST body)

```python
class LabelCreate(BaseModel):
    name: str
    color: str
    category: LabelCategory  # required, no default
```

422 when `category` missing.

### `LabelPatch` (PATCH body, new endpoint if absent)

```python
class LabelPatch(BaseModel):
    name: str | None = None
    color: str | None = None
    category: LabelCategory | None = None
```

### `GET /api/labels`

Order by `(category, name)` server-side. Frontend renders in received
order — no client sort.

---

## 5. Frontend

### Types

```ts
type LabelCategory =
  | "role" | "tech" | "domain" | "seniority"
  | "work_mode" | "location" | "company_size"
  | "language" | "company" | "other";

type Label = {
  id: string;
  name: string;
  color: string;
  category: LabelCategory;
};
```

### Filter dropdown (`/applications` page label filter)

Replace flat chip list with collapsible sections, one per category:

- `<details>` element per non-empty category.
- Summary: category name (Title Case) + `(N)` chip count.
- Body: chips. Click toggles filter selection (existing behavior).
- Default state: all sections **collapsed**.
- Open state persisted to `localStorage` under key
  `applicator.labelFilter.openCategories` (string array of category
  keys).
- Empty categories not rendered.

### Detail view (job posting chip cluster)

Render chips bunched by category in row groups:

```
[Role]
  AI Engineer  Data Scientist
[Tech]
  Python  AWS  PostgreSQL
[Location]
  Frankfurt
```

Category headers small uppercase slate-500. Reusable
`<LabelChipGroups labels={…}/>` component used on detail page and any
future card layout.

### LabelEditor (create / rename)

Existing text input gets a sibling `<select>` for `category`. All 10
values selectable (including `other`). `category` required on create
— submit button disabled until both name and category are set.

Editing an existing label: dropdown pre-filled with current category;
saving sends PATCH.

---

## 6. Refactor `app/tasks/backfill.py`

Current file is 188 LOC and mixes:

- Field eligibility logic (`ELIGIBLE_FIELDS`, `pick_missing`,
  `_is_empty`)
- Write-back routing (`process_row`)
- Adaptive pacing (`_adaptive_sleep`)
- Candidate query (`_candidate_query`)
- DB session context manager (`_db`)
- Celery task entrypoint + Redis lock (`backfill_missing_task`)
- Runner loop (`_run`)

Convert to a package:

```
app/tasks/backfill/
  __init__.py        # re-exports public symbols
  task.py            # celery task, Redis lock, entrypoint
  processor.py       # pick_missing, process_row, _is_empty, ELIGIBLE_FIELDS
  pacing.py          # _adaptive_sleep + threshold constants
  query.py           # _candidate_query, _db, _run
```

`__init__.py` re-exports `backfill_missing_task`, `pick_missing`,
`process_row`, `_adaptive_sleep`, `ELIGIBLE_FIELDS` so existing test
imports keep working without modification.

Target: every file under 70 LOC, single responsibility, no cyclic
imports.

---

## 7. Migration

New Alembic revision after `c1d2e3f4a5b6`:

```python
revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"

def upgrade():
    op.add_column(
        "label",
        sa.Column(
            "category", sa.Enum(LabelCategory, name="labelcategory"),
            nullable=False, server_default="other",
        ),
    )

def downgrade():
    op.drop_column("label", "category")
    op.execute("DROP TYPE labelcategory")
```

No data copy in the migration — the Celery task does the
categorization on worker boot.

---

## 8. Testing

### Unit

- `test_label_category_enum_values` — enum has exact 10 members in
  expected order
- `test_extracted_job_posting_suggested_labels_structured` —
  `LabelSuggestions` defaults all categories to empty list
- `test_upsert_and_assign_labels_writes_category` — new labels get
  the category passed in
- `test_upsert_preserves_existing_category` — label with name X in
  category `tech` stays `tech` even if a later extraction emits X
  under `role`
- `test_categorizer_chunks_into_batches_of_20`
- `test_categorizer_applies_name_to_category_map`
- `test_categorizer_skips_user_created_labels` — `is_auto = false`
  rows untouched
- `test_categorizer_logs_and_continues_on_batch_failure`

### Integration

- `test_categorize_existing_labels_task` — seed 25 `other` labels,
  mock GroqClient, run task, assert all updated and second run is a
  no-op
- `test_labels_endpoint_returns_category_sorted`
- `test_create_label_requires_category` — POST without category → 422
- `test_label_patch_updates_category`
- `test_migration_adds_category_column_with_other_default` — pattern
  copied from `test_contact_migration.py`

### Frontend

- TypeScript build fails if `Label` consumers ignore `category`
  (catches the refactor)
- E2E: filter dropdown shows collapsible sections, opening one
  category filters by its labels; LabelEditor blocks save without
  category. Deferred if Playwright environment still segfaults.

### Manual smoke after deploy

- All 45 existing labels visible in DB with `category != 'other'` (or
  documented warnings on the few that failed categorization)
- Filter panel groups them as expected; all sections collapsed on
  first visit
- Create new label without category → form blocks; with category →
  appears in correct group on next reload
- One posting goes through the extractor end-to-end; chips appear
  pre-grouped in the detail view

---

## 9. Rollout

Single backend deploy:

1. Migration adds `category` column with server default `other`.
2. API + frontend ship with the new shape simultaneously (frontend
   tolerates `other`-tagged labels until the task runs).
3. Worker boots, runs `tasks.categorize_existing_labels`, ~60 s
   later most labels have real categories.
4. Refresh — filter now grouped properly.

No backfill of historic applications needed beyond what the existing
`tasks.backfill_missing` already does (now using the structured
`suggested_labels` payload).

---

## 10. Non-Goals

- **Semantic merge** of near-duplicates (`AI` / `Artificial
  Intelligence`, `Deep Learning` / `Machine Learning`). User picks
  manually if desired. Once grouped by category the noise drops a
  lot.
- **Color picker for category** — categories don't have a visual
  color; the per-label color stays as today.
- **User-editable category enum** — fixed code-side. Adding a new
  category is a code+migration change.
- **Multi-category labels** — one label = one row = one category.
- **Auto-categorization on user create** — user picks at create time
  (or edits later). No hidden LLM call.
