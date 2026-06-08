# Inquiry-prompt Live Pipeline Preview — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, live preview to the inquiry-prompt settings page that shows the full pipeline (prompt → sample LLM output → final email) rendered from the user's unsaved draft.

**Architecture:** A new no-write `POST /api/settings/inquiry-prompt/preview` renders DE+EN through the real `user_prompt()` / `build_body()` with a fixed sample job and a canned greeting (no LLM, no DB). The React page keeps every existing field and adds a sticky preview pane that debounce-fetches the endpoint and colour-codes greeting (LLM) vs questions (user fields). Highlight logic is a pure TS function so it is unit-testable; the React pane is verified manually.

**Tech Stack:** FastAPI + Pydantic + pytest (backend); React 18 + @tanstack/react-query + Tailwind, `node --test` for pure-TS units (frontend).

Spec: `docs/superpowers/specs/2026-06-08-inquiry-prompt-preview-design.md`

---

## File Structure

- Create `backend/app/inquiry/preview.py` — sample fixtures + `build_preview()` render (DB-free, LLM-free).
- Modify `backend/app/api/inquiry_prompt.py` — add `InquiryPreviewOut`/`InquiryPreviewLang` models + `POST /preview` route. (Route is added to the existing `router`, already mounted — no `main.py` change.)
- Create `backend/tests/unit/test_inquiry_preview.py` — DB-free unit tests for `build_preview()`.
- Create `backend/tests/integration/test_inquiry_preview_endpoint.py` — auth + endpoint tests.
- Create `frontend/src/lib/inquiryHighlight.ts` — pure segmenter for colour highlighting.
- Create `frontend/src/lib/inquiryHighlight.test.ts` — `node --test` units.
- Modify `frontend/src/api/inquiry.ts` — preview types + `inquiryPrompt.preview()`.
- Create `frontend/src/components/InquiryPreview.tsx` — presentational pipeline pane.
- Modify `frontend/src/pages/SettingsInquiryPrompt.tsx` — two-column layout + debounced fetch.

---

## Task 1: Backend — `build_preview()` render function (DB-free)

**Files:**
- Create: `backend/app/inquiry/preview.py`
- Test: `backend/tests/unit/test_inquiry_preview.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_inquiry_preview.py`:

```python
from app.inquiry.preview import build_preview


def test_preview_renders_both_languages_with_sample_greeting():
    out = build_preview(source_md="SYS")
    assert set(out) == {"de", "en"}
    assert out["de"]["system_prompt"] == "SYS"
    assert out["de"]["greeting"] == "Sehr geehrte Frau Müller"
    assert out["en"]["greeting"] == "Dear Ms Müller"
    # canned subject + greeting land in stage 2 / stage 3
    assert out["de"]["subject"]
    assert out["de"]["greeting"] in out["de"]["email"]


def test_preview_questions_list_is_populated_and_present_in_email():
    de = build_preview(source_md="SYS")["de"]
    assert isinstance(de["questions"], list) and len(de["questions"]) == 2
    for q in de["questions"]:
        assert q in de["email"]
        assert q in de["user_prompt"]


def test_preview_custom_question_text_flows_through_de():
    de = build_preview(source_md="SYS", question_home_office_de="WUNSCH_HO_DE?")["de"]
    assert "WUNSCH_HO_DE?" in de["user_prompt"]
    assert "WUNSCH_HO_DE?" in de["email"]
    assert "WUNSCH_HO_DE?" in de["questions"]


def test_preview_custom_body_template_de_is_used():
    de = build_preview(source_md="SYS", body_template_de="DE::{greeting}::{questions}")["de"]
    assert de["email"].startswith("DE::Sehr geehrte Frau Müller::")


def test_preview_default_de_topics_use_backend_defaults():
    de = build_preview(source_md="SYS")["de"]
    assert "Homeoffice" in de["email"]  # DEFAULT_HO_TOPIC_DE wording
    assert "80" in de["email"]          # DEFAULT_PT_TOPIC_DE wording
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_inquiry_preview.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.inquiry.preview'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/inquiry/preview.py`:

