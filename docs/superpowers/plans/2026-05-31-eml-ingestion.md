# .eml Ingestion → Split Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user drop a single `.eml` file on an application's activity panel; the backend splits the email thread into one interaction per message (deterministic, LLM fallback on low confidence) and auto-creates them, with a toast + Undo on the frontend.

**Architecture:** New pure-Python `backend/app/email_ingest/` package (parser, confidence, llm_split, models) feeds a new `POST /api/applications/{aid}/interactions/import-eml` endpoint that maps each parsed message to an `Interaction` (direction/contact/timestamp computed deterministically for both paths). Frontend adds a native dropzone to `ActivityPanel`, a minimal toast component, and an Undo that deletes the returned ids.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, stdlib `email`, `python-dateutil`, Pydantic v2, React + `@tanstack/react-query`, Playwright.

**Source spec:** `docs/superpowers/specs/2026-05-31-eml-ingestion-design.md`

---

## File Structure

**Backend (new package `backend/app/email_ingest/`):**
- `__init__.py` — empty package marker.
- `models.py` — `ParsedMessage`, `ParsedThread` Pydantic models (pure data).
- `parser.py` — deterministic, pure parsing: `extract_top_message`, `html_to_text`, `split_quoted`, `parse_quote_header`, `parse_eml`.
- `llm_split.py` — `llm_split_thread` + `LlmThread`/`LlmMessage` schema (LLM path).
- `confidence.py` — `Confidence` enum + `score`.

**Backend (modified):**
- `backend/app/db/models.py` — add `eml_import` to `InteractionCreatedFrom`.
- `backend/alembic/versions/<new>.py` — `ALTER TYPE interactioncreatedfrom ADD VALUE 'eml_import'`.
- `backend/app/api/interactions.py` — add `import-eml` endpoint, `_eml_llm`, mapping helper, response model.
- `backend/pyproject.toml` — add `python-dateutil` dependency.

**Frontend (new):**
- `frontend/src/components/Toast.tsx` — minimal toast context/provider/hook with optional action button.

**Frontend (modified):**
- `frontend/src/main.tsx` (or app root) — wrap tree in `<ToastProvider>`.
- `frontend/src/api/interactions.ts` — `importEml`, `ImportEmlResp`, extend `created_from` union with `"eml_import"`.
- `frontend/src/components/ActivityPanel.tsx` — dropzone + import mutation + toast/undo.
- `frontend/tests/import-eml.spec.ts` — Playwright e2e.

**Backend tests:**
- `backend/tests/unit/test_email_parser.py`, `test_email_confidence.py`, `test_email_llm_split.py`, `test_email_parse_eml.py`.
- `backend/tests/integration/test_import_eml_api.py`, `test_eml_enum_migration.py`.
- Fixtures: `backend/tests/fixtures/eml/*.eml`.

**Conventions confirmed:**
- PG enum type name is `interactioncreatedfrom` (verified in model `models.py:345` and `c4d5e6f7a8b9_mini_crm.py`).
- Alembic head revision is `d5e6f7a8b9c0` — the new migration's `down_revision`.
- LLM is stubbed in tests via existing `backend/tests/fakes/llm.py` `FakeLLM` (implements the `LLMClient` Protocol).
- Run backend tests: `cd backend && .venv/bin/pytest <path> -v`. Integration tests need Docker (testcontainers).
- Run frontend e2e: `cd frontend && npx playwright test tests/import-eml.spec.ts`.
- Run typecheck/build: `cd frontend && npm run build`.

---

## Task 1: Add `eml_import` enum value (model + migration)

**Files:**
- Modify: `backend/app/db/models.py:98-101`
- Create: `backend/alembic/versions/e1f2a3b4c5d6_interaction_created_from_eml_import.py`
- Test: `backend/tests/integration/test_eml_enum_migration.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_eml_enum_migration.py`:

```python
import importlib.util
from pathlib import Path

from app.db.models import (
    Application,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
    InteractionDirection,
)


def _load_migration():
    p = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "e1f2a3b4c5d6_interaction_created_from_eml_import.py"
    )
    spec = importlib.util.spec_from_file_location("eml_enum_mig", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_enum_member_exists():
    assert InteractionCreatedFrom.eml_import.value == "eml_import"


def test_migration_chains_from_head():
    mod = _load_migration()
    assert mod.revision == "e1f2a3b4c5d6"
    assert mod.down_revision == "d5e6f7a8b9c0"


def test_can_persist_interaction_with_eml_import(db_session, auth_user):
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/e", url_hash="he")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    it = Interaction(
        application_id=a.id,
        direction=InteractionDirection.in_,
        channel=InteractionChannel.mail,
        created_from=InteractionCreatedFrom.eml_import,
    )
    db_session.add(it)
    db_session.commit()
    db_session.refresh(it)
    assert it.created_from == InteractionCreatedFrom.eml_import
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/integration/test_eml_enum_migration.py -v`
Expected: FAIL — `AttributeError: eml_import` (enum member missing) and migration file not found.

- [ ] **Step 3: Add the enum member**

In `backend/app/db/models.py`, edit `InteractionCreatedFrom` (lines 98-101):

```python
class InteractionCreatedFrom(str, enum.Enum):
    manual = "manual"
    inquiry_migration = "inquiry_migration"
    graph_sync = "graph_sync"
    eml_import = "eml_import"
```

- [ ] **Step 4: Create the migration**

Create `backend/alembic/versions/e1f2a3b4c5d6_interaction_created_from_eml_import.py`:

```python
"""add eml_import to interactioncreatedfrom enum

Single-purpose migration: a newly added Postgres enum value is only usable
after the adding transaction commits, so this migration does nothing but
ADD VALUE and must NOT be combined with code that consumes 'eml_import'.

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE interactioncreatedfrom ADD VALUE IF NOT EXISTS 'eml_import'"
    )


def downgrade() -> None:
    # Postgres cannot drop a single enum value; no-op.
    pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/integration/test_eml_enum_migration.py -v`
Expected: PASS (all three tests). The `db_session` fixture builds the enum from the ORM via `create_all`, so the new member is accepted.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/e1f2a3b4c5d6_interaction_created_from_eml_import.py backend/tests/integration/test_eml_enum_migration.py
git commit -m "feat(crm): add eml_import to InteractionCreatedFrom enum"
```

---

## Task 2: Add `python-dateutil` dependency

**Files:**
- Modify: `backend/pyproject.toml:5-23`

- [ ] **Step 1: Add the dependency**

In `backend/pyproject.toml`, add `python-dateutil>=2.9` to the `dependencies` list (after `"markdown>=3.6",`):

```toml
  "markdown>=3.6",
  "python-dateutil>=2.9",
  "celery[redis]>=5.4",
