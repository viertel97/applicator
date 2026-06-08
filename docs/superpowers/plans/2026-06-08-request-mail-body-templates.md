# Editable DE/EN Request-Mail Body Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user edit the entire inquiry-mail body (DE + EN) as a placeholder template in `SettingsInquiryPrompt`, falling back to current hardcoded wording when blank.

**Architecture:** Two nullable Text columns on `inquiry_prompt_template` store the templates. `build_body` substitutes six known tokens via `.replace()` (not `str.format`, so stray `{`/`}` are safe) against the stored template or a code default. The template flows DB → `inquiry_prompt.py` API → `applications.draft_inquiry` → `inquiry.draft` → `build_body`. Frontend adds two textareas wired to the existing draft/save flow.

**Tech Stack:** FastAPI, SQLAlchemy 2 (Mapped), Alembic, Pydantic v2, React + TanStack Query + TypeScript, pytest + testcontainers.

---

## File Structure

- `backend/app/inquiry/prompts.py` — add `DEFAULT_BODY_TEMPLATE_DE/_EN`; rewrite `build_body` to template + `.replace()` substitution. (Task 1)
- `backend/app/db/models.py` — `InquiryPromptTemplate` gains `body_template_de`, `body_template_en`. (Task 2)
- `backend/alembic/versions/f2a3b4c5d6e7_inquiry_prompt_body_template.py` — new migration. (Task 3)
- `backend/tests/integration/test_inquiry_body_template_migration.py` — alembic round-trip. (Task 3)
- `backend/app/inquiry/__init__.py` — `draft()` gains `body_de`/`body_en`. (Task 4)
- `backend/app/api/applications.py` — `draft_inquiry` threads the body templates. (Task 5)
- `backend/app/api/inquiry_prompt.py` — Out/Put/`_row_to_out`/`put_prompt` gain the two fields. (Task 6)
- `frontend/src/api/inquiry.ts` — `InquiryPrompt` type gains two fields. (Task 7)
- `frontend/src/pages/SettingsInquiryPrompt.tsx` — new "Request mail body" section. (Task 8)

Token reference (used by `build_body`):

| Token                | Value                                          |
|----------------------|------------------------------------------------|
| `{greeting}`         | LLM Anrede, e.g. `Sehr geehrte Frau Müller`    |
| `{title}`            | Job title                                      |
| `{ref}`              | ` (Ref. 123)` suffix, or `""`                  |
| `{questions}`        | `"\n".join(question texts)` (no bullets — matches current output) |
| `{company}`          | Company name, or `""`                          |
| `{reference_number}` | Raw reference number, or `""`                  |

---

### Task 1: Backend default templates + token-substituting `build_body`

**Files:**
- Modify: `backend/app/inquiry/prompts.py:19-50` (the `build_body` function)
- Test: `backend/tests/unit/test_inquiry_prompts.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_inquiry_prompts.py`:

```python
from app.inquiry.prompts import (
    DEFAULT_BODY_TEMPLATE_DE,
    DEFAULT_BODY_TEMPLATE_EN,
    build_body,
)


def test_build_body_default_de_matches_current_wording():
    out = build_body(
        greeting="Sehr geehrte Frau Müller",
        title="Entwickler",
        ref_number="123",
        questions=["Frage eins?", "Frage zwei?"],
        language="de",
    )
    assert out.startswith("Sehr geehrte Frau Müller,\n\n")
    assert "Ihre Stellenausschreibung als „Entwickler (Ref. 123)“." in out
    assert "zwei kurze Fragen:" in out
    assert "Frage eins?\nFrage zwei?" in out
    assert out.endswith("mit freundlichen Grüßen\nJanik Viertel")


def test_build_body_default_en_matches_current_wording():
    out = build_body(
        greeting="Dear Ms Smith",
        title="Developer",
        ref_number=None,
        questions=["Q one?", "Q two?"],
        language="en",
    )
    assert out.startswith("Dear Ms Smith,\n\n")
    assert 'the position of "Developer".' in out
    assert "a couple of questions:" in out
    assert out.endswith("Kind regards\nJanik Viertel")


def test_build_body_custom_template_substitutes_all_tokens():
    tpl = "{greeting}|{title}|{ref}|{company}|{reference_number}|{questions}"
    out = build_body(
        greeting="Hi",
        title="Dev",
        ref_number="42",
        questions=["a", "b"],
        language="en",
        template=tpl,
        company="Acme",
    )
    assert out == "Hi|Dev| (Ref. 42)|Acme|42|a\nb"


def test_build_body_stray_braces_are_safe():
    out = build_body(
        greeting="Hi",
        title="Dev",
        ref_number=None,
        questions=["a"],
        language="en",
        template="{greeting} {oops} {title}",
    )
    assert out == "Hi {oops} Dev"


def test_default_body_templates_are_nonempty():
    assert DEFAULT_BODY_TEMPLATE_DE.strip() and DEFAULT_BODY_TEMPLATE_EN.strip()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/unit/test_inquiry_prompts.py -q`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_BODY_TEMPLATE_DE'`.

