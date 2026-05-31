# .eml Ingestion → Split Interactions Design

**Date**: 2026-05-31
**Status**: Draft — pending user review
**Scope**: Let a user drop a single `.eml` file onto an application's activity panel. The backend parses the email thread, splits it into one interaction per message (deterministic first, LLM fallback on low confidence), and auto-creates the interactions. The frontend shows a toast with Undo.

## Goals

- Drag-and-drop (or click-to-pick) a `.eml` file in the activity panel of an application.
- Parse the email **thread** and create **one interaction per message** in it, with correct per-message direction, timestamp, contact, subject, and body.
- Deterministic parsing is primary (free, offline). When it is low-confidence, fall back to the LLM to split the thread.
- Auto-create the interactions immediately, then show a toast: `Imported N interactions · Undo`.
- Reuse existing patterns: `UploadFile` upload (documents API), native drag-drop (variant settings), LLM structured-extraction (extractor), React Query timeline.

## Non-Goals (deferred)

- `.msg` (Outlook binary) support — `.eml` only.
- Global / dashboard drop that auto-matches an email to an application — drop is scoped to the open application.
- Attachment storage — attachments in the `.eml` are ignored.
- LLM sentiment classification — `sentiment` is left `NULL`; the user sets it manually (consistent with the existing manual flow).
- MS Graph inbox auto-sync (the `graph_sync` enum value stays a placeholder).
- A batch-delete endpoint — Undo deletes the returned ids one by one.

## Current State (confirmed)

- `Interaction` is denormalized and always tied to `application_id` (FK). No standalone Contact/Company tables. Model: `backend/app/db/models.py:321-352`. Channel enum (`mail, linkedin, phone, portal, xing, interview, other`) and friends: `models.py:76-101`.
- Create endpoint: `POST /api/applications/{aid}/interactions`, `backend/app/api/interactions.py:103`. Hardcodes `created_from=manual`. Returns `suggest_discard` when `direction=in_` and `sentiment=rejection`.
- "Log interaction" modal: `frontend/src/components/InteractionLogModal.tsx`, mounted in `ActivityPanel` (`frontend/src/components/ActivityPanel.tsx:74`) inside the `ApplicationDetail` page. No standalone CRM page — so the drop zone belongs in `ActivityPanel`.
- `User.email` exists (`models.py:157`) → used to compute direction. `JobPosting.contact` JSON (`models.py:256`) → fallback counterpart when the email's counterpart is unparseable.
- Existing upload pattern: `backend/app/api/documents.py` (`upload_cv`, `_read_docx_upload`: `UploadFile`, 10 MB cap, extension check). Frontend `frontend/src/api/documents.ts:uploadDocx` (FormData, `credentials: include`, no manual `Content-Type`). Native dropzone: `frontend/src/pages/_VariantSettings.tsx` (`onDrop`/`onDragOver` + hidden `<input type=file>`).
- LLM: sync `GroqClient.complete(messages, *, json_schema=None, temperature=0.2)` (`backend/app/llm/groq.py`) behind the `LLMClient` Protocol (`backend/app/llm/base.py`). Structured-extraction pattern in `backend/app/extractor/__init__.py`: Pydantic model → `.model_json_schema()` → `complete(json_schema=...)` → `model_validate_json()`.
- Deps present: `fastapi`, `python-multipart`, `httpx`, `pydantic`, `msal`. **Not present**: any email/MIME lib (stdlib `email` is available, unused), `python-dateutil`, frontend dropzone/form libs. Frontend uses `@tanstack/react-query`.

## UX Flow

```
drop .eml (or pick) on ActivityPanel dropzone
  → POST /api/applications/{aid}/interactions/import-eml   (multipart, 1 file)
  → backend: parse thread → N message drafts → bulk insert N interactions (channel=mail, created_from=eml_import)
  → 200 { interactions: [InteractionOut...], count, used_llm }
  → frontend: invalidate interactions query (timeline re-renders with N rows)
  → toast: "Imported N interactions · Undo"
       Undo → DELETE /api/interactions/{id} for each returned id → invalidate
```

Each created row is a normal interaction — editable/deletable through the existing timeline UI. No new edit affordance is required.

## Architecture

New backend package `backend/app/email_ingest/` with small, independently testable units:

1. `models.py` — `ParsedMessage` (Pydantic): `sender_name: str | None`, `sender_email: str | None`, `recipients: list[str]`, `occurred_at: datetime | None`, `subject: str | None`, `body: str`. Plus `ParsedThread`: `messages: list[ParsedMessage]`, `used_llm: bool`.
2. `parser.py` — deterministic path, **pure** (no DB, no FastAPI):
   - `extract_top_message(raw: bytes) -> (headers, text)` — stdlib `email` with `policy=default`; prefer the `text/plain` part, else `html_to_text(html)`.
   - `html_to_text(html: str) -> str` — minimal tag strip / unwrap (no new dep).
   - `split_quoted(text: str) -> list[Segment]` — regex separators: Outlook block `From:/Sent:/To:/Subject:` (EN) and `Von:/Gesendet:/An:/Betreff:` (DE); `On … wrote:` / `Am … schrieb …:`; forwarded markers (`-----Original Message-----`, `---------- Forwarded message ----------`); `>`-quote de-indentation.
   - `parse_quote_header(block: str) -> dict` — pull `sender`, `date`, `to`, `subject` from a separator block.
   - `parse_eml(raw: bytes, *, llm: LLMClient | None) -> ParsedThread` — orchestrates the steps below.
3. `llm_split.py` — `llm_split_thread(text: str, llm: LLMClient) -> list[ParsedMessage]`. Pydantic `LlmThread { messages: [LlmMessage] }` → `model_json_schema()` → `GroqClient.complete(..., json_schema=, temperature=0.0)` → `model_validate_json()`. Sync.
4. `confidence.py` — `score(det_messages, body_text) -> Confidence` (HIGH | LOW), see rules below.

`parse_eml` orchestration:
```
top_headers, top_text = extract_top_message(raw)
det = [top_message] + split_quoted(top_text)
conf = score(det, top_text)
if conf == LOW and llm is not None:
    msgs = llm_split_thread(assemble(top_headers, top_text), llm)
    # message[0] is the newest: OVERRIDE its sender/date/subject with authoritative top_headers
    msgs[0].sender_*/occurred_at/subject = from top_headers
    used_llm = True
else:
    msgs = det
    used_llm = False
return ParsedThread(messages=msgs, used_llm=used_llm)
```

The LLM only splits text and extracts raw fields. **Direction, contact-counterpart, and final timestamps are computed deterministically by the endpoint for both paths**, so the LLM never influences direction or the rejection/discard logic.

## Confidence Rule (explicit, testable)

`score` returns **LOW** when either holds:
- The body contains a quote marker (`wrote:`, `schrieb`, `From:`, `Von:`, `-----Original`, `Forwarded message`) but `split_quoted` produced **0** quoted segments (i.e., only the top message), OR
- Any deterministic message has **both** an unknown sender **and** an unparseable date.

Otherwise **HIGH** → use deterministic result, no LLM call.

## LLM Fallback Policy

- On LOW confidence, **always** invoke the LLM when one is configured (token cost is acceptable — per user). No additional token-budget gating beyond the confidence check.
- **Graceful degrade**: if `Settings.llm_api_key` is unset, or the LLM call raises / returns invalid JSON, fall back to the deterministic best-effort result. A drop never hard-fails because of the LLM.
- LLM availability is read the same way as `applications.py:_inquiry_llm()` (`get_settings()` → `llm_api_key`, `llm_model`, `llm_base_url`).

## Per-Message Mapping (deterministic, both paths)

For each `ParsedMessage` → one `Interaction`:

- **channel** = `mail`.
- **created_from** = `eml_import` (new enum value).
- **direction**: `out` if `sender_email == user.email` (case-insensitive), else `in_`. If `sender_email` is unknown → default `in_`.
- **contact = the counterpart, not the user**:
  - `in_` → contact = sender (`contact_name`=sender_name, `contact_handle`=sender_email).
  - `out` → contact = primary recipient (To).
  - If the counterpart is unknown → fall back to `JobPosting.contact` (`name` / `email`) of the application.
- **occurred_at**: top message uses the real RFC822 `Date` header (`email.utils.parsedate_to_datetime`). Quoted messages use the parsed quote date; **if unparseable → `top_date − index_seconds`** so relative order (newer→older down the thread) is preserved and the NOT-NULL column is satisfied.
- **subject**: from the block's `Subject:` if present, else inherit the top subject.
- **body**: that message's own segment text only (the span between its header and the next separator). This is the point of splitting.
- **sentiment**: `NULL` (deterministic-only; user sets later).

Cap at **20 messages** per `.eml` to bound runaway threads (extra messages dropped, oldest first).

## Data Model Change

Add value `eml_import` to the `InteractionCreatedFrom` enum (`models.py:98-101`).