```python
from app.extractor.schemas import ContactInfo, ExtractedJobPosting
from app.inquiry.prompts import _topic_lines, build_body, user_prompt

SAMPLE_JOB = ExtractedJobPosting(
    title="Data Engineer",
    company="Acme GmbH",
    contact=ContactInfo(name="Müller"),
    reference_number="7",
    language="de",
)
SAMPLE_GREETING = {"de": "Sehr geehrte Frau Müller", "en": "Dear Ms Müller"}
SAMPLE_SUBJECT = {
    "de": "Offene Fragen – Data Engineer (Ref. 7)",
    "en": "Open questions – Data Engineer (Ref. 7)",
}


def _render_lang(
    lang: str,
    *,
    source_md: str,
    user_prompt_md: str | None,
    ho_de: str | None,
    ho_en: str | None,
    pt_de: str | None,
    pt_en: str | None,
    body_de: str | None,
    body_en: str | None,
) -> dict:
    up = user_prompt(
        job=SAMPLE_JOB,
        language=lang,
        ask_home_office=True,
        ask_part_time=True,
        template=user_prompt_md or None,
        ho_de=ho_de,
        ho_en=ho_en,
        pt_de=pt_de,
        pt_en=pt_en,
    )
    topics = _topic_lines(lang, True, True, ho_de, ho_en, pt_de, pt_en)
    body_tpl = (body_en if lang == "en" else body_de) or None
    email = build_body(
        greeting=SAMPLE_GREETING[lang],
        title=SAMPLE_JOB.title or "",
        ref_number=SAMPLE_JOB.reference_number,
        questions=topics,
        language=lang,
        template=body_tpl,
        company=SAMPLE_JOB.company,
    )
    return {
        "system_prompt": source_md,
        "user_prompt": up,
        "subject": SAMPLE_SUBJECT[lang],
        "greeting": SAMPLE_GREETING[lang],
        "questions": topics,
        "email": email,
    }


def build_preview(
    *,
    source_md: str,
    user_prompt_md: str | None = None,
    question_home_office_de: str | None = None,
    question_home_office_en: str | None = None,
    question_part_time_de: str | None = None,
    question_part_time_en: str | None = None,
    body_template_de: str | None = None,
    body_template_en: str | None = None,
) -> dict:
    kw = dict(
        source_md=source_md,
        user_prompt_md=user_prompt_md,
        ho_de=question_home_office_de,
        ho_en=question_home_office_en,
        pt_de=question_part_time_de,
        pt_en=question_part_time_en,
        body_de=body_template_de,
        body_en=body_template_en,
    )
    return {"de": _render_lang("de", **kw), "en": _render_lang("en", **kw)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_inquiry_preview.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/inquiry/preview.py backend/tests/unit/test_inquiry_preview.py
git commit -m "feat(inquiry): build_preview renders sample pipeline for settings preview"
```

---

## Task 2: Backend — `POST /preview` endpoint

**Files:**
- Modify: `backend/app/api/inquiry_prompt.py`
- Test: `backend/tests/integration/test_inquiry_preview_endpoint.py`

> Integration tests use Testcontainers (real Postgres) and need Docker. If Docker is unavailable in this environment, run this task's tests in a terminal with Docker. Task 1's unit test already covers the rendering logic DB-free.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_inquiry_preview_endpoint.py`:

```python
def test_preview_requires_auth(app_client):
    r = app_client.post("/api/settings/inquiry-prompt/preview", json={"source_md": "x"})
    assert r.status_code == 401


def test_preview_returns_both_languages(auth_user):
    client, _ = auth_user
    r = client.post("/api/settings/inquiry-prompt/preview", json={"source_md": "SYS"})
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"de", "en"}
    assert data["de"]["system_prompt"] == "SYS"
    assert data["de"]["greeting"] in data["de"]["email"]
    assert len(data["de"]["questions"]) == 2


