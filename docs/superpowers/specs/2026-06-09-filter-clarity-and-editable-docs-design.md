# Filter Clarity + Editable Required Documents — Design

**Date:** 2026-06-09
**Status:** Approved (pending spec review)

## Problem

Two related pain points in the applications list:

1. **Filter logic is silently mixed.** Some facets combine with OR, some with AND,
   and the UI gives no indication which is which:
   - Labels (`label_ids`, backend): OR within the set — `Application.labels.any(LabelModel.id.in_(label_ids))`.
   - Required documents (`filterDocs`, frontend): AND within the set — `f.filterDocs.every((d) => docs.includes(d))`.
   - Statuses (`hiddenStatuses`, frontend): visibility toggle (show all not hidden).
   - Awaiting (`awaitingFilter`, frontend): tristate all/only/hide.
   - All facets are ANDed together.

   The awaiting tristate button and the document chips also share one unlabeled row
   (`ApplicationsList.tsx:362`), which makes the document filter look like an
   afterthought and hides its meaning.

2. **Auto-extracted required documents can't be corrected.** The LLM extractor
   populates `job_posting.required_documents` (vocab: `cv, cover_letter, portfolio,
   references, certificates, other`). When it gets them wrong, the user can't fix
   them: the chips are read-only (`JobPostingPanel.tsx:119-135`), the section is
   hidden when empty, and `required_documents` is absent from `JobPostingPatch`
   (`applications.py:83`).

## Goal

- Make the filter bar self-explanatory: every facet shows its own combining
  operator; the cross-facet rule (AND) is stated once.
- Let the user manually edit a position's required-documents set.

Non-goals (explicitly out of scope, YAGNI):
- Per-facet AND/OR toggles. The user wants visibility, not switches.
- Changing the matching semantics of any filter.
- Making other auto-extracted fields editable (only `required_documents`).

## Decision

**Do not flatten the logic. Label it.** Each facet keeps its natural operator;
the UI surfaces it. Cross-facet logic stays AND.

Confirmed facet semantics (unchanged):

| Facet            | Within-facet logic        | Source (unchanged)                         |
|------------------|---------------------------|--------------------------------------------|
| Status           | visibility (show ≠ hidden)| `hiddenStatuses` set                       |
| Awaiting         | tristate all/only/hide    | `awaitingFilter`                           |
| Requires (docs)  | **all of** (AND, subset)  | `filterDocs.every(...)` in filterDiagnostics |
| Labels           | **any of** (OR)           | `label_ids` `.any(...)` backend            |
| Search           | substring                 | `query`                                    |

"Requires = all of" matches the user's chosen semantics: selecting `cv, cover_letter`
shows positions that require *at least* those documents (may require more).

## Part 1 — Filter clarity (presentation only)

File: `frontend/src/pages/ApplicationsList.tsx` (filter bar markup).
No change to `frontend/src/lib/filterDiagnostics.ts` (matching logic untouched).

Layout after change:

```
Search: [_______________]

Status — showing 5 of 7        [Applied][Interview]...      (visibility)
Awaiting reply  ⟳ all/only/hide                             (tristate, own row)

Requires · all of    [CV][Cover letter][Portfolio]...       (AND within)
Labels · any of      [Berlin][Remote]...                    (OR within)

ⓘ Sections combine with AND. Within a section: Requires = all, Labels = any.
```

Concrete edits:
- Split the shared awaiting+docs row (`ApplicationsList.tsx:362`) into two rows:
  awaiting on its own row; required-documents chips in their own labeled section
  with header `Requires · all of`.
- Add `· any of` operator hint to the existing Labels header (`ApplicationsList.tsx:413`).
- Add a one-line legend below the filter bar:
  `Sections combine with AND. Within a section: Requires = all, Labels = any.`
- Keep the Status header's existing `showing N of M` text (it is a visibility
  toggle, not an AND/OR facet, so no operator badge).

## Part 2 — Editable required documents

### Backend
File: `backend/app/api/applications.py`.

- Add to `JobPostingPatch` (line 83): `required_documents: list[str] | None = None`.
- Validate values against the vocab `{cv, cover_letter, portfolio, references,
  certificates, other}`. Reject any unknown value with HTTP 422. Use a Pydantic
  field validator on `JobPostingPatch` so validation happens before the handler.
  Source the vocab from one canonical constant: `_DOC_VOCAB` in
  `extractor/schemas.py` is currently a prompt string
  (`"cv, cover_letter, portfolio, references, certificates, other"`). Introduce a
  canonical `DOC_TYPES: tuple[str, ...]` (or frozenset) and derive the prompt
  string from it (`", ".join(DOC_TYPES)`) so the LLM vocab and the validation set
  never drift. Import `DOC_TYPES` into the validator.
- The existing `patch_job_posting` handler already does
  `model_dump(exclude_unset=True)` + `setattr` and sets `job_posting_dirty` for
  non-contact edits, so `required_documents` is persisted with no handler change.
- No migration: `required_documents` already exists as a JSON column.

### Frontend
Files: `frontend/src/pages/ApplicationsList.tsx`, `frontend/src/components/JobPostingPanel.tsx`,
new `frontend/src/lib/docs.ts`.

- Extract `ALL_DOCS` and `DOC_LABEL` (currently in `ApplicationsList.tsx:27-36`)
  into `frontend/src/lib/docs.ts`; import in both ApplicationsList and JobPostingPanel.
- In `JobPostingPanel`, replace the read-only chips (`lines 119-135`) with toggle
  chips over all 6 vocab values: selected = filled, unselected = outline. Toggling
  writes to the existing `draft` via `update("required_documents", nextArray)`.
- Render the section always (not only when non-empty), so the user can **add**
  documents the extractor missed.
- Persist via the existing Save button (`applications.patchJobPosting`); no new
  endpoint or mutation.

## Testing

- **Backend (pytest):** PATCH `/{aid}/job-posting` with `required_documents`:
  - valid subset persists and round-trips on GET;
  - unknown value → 422;
  - edit sets `job_posting_dirty` like other non-contact edits.
  This change adds no enum/migration, so the testcontainers schema-drift concern
  does not apply here.
- **Frontend:** verify in the browser against the built Docker image — toggle chips
  on/off, add a doc to an empty set, save, reload, confirm persistence; confirm the
  relabeled filter bar reads correctly and matching is unchanged.

## Files touched

- `backend/app/api/applications.py` — `JobPostingPatch` field + validator.
- `backend/app/extractor/schemas.py` — add canonical `DOC_TYPES`; derive `_DOC_VOCAB` from it.
- `frontend/src/lib/docs.ts` — new shared `ALL_DOCS` / `DOC_LABEL`.
- `frontend/src/pages/ApplicationsList.tsx` — import shared docs; regroup + relabel filter bar.
- `frontend/src/components/JobPostingPanel.tsx` — editable doc chips.
- Tests: backend PATCH test for `required_documents`.