Alembic migration notes (account for the gotcha fixed in `6d66831`):
- `op.execute("ALTER TYPE <enumtype> ADD VALUE IF NOT EXISTS 'eml_import'")`.
- Run it in its **own** migration and do **not** consume the new value in the same transaction (Postgres makes a newly added enum value usable only after commit).
- Confirm the actual PG enum type name from the existing mini-crm migration before writing (do not assume `interactioncreatedfrom`).

No other schema change — `Interaction` already has every field we set.

## Backend API

Extend `backend/app/api/interactions.py`:

- `POST /api/applications/{aid}/interactions/import-eml`
  - Params: `file: UploadFile = File(...)`, `db`, `user`.
  - Reuse `_own_app(db, user, aid)` for ownership (404 otherwise).
  - Validate: extension `.eml`, size ≤ 10 MB (mirror `_read_docx_upload`). Reject others with 400/413.
  - `thread = parse_eml(await file.read(), llm=_eml_llm())`.
  - Map each message → `Interaction(...)`, bulk `add` + single `commit`.
  - Response model `ImportEmlOut { interactions: list[InteractionOut], count: int, used_llm: bool }`.
  - If `thread.messages` is empty (parse produced nothing) → 422 `could not parse email`.
- Reuse existing `DELETE /api/interactions/{iid}` for Undo (no new endpoint).
- `suggest_discard` is **not** computed here (sentiment is NULL on import).

## Frontend

- `frontend/src/api/interactions.ts`: add `importEml(appId: string, file: File): Promise<ImportEmlResp>` — FormData + `fetch`, `credentials: "include"`, no manual `Content-Type` (mirror `documents.uploadDocx`). Add `ImportEmlResp` type.
- `frontend/src/components/ActivityPanel.tsx`: add a dropzone (native `onDrop`/`onDragOver` + hidden `<input type=file accept=".eml">`, mirror `_VariantSettings.tsx`). On success:
  - `queryClient.invalidateQueries` for the interactions list.
  - Toast `Imported {count} interaction(s) · Undo`. Undo calls `interactions.delete(id)` for each returned id, then invalidates.
- Toast/Undo: reuse an existing notification mechanism if one exists; otherwise add a minimal transient snackbar component. (Resolve during planning by checking the frontend for an existing toast.)
- Drag-over visual state on the dropzone (highlight), and a spinner while the POST is in flight (LLM fallback can take a few seconds).

## Dependencies

- Backend: add `python-dateutil` for best-effort parsing of quoted-message date lines (stdlib only handles the RFC822 top header). `python-multipart` already present.
- Frontend: none (native drag-drop, existing fetch + react-query).

## Testing

- **Parser unit tests** (`backend/tests/`), fixture `.eml` files under a test fixtures dir:
  - single message (no thread) → 1 interaction, direction from `From` vs `user.email`.
  - Outlook-EN threaded reply → N messages, alternating directions, descending timestamps.
  - Gmail `On … wrote:` thread → N messages.
  - German `Von:/Gesendet:` and `Am … schrieb` thread → correct split + dates.
  - HTML-only email → `html_to_text` then split; assert non-empty bodies.
- **Confidence unit tests**: markers present + 1 segment → LOW; clean multi-segment → HIGH; unknown-sender+unparseable-date → LOW.
- **LLM fallback tests**: inject a **stub `LLMClient`** (Protocol already exists → no network) returning canned `LlmThread` JSON; assert a messy HTML-only thread → LOW → multi-message, and that `message[0]` is overridden by the stdlib top headers. Assert graceful degrade when `llm=None`.
- **API tests**: import creates N interactions and returns their ids; ownership → 404; wrong extension → 400; oversize → 413; empty parse → 422; works with LLM disabled.
- **Playwright e2e**: set the hidden file input to a fixture `.eml` (drag-drop of OS files isn't reliable in Playwright, so the input is the test surface) → timeline shows N rows → toast → Undo removes them.

## Risks / Open Items

- **Thread-split is best-effort.** Reliable: top message, EN/DE Outlook blocks, `On/Am … wrote/schrieb`. Weak: deeply nested HTML quotes, exotic clients, locale date formats. Mitigated by the LLM fallback and order-preserving date fallback. Auto-create + Undo keeps wrong splits one click from removal; rows are individually editable.
- **Direction for quoted blocks without a parseable sender** defaults to `in_` — may misclassify the user's own quoted replies in rare formats. Acceptable; user can flip direction per row.
- **Toast mechanism** may not exist yet in the frontend — resolve in planning.
- **PG enum type name** must be confirmed from the existing migration before writing the new one.