```

- [ ] **Step 2: Install it**

Run: `cd backend && .venv/bin/pip install "python-dateutil>=2.9"`
Expected: `Successfully installed python-dateutil-...` (or "already satisfied").

- [ ] **Step 3: Verify import**

Run: `cd backend && .venv/bin/python -c "from dateutil import parser; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build(backend): add python-dateutil for quote-date parsing"
```

---

## Task 3: `email_ingest` package + Pydantic models

**Files:**
- Create: `backend/app/email_ingest/__init__.py`
- Create: `backend/app/email_ingest/models.py`
- Test: `backend/tests/unit/test_email_parser.py` (started here, extended later)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_email_parser.py`:

```python
from datetime import datetime, timezone

from app.email_ingest.models import ParsedMessage, ParsedThread


def test_parsed_message_defaults():
    m = ParsedMessage(body="hi")
    assert m.sender_name is None
    assert m.sender_email is None
    assert m.recipients == []
    assert m.occurred_at is None
    assert m.subject is None
    assert m.body == "hi"


def test_parsed_thread_holds_messages():
    t = ParsedThread(
        messages=[
            ParsedMessage(
                sender_email="a@b.c",
                occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                body="x",
            )
        ],
        used_llm=True,
    )
    assert len(t.messages) == 1
    assert t.used_llm is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: app.email_ingest`.

- [ ] **Step 3: Create the package and models**

Create `backend/app/email_ingest/__init__.py` (empty file).

Create `backend/app/email_ingest/models.py`:

```python
from datetime import datetime

from pydantic import BaseModel, Field


class ParsedMessage(BaseModel):
    sender_name: str | None = None
    sender_email: str | None = None
    recipients: list[str] = Field(default_factory=list)
    occurred_at: datetime | None = None
    subject: str | None = None
    body: str = ""


class ParsedThread(BaseModel):
    messages: list[ParsedMessage] = Field(default_factory=list)
    used_llm: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parser.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/email_ingest/__init__.py backend/app/email_ingest/models.py backend/tests/unit/test_email_parser.py
git commit -m "feat(email_ingest): add ParsedMessage/ParsedThread models"
```

---

## Task 4: `extract_top_message` + `html_to_text`

**Files:**
- Create: `backend/app/email_ingest/parser.py`
- Create: `backend/tests/fixtures/eml/single_plain.eml`
- Create: `backend/tests/fixtures/eml/html_only.eml`
- Test: extend `backend/tests/unit/test_email_parser.py`

- [ ] **Step 1: Create fixtures**

Create `backend/tests/fixtures/eml/single_plain.eml`:

```
From: Recruiter Anna <anna@acme.test>
To: Me <me@self.test>
Subject: Your application
Date: Thu, 01 May 2026 09:30:00 +0000
Content-Type: text/plain; charset="utf-8"

Hi, thanks for applying. We will be in touch.

Anna
```

Create `backend/tests/fixtures/eml/html_only.eml`:

```
From: Recruiter Anna <anna@acme.test>
To: Me <me@self.test>
Subject: HTML hello
Date: Thu, 01 May 2026 09:30:00 +0000
MIME-Version: 1.0
Content-Type: text/html; charset="utf-8"

<html><body><p>Hello&nbsp;there.</p><div>Second line</div></body></html>
```

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/unit/test_email_parser.py`:

```python
from pathlib import Path

from app.email_ingest.parser import extract_top_message, html_to_text

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "eml"


def _read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_extract_top_message_plain():
    msg, text = extract_top_message(_read("single_plain.eml"))
    assert msg["Subject"] == "Your application"
    assert msg["From"] == "Recruiter Anna <anna@acme.test>"
    assert "thanks for applying" in text


def test_extract_top_message_html_is_converted():
    msg, text = extract_top_message(_read("html_only.eml"))
    assert "Hello there." in text
    assert "Second line" in text
    assert "<p>" not in text


def test_html_to_text_strips_tags_and_unescapes():
    out = html_to_text("<p>A&amp;B</p><br><div>C</div>")
    assert "A&B" in out
    assert "C" in out
    assert "<" not in out
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'extract_top_message'`.

- [ ] **Step 4: Implement `extract_top_message` + `html_to_text`**

Create `backend/app/email_ingest/parser.py`:

```python
import html as _html
import re
from email import message_from_bytes, policy
from email.message import EmailMessage

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_BR_RE = re.compile(r"(?i)<br\s*/?>")
_BLOCK_END_RE = re.compile(r"(?i)</(p|div|tr|li|h[1-6]|table)>")
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    s = _SCRIPT_STYLE_RE.sub("", html)
    s = _BR_RE.sub("\n", s)
    s = _BLOCK_END_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _best_body(msg: EmailMessage) -> str:
    if msg.is_multipart():
        plain = None
        html = None
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = part.get_content()
            elif ctype == "text/html" and html is None:
                html = part.get_content()
        if plain:
            return plain
        if html:
            return html_to_text(html)
        return ""
    content = msg.get_content()
    if msg.get_content_type() == "text/html":
        return html_to_text(content)
    return content


def extract_top_message(raw: bytes) -> tuple[EmailMessage, str]:
    msg = message_from_bytes(raw, policy=policy.default)
    return msg, _best_body(msg)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parser.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 6: Commit**

```bash
git add backend/app/email_ingest/parser.py backend/tests/unit/test_email_parser.py backend/tests/fixtures/eml/single_plain.eml backend/tests/fixtures/eml/html_only.eml
git commit -m "feat(email_ingest): extract top message body + html_to_text"
```

---

## Task 5: `split_quoted` + `parse_quote_header`

**Files:**
- Modify: `backend/app/email_ingest/parser.py`
- Test: extend `backend/tests/unit/test_email_parser.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_email_parser.py`:

```python
from app.email_ingest.parser import parse_quote_header, split_quoted

OUTLOOK_EN = """Thanks, talk soon.

From: Recruiter Anna <anna@acme.test>
Sent: Wednesday, April 30, 2026 4:00 PM
To: Me <me@self.test>
Subject: Re: Your application

Hi, we received your CV.

From: Me <me@self.test>
Sent: Wednesday, April 30, 2026 1:00 PM
To: Recruiter Anna <anna@acme.test>
Subject: Your application

Here is my application.
"""

GMAIL_EN = """Sounds good.

On Wed, Apr 30, 2026 at 4:00 PM Anna <anna@acme.test> wrote:
Thanks for applying, we will review.
"""

GERMAN = """Vielen Dank.

Am 30.04.2026 um 16:00 schrieb Anna <anna@acme.test>:
Wir haben Ihre Bewerbung erhalten.
"""


def test_split_quoted_outlook_two_quotes():
    segs = split_quoted(OUTLOOK_EN)
    assert len(segs) == 2
    assert "we received your CV" in segs[0].body
    assert "Here is my application" in segs[1].body
    assert segs[0].header.startswith("From: Recruiter Anna")


def test_split_quoted_gmail_attribution():
    segs = split_quoted(GMAIL_EN)
    assert len(segs) == 1
    assert "Thanks for applying" in segs[0].body
    assert "wrote:" in segs[0].header


def test_split_quoted_german_attribution():
    segs = split_quoted(GERMAN)
    assert len(segs) == 1
    assert "Bewerbung erhalten" in segs[0].body


def test_split_quoted_no_markers_returns_empty():
    assert split_quoted("Just a flat message.\nNo quotes here.") == []


def test_parse_quote_header_outlook_block():
    block = (
        "From: Recruiter Anna <anna@acme.test>\n"
        "Sent: Wednesday, April 30, 2026 4:00 PM\n"
        "To: Me <me@self.test>\n"
        "Subject: Re: Your application"
    )
    h = parse_quote_header(block)
    assert h["sender_email"] == "anna@acme.test"
    assert h["sender_name"] == "Recruiter Anna"
    assert h["to"] == ["me@self.test"]
    assert h["subject"] == "Re: Your application"
    assert h["date"] == "Wednesday, April 30, 2026 4:00 PM"


def test_parse_quote_header_attribution_line():
    h = parse_quote_header("On Wed, Apr 30, 2026 at 4:00 PM Anna <anna@acme.test> wrote:")
    assert h["sender_email"] == "anna@acme.test"
    assert "Apr 30, 2026" in h["date"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'split_quoted'`.

