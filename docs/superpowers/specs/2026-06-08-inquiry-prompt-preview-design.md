# Inquiry-prompt settings: live pipeline preview

Date: 2026-06-08
Status: Approved (design)

## Problem

The `/settings/inquiry-prompt` page (`frontend/src/pages/SettingsInquiryPrompt.tsx`)
is a flat list of textareas: system prompt, user-prompt template, four question-text
overrides, two body templates. Nothing on the page shows how the parts compose. In
particular it is invisible that:

- `{greeting}` in the body template is **LLM output**, not something the user writes.
- `{questions}` is **the user's question-text fields**, and is formatted two different
  ways — a bulleted block in the user prompt, plain newline-joined lines in the email body.

The user asked for either one merged field or a clearer overview of what the placeholders
resolve to. A merged field was rejected (it only hides delimiters). The chosen direction
is a **live, read-only pipeline preview** beside the existing fields.

## Goals

- Show, with sample data, the full pipeline as three stages: **① prompt sent to the LLM
  → ② LLM returns (sample subject + greeting) → ③ final assembled email**.
- Make the origin of `{greeting}` (LLM) and `{questions}` (user fields) visually obvious
  by colour-coding the same spans in both the prompt and the email.
- Preview reflects the **current unsaved draft** and updates as the user edits.
- Preview is produced by the **real** backend rendering functions, so it cannot drift
  from what production actually emits.

## Non-goals (deliberately out of scope — keep it small)

- No editable sample inputs. One hardcoded sample job.
- No real LLM call. Greeting and subject for stage ② are canned constants.
- No new DB columns, no persistence of preview state.
- No "rendering" of the system prompt — it is static text, echoed as-is.
- No controls beyond a DE/EN language toggle.

## Architecture

### Backend — new preview endpoint

Add to `backend/app/api/inquiry_prompt.py`:

```
POST /api/settings/inquiry-prompt/preview
```

- **Request body:** reuse the existing `InquiryPromptPut` model (the unsaved draft). The
  endpoint renders from the request body, never from the DB, and performs **no writes**.
- **Auth:** same `current_user` dependency as the GET/PUT.
- **No LLM, no DB mutation.**

Rendering, per language `lang in ("de", "en")`, reuses the real functions in
`backend/app/inquiry/prompts.py`:

- `user_prompt(job=_SAMPLE_JOB, language=lang, ask_home_office=True, ask_part_time=True,
  template=draft.user_prompt_md or None, ho_de=…, ho_en=…, pt_de=…, pt_en=…)`
  — both topics forced `True` so the preview always shows both question lines.
- topic lines for the body come from the same `_topic_lines(lang, True, True, …)` the
  user prompt uses, then `build_body(greeting=_SAMPLE_GREETING[lang], title=_SAMPLE_JOB.title,
  ref_number=_SAMPLE_JOB.reference_number, questions=topics, language=lang,
  template=draft.body_template_de/en or None, company=_SAMPLE_JOB.company)`.

