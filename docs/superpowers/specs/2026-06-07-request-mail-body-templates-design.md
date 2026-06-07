# Editable DE/EN Request-Mail Body Templates

**Date:** 2026-06-07
**Status:** Approved (design)

## Problem

The pre-application inquiry ("Request Mail") body is assembled in Python by
`build_body` (`backend/app/inquiry/prompts.py`). The wrapper prose, the
singular/plural count phrase, and the "Janik Viertel" signature are hardcoded
per language and are **not editable in the UI**. Only the LLM-generated greeting
(`Anrede`) and the four question texts are configurable, and they live in
separate settings fields. The result feels "split up": there is no single place
to see or edit the whole mail.

## Goal

Give the user two editable textareas — German and English — that each hold the
**entire** mail body as a template with placeholders (greeting, title,
reference, questions, signature). Editing happens in the existing
`SettingsInquiryPrompt` page. When a template is left blank, the current
hardcoded wording is used as the default.

## Decisions (from brainstorming)

- **Full body in each textarea**: greeting placeholder → intro prose → questions
  slot → closing → signature. Most editable, fully consolidated.
- **Always two questions.** No singular/plural logic. Plural wording is baked
  into the default template text. (Accepted consequence: if only one question is
  ever asked, the default wording's number won't agree.)
- Questions are still injected via the `{questions}` placeholder, sourced from
  the existing four question fields. Greeting still comes from the LLM via
  `{greeting}`.
- Free-form body may contain stray `{`/`}`; substitution uses explicit
  `.replace()` of known tokens, **not** `str.format`, so stray braces are safe.

## Placeholders

| Token                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| `{greeting}`         | LLM-generated Anrede, e.g. `Sehr geehrte Frau Müller`        |
| `{title}`            | Job title                                                    |
| `{ref}`              | Pre-formatted ` (Ref. 123)` suffix, or empty string if none  |
| `{questions}`        | Bullet block built from the configured question texts        |
| `{company}`          | Company name (bonus; cheap to thread through)                |
| `{reference_number}` | Raw reference number, or empty string                        |

## Changes

### 1. Data model — `backend/app/db/models.py`
`InquiryPromptTemplate` gains two nullable Text columns:
```python
body_template_de: Mapped[str | None] = mapped_column(Text, nullable=True)
body_template_en: Mapped[str | None] = mapped_column(Text, nullable=True)
```
`null` = use code default.

### 2. Migration
New Alembic revision with `down_revision = "e1f2a3b4c5d6"` (the current head),
structured like `e0f1a2b3c4d5_inquiry_prompt_user_template`:
- `upgrade`: `op.add_column` for both columns, nullable.
- `downgrade`: `op.drop_column` for both.

### 3. Backend — `backend/app/inquiry/prompts.py`
Add default templates (current prose, plural baked in, signature included):

```
DEFAULT_BODY_TEMPLATE_DE:
{greeting},

ich interessiere mich sehr für Ihre Stellenausschreibung als „{title}{ref}“. Bevor ich meine Bewerbung einreiche, hätte ich zwei kurze Fragen:

{questions}

Vielen Dank im Voraus für Ihre Rückmeldung und mit freundlichen Grüßen
Janik Viertel
```

```
DEFAULT_BODY_TEMPLATE_EN:
{greeting},

I am very interested in your job posting for the position of "{title}{ref}". Before submitting my application, I have a couple of questions:

{questions}

Thank you in advance for your reply.

Kind regards
Janik Viertel
```

`build_body(...)` signature gains `template: str | None = None` and
`company: str | None = None`. Logic:
- Compute `ref` suffix (` (Ref. {ref_number})` or `""`) and `q_block` as today.
- `tpl = template or (DEFAULT_BODY_TEMPLATE_EN if lang == "en" else DEFAULT_BODY_TEMPLATE_DE)`.
- Substitute the six known tokens via a dict + `.replace()` loop.
- Old `count`/singular-plural branch is removed.

### 4. `backend/app/inquiry/__init__.py` — `draft()`
Add `body_de: str | None = None` and `body_en: str | None = None` params. Pick
by language and pass to `build_body` as `template`, plus `company=job.company`.

### 5. `backend/app/api/applications.py` — `draft_inquiry`
Pass `body_de=prompt_row.body_template_de`, `body_en=prompt_row.body_template_en`
into `inquiry_draft(...)`.

### 6. `backend/app/api/inquiry_prompt.py`
Add `body_template_de` / `body_template_en` to `InquiryPromptOut`,
`InquiryPromptPut`, `_row_to_out`, and `put_prompt` (empty string → `None`).

### 7. Frontend
- `frontend/src/api/inquiry.ts`: add `body_template_de` / `body_template_en`
  (`string | null`) to the `InquiryPrompt` type.
- `frontend/src/pages/SettingsInquiryPrompt.tsx`:
  - Mirror `DEFAULT_BODY_TEMPLATE_DE` / `_EN` as TS consts for placeholder text.
  - New `<section>` "Request mail body" with two `Field` textareas (DE/EN,
    ~12 rows), plus a code-chip list of available placeholders.
  - Add both fields to the `draft` initial state and the `set` flow.

## Testing

- **prompts unit** (`backend/tests`): `build_body` with a custom template
  substitutes all tokens; with `template=None` returns the existing default
  wording (DE and EN).
- **migration test** (`backend/tests/integration`): after `upgrade`, the two new
  columns exist on `inquiry_prompt_template`. (Per project rule: integration
  tests build schema from models, not migrations, so schema changes get an
  explicit migration test.)
- **API round-trip**: `PUT` body templates, then `GET` returns them; blank
  values round-trip to `null`.

## Out of scope

- Per-application overrides of the body template (templates are user-level).
- Rich-text / WYSIWYG editing — plain textareas only.
- Variable question count wording.