- [ ] **Step 3: Implement the templates and new `build_body`**

In `backend/app/inquiry/prompts.py`, replace the whole `build_body` function (lines 19-50) with:

```python
DEFAULT_BODY_TEMPLATE_DE = (
    "{greeting},\n\n"
    "ich interessiere mich sehr für Ihre Stellenausschreibung als "
    "„{title}{ref}“. "
    "Bevor ich meine Bewerbung einreiche, hätte ich zwei kurze Fragen:\n\n"
    "{questions}\n\n"
    "Vielen Dank im Voraus für Ihre Rückmeldung und mit freundlichen Grüßen\n"
    "Janik Viertel"
)

DEFAULT_BODY_TEMPLATE_EN = (
    "{greeting},\n\n"
    'I am very interested in your job posting for the position of "{title}{ref}". '
    "Before submitting my application, I have a couple of questions:\n\n"
    "{questions}\n\n"
    "Thank you in advance for your reply.\n\n"
    "Kind regards\n"
    "Janik Viertel"
)


def build_body(
    greeting: str,
    title: str,
    ref_number: str | None,
    questions: list[str],
    language: str,
    template: str | None = None,
    company: str | None = None,
) -> str:
    lang = (language or "de").lower()
    ref = f" (Ref. {ref_number})" if ref_number else ""
    q_block = "\n".join(questions)
    tpl = template or (
        DEFAULT_BODY_TEMPLATE_EN if lang == "en" else DEFAULT_BODY_TEMPLATE_DE
    )
    tokens = {
        "{greeting}": greeting,
        "{title}": title,
        "{reference_number}": ref_number or "",
        "{ref}": ref,
        "{company}": company or "",
        "{questions}": q_block,
    }
    out = tpl
    for token, value in tokens.items():
        out = out.replace(token, value)
    return out
```

Note: `{reference_number}` is replaced before `{ref}` so the longer token wins; `.replace()` (not `str.format`) keeps stray braces literal.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/unit/test_inquiry_prompts.py -q`
Expected: PASS (all tests green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/inquiry/prompts.py backend/tests/unit/test_inquiry_prompts.py
git commit -m "feat(inquiry): template-driven build_body with DE/EN defaults"
```

---

### Task 2: Data model columns

**Files:**
- Modify: `backend/app/db/models.py:301` (after `question_part_time_en`)

- [ ] **Step 1: Add the columns**

In `backend/app/db/models.py`, in `class InquiryPromptTemplate`, immediately after the line
`    question_part_time_en: Mapped[str | None] = mapped_column(Text, nullable=True)`
insert:

```python
    body_template_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_template_en: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Verify models import cleanly**

Run: `cd backend && .venv/bin/python -c "from app.db.models import InquiryPromptTemplate; print(InquiryPromptTemplate.body_template_de, InquiryPromptTemplate.body_template_en)"`
Expected: prints the two column attributes, no error.

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/models.py
git commit -m "feat(inquiry): body template columns on inquiry_prompt_template"
```

---

### Task 3: Alembic migration + migration round-trip test

The integration `db_session` fixture builds schema via `Base.metadata.create_all` (models, not migrations), so the new columns are auto-present there. Per project rule, schema changes get an explicit alembic test that runs the real migration.

