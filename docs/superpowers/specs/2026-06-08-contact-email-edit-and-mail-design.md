# Contact Email Edit + Mail-from-Log-Interaction — Design

## Problem

A job posting's contact lives in `JobPosting.contact` (JSON: `name`, `role`,
`email`, `phone`), populated by LLM extraction. When extraction finds no email
there is no way to add one: `ContactBlock` is read-only and renders nothing when
empty, and `JobPostingPanel` edits every other field but not the contact.

Two flows depend on `contact.email` and break when it is missing:

- **Draft inquiry** (`POST /{aid}/inquiry/draft`) returns `recipient =
  contact.email`, so a generated draft has no addressee.
- **"Open in mail"** in `InteractionLogModal` builds a `mailto:` from the stored
  `contact.email` only — the editable `contactHandle` field the user types is
  ignored, and the typed value never persists back to the posting.

## Goal

1. Let the user add/edit a job posting's contact email (and the other contact
   fields) even when extraction produced none.
2. When the user types an email while logging an outgoing mail interaction:
   "Open in mail" uses it immediately, and saving persists it onto the job
   posting so future drafts/mailto are addressed.

## Decisions (locked)

- **Edit surfaces:** both the job-posting panel and the log-interaction modal.
- **Save-back rule:** typed email in the modal **always overwrites** the stored
  `contact.email`.
- **Recipient source:** prefer the typed value, fall back to the stored email
  (so mailto works before saving).
- **Persistence approach:** frontend-only, reusing the existing
  `PATCH /{aid}/job-posting` (its `JobPostingPatch` already accepts `contact`).
  No new endpoint, no schema change, no migration.
- **Dirty flag:** a contact-only edit must **not** set `job_posting_dirty`
  (contact does not affect generated documents).

## Approach

The backend already supports updating `contact` via `PATCH /{aid}/job-posting`;
`setattr` replaces the whole `contact` dict, so the frontend always sends the
full merged dict (no clobber of `name`/`role`/`phone`). The only backend change
is guarding the dirty flag so contact-only patches don't falsely mark the
application as needing regeneration. Everything else is frontend wiring across
three components, reusing the existing `patchJobPosting` API client and the
modal's existing multi-mutation pattern.

Rejected alternatives:
- **Backend writeback inside the interactions create endpoint** — atomic single
  request, but couples the interactions module to job-posting state.
- **Dedicated `PATCH /{aid}/contact` endpoint** — cleaner partial-merge
  semantics, but new surface where PATCH job-posting already does the job.

## Backend changes (`backend/app/api/applications.py`)

`patch_job_posting` (~line 368). Today: any update sets `job_posting_dirty` when
`generated_md` is present. Change so only non-contact keys trip the flag:

```python
updates = body.model_dump(exclude_unset=True)
for k, v in updates.items():
    setattr(app_row.job_posting, k, v)
non_contact = {k for k in updates if k != "contact"}
if app_row.generated_md is not None and non_contact:
    app_row.job_posting_dirty = True
```

`JobPostingPatch.contact` already exists — no schema change. No migration.

## Frontend changes

### 1. `frontend/src/components/ContactBlock.tsx` — read-only → editable

- Render **always** (drop the `null`-when-empty early returns) so a missing
  email can be added.
- Props change from `{ contact }` to a controlled shape:
  `{ contact, disabled, onChange(field, value) }`.
- Inputs for `email`, `name`, `role`, `phone`; empty string → `null` on change.
- Keep it presentational — state lives in the parent panel.

### 2. `frontend/src/components/JobPostingPanel.tsx` — nested contact in draft

- `contactValue(field) = draft.contact?.[field] ?? jp.contact?.[field] ?? ""`.
- `updateContact(field, val)`: merge into `draft.contact` seeded from
  `jp.contact` (`{ ...(draft.contact ?? jp.contact ?? {}), [field]: val || null }`),
  then mark dirty.
- Pass `contact`, `disabled`, and `updateContact` to `ContactBlock`.
- Existing Save already sends the whole `draft`, so `{ contact }` rides along to
  `patchJobPosting`. On success the `["application", appId]` invalidation already
  refreshes the panel.

### 3. `frontend/src/components/InteractionLogModal.tsx`

- **Recipient prefers typed.** Replace use of the stored-only `recipient`
  (line 89) in the mail-actions block with
  `effectiveRecipient = contactHandle.trim() || (app?.job_posting?.contact?.email ?? null)`.
  mailto and the link's disabled/styling use `effectiveRecipient`. The block is
  already mail + outgoing only, so `contactHandle` is an email here.
- **Writeback on save.** In `create.onSuccess`, when
  `channel === "mail" && direction === "out" && contactHandle.trim() &&
  app?.job_posting`, fire a `patchJobPosting(appId, { contact: { ...(app.job_posting.contact ?? {}), email: contactHandle.trim() } })`
  mutation (always overwrite) and invalidate `["application", appId]`. Capture
  the email before `reset()`. This is **best-effort**: the interaction is already
  saved; a writeback failure surfaces a small inline error and does not block
  closing the modal.
- Draft button is unchanged (gated on pipeline-ready, works without an email).
- The writeback path (`direction=out`) never overlaps the discard suggestion flow
  (`direction=in`).

### API client

`frontend/src/api/applications.ts` — none. `patchJobPosting` exists (line 113)
and `contact` is already on the `JobPosting` type (line 33).

## Data flow

- **Panel:** type email → Save → `PATCH /job-posting { contact }` (no dirty) →
  invalidate → `ContactBlock` and any mailto reflect it.
- **Modal:** type email → "Open in mail" works live → Save → interaction created
  **and** email persisted onto the posting → future drafts/mailto are addressed.

## Testing

**Backend** (extend the job-posting patch test module):
- PATCH with only `contact` and `generated_md` present → `job_posting_dirty`
  stays `False`.
- PATCH with a non-contact field and `generated_md` present → dirty becomes
  `True` (regression guard for existing behavior).

**Frontend** — manual verification against the built Docker image (rebuild after
edits): panel add-email persists and survives reload; modal typed email enables
"Open in mail" and persists to the posting after Save. Playwright e2e is skipped
here (SIGSEGVs inside the sandbox); verify manually or run outside the sandbox.

## Out of scope

- Validating email format (browser `type="email"` only, if convenient).
- Writing back `contact_name` from the modal (email only, per the locked rule).
- A dedicated contact endpoint or partial-merge PATCH semantics.
