# Pre-Application Inquiry Email — Design

Date: 2026-05-22

## Problem

Before sending the actual application, the user wants to ask the employer two
recurring questions when the job posting itself does **not** answer them:

1. How much home office per week is permitted (assuming customer projects /
   other conditions are met)?
2. Is a 80% position (working Monday–Thursday) acceptable?

If a posting already addresses a topic, that topic must be omitted from the
inquiry. If both topics are addressed, no inquiry is needed.

The user wants the LLM to draft this email and wants the underlying prompt
(system instructions) to be easily editable from the UI.

## High-level approach

1. Extend the existing `extractor` step to emit two boolean flags on the job
   posting: `mentions_home_office_policy`, `mentions_part_time`.
2. Add a single per-user editable `InquiryPromptTemplate` (no variants).
3. On the application detail page, add an **Inquiry** panel with a
   "Draft inquiry" button that becomes enabled only when at least one flag is
   false. Generation is manual (no auto-trigger after extract).
4. Persist the generated subject/body on the `Application` row, plus a
   `inquiry_sent_at` timestamp. One inquiry per application; regenerate
   overwrites (with confirm).
5. Sending is out of scope — the UI offers Copy and a `mailto:` link prefilled
   from `job_posting.application_email`. A "Mark sent" action records the
   timestamp.

## Data model

### Add to `JobPosting`

| Column                          | Type           | Notes                          |
|---------------------------------|----------------|--------------------------------|
| `mentions_home_office_policy`   | `Boolean`      | Nullable for legacy rows       |
| `mentions_part_time`            | `Boolean`      | Nullable for legacy rows       |

Null is treated as `false` (button stays enabled).

### Add to `Application`

| Column              | Type        |
|---------------------|-------------|
| `inquiry_subject`   | `Text NULL` |
| `inquiry_body`      | `Text NULL` |
| `inquiry_sent_at`   | `DateTime NULL` |

### New table `inquiry_prompt_template`

| Column        | Type                                  |
|---------------|---------------------------------------|
| `id`          | `UUID PK`                             |
| `user_id`     | `UUID FK user.id UNIQUE`              |
| `source_md`   | `Text` (system prompt for the LLM)    |
| `created_at`  | `DateTime`                            |
| `updated_at`  | `DateTime`                            |

One row per user. Default seeded on first `GET /api/settings/inquiry-prompt`
if missing.

### Alembic migration

Single revision: add five columns + new table. No data migration needed
(nullables default to NULL).

## Extractor changes

### `app/extractor/schemas.py`

Add to `ExtractedJobPosting`:

```python
mentions_home_office_policy: bool = Field(
    default=False,
    description=(
        "True iff the posting explicitly states a home office / remote / "
        "hybrid policy with a frequency or percentage (e.g. 'Homeoffice "
        "möglich', '2 Tage pro Woche remote', 'fully remote', "
        "'hybrid 60/40'). False if home office is not mentioned at all "
        "or only implied."
    ),
)
mentions_part_time: bool = Field(
    default=False,
    description=(
        "True iff the posting explicitly mentions part-time availability "
        "(e.g. 'Teilzeit möglich', '80%', 'part-time'). False if only "
        "Vollzeit / full-time is mentioned or nothing is said about it."
    ),
)
```

### `app/extractor/prompts.py`

Extend `SYSTEM` to instruct the LLM to set both flags using the descriptions
above.

### `app/pipeline/extract.py`

Persist both flags onto the new `JobPosting` columns.

## New backend module `app/inquiry/`

### `schemas.py`

```python
class InquiryEmail(BaseModel):
    subject: str
    body: str
```

### `prompts.py`

```python
DEFAULT_TEMPLATE = """\
Du bist ein Bewerber und schreibst eine kurze, höfliche Vorab-Mail an den
Ansprechpartner einer Stellenausschreibung. Ziel: zwei offene Punkte klären,
bevor du die vollständige Bewerbung schickst.

- Halte die Mail kurz (max. 8 Sätze).
- Stelle nur die explizit genannten Fragen, keine zusätzlichen Themen.
- Frage am Ende, ob eine Bewerbung unter diesen Bedingungen willkommen ist.
- Passe die Sprache an die angegebene Sprache an (de oder en).
- Gib JSON zurück: {"subject": "...", "body": "..."}. Kein zusätzlicher Text.
"""

def user_prompt(
    *,
    job: ExtractedJobPosting,
    language: str,
    ask_home_office: bool,
    ask_part_time: bool,
) -> str:
    topics: list[str] = []
    if ask_home_office:
        topics.append(
            "Wie viele Tage Home Office pro Woche sind möglich (unter der "
            "Voraussetzung, dass Kundenprojekte und sonstige Anforderungen "
            "erfüllt sind)?"
        )
    if ask_part_time:
        topics.append(
            "Wäre eine 80%-Stelle (Montag bis Donnerstag) grundsätzlich "
            "denkbar?"
        )
    return (
        f"Zielsprache: {language}\n\n"
        f"Stelle: {job.title} bei {job.company}\n"
        f"Ansprechpartner: {job.contact_person or 'unbekannt'}\n\n"
        f"Fragen, die in der Mail vorkommen müssen:\n- "
        + "\n- ".join(topics)
    )
```

### `__init__.py`