- [ ] **Step 3: Implement `split_quoted` + `parse_quote_header`**

Add to `backend/app/email_ingest/parser.py` (after the imports add `from dataclasses import dataclass, field` and `from email.utils import getaddresses, parseaddr`):

```python
from dataclasses import dataclass, field
from email.utils import getaddresses, parseaddr


@dataclass
class Segment:
    header: str
    body: str
    kind: str = "outlook"


_OUTLOOK_FROM_RE = re.compile(r"(?im)^[ \t>]*(From|Von):[ \t]*\S")
_HEADER_LINE_RE = re.compile(
    r"(?im)^[ \t>]*(From|Von|Sent|Gesendet|To|An|Cc|Subject|Betreff):[ \t]*.*$"
)
_ATTRIB_EN_RE = re.compile(r"(?im)^[ \t>]*On\b.+?\bwrote:[ \t]*$")
_ATTRIB_DE_RE = re.compile(r"(?im)^[ \t>]*Am\b.+?\bschrieb\b.+?:[ \t]*$")
_FORWARD_RE = re.compile(
    r"(?im)^[ \t>]*(-{2,}\s*Original Message\s*-{2,}|-{2,}\s*Forwarded message\s*-{2,})[ \t]*$"
)


def _dequote(line: str) -> str:
    return re.sub(r"^[ \t]*>+[ \t]?", "", line)


def _find_separators(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return (start_line, header_end_line_exclusive, kind) for each separator."""
    seps: list[tuple[int, int, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if _FORWARD_RE.match(line):
            seps.append((i, i + 1, "forward"))
            i += 1
            continue
        if _ATTRIB_EN_RE.match(line) or _ATTRIB_DE_RE.match(line):
            seps.append((i, i + 1, "attrib"))
            i += 1
            continue
        if _OUTLOOK_FROM_RE.match(line):
            j = i
            while j < n and _HEADER_LINE_RE.match(lines[j]):
                j += 1
            seps.append((i, j, "outlook"))
            i = j
            continue
        i += 1
    return seps


def split_quoted(text: str) -> list[Segment]:
    lines = text.splitlines()
    seps = _find_separators(lines)
    if not seps:
        return []
    segs: list[Segment] = []
    for idx, (start, hdr_end, kind) in enumerate(seps):
        header = "\n".join(_dequote(l) for l in lines[start:hdr_end]).strip()
        body_start = hdr_end
        body_end = seps[idx + 1][0] if idx + 1 < len(seps) else len(lines)
        body = "\n".join(_dequote(l) for l in lines[body_start:body_end]).strip()
        segs.append(Segment(header=header, body=body, kind=kind))
    return segs


_HDR_FIELD_RE = {
    "from": re.compile(r"(?i)^(From|Von):[ \t]*(.+)$"),
    "date": re.compile(r"(?i)^(Sent|Gesendet):[ \t]*(.+)$"),
    "to": re.compile(r"(?i)^(To|An):[ \t]*(.+)$"),
    "subject": re.compile(r"(?i)^(Subject|Betreff):[ \t]*(.+)$"),
}
_ATTRIB_EN_PARSE = re.compile(r"(?i)^On\s+(?P<date>.+?),?\s+(?P<who>[^,]+?)\s+wrote:")
_ATTRIB_DE_PARSE = re.compile(r"(?i)^Am\s+(?P<date>.+?)\s+schrieb\s+(?P<who>.+?):")


def parse_quote_header(block: str) -> dict:
    out: dict = {}
    block = block.strip()
    m = _ATTRIB_EN_PARSE.match(block) or _ATTRIB_DE_PARSE.match(block)
    if m:
        name, email = parseaddr(m.group("who").strip())
        out["sender_name"] = name or (None if email else m.group("who").strip())
        out["sender_email"] = email or None
        out["date"] = m.group("date").strip()
        return out
    for line in block.splitlines():
        line = line.strip()
        if _HDR_FIELD_RE["from"].match(line):
            name, email = parseaddr(_HDR_FIELD_RE["from"].match(line).group(2))
            out["sender_name"] = name or None
            out["sender_email"] = email or None
        elif _HDR_FIELD_RE["date"].match(line):
            out["date"] = _HDR_FIELD_RE["date"].match(line).group(2).strip()
        elif _HDR_FIELD_RE["to"].match(line):
            addrs = [a for _, a in getaddresses([_HDR_FIELD_RE["to"].match(line).group(2)]) if a]
            out["to"] = addrs
        elif _HDR_FIELD_RE["subject"].match(line):
            out["subject"] = _HDR_FIELD_RE["subject"].match(line).group(2).strip()
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parser.py -v`
Expected: PASS (all parser tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/email_ingest/parser.py backend/tests/unit/test_email_parser.py
git commit -m "feat(email_ingest): split quoted segments + parse quote headers"
```

---

## Task 6: `confidence.score`

**Files:**
- Create: `backend/app/email_ingest/confidence.py`
- Test: `backend/tests/unit/test_email_confidence.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_email_confidence.py`:

```python
from app.email_ingest.confidence import Confidence, score
from app.email_ingest.models import ParsedMessage


def _msg(**kw):
    return ParsedMessage(**kw)


def test_markers_present_but_no_segments_is_low():
    # body mentions a quote marker but split produced only the top message
    det = [_msg(sender_email="a@b.c", body="On Wed wrote: see below")]
    body = "Some text\nOn Wed, Apr 30, 2026 someone wrote:\nold stuff"
    assert score(det, body) == Confidence.LOW


def test_clean_multi_segment_is_high():
    det = [
        _msg(sender_email="a@b.c", occurred_at=None, body="new"),
        _msg(sender_email="x@y.z", body="old"),
    ]
    body = "new\nFrom: X\nold"
    assert score(det, body) == Confidence.HIGH


def test_unknown_sender_and_unparseable_date_is_low():
    from datetime import datetime

    det = [
        _msg(sender_email="a@b.c", occurred_at=datetime.now(), body="new"),
        _msg(sender_email=None, occurred_at=None, body="old"),
    ]
    body = "new\nFrom: ?\nold"
    assert score(det, body) == Confidence.LOW


def test_single_message_no_markers_is_high():
    det = [_msg(sender_email="a@b.c", body="just one message")]
    assert score(det, "just one message") == Confidence.HIGH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_confidence.py -v`
Expected: FAIL — `ModuleNotFoundError: app.email_ingest.confidence`.

- [ ] **Step 3: Implement `confidence.score`**

Create `backend/app/email_ingest/confidence.py`:

```python
import enum
import re

from app.email_ingest.models import ParsedMessage

_MARKER_RE = re.compile(
    r"(?i)(\bwrote:|\bschrieb\b|^\s*(From|Von):|-{2,}\s*Original|Forwarded message)",
    re.MULTILINE,
)


class Confidence(str, enum.Enum):
    HIGH = "high"
    LOW = "low"


def score(det_messages: list[ParsedMessage], body_text: str) -> Confidence:
    has_marker = bool(_MARKER_RE.search(body_text))
    quoted_count = max(len(det_messages) - 1, 0)
    if has_marker and quoted_count == 0:
        return Confidence.LOW
    for m in det_messages:
        if not m.sender_email and m.occurred_at is None:
            return Confidence.LOW
    return Confidence.HIGH
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_confidence.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/email_ingest/confidence.py backend/tests/unit/test_email_confidence.py
git commit -m "feat(email_ingest): deterministic confidence scoring"
```

---

## Task 7: `llm_split_thread` (LLM path)

**Files:**
- Create: `backend/app/email_ingest/llm_split.py`
- Test: `backend/tests/unit/test_email_llm_split.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_email_llm_split.py`:

```python
import json

from app.email_ingest.llm_split import LlmThread, llm_split_thread
from tests.fakes.llm import FakeLLM


def _canned(_messages, _schema):
    return json.dumps(
        {
            "messages": [
                {
                    "sender_name": "Anna",
                    "sender_email": "anna@acme.test",
                    "recipients": ["me@self.test"],
                    "date_text": "Apr 30 2026 16:00",
                    "subject": "Re: Your application",
                    "body": "newest message",
                },
                {
                    "sender_name": "Me",
                    "sender_email": "me@self.test",
                    "recipients": ["anna@acme.test"],
                    "date_text": "Apr 30 2026 13:00",
                    "subject": "Your application",
                    "body": "older message",
                },
            ]
        }
    )


def test_llm_split_returns_parsed_messages():
    llm = FakeLLM(handler=_canned)
    msgs = llm_split_thread("some messy thread text", llm)
    assert len(msgs) == 2
    assert msgs[0].sender_email == "anna@acme.test"
    assert msgs[0].body == "newest message"
    # date_text parsed into occurred_at
    assert msgs[0].occurred_at is not None
    assert msgs[0].occurred_at.year == 2026
    # llm was asked for JSON schema
    assert llm.calls[0][1] is not None  # json_schema passed


def test_llm_schema_has_messages_array():
    schema = LlmThread.model_json_schema()
    assert "messages" in schema["properties"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_llm_split.py -v`
Expected: FAIL — `ModuleNotFoundError: app.email_ingest.llm_split`.

- [ ] **Step 3: Implement `llm_split_thread`**

Create `backend/app/email_ingest/llm_split.py`:

```python
from pydantic import BaseModel, Field

from app.email_ingest.models import ParsedMessage
from app.llm.base import LLMClient

_SYSTEM = (
    "You split an email thread into individual messages, newest first. "
    "For each message return sender_name, sender_email, recipients (emails), "
    "date_text (the raw date string as written, or empty), subject, and body "
    "(that message's own text only, excluding quoted older messages). "
    "Do not invent addresses; use empty strings when unknown."
)


class LlmMessage(BaseModel):
    sender_name: str = ""
    sender_email: str = ""
    recipients: list[str] = Field(default_factory=list)
    date_text: str = ""
    subject: str = ""
    body: str = ""


class LlmThread(BaseModel):
    messages: list[LlmMessage] = Field(default_factory=list)


def _parse_date(text: str):
    if not text.strip():
        return None
    try:
        from dateutil import parser as dtparser

        return dtparser.parse(text, fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None


def llm_split_thread(text: str, llm: LLMClient) -> list[ParsedMessage]:
    raw = llm.complete(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": text},
        ],
        json_schema=LlmThread.model_json_schema(),
        temperature=0.0,
    )
    thread = LlmThread.model_validate_json(raw)
    out: list[ParsedMessage] = []
    for m in thread.messages:
        out.append(
            ParsedMessage(
                sender_name=m.sender_name or None,
                sender_email=m.sender_email or None,
                recipients=[r for r in m.recipients if r],
                occurred_at=_parse_date(m.date_text),
                subject=m.subject or None,
                body=m.body,
            )
        )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_llm_split.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/email_ingest/llm_split.py backend/tests/unit/test_email_llm_split.py
git commit -m "feat(email_ingest): LLM thread split with structured schema"
```

---

## Task 8: `parse_eml` orchestration

**Files:**
- Modify: `backend/app/email_ingest/parser.py`
- Create: `backend/tests/fixtures/eml/outlook_thread.eml`
- Test: `backend/tests/unit/test_email_parse_eml.py`

- [ ] **Step 1: Create the threaded fixture**

Create `backend/tests/fixtures/eml/outlook_thread.eml`:

```
From: Recruiter Anna <anna@acme.test>
To: Me <me@self.test>
Subject: Re: Your application
Date: Wed, 30 Apr 2026 16:00:00 +0000
Content-Type: text/plain; charset="utf-8"

Thanks, we received your CV and will review.

From: Me <me@self.test>
Sent: Wednesday, April 30, 2026 1:00 PM
To: Recruiter Anna <anna@acme.test>
Subject: Your application

Hello, please find my application attached.
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/unit/test_email_parse_eml.py`:

```python
import json
from pathlib import Path

from app.email_ingest.parser import parse_eml
from tests.fakes.llm import FakeLLM

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "eml"


def _read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_parse_eml_single_message_no_llm():
    thread = parse_eml(_read("single_plain.eml"), llm=None)
    assert thread.used_llm is False
    assert len(thread.messages) == 1
    top = thread.messages[0]
    assert top.sender_email == "anna@acme.test"
    assert top.subject == "Your application"
    assert top.occurred_at is not None  # from RFC822 Date header
    assert "thanks for applying" in top.body.lower()


def test_parse_eml_outlook_thread_splits_high_confidence():
    thread = parse_eml(_read("outlook_thread.eml"), llm=None)
    assert thread.used_llm is False
    assert len(thread.messages) == 2
    assert thread.messages[0].sender_email == "anna@acme.test"
    assert "received your CV" in thread.messages[0].body
    assert thread.messages[1].sender_email == "me@self.test"
    assert "my application" in thread.messages[1].body
    # top message keeps the real RFC822 date
    assert thread.messages[0].occurred_at.year == 2026


def test_parse_eml_low_confidence_uses_llm_and_overrides_top():
    def handler(_m, _s):
        return json.dumps(
            {
                "messages": [
                    {"sender_name": "WRONG", "sender_email": "wrong@x.test",
                     "recipients": [], "date_text": "", "subject": "WRONG",
                     "body": "newest"},
                    {"sender_name": "Old", "sender_email": "old@x.test",
                     "recipients": [], "date_text": "Apr 29 2026", "subject": "Older",
                     "body": "older"},
                ]
            }
        )

    llm = FakeLLM(handler=handler)
    # html_only triggers a marker-free single message; force LOW by using a
    # body that has a marker but no parseable split:
    raw = _read("html_marker_no_split.eml")
    thread = parse_eml(raw, llm=llm)
    assert thread.used_llm is True
    # message[0] sender/subject/date OVERRIDDEN by authoritative top headers
    assert thread.messages[0].sender_email == "anna@acme.test"
    assert thread.messages[0].subject == "Quote but no split"
    assert thread.messages[0].sender_name == "Recruiter Anna"


def test_parse_eml_llm_unavailable_degrades_gracefully():
    raw = _read("html_marker_no_split.eml")
    thread = parse_eml(raw, llm=None)
    assert thread.used_llm is False
    assert len(thread.messages) >= 1  # best-effort deterministic result


def test_parse_eml_llm_raises_degrades_gracefully():
    def boom(_m, _s):
        raise RuntimeError("llm down")

    raw = _read("html_marker_no_split.eml")
    thread = parse_eml(raw, llm=FakeLLM(handler=boom))
    assert thread.used_llm is False
    assert len(thread.messages) >= 1
```

Create `backend/tests/fixtures/eml/html_marker_no_split.eml` (a marker present in body, but no deterministic separator → LOW confidence):

```
From: Recruiter Anna <anna@acme.test>
To: Me <me@self.test>
Subject: Quote but no split
Date: Wed, 30 Apr 2026 16:00:00 +0000
MIME-Version: 1.0
Content-Type: text/html; charset="utf-8"

<html><body><p>See what they wrote: below in this messy quote.</p>
<blockquote>some older content with no parseable header</blockquote></body></html>
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parse_eml.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_eml'`.

- [ ] **Step 4: Implement `parse_eml`**

Add to `backend/app/email_ingest/parser.py` (add `from datetime import timedelta` and `from email.utils import parsedate_to_datetime` to imports, plus `from app.email_ingest.models import ParsedMessage, ParsedThread`, `from app.email_ingest.confidence import Confidence, score`, `from app.llm.base import LLMClient`):

```python
from datetime import timedelta
from email.utils import parsedate_to_datetime

from app.email_ingest.confidence import Confidence, score
from app.email_ingest.models import ParsedMessage, ParsedThread
from app.llm.base import LLMClient

MAX_MESSAGES = 20


def _top_message(msg: EmailMessage, body: str) -> ParsedMessage:
    name, email = parseaddr(msg.get("From", ""))
    recipients = [a for _, a in getaddresses(msg.get_all("To", [])) if a]
    occurred = None
    date_hdr = msg.get("Date")
    if date_hdr:
        try:
            occurred = parsedate_to_datetime(date_hdr)
        except (TypeError, ValueError):
            occurred = None
    return ParsedMessage(
        sender_name=name or None,
        sender_email=email or None,
        recipients=recipients,
        occurred_at=occurred,
        subject=msg.get("Subject") or None,
        body=body.strip(),
    )


def _segment_to_message(seg: Segment, top_subject: str | None) -> ParsedMessage:
    from app.email_ingest.llm_split import _parse_date  # reuse dateutil helper

    h = parse_quote_header(seg.header)
    return ParsedMessage(
        sender_name=h.get("sender_name"),
        sender_email=h.get("sender_email"),
        recipients=h.get("to", []),
        occurred_at=_parse_date(h.get("date", "")) if h.get("date") else None,
        subject=h.get("subject") or top_subject,
        body=seg.body,
    )


def parse_eml(raw: bytes, *, llm: LLMClient | None) -> ParsedThread:
    msg, top_text = extract_top_message(raw)
    top = _top_message(msg, top_text)
    quoted = split_quoted(top_text)
    det = [top] + [_segment_to_message(s, top.subject) for s in quoted]

    conf = score(det, top_text)
    if conf == Confidence.LOW and llm is not None:
        try:
            from app.email_ingest.llm_split import llm_split_thread

            llm_msgs = llm_split_thread(top_text, llm)
            if llm_msgs:
                # message[0] is newest: override with authoritative top headers
                llm_msgs[0].sender_name = top.sender_name
                llm_msgs[0].sender_email = top.sender_email
                llm_msgs[0].occurred_at = top.occurred_at
                llm_msgs[0].subject = top.subject
                if not llm_msgs[0].recipients:
                    llm_msgs[0].recipients = top.recipients
                return ParsedThread(messages=llm_msgs[:MAX_MESSAGES], used_llm=True)
        except Exception:  # noqa: BLE001 — graceful degrade, never hard-fail
            pass

    return ParsedThread(messages=det[:MAX_MESSAGES], used_llm=False)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parse_eml.py -v`
Expected: PASS (5 tests). If `html_marker_no_split.eml` does not score LOW, adjust the fixture body so it contains a marker word (`wrote:`) with no deterministic header — the provided fixture does this via "they wrote:".

- [ ] **Step 6: Run the whole email_ingest unit suite**

Run: `cd backend && .venv/bin/pytest tests/unit/test_email_parser.py tests/unit/test_email_confidence.py tests/unit/test_email_llm_split.py tests/unit/test_email_parse_eml.py -v`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add backend/app/email_ingest/parser.py backend/tests/unit/test_email_parse_eml.py backend/tests/fixtures/eml/outlook_thread.eml backend/tests/fixtures/eml/html_marker_no_split.eml
git commit -m "feat(email_ingest): parse_eml orchestration with LLM fallback"
```

---

## Task 9: `import-eml` API endpoint + per-message mapping

**Files:**
- Modify: `backend/app/api/interactions.py`
- Test: `backend/tests/integration/test_import_eml_api.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_import_eml_api.py`:

```python
import uuid
from pathlib import Path

import app.api.interactions as interactions_module
from app.db.models import Application
from tests.fakes.llm import FakeLLM

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "eml"


def _read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def _make_app(db_session, user):
    a = Application(user_id=user.id, url="https://x.test/eml", url_hash="heml")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def test_import_single_message(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user  # u.email == "a@b.c"
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("mail.eml", _read("single_plain.eml"), "message/rfc822")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["used_llm"] is False
    it = body["interactions"][0]
    assert it["channel"] == "mail"
    assert it["created_from"] == "eml_import"
    assert it["direction"] == "in"  # sender anna@acme.test != user a@b.c
    assert it["contact_handle"] == "anna@acme.test"
    assert it["sentiment"] is None


def test_import_outlook_thread_creates_two(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("t.eml", _read("outlook_thread.eml"), "message/rfc822")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    # newest first by occurred_at desc when listed
    listing = client.get(f"/api/applications/{a.id}/interactions").json()
    assert len(listing) == 2


def test_import_direction_out_when_sender_is_user(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user  # a@b.c
    a = _make_app(db_session, u)
    raw = (
        b"From: Me <a@b.c>\r\n"
        b"To: Recruiter <anna@acme.test>\r\n"
        b"Subject: Hi\r\n"
        b"Date: Thu, 01 May 2026 09:30:00 +0000\r\n"
        b"Content-Type: text/plain; charset=\"utf-8\"\r\n\r\n"
        b"My note.\r\n"
    )
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("o.eml", raw, "message/rfc822")},
    )
    it = r.json()["interactions"][0]
    assert it["direction"] == "out"
    assert it["contact_handle"] == "anna@acme.test"  # the recipient


def test_import_unowned_app_404(client, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    r = client.post(
        f"/api/applications/{uuid.uuid4()}/interactions/import-eml",
        files={"file": ("m.eml", b"From: x@y.z\r\n\r\nhi", "message/rfc822")},
    )
    assert r.status_code == 404


def test_import_wrong_extension_400(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("m.txt", b"hi", "text/plain")},
    )
    assert r.status_code == 400


def test_import_oversize_413(client, db_session, auth_user, monkeypatch):
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    _, u = auth_user
    a = _make_app(db_session, u)
    big = b"From: x@y.z\r\n\r\n" + b"a" * (10 * 1024 * 1024 + 1)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("big.eml", big, "message/rfc822")},
    )
    assert r.status_code == 413


def test_import_empty_parse_422(client, db_session, auth_user, monkeypatch):
    # force parse_eml to yield no messages
    monkeypatch.setattr(interactions_module, "_eml_llm", lambda: None)
    from app.email_ingest.models import ParsedThread

    monkeypatch.setattr(
        interactions_module,
        "parse_eml",
        lambda raw, *, llm: ParsedThread(messages=[], used_llm=False),
    )
    _, u = auth_user
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions/import-eml",
        files={"file": ("e.eml", b"From: x@y.z\r\n\r\n", "message/rfc822")},
    )
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/integration/test_import_eml_api.py -v`
Expected: FAIL — 404/405 (route missing) / `AttributeError: _eml_llm`.

- [ ] **Step 3: Implement the endpoint**

In `backend/app/api/interactions.py`:

Add imports at top:

```python
from datetime import timedelta