Because rendering goes through `user_prompt()` / `build_body()` unchanged, the two
different `{questions}` formats and all token substitution are exactly production-faithful.
(Note: in the email, question lines are **not** bulleted — `build_body` newline-joins them;
the bullets only appear in the user prompt. The mockup's dashes in stage ③ were illustrative.)

Sample fixtures (module-level constants in `inquiry_prompt.py` or `prompts.py`):

```python
_SAMPLE_JOB = ExtractedJobPosting(
    title="Data Engineer",
    company="Acme GmbH",
    contact=ContactInfo(name="Müller"),
    reference_number="7",
    language="de",
)
_SAMPLE_GREETING = {"de": "Sehr geehrte Frau Müller", "en": "Dear Ms Müller"}
_SAMPLE_SUBJECT  = {"de": "Offene Fragen – Data Engineer (Ref. 7)",
                    "en": "Open questions – Data Engineer (Ref. 7)"}
```

**Response model** `InquiryPreviewOut`:

```python
class InquiryPreviewLang(BaseModel):
    system_prompt: str   # echo of draft.source_md
    user_prompt: str     # rendered stage ①
    subject: str         # canned, stage ②
    greeting: str        # canned, stage ②
    email: str           # rendered stage ③

class InquiryPreviewOut(BaseModel):
    de: InquiryPreviewLang
    en: InquiryPreviewLang
```

### Frontend — preview pane

`frontend/src/api/inquiry.ts`: add the types above and
`inquiryPrompt.preview(body: InquiryPrompt) => POST /api/settings/inquiry-prompt/preview`.

`frontend/src/pages/SettingsInquiryPrompt.tsx`:

- Keep every existing field and the `Field` component unchanged.
- Wrap the page in a two-column layout (approved option A): left = existing edit fields,
  right = sticky preview. Collapses to single column / preview-below on narrow screens.
- Preview pane:
  - DE/EN toggle (default DE).
  - **Stage ①** "Sent to the LLM" — system + rendered user prompt. **Collapsed by default**
    behind a `▸ show prompt sent to the LLM` disclosure; the page leads with the email.
  - **Stage ②** "LLM returns (sample)" — subject + greeting.
  - **Stage ③** "Final email" — rendered `email`, the visual focus.
  - Colour spans: greeting (amber) and the question lines (blue), applied in both ① and ③.
    Implemented by wrapping the known canned greeting / question-text substrings; if a
    substring isn't found (custom template moved it), skip the highlight — never corrupt text.
  - Footer note: "Preview uses a fixed sample job: Data Engineer @ Acme GmbH, Frau Müller,
    Ref 7. Greeting is illustrative — the real one is generated per job."
- Data fetch: debounce the draft ~400 ms; fetch via react-query keyed on the debounced
  draft. Show stale preview while refetching (no flicker); show a small inline error if the
  request fails. Preview is independent of Save — it reflects the live draft.

## Data flow

```
draft (unsaved)
  └─ debounce 400ms ─▶ POST /preview ─▶ user_prompt() + build_body()  (real fns, sample job)
                                          │
                                          ▼
                       { de:{system,user,subject,greeting,email}, en:{…} }
                                          │
        right pane renders 3 stages, greeting=amber / questions=blue in ① and ③
```

## Edge cases

- **Cleared optional fields:** frontend already sends `value || null`; backend already maps
  `body.x or None` → defaults apply, same as PUT. Preview shows the default wording.
- **Custom templates that drop a token:** `build_body`'s `_TOKEN_RE.sub` only replaces known
  tokens; unknown braces pass through untouched. Highlight spans are best-effort substring
  matches and skip silently when not found.
- **Rapid typing:** debounce + stale-while-loading prevents request floods and flicker.
- **Long templates:** preview pane scrolls within the sticky column.

## Testing

- **Backend unit (DB-free):** test the render helper directly (no Testcontainers needed) —
  empty draft → email contains the canned greeting and both default question texts for DE
  and EN; a custom `body_template_de` is reflected; a custom `question_home_office_de`
  appears in both `user_prompt` and `email`.
- **Backend integration:** `POST /preview` returns 200 with both languages and performs no
  DB write (row count / `updated_at` unchanged).
- **Frontend:** component renders three stages from a mocked `preview` response; DE/EN
  toggle switches content; collapsed stage ① expands on click. (Avoid Playwright e2e in the
  sandbox — known to SIGSEGV; verify the full page manually in the built Docker image.)
- **Manual verification:** rebuild the frontend Docker image, load the settings page, edit a
  body template and a question text, confirm the preview updates and the highlight colours
  track greeting vs questions in both stages.

## Files touched

- `backend/app/api/inquiry_prompt.py` — preview route, response models, sample fixtures.
- `backend/app/inquiry/prompts.py` — (optional) home for sample constants if shared.
- `backend/tests/…` — preview render unit test + endpoint test.
- `frontend/src/api/inquiry.ts` — preview types + call.
- `frontend/src/pages/SettingsInquiryPrompt.tsx` — two-column layout + preview pane.