```python
def draft(
    *,
    job: ExtractedJobPosting,
    language: str,
    ask_home_office: bool,
    ask_part_time: bool,
    system_md: str,
    llm: LLMClient,
) -> InquiryEmail:
    schema = InquiryEmail.model_json_schema()
    raw = llm.complete(
        [
            {"role": "system", "content": system_md},
            {"role": "user", "content": user_prompt(
                job=job, language=language,
                ask_home_office=ask_home_office, ask_part_time=ask_part_time,
            )},
        ],
        json_schema=schema,
        temperature=0.3,
    )
    return InquiryEmail.model_validate_json(raw)
```

## API endpoints

### Application-scoped (`api/applications.py`)

All require auth + ownership check (existing pattern).

| Method | Path                                  | Body                          | Response                        |
|--------|---------------------------------------|-------------------------------|---------------------------------|
| POST   | `/applications/{id}/inquiry/draft`    | empty                         | `{subject, body, recipient}`    |
| PATCH  | `/applications/{id}/inquiry`          | `{subject, body}`             | `{subject, body, sent_at}`      |
| POST   | `/applications/{id}/inquiry/mark-sent`| empty                         | `{sent_at}`                     |

`POST /inquiry/draft`:

1. Loads `Application` + `JobPosting`.
2. Computes `ask_home_office = not job.mentions_home_office_policy` (null → True),
   same for `ask_part_time`.
3. If both are False → 400 `{detail: "Posting covers both topics."}`.
4. Loads user's `InquiryPromptTemplate.source_md` (seeds default if absent).
5. Calls `inquiry.draft(...)`. On LLM error → 502.
6. Saves `inquiry_subject`, `inquiry_body` onto `Application`.
7. `recipient` in response = `job_posting.application_email` (may be null).

`PATCH /inquiry`: saves user edits to `inquiry_subject`/`inquiry_body`.
`POST /inquiry/mark-sent`: sets `inquiry_sent_at = func.now()`.

Application GET response gains: `inquiry_subject`, `inquiry_body`,
`inquiry_sent_at`, plus the two `JobPosting` flags so the UI can decide the
button state without a second request.

### Settings (`api/inquiry_prompt.py`, new file mounted under `/api/settings`)

| Method | Path                          | Body              | Response          |
|--------|-------------------------------|-------------------|-------------------|
| GET    | `/api/settings/inquiry-prompt`| —                 | `{source_md}`     |
| PUT    | `/api/settings/inquiry-prompt`| `{source_md}`     | `{source_md}`     |

GET seeds `DEFAULT_TEMPLATE` from `inquiry/prompts.py` on first call.

## Frontend

### New `SettingsInquiryPrompt.tsx`

- Mirror `SettingsAnschreiben.tsx`.
- Single textarea bound to `source_md`. Save button → PUT.
- Mounted in `App.tsx` settings route alongside CV and Anschreiben.

### New `InquiryPanel.tsx` on `ApplicationDetail`

Reads from the application response:
- `mentions_home_office_policy`, `mentions_part_time` (from `job_posting`)
- `inquiry_subject`, `inquiry_body`, `inquiry_sent_at` (from `application`)
- `application_email` (from `job_posting`)

States:

| Condition                                                            | UI                                                                                       |
|----------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| `job_state` not in `{extracted, ready}`                              | Panel hidden / shows "waiting for extraction"                                            |
| Both flags true                                                      | Disabled note: "Posting covers both topics — no inquiry needed."                         |
| At least one flag false AND no draft yet                             | Button **Draft inquiry**                                                                 |
| Draft exists, not yet marked sent                                    | Editable subject + body, buttons: **Save**, **Open in mail**, **Mark sent**, **Regenerate** |
| `inquiry_sent_at` set                                                | Read-only view + badge "Sent {date}"; **Regenerate** still available (confirm)           |

Behaviors:

- **Open in mail**: `mailto:{application_email}?subject={enc}&body={enc}`.
  Disabled with tooltip if `application_email` is null.
- **Regenerate**: if a draft already exists, confirm dialog before POSTing
  `/inquiry/draft` again (will overwrite).
- After draft response: subject/body populate the inputs; user can edit and
  Save.

## Error handling

| Situation                                  | Behavior                                                |
|--------------------------------------------|---------------------------------------------------------|
| LLM call fails                             | 502 from backend; UI toast "Draft failed, try again".   |
| No `application_email` on posting          | Mailto disabled, tooltip "Add recipient manually". Copy still works. |
| Both flags true (no topics to ask)         | Backend 400, UI shouldn't have offered the button anyway. |
| Legacy postings (flags null)               | Treated as false → button enabled, user decides.        |
| Concurrent edits                           | Last write wins (matches existing app behavior).        |

## Testing

### Backend (`backend/tests/`)

- `test_extractor.py`: mocked LLM returns JSON with both bools → assert
  fields propagate to `JobPosting` after `run_extract`.
- `test_inquiry.py`: `user_prompt` includes only the requested topics in
  each of `{HO only, PT only, both}`; `draft()` returns parsed `InquiryEmail`
  from mocked LLM.
- `test_api_applications.py`: `draft` happy path, `draft` when both flags
  true → 400, `PATCH` updates, `mark-sent` sets timestamp.
- `test_api_inquiry_prompt.py`: GET seeds default on first call, PUT updates.

### Frontend (`frontend/tests/`)

- Playwright: button disabled when both flags true, enabled otherwise;
  after draft the textareas appear; mailto link well-formed; Mark sent
  toggles badge.

## Out of scope

- Sending the email through Microsoft Graph (planned later, requires
  additional scopes).
- Multiple inquiry prompt variants per user.
- Tracking responses / threading.
- Auto-generation immediately after extract.