def test_preview_reflects_custom_body_template(auth_user):
    client, _ = auth_user
    r = client.post(
        "/api/settings/inquiry-prompt/preview",
        json={"source_md": "SYS", "body_template_de": "DE::{greeting}"},
    )
    assert r.status_code == 200
    assert r.json()["de"]["email"] == "DE::Sehr geehrte Frau Müller"


def test_preview_does_not_write_db(auth_user, db_session):
    from app.db.models import InquiryPromptTemplate

    client, _ = auth_user
    before = db_session.query(InquiryPromptTemplate).count()
    client.post("/api/settings/inquiry-prompt/preview", json={"source_md": "SYS"})
    after = db_session.query(InquiryPromptTemplate).count()
    assert before == after == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/integration/test_inquiry_preview_endpoint.py -v`
Expected: FAIL — POST returns 404/405 (route not defined) so assertions fail.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/inquiry_prompt.py`, add the import near the existing prompts import:

```python
from app.inquiry.preview import build_preview
```

Add the response models after `InquiryPromptPut`:

```python
class InquiryPreviewLang(BaseModel):
    system_prompt: str
    user_prompt: str
    subject: str
    greeting: str
    questions: list[str]
    email: str


class InquiryPreviewOut(BaseModel):
    de: InquiryPreviewLang
    en: InquiryPreviewLang
```

Add the route at the end of the file (auth only — `current_user` already resolves and 401s on its own; no `db_dep`, no writes):

```python
@router.post("/preview", response_model=InquiryPreviewOut)
def preview_prompt(
    body: InquiryPromptPut,
    user: Annotated[User, Depends(current_user)],
):
    return build_preview(**body.model_dump())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/integration/test_inquiry_preview_endpoint.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/inquiry_prompt.py backend/tests/integration/test_inquiry_preview_endpoint.py
git commit -m "feat(inquiry): no-write POST /inquiry-prompt/preview endpoint"
```

---

## Task 3: Frontend — pure highlight segmenter

**Files:**
- Create: `frontend/src/lib/inquiryHighlight.ts`
- Test: `frontend/src/lib/inquiryHighlight.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/inquiryHighlight.test.ts`:

```ts
import test from "node:test";
import assert from "node:assert/strict";
import { highlightSegments } from "./inquiryHighlight.ts";

test("wraps greeting and questions, leaves rest plain", () => {
  const segs = highlightSegments("Hi NAME, see Q1 and Q2 end", [
    { text: "NAME", kind: "greeting" },
    { text: "Q1", kind: "questions" },
    { text: "Q2", kind: "questions" },
  ]);
  assert.deepEqual(segs, [
    { text: "Hi ", kind: null },
    { text: "NAME", kind: "greeting" },
    { text: ", see ", kind: null },
    { text: "Q1", kind: "questions" },
    { text: " and ", kind: null },
    { text: "Q2", kind: "questions" },
    { text: " end", kind: null },
  ]);
});

test("missing target produces no highlight", () => {
  const segs = highlightSegments("plain text", [{ text: "ZZZ", kind: "greeting" }]);
  assert.deepEqual(segs, [{ text: "plain text", kind: null }]);
});

test("empty target is ignored", () => {
  const segs = highlightSegments("abc", [{ text: "", kind: "greeting" }]);
  assert.deepEqual(segs, [{ text: "abc", kind: null }]);
});

test("overlapping matches: first wins, no double-wrap", () => {
  const segs = highlightSegments("abcdef", [
    { text: "abcd", kind: "greeting" },
    { text: "cdef", kind: "questions" },
  ]);
  assert.deepEqual(segs, [
    { text: "abcd", kind: "greeting" },
    { text: "ef", kind: null },
  ]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit`
Expected: FAIL — cannot resolve `./inquiryHighlight.ts`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/lib/inquiryHighlight.ts`:

```ts
export type SegmentKind = "greeting" | "questions";

export interface Segment {
  text: string;
  kind: SegmentKind | null;
}

export interface HighlightTarget {
  text: string;
  kind: SegmentKind;
}