**Files:**
- Create: `backend/alembic/versions/f2a3b4c5d6e7_inquiry_prompt_body_template.py`
- Create: `backend/tests/integration/test_inquiry_body_template_migration.py`

- [ ] **Step 1: Write the failing migration test**

Create `backend/tests/integration/test_inquiry_body_template_migration.py`:

```python
"""Alembic round-trip for inquiry_prompt_template body template columns."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PRIOR_REVISION = "e1f2a3b4c5d6"
BODY_REVISION = "f2a3b4c5d6e7"


def _alembic_cfg(url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def fresh_db(pg_container, monkeypatch):
    raw_url = pg_container.get_connection_url()
    url = (
        raw_url
        .replace("postgresql+psycopg2://", "postgresql+psycopg://")
        .replace("postgresql://", "postgresql+psycopg://")
    )
    monkeypatch.setenv("DATABASE_URL", url)
    engine = sa.create_engine(url, future=True, isolation_level="AUTOCOMMIT")

    def _wipe():
        with engine.connect() as conn:
            conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(sa.text("CREATE SCHEMA public"))

    _wipe()
    yield engine, url
    _wipe()
    engine.dispose()


def _columns(engine):
    with engine.connect() as conn:
        return {
            r[0] for r in conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='inquiry_prompt_template'"
            ))
        }


def test_migration_adds_body_template_columns(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))
    command.upgrade(cfg, BODY_REVISION)
    cols = _columns(engine)
    assert "body_template_de" in cols
    assert "body_template_en" in cols


def test_migration_downgrade_drops_columns(fresh_db):
    engine, _url = fresh_db
    cfg = _alembic_cfg(str(engine.url))
    command.upgrade(cfg, BODY_REVISION)
    command.downgrade(cfg, PRIOR_REVISION)
    cols = _columns(engine)
    assert "body_template_de" not in cols
    assert "body_template_en" not in cols
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/integration/test_inquiry_body_template_migration.py -q`
Expected: FAIL — alembic cannot find revision `f2a3b4c5d6e7` (`KeyError`/`CommandError`).

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/f2a3b4c5d6e7_inquiry_prompt_body_template.py`:

```python
"""inquiry_prompt: editable DE/EN body templates

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-08 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("inquiry_prompt_template", sa.Column("body_template_de", sa.Text(), nullable=True))
    op.add_column("inquiry_prompt_template", sa.Column("body_template_en", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("inquiry_prompt_template", "body_template_en")
    op.drop_column("inquiry_prompt_template", "body_template_de")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/integration/test_inquiry_body_template_migration.py -q`
Expected: PASS (both tests green).

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/f2a3b4c5d6e7_inquiry_prompt_body_template.py backend/tests/integration/test_inquiry_body_template_migration.py
git commit -m "feat(inquiry): migration for body template columns"
```

---

### Task 4: `draft()` accepts and forwards body templates

**Files:**
- Modify: `backend/app/inquiry/__init__.py:7-52`

- [ ] **Step 1: Add params and pass to `build_body`**

In `backend/app/inquiry/__init__.py`, add two params to `draft()` signature (after `pt_en`):

```python
    pt_en: str | None = None,
    body_de: str | None = None,
    body_en: str | None = None,
) -> InquiryEmail:
```

Then replace the `build_body(...)` call (lines 45-51) with:

```python
    body = build_body(
        greeting=llm_out.greeting,
        title=job.title or "",
        ref_number=job.reference_number,
        questions=questions,
        language=language,
        template=(body_en if (language or "de").lower() == "en" else body_de),
        company=job.company,
    )
```

- [ ] **Step 2: Verify import + signature**

Run: `cd backend && .venv/bin/python -c "import inspect; from app.inquiry import draft; print('body_de' in inspect.signature(draft).parameters and 'body_en' in inspect.signature(draft).parameters)"`
Expected: prints `True`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/inquiry/__init__.py
git commit -m "feat(inquiry): thread body templates through draft()"
```

---

### Task 5: `draft_inquiry` passes stored templates

**Files:**
- Modify: `backend/app/api/applications.py:617-629`

- [ ] **Step 1: Pass the template fields**

In `backend/app/api/applications.py`, in the `inquiry_draft(...)` call inside `draft_inquiry`, add after `pt_en=prompt_row.question_part_time_en,`:

```python
            pt_en=prompt_row.question_part_time_en,
            body_de=prompt_row.body_template_de,
            body_en=prompt_row.body_template_en,
        )
```

- [ ] **Step 2: Verify import**

Run: `cd backend && .venv/bin/python -c "import app.api.applications"`
Expected: no output, no error.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/applications.py
git commit -m "feat(inquiry): draft_inquiry forwards stored body templates"
```

---

### Task 6: API schemas + round-trip

**Files:**
- Modify: `backend/app/api/inquiry_prompt.py` (Out, Put, `_row_to_out`, `put_prompt`)
- Test: `backend/tests/integration/test_inquiry_prompt_endpoint.py`

- [ ] **Step 1: Write the failing round-trip test**

Append to `backend/tests/integration/test_inquiry_prompt_endpoint.py`:

```python
def test_body_templates_round_trip(auth_user):
    client, _ = auth_user
    client.get("/api/settings/inquiry-prompt")
    r = client.put(
        "/api/settings/inquiry-prompt",
        json={
            "source_md": "x",
            "body_template_de": "DE body {greeting}",
            "body_template_en": "EN body {greeting}",
        },
    )
    assert r.status_code == 200
    assert r.json()["body_template_de"] == "DE body {greeting}"
    assert r.json()["body_template_en"] == "EN body {greeting}"

    again = client.get("/api/settings/inquiry-prompt").json()
    assert again["body_template_de"] == "DE body {greeting}"
    assert again["body_template_en"] == "EN body {greeting}"


def test_blank_body_template_round_trips_to_null(auth_user):
    client, _ = auth_user
    client.get("/api/settings/inquiry-prompt")
    r = client.put(
        "/api/settings/inquiry-prompt",
        json={"source_md": "x", "body_template_de": "", "body_template_en": ""},
    )
    assert r.status_code == 200
    assert r.json()["body_template_de"] is None
    assert r.json()["body_template_en"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/integration/test_inquiry_prompt_endpoint.py -q`
Expected: FAIL — response JSON has no `body_template_de` key (`KeyError`/assert).

- [ ] **Step 3: Add fields to the schemas and handlers**

In `backend/app/api/inquiry_prompt.py`:

Add to `class InquiryPromptOut` (after `question_part_time_en`):

```python
    body_template_de: str | None = None
    body_template_en: str | None = None
```

Add the same two lines to `class InquiryPromptPut` (after its `question_part_time_en`).

Add to `_row_to_out(...)` return (after `question_part_time_en=row.question_part_time_en,`):

```python
        body_template_de=row.body_template_de,
        body_template_en=row.body_template_en,
```

Add to `put_prompt(...)` (after `row.question_part_time_en = body.question_part_time_en or None`):

```python
    row.body_template_de = body.body_template_de or None
    row.body_template_en = body.body_template_en or None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/integration/test_inquiry_prompt_endpoint.py -q`
Expected: PASS (existing + new tests green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/inquiry_prompt.py backend/tests/integration/test_inquiry_prompt_endpoint.py
git commit -m "feat(inquiry): expose body templates on inquiry-prompt API"
```

---

### Task 7: Frontend API type

**Files:**
- Modify: `frontend/src/api/inquiry.ts:3-10`

- [ ] **Step 1: Add fields to the type**

In `frontend/src/api/inquiry.ts`, add to the `InquiryPrompt` type (after `question_part_time_en`):

```typescript
  body_template_de: string | null;
  body_template_en: string | null;
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: reports errors in `SettingsInquiryPrompt.tsx` (missing fields in the `useState` initial object) — confirms the type is wired. These are fixed in Task 8.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/inquiry.ts
git commit -m "feat(inquiry): body template fields on InquiryPrompt type"
```

---

### Task 8: Frontend "Request mail body" section

**Files:**
- Modify: `frontend/src/pages/SettingsInquiryPrompt.tsx`

- [ ] **Step 1: Add default-template consts**

In `frontend/src/pages/SettingsInquiryPrompt.tsx`, after the `DEFAULT_PT_EN` const (line 18), add:

```typescript
const DEFAULT_BODY_TEMPLATE_DE =
  "{greeting},\n\n" +
  "ich interessiere mich sehr für Ihre Stellenausschreibung als „{title}{ref}“. " +
  "Bevor ich meine Bewerbung einreiche, hätte ich zwei kurze Fragen:\n\n" +
  "{questions}\n\n" +
  "Vielen Dank im Voraus für Ihre Rückmeldung und mit freundlichen Grüßen\n" +
  "Janik Viertel";
const DEFAULT_BODY_TEMPLATE_EN =
  "{greeting},\n\n" +
  'I am very interested in your job posting for the position of "{title}{ref}". ' +
  "Before submitting my application, I have a couple of questions:\n\n" +
  "{questions}\n\n" +
  "Thank you in advance for your reply.\n\n" +
  "Kind regards\n" +
  "Janik Viertel";
```

- [ ] **Step 2: Add the two fields to the `useState` initial object**

In the `useState<InquiryPrompt>({ ... })` initializer (lines 54-61), add after `question_part_time_en: null,`:

```typescript
    body_template_de: null,
    body_template_en: null,
```

- [ ] **Step 3: Add the "Request mail body" section**

Insert a new `<section>` immediately after the closing `</section>` of the "Question texts" block (after line 160), before the save-button `<div>`:

```tsx
      <section className="space-y-3">
        <h2 className="font-medium text-slate-800">Request mail body</h2>
        <p className="text-xs text-slate-500">
          The full inquiry email body. Available placeholders:{" "}
          <code className="bg-slate-100 px-1 rounded">{"{greeting}"}</code>{" "}
          <code className="bg-slate-100 px-1 rounded">{"{title}"}</code>{" "}
          <code className="bg-slate-100 px-1 rounded">{"{ref}"}</code>{" "}
          <code className="bg-slate-100 px-1 rounded">{"{questions}"}</code>{" "}
          <code className="bg-slate-100 px-1 rounded">{"{company}"}</code>{" "}
          <code className="bg-slate-100 px-1 rounded">{"{reference_number}"}</code>
          . Leave blank to use the default wording.
        </p>
        <div className="grid grid-cols-1 gap-3">
          <Field
            label="Body — DE"
            placeholder={DEFAULT_BODY_TEMPLATE_DE}
            value={draft.body_template_de ?? ""}
            rows={12}
            onChange={(v) => set("body_template_de", v)}
          />
          <Field
            label="Body — EN"
            placeholder={DEFAULT_BODY_TEMPLATE_EN}
            value={draft.body_template_en ?? ""}
            rows={12}
            onChange={(v) => set("body_template_en", v)}
          />
        </div>
      </section>
```

- [ ] **Step 4: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: PASS — no type errors, build succeeds.

- [ ] **Step 5: Manually verify in the browser**

Start the dev server, open Settings → inquiry prompt page, confirm the "Request mail body" section shows two 12-row textareas with the default DE/EN wording as greyed placeholder text, edit + Save, reload, confirm values persist. (If the dev environment can't run the browser, say so explicitly instead of claiming success.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SettingsInquiryPrompt.tsx
git commit -m "feat(inquiry): editable DE/EN body templates in settings UI"
```

---

## Self-Review notes

- **Spec coverage:** model cols (Task 2), migration `down_revision=e1f2a3b4c5d6` (Task 3), default templates + `build_body` template/company params + removed singular-plural branch (Task 1), `draft()` body_de/body_en (Task 4), `draft_inquiry` wiring (Task 5), API Out/Put/`_row_to_out`/`put_prompt` (Task 6), FE type (Task 7), FE consts + section + initial state + set flow (Task 8). Tests: prompts unit (Task 1), migration (Task 3), API round-trip incl. blank→null (Task 6).
- **`{questions}` stays `"\n".join(...)` (no bullets)** to exactly reproduce current default output — the prior `build_body` did not bullet.
- **Token order:** `{reference_number}` replaced before `{ref}` (defensive longest-first), `.replace()` keeps stray braces literal — matches spec decision.
- **Type consistency:** field names `body_template_de` / `body_template_en` identical across model, migration, API, TS type, and UI.