from fastapi import File, UploadFile

from app.db.models import JobPosting
from app.email_ingest.parser import parse_eml
```

Add constants + helpers (after `router = APIRouter(...)`):

```python
MAX_EML_BYTES = 10 * 1024 * 1024  # 10 MB


def _eml_llm():
    from app.config import get_settings
    from app.llm.groq import GroqClient

    s = get_settings()
    if not s.llm_api_key:
        return None
    return GroqClient(api_key=s.llm_api_key, model=s.llm_model, base_url=s.llm_base_url)


class ImportEmlOut(BaseModel):
    interactions: list[InteractionOut]
    count: int
    used_llm: bool
```

Add the mapping helper:

```python
def _message_to_interaction(aid, msg, user, top_dt, index, job_contact):
    sender = (msg.sender_email or "").lower()
    is_out = bool(sender and user.email and sender == user.email.lower())
    direction = InteractionDirection.out if is_out else InteractionDirection.in_

    if direction == InteractionDirection.in_:
        cname, chandle = msg.sender_name, msg.sender_email
    else:
        chandle = msg.recipients[0] if msg.recipients else None
        cname = None

    if not (cname or chandle) and job_contact:
        cname = job_contact.get("name")
        chandle = job_contact.get("email")

    occurred = msg.occurred_at or (top_dt - timedelta(seconds=index))

    return Interaction(
        application_id=aid,
        occurred_at=occurred,
        direction=direction,
        channel=InteractionChannel.mail,
        subject=msg.subject,
        body=msg.body or None,
        contact_name=cname,
        contact_handle=chandle,
        sentiment=None,
        created_from=InteractionCreatedFrom.eml_import,
    )