export function highlightSegments(text: string, targets: HighlightTarget[]): Segment[] {
  const ranges: { start: number; end: number; kind: SegmentKind }[] = [];
  for (const t of targets) {
    if (!t.text) continue;
    let from = 0;
    let i = text.indexOf(t.text, from);
    while (i !== -1) {
      ranges.push({ start: i, end: i + t.text.length, kind: t.kind });
      from = i + t.text.length;
      i = text.indexOf(t.text, from);
    }
  }
  // earliest start first; on a tie prefer the longer match
  ranges.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start));

  const out: Segment[] = [];
  let pos = 0;
  for (const r of ranges) {
    if (r.start < pos) continue; // overlaps an already-emitted highlight
    if (r.start > pos) out.push({ text: text.slice(pos, r.start), kind: null });
    out.push({ text: text.slice(r.start, r.end), kind: r.kind });
    pos = r.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), kind: null });
  return out;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit`
Expected: PASS (existing lib tests + 4 new ones).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/inquiryHighlight.ts frontend/src/lib/inquiryHighlight.test.ts
git commit -m "feat(inquiry): pure highlight segmenter for preview colour-coding"
```

---

## Task 4: Frontend — preview API types + call

**Files:**
- Modify: `frontend/src/api/inquiry.ts`

(No unit test — thin typed wrapper over `api()`. Verified by `tsc` in Task 5.)

- [ ] **Step 1: Add types and the `preview` call**

In `frontend/src/api/inquiry.ts`, after the `InquiryPrompt` type add:

```ts
export type InquiryPreviewLang = {
  system_prompt: string;
  user_prompt: string;
  subject: string;
  greeting: string;
  questions: string[];
  email: string;
};

export type InquiryPreviewOut = {
  de: InquiryPreviewLang;
  en: InquiryPreviewLang;
};
```

Inside the `inquiryPrompt` object, after `put`, add:

```ts
  preview: (body: InquiryPrompt) =>
    api<InquiryPreviewOut>("/api/settings/inquiry-prompt/preview", {
      method: "POST",
      body: JSON.stringify(body),
    }),
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/inquiry.ts
git commit -m "feat(inquiry): preview API types and client call"
```

---

## Task 5: Frontend — preview pane component + page layout

**Files:**
- Create: `frontend/src/components/InquiryPreview.tsx`
- Modify: `frontend/src/pages/SettingsInquiryPrompt.tsx`

- [ ] **Step 1: Create the presentational component**

Create `frontend/src/components/InquiryPreview.tsx`:

```tsx
import { useState } from "react";
import type { InquiryPreviewOut } from "../api/inquiry";
import { highlightSegments } from "../lib/inquiryHighlight";

const SAMPLE_NOTE =
  "Preview uses a fixed sample job: Data Engineer @ Acme GmbH, contact Frau Müller, Ref 7. " +
  "Greeting is illustrative — the real one is generated per job.";

function Highlighted({
  text,
  greeting,
  questions,
}: {
  text: string;
  greeting: string;
  questions: string[];
}) {
  const segs = highlightSegments(text, [
    { text: greeting, kind: "greeting" },
    ...questions.map((q) => ({ text: q, kind: "questions" as const })),
  ]);
  return (
    <>
      {segs.map((s, i) =>
        s.kind === null ? (
          <span key={i}>{s.text}</span>
        ) : (
          <mark
            key={i}
            className={s.kind === "greeting" ? "bg-amber-200" : "bg-blue-200"}
          >
            {s.text}
          </mark>
        ),
      )}
    </>
  );
}

export default function InquiryPreview({
  data,
  loading,
  error,
}: {
  data: InquiryPreviewOut | undefined;
  loading: boolean;
  error: string | null;
}) {
  const [lang, setLang] = useState<"de" | "en">("de");
  const [showPrompt, setShowPrompt] = useState(false);
  const block = data?.[lang];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Live preview{loading ? " · updating…" : ""}
        </span>
        <div className="inline-flex rounded border border-slate-300 text-xs font-semibold overflow-hidden">
          {(["de", "en"] as const).map((l) => (
            <button
              key={l}
              type="button"
              className={
                l === lang
                  ? "px-3 py-1 bg-slate-900 text-white"
                  : "px-3 py-1 bg-white text-slate-500"
              }
              onClick={() => setLang(l)}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="text-rose-600 text-sm">{error}</div>}
      {!block && !error && (
        <div className="text-slate-400 text-sm">Loading preview…</div>
      )}

      {block && (
        <>
          <div className="border rounded-lg p-3">
            <button
              type="button"
              className="text-xs font-bold text-slate-900"
              onClick={() => setShowPrompt((v) => !v)}
            >
              {showPrompt ? "▾" : "▸"} ① Prompt sent to the LLM
            </button>
            {showPrompt && (
              <div className="mt-2 space-y-2">
                <div className="text-[11px] uppercase text-slate-400">system</div>
                <pre className="whitespace-pre-wrap font-mono text-xs text-slate-600">
                  {block.system_prompt}
                </pre>
                <div className="text-[11px] uppercase text-slate-400">user</div>
                <pre className="whitespace-pre-wrap font-mono text-xs text-slate-600">
                  <Highlighted
                    text={block.user_prompt}
                    greeting={block.greeting}
                    questions={block.questions}
                  />
                </pre>
              </div>
            )}
          </div>

          <div className="text-center text-slate-400">↓</div>

          <div className="border rounded-lg p-3">
            <div className="text-xs font-bold text-slate-900 mb-2">
              ② LLM returns <span className="font-normal text-slate-400">(sample)</span>
            </div>
            <pre className="whitespace-pre-wrap font-mono text-xs text-slate-600">
              {"subject:  "}
              {block.subject}
              {"\ngreeting: "}
              <mark className="bg-amber-200">{block.greeting}</mark>
            </pre>
          </div>

          <div className="text-center text-slate-400">↓</div>

          <div className="border rounded-lg p-3">
            <div className="text-xs font-bold text-slate-900 mb-2">
              ③ Final email{" "}
              <span className="font-normal text-slate-400">(assembled in code)</span>
            </div>
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
              <Highlighted
                text={block.email}
                greeting={block.greeting}
                questions={block.questions}
              />
            </div>
          </div>

          <div className="text-[11px] text-slate-500">
            <mark className="bg-amber-200">greeting</mark> = LLM output ·{" "}
            <mark className="bg-blue-200">questions</mark> = your Question-texts fields
          </div>
          <div className="text-[11px] text-slate-400">{SAMPLE_NOTE}</div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire the page — imports + debounced preview query**

In `frontend/src/pages/SettingsInquiryPrompt.tsx`, update the imports at the top:

```tsx
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { inquiryPrompt, type InquiryPrompt } from "../api/inquiry";
import InquiryPreview from "../components/InquiryPreview";
```

Immediately after the existing `save` mutation block (before `if (q.isLoading)`), add the debounced preview fetch:

```tsx
  const [debounced, setDebounced] = useState<InquiryPrompt>(draft);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(draft), 400);
    return () => clearTimeout(t);
  }, [draft]);

  const preview = useQuery({
    queryKey: ["inquiry-preview", debounced],
    queryFn: () => inquiryPrompt.preview(debounced),
    enabled: !q.isLoading,
    placeholderData: (prev) => prev,
  });
```

- [ ] **Step 3: Wire the page — two-column layout**

Replace the outer wrapper. The current return is:

```tsx
  return (
    <div className="p-6 max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-xl font-semibold mb-2">Pre-application inquiry prompt</h1>
```

Change the opening so the existing content becomes the left column and the preview is the right column. Replace those three lines with:

```tsx
  return (
    <div className="p-6 max-w-6xl mx-auto lg:grid lg:grid-cols-2 lg:gap-8">
      <div className="space-y-8">
        <div>
          <h1 className="text-xl font-semibold mb-2">Pre-application inquiry prompt</h1>
```

Then find the closing of the component's outer `div` (the final `</div>` before the closing `);` of the return) and, just before it, close the left column and add the right column. The end of the return currently looks like:

```tsx
      <div className="flex gap-2 items-center">
        <button
          type="button"
          className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate(draft)}
        >
          Save
        </button>
        {save.isError && (
          <span className="text-rose-600 text-sm">{(save.error as Error).message}</span>
        )}
      </div>
    </div>
  );
```

Replace that trailing section with (note the Save block is unchanged; we add a `</div>` to close the left column and a new right-column `<div>` with the preview):

```tsx
        <div className="flex gap-2 items-center">
          <button
            type="button"
            className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate(draft)}
          >
            Save
          </button>
          {save.isError && (
            <span className="text-rose-600 text-sm">{(save.error as Error).message}</span>
          )}
        </div>
      </div>

      <div className="mt-8 lg:mt-0">
        <div className="lg:sticky lg:top-6">
          <InquiryPreview
            data={preview.data}
            loading={preview.isFetching}
            error={preview.isError ? (preview.error as Error).message : null}
          />
        </div>
      </div>
    </div>
  );
```

> Note: the inner `<section>` blocks between the header and the Save button are unchanged — they keep their existing indentation. Only the outer wrapper (left-column open) and the trailing Save/closing region (left-column close + right column) change. After editing, confirm the JSX still balances.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no errors).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/InquiryPreview.tsx frontend/src/pages/SettingsInquiryPrompt.tsx
git commit -m "feat(inquiry): live pipeline preview pane on settings page"
```

---

## Task 6: Verify end-to-end in the built image

**Files:** none (verification only).

> Per project memory: the app is served from the built Docker image and the harness cannot build it (keychain cred error -50). Ask the user to build/run in their terminal; do not rely on in-container python replays.

- [ ] **Step 1: Backend unit + frontend unit suites (no Docker)**

Run: `cd backend && python -m pytest tests/unit/test_inquiry_preview.py tests/unit/test_inquiry_prompts.py -v`
Expected: PASS.

Run: `cd frontend && npm run test:unit`
Expected: PASS.

- [ ] **Step 2: Backend integration (Docker — user terminal if needed)**

Run: `cd backend && python -m pytest tests/integration/test_inquiry_preview_endpoint.py tests/integration/test_inquiry_prompt_endpoint.py -v`
Expected: PASS.

- [ ] **Step 3: Manual verification in the running image**

Have the user rebuild the frontend image and bring it up (per their normal flow). Then:
- Open `/settings/inquiry-prompt`. Confirm two-column layout, preview on the right.
- Edit `Body — DE` (e.g., change the opening sentence) → within ~0.4s the stage ③ email updates.
- Edit `Home office — DE` question text → it changes in both the expanded stage ① user prompt and stage ③ email.
- Toggle DE/EN → preview switches language.
- Expand "① Prompt sent to the LLM" → shows system + user prompt; collapsed by default.
- Confirm greeting renders amber and the two question lines render blue in both stages.

- [ ] **Step 4: Final commit (if any tweaks were needed)**

```bash
git add -A
git commit -m "chore(inquiry): preview verification tweaks"
```

(Skip if no changes.)

---

## Self-Review

- **Spec coverage:** ① pipeline (Task 1/5), real-function rendering no-drift (Task 1), unsaved-draft + debounced live update (Task 5), greeting/questions colour mapping (Task 3/5), no LLM/no DB write (Task 1/2 + `test_preview_does_not_write_db`), DE/EN toggle + stage ① collapsed (Task 5), fixed sample + illustrative-greeting note (Task 1 constants + Task 5 note). Non-goals respected — no editable samples, no new DB columns, no extra toggles.
- **Placeholders:** none — every code/test step is complete.
- **Type consistency:** `build_preview(**body.model_dump())` keys match `InquiryPromptPut`/`InquiryPrompt` field names; response keys (`system_prompt,user_prompt,subject,greeting,questions,email`) match `InquiryPreviewLang` (py) and `InquiryPreviewLang` (ts); `highlightSegments`/`Segment`/`HighlightTarget`/`SegmentKind` consistent across `inquiryHighlight.ts`, its test, and `InquiryPreview.tsx`.