```

Add the route:

```python
@router.post(
    "/applications/{aid}/interactions/import-eml",
    response_model=ImportEmlOut,
)
async def import_eml(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    file: Annotated[UploadFile, File()],
):
    app_row = _own_app(db, user, aid)
    if not (file.filename or "").lower().endswith(".eml"):
        raise HTTPException(400, "only .eml files are accepted")
    raw = await file.read()
    if len(raw) > MAX_EML_BYTES:
        raise HTTPException(413, "file too large")

    thread = parse_eml(raw, llm=_eml_llm())
    if not thread.messages:
        raise HTTPException(422, "could not parse email")

    job = db.query(JobPosting).filter_by(application_id=aid).first()
    job_contact = job.contact if job and isinstance(job.contact, dict) else None
    top_dt = thread.messages[0].occurred_at or datetime.now(timezone.utc)

    rows = [
        _message_to_interaction(aid, m, user, top_dt, i, job_contact)
        for i, m in enumerate(thread.messages)
    ]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)

    return ImportEmlOut(
        interactions=[InteractionOut.model_validate(r) for r in rows],
        count=len(rows),
        used_llm=thread.used_llm,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/integration/test_import_eml_api.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (existing tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/interactions.py backend/tests/integration/test_import_eml_api.py
git commit -m "feat(crm): POST import-eml endpoint splits thread into interactions"
```

---

## Task 10: Minimal Toast component

**Files:**
- Create: `frontend/src/components/Toast.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Inspect the app root**

Read `frontend/src/main.tsx` to find where `QueryClientProvider` / `RouterProvider` wraps the tree. The `<ToastProvider>` must wrap the same subtree so any component can call `useToast()`.

- [ ] **Step 2: Implement the Toast provider**

Create `frontend/src/components/Toast.tsx`:

```tsx
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

type ToastAction = { label: string; onClick: () => void };
type ToastState = { id: number; message: string; action?: ToastAction } | null;

const ToastCtx = createContext<(message: string, action?: ToastAction) => void>(() => {});

export function useToast() {
  return useContext(ToastCtx);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback((message: string, action?: ToastAction) => {
    if (timer.current) clearTimeout(timer.current);
    const id = Date.now();
    setToast({ id, message, action });
    timer.current = setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 8000);
  }, []);

  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-slate-900 text-white rounded px-4 py-2 shadow-lg text-sm">
          <span>{toast.message}</span>
          {toast.action && (
            <button
              type="button"
              className="text-blue-300 font-semibold underline"
              onClick={() => {
                toast.action!.onClick();
                setToast(null);
              }}
            >
              {toast.action.label}
            </button>
          )}
        </div>
      )}
    </ToastCtx.Provider>
  );
}
```

Note: `useRef` import — React exports it as `useRef` (lowercase r). Fix the import line to `import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";`.

- [ ] **Step 3: Wrap the app**

In `frontend/src/main.tsx`, import and wrap the tree:

```tsx
import { ToastProvider } from "./components/Toast";
```

Wrap the existing root element, e.g.:

```tsx
<QueryClientProvider client={queryClient}>
  <ToastProvider>
    {/* existing RouterProvider / App */}
  </ToastProvider>
</QueryClientProvider>
```

(Place `ToastProvider` inside `QueryClientProvider` so toasts triggered from query callbacks work.)

- [ ] **Step 4: Typecheck/build**

Run: `cd frontend && npm run build`
Expected: build succeeds (no TS errors).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Toast.tsx frontend/src/main.tsx
git commit -m "feat(ui): minimal toast provider with optional action button"
```

---

## Task 11: Frontend `importEml` API + types

**Files:**
- Modify: `frontend/src/api/interactions.ts`

- [ ] **Step 1: Extend the `created_from` union and add the import call**

In `frontend/src/api/interactions.ts`:

Update the `Interaction` type's `created_from` (line 18):

```ts
  created_from: "manual" | "inquiry_migration" | "graph_sync" | "eml_import";
```

Add after the `Interaction` type (before `CreateInteractionInput`):

```ts
export type ImportEmlResp = {
  interactions: Interaction[];
  count: number;
  used_llm: boolean;
};
```

Add an `importEml` method inside the `interactions` object (after `remove`):

```ts
  importEml: async (appId: string, file: File): Promise<ImportEmlResp> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/applications/${appId}/interactions/import-eml`, {
      method: "POST",
      credentials: "include",
      body: fd,
    });
    if (!res.ok) {
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, body);
    }
    return (await res.json()) as ImportEmlResp;
  },
```

Add `ApiError` to the import at the top (line 1):

```ts
import { ApiError, api } from "./client";
```

- [ ] **Step 2: Typecheck/build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/interactions.ts
git commit -m "feat(api): importEml client + ImportEmlResp type"
```

---

## Task 12: ActivityPanel dropzone + import + toast/undo

**Files:**
- Modify: `frontend/src/components/ActivityPanel.tsx`

- [ ] **Step 1: Add the dropzone, import mutation, and undo**

Rewrite `frontend/src/components/ActivityPanel.tsx` to add a dropzone above the tab content. Full file:

```tsx
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ActivityTimeline } from "./ActivityTimeline";
import { InteractionLogModal } from "./InteractionLogModal";
import { useToast } from "./Toast";
import { interactions, type Interaction } from "../api/interactions";
import type { Application } from "../api/applications";

type Tab = "timeline" | "interactions" | "notes";

export function ActivityPanel({
  appId, app, notes: _notes, onNotesBlur, notesValue, onNotesChange,
}: {
  appId: string;
  app?: Application;
  notes: string | null;
  onNotesBlur: () => void;
  notesValue: string;
  onNotesChange: (v: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("timeline");
  const [showLog, setShowLog] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const toast = useToast();

  const ints = useQuery({
    queryKey: ["interactions", appId],
    queryFn: () => interactions.list(appId),
    enabled: tab === "interactions",
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["interactions", appId] });
    qc.invalidateQueries({ queryKey: ["application-timeline", appId] });
  };

  const undo = async (ids: string[]) => {
    await Promise.all(ids.map((id) => interactions.remove(id)));
    refresh();
  };

  const importEml = useMutation({
    mutationFn: (file: File) => interactions.importEml(appId, file),
    onSuccess: (resp) => {
      refresh();
      const ids = resp.interactions.map((it) => it.id);
      toast(`Imported ${resp.count} interaction${resp.count === 1 ? "" : "s"}`, {
        label: "Undo",
        onClick: () => undo(ids),
      });
    },
    onError: (err) => toast(`Import failed: ${(err as Error).message}`),
  });

  const onFiles = (files: FileList | null) => {
    const f = Array.from(files ?? []).find((x) => x.name.toLowerCase().endsWith(".eml"));
    if (f) importEml.mutate(f);
    else if (files && files.length) toast("Only .eml files are supported");
  };

  return (
    <div className="border rounded bg-white">
      <div className="border-b px-2 py-1 flex gap-2 items-center">
        {(["timeline", "interactions", "notes"] as Tab[]).map((t) => (
          <button key={t} type="button"
                  onClick={() => setTab(t)}
                  className={`px-2 py-1 text-sm ${tab === t ? "border-b-2 border-blue-600 font-semibold" : "text-slate-600"}`}>
            {t}
          </button>
        ))}
        <button type="button"
                className="ml-auto bg-blue-600 text-white rounded px-2 py-1 text-xs"
                onClick={() => setShowLog(true)}>
          + Log interaction
        </button>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); onFiles(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
        className={`mx-3 mt-3 border-2 border-dashed rounded p-3 text-center text-xs cursor-pointer ${
          dragging ? "border-blue-500 bg-blue-50" : "border-slate-300 hover:bg-slate-50"
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".eml"
          className="hidden"
          onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }}
        />
        <span className="text-slate-600">
          {importEml.isPending ? "Importing email…" : "Drop an .eml here, or click to import an email thread"}
        </span>
      </div>

      <div className="p-3">
        {tab === "timeline" && <ActivityTimeline appId={appId} />}
        {tab === "interactions" && (
          <ul className="divide-y">
            {(ints.data ?? []).map((it: Interaction) => (
              <li key={it.id} className="py-2 text-sm">
                <span className="text-slate-400 mr-2">
                  {it.direction === "out" ? "→" : "←"}
                </span>
                <span>{it.channel}</span>
                {it.subject && <> — <strong>{it.subject}</strong></>}
                <div className="text-xs text-slate-500">
                  {new Date(it.occurred_at).toLocaleString()}
                </div>
                {it.body && <div className="text-slate-700 whitespace-pre-wrap">{it.body}</div>}
              </li>
            ))}
          </ul>
        )}
        {tab === "notes" && (
          <textarea
            className="w-full border rounded px-2 py-1 text-sm resize-none"
            rows={6}
            placeholder="Long-form notes…"
            value={notesValue}
            onChange={(e) => onNotesChange(e.target.value)}
            onBlur={onNotesBlur}
          />
        )}
      </div>
      <InteractionLogModal appId={appId} app={app} open={showLog} onClose={() => setShowLog(false)} />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck/build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual smoke (if a dev server is available)**

Run: `cd frontend && npm run dev`, open an application detail page, drag/click an `.eml`, confirm rows appear in the timeline and a toast with Undo shows; click Undo and confirm rows disappear. If a dev server / backend is not available, note this and rely on the e2e test in Task 13.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ActivityPanel.tsx
git commit -m "feat(crm): .eml dropzone on ActivityPanel with import + undo toast"
```

---

## Task 13: Playwright e2e

**Files:**
- Create: `frontend/tests/import-eml.spec.ts`
- Create: `frontend/tests/fixtures/sample.eml`

- [ ] **Step 1: Create the fixture**

Create `frontend/tests/fixtures/sample.eml`:

```
From: Recruiter Anna <anna@acme.test>
To: Me <me@self.test>
Subject: Re: Your application
Date: Wed, 30 Apr 2026 16:00:00 +0000
Content-Type: text/plain; charset="utf-8"

Thanks, we received your CV.
```

- [ ] **Step 2: Write the e2e test**

Create `frontend/tests/import-eml.spec.ts` (mirror the route-mocking style of `interaction-log.spec.ts`; set the hidden file input directly since OS drag-drop is unreliable in Playwright):

```ts
import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const emlPath = path.join(here, "fixtures", "sample.eml");

test("import .eml creates interactions, shows toast, undo removes them", async ({ page }) => {
  const buildApp = () => ({
    id: "a1", display_id: 1, url: "https://x.test/j", status: "draft",
    job_state: "ready", job_error: null, failed_stage: null, language: "en",
    generated_md: null, has_docx: false, cv_variant_id: null,
    anschreiben_variant_id: null, job_posting_dirty: false, posting_online: null,
    labels: [], folder_name: "a1-folder", notes: null, discard_note: null,
    discard_reason_id: null, discard_interaction_id: null,
    job_posting: {
      title: "Dev", company: "Acme", location: null, description: null,
      requirements: null, contact: null, deadline: null, salary: null,
      tech_stack: null, seniority: null, work_mode: null, benefits: null,
      language: "en", required_documents: null, reference_number: null,
      mentions_home_office_policy: null, mentions_part_time: null,
    },
  });

  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "me@self.test", display_name: "X", oauth_enabled: false }) }));
  await page.route("**/api/cv-variants", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/anschreiben-variants", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/labels", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/applications/a1", (r) => r.fulfill({ status: 200, body: JSON.stringify(buildApp()) }));
  await page.route("**/api/applications/a1/chat", (r) => r.fulfill({ status: 200, body: "[]" }));

  const created = {
    id: "i1", application_id: "a1", occurred_at: new Date().toISOString(),
    direction: "in", channel: "mail", subject: "Re: Your application",
    body: "Thanks, we received your CV.", contact_name: "Recruiter Anna",
    contact_handle: "anna@acme.test", sentiment: null, created_from: "eml_import",
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  };

  let timelineRows: Array<Record<string, unknown>> = [];
  await page.route("**/api/applications/a1/timeline", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify(timelineRows) }));

  await page.route("**/api/applications/a1/interactions/import-eml", (r) => {
    timelineRows = [{ kind: "interaction", at: created.occurred_at, data: created }];
    return r.fulfill({ status: 200, body: JSON.stringify({ interactions: [created], count: 1, used_llm: false }) });
  });

  await page.route("**/api/interactions/i1", (r) => {
    timelineRows = [];
    return r.fulfill({ status: 204, body: "" });
  });

  await page.goto("/applications/a1");
  await expect(page.locator('a[href="https://x.test/j"]')).toBeVisible();

  // Set the hidden .eml file input (drag-drop of OS files is unreliable in Playwright).
  await page.setInputFiles('input[type="file"][accept=".eml"]', emlPath);

  // Timeline (default tab) re-renders with the imported row.
  await expect(page.locator("text=Re: Your application")).toBeVisible();

  // Toast with Undo appears.
  await expect(page.locator("text=Imported 1 interaction")).toBeVisible();
  await page.click("button:has-text('Undo')");

  // After undo, the row is gone.
  await expect(page.locator("text=Re: Your application")).toHaveCount(0);
});
```

- [ ] **Step 3: Run the e2e test**

Run: `cd frontend && npx playwright test tests/import-eml.spec.ts`
Expected: PASS. If the timeline does not auto-refetch after import, confirm the invalidation in Task 12 targets `["application-timeline", appId]` (the exact key used in `ActivityTimeline.tsx`).

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/import-eml.spec.ts frontend/tests/fixtures/sample.eml
git commit -m "test(crm): playwright e2e for .eml import + undo"
```

---

## Final verification

- [ ] **Backend unit + integration:** `cd backend && .venv/bin/pytest -q` → all pass (Docker required for integration).
- [ ] **Frontend build:** `cd frontend && npm run build` → no TS errors.
- [ ] **Frontend e2e:** `cd frontend && npx playwright test` → all pass.
- [ ] **Spec coverage self-check:** drag-drop + click import ✓ (Task 12), one interaction per message ✓ (Task 9), deterministic-primary + LLM fallback ✓ (Task 8), toast + Undo ✓ (Tasks 10/12), enum + migration ✓ (Task 1), graceful degrade ✓ (Task 8 tests), 20-message cap ✓ (Task 8 `MAX_MESSAGES`), sentiment NULL / no suggest_discard ✓ (Task 9), ownership/extension/size/empty errors ✓ (Task 9 tests).

---

## Notes for the implementer

- **Direction/contact/timestamp are computed in the endpoint for BOTH paths** (`_message_to_interaction`). The LLM only splits text and fills raw fields; it never sets direction. Keep it that way.
- **The `db_session` test fixture builds enums from the ORM** (`Base.metadata.create_all`), so Task 1's model change is what makes `eml_import` insertable in tests; the Alembic migration is for real Postgres deploys.
- **Graceful degrade is load-bearing:** any LLM failure (no key, raise, bad JSON) must fall back to the deterministic result with `used_llm=False`. The `except Exception` in `parse_eml` is intentional and covered by tests.
- If a deterministic fixture unexpectedly scores HIGH/LOW differently than the test asserts, adjust the *fixture* to match the documented confidence rule rather than weakening the rule.
- **Environment baseline (verified 2026-05-31 in worktree):**
  - Backend has 3 *pre-existing, unrelated* unit failures on main: `test_config.py::test_settings_loads_from_env` and `test_inquiry_prompts.py` (×2). Ignore these; do not "fix" them. Judge your tasks by *your* new tests passing.
  - **Node is v26.0.0, which segfaults on process exit (exit code 139).** `tsc -b` and `vite build` and `playwright test` complete their actual work but the process then crashes. **Judge frontend success by LOG OUTPUT, not exit code:** `tsc -b` printing `TypeScript: No errors found` = typecheck passed; `vite build` printing `ok`/build summary = build passed; Playwright printing its pass/fail summary = the result. Do not treat exit 139 as a failure if the log shows success.
