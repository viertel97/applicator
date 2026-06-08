# Filter Dependencies & Empty-State Diagnostics — Design

**Date:** 2026-06-08
**Status:** Approved

## Goal

Make the applications-list filters self-explanatory. Today, deselecting all
status buttons shows zero entries with no explanation, and the Reason picker
silently appears/disappears with the Discarded status. Surface *why* the list
is empty and *which* filters relate to which — without changing any existing
filter behavior.

## Background — current filter semantics

`frontend/src/pages/ApplicationsList.tsx` combines five filters with logical
AND:

- **Status** (`hiddenStatuses: Set<AppStatus>`): inclusion-style. A highlighted
  button = "show this status". Predicate hides when `hiddenStatuses.has(status)`
  (line ~218). Deselect all → every status hidden → **zero entries**.
- **Reason** (`reasonFilter`): only applies to `discarded` items. The picker is
  rendered only while Discarded is visible and auto-clears when Discarded is
  re-hidden (lines ~145-150, ~274).
- **Docs** (`filterDocs`): narrowing. Empty = show all; selecting requires the
  item to have *all* selected docs.
- **Labels** (`filterLabelIds`): server-side — `applications.list(filterLabelIds)`
  (line ~109). Empty = all.
- **Search** (`query`): `matchesSearch` over title/company/location.

The status filter's "empty = nothing" is the opposite of docs/labels'
"empty = everything", which is the core source of confusion.

## Scope

In scope:
- A diagnostic empty-state with a one-click fix when filters exclude all items.
- Persistent cues: explicit "showing N of 9" on the status row; the Reason
  picker always visible, disabled with a hint when Discarded is hidden.
- Extracting the filter predicate into a pure, unit-tested helper.

Out of scope:
- Changing any filter's behavior or empty-selection semantics.
- Backend / API changes.
- Reworking filter state into a hook or declarative registry (considered as
  approach C, rejected as scope creep).

## Where

- New: `frontend/src/lib/filterDiagnostics.ts` (+ `filterDiagnostics.test.ts`)
- New: `frontend/src/components/FilterEmptyState.tsx`
- Edit: `frontend/src/pages/ApplicationsList.tsx`
- Edit: `frontend/src/components/DiscardReasonPicker.tsx` (add `disabled` prop)

## Implementation

### 1. Diagnostic core — `lib/filterDiagnostics.ts`

Single source of truth for the client-side filter predicate (moved out of the
`visible` useMemo) plus the empty-state diagnosis.

```ts
import type { Application, AppStatus } from "../api/applications";

const ALL_STATUSES: AppStatus[] = [
  "draft", "applied", "offer", "rejected", "accepted",
  "withdrawn", "discarded", "need_call", "apply_direct",
];

export interface FilterState {
  hiddenStatuses: Set<AppStatus>;
  reasonFilter: string | null;
  filterDocs: string[];
  query: string;
  filterLabelIds: string[];
}

export type EmptyReason =
  | "all-statuses-hidden"
  | "no-status-match"
  | "reason"
  | "docs"
  | "search"
  | "labels"
  | "mixed"
  | null;

export function applyFilters(data: Application[], f: FilterState): Application[];
export function diagnoseEmpty(data: Application[], f: FilterState): EmptyReason;
```

`applyFilters` replicates today's predicate exactly: hide if
`hiddenStatuses.has(status)`; if `reasonFilter` and status is `discarded`,
require `discard_reason_id === reasonFilter`; if `filterDocs` non-empty, require
the posting's `required_documents` to include all; require `matchesSearch`.
Labels are excluded from this predicate (already applied server-side).

`diagnoseEmpty` (only meaningful copy lives here; the *cause*, not the message):

1. **`data` empty:**
   - `filterLabelIds` non-empty → `"labels"`.
   - else → `null` (no applications exist at all; render the normal empty list,
     not a filter warning).
2. **`data` non-empty but `applyFilters(...)` empty:**
   - every status in `ALL_STATUSES` is hidden → `"all-statuses-hidden"`.
   - else relax each filter independently (ignore status / ignore reason /
     ignore docs / ignore query) and count how many single relaxations recover
     ≥1 item:
     - exactly one recovers → that filter's kind (`"no-status-match"`,
       `"reason"`, `"docs"`, `"search"`).
     - zero, or more than one → `"mixed"`.
3. Otherwise (`applyFilters` non-empty) → `null`.

### 2. EmptyState — `components/FilterEmptyState.tsx`

Presentational. Owns the copy and the fix-button label per kind; emits a fix
intent to the parent.

```tsx
type Props = {
  reason: Exclude<EmptyReason, null>;
  onFix: (reason: Exclude<EmptyReason, null>) => void;
};
```

| reason               | message                                          | fix label              |
|----------------------|--------------------------------------------------|------------------------|
| all-statuses-hidden  | All statuses deselected — nothing to show.       | Show all statuses      |
| no-status-match      | No items match the selected statuses.            | Show all statuses      |
| reason               | Reason filter excludes every discarded item.     | Clear reason           |
| docs                 | No items have all the selected documents.        | Clear document filters |
| search               | No items match your search.                      | Clear search           |
| labels               | No items have all the selected labels.           | Clear labels           |
| mixed                | Active filters exclude all items.                | Reset all filters      |

Renders a muted warning box (slate/amber palette, consistent with existing
chips) containing the message and a single fix button that calls
`onFix(reason)`.

### 3. Wire into `ApplicationsList.tsx`

- Build a `FilterState` from existing state and pass it to `applyFilters` inside
  the existing `visible` useMemo (replacing the inline predicate).
- Compute `const emptyReason = isLoading ? null : diagnoseEmpty(data ?? [], state);`
- When `visible.length === 0 && emptyReason`, render `<FilterEmptyState reason={emptyReason} onFix={handleFix} />`
  in place of the empty `<ul>`. The `{visible.length} of {data.length}` counter
  line stays.
- `handleFix(reason)` maps to the existing setters (reusing the current
  `saveHiddenStatuses` / localStorage writes):
  - `all-statuses-hidden` | `no-status-match` → `setHiddenStatuses(new Set())` + save
  - `reason` → `setReasonFilter(null)`
  - `docs` → `setFilterDocs([])` + localStorage
  - `search` → `setQuery("")`
  - `labels` → `setFilterLabelIds([])`
  - `mixed` → all of the above (full reset)

  Note: "Show all statuses" clears the hidden set entirely, which also reveals
  the default-hidden rejected/withdrawn/discarded — intended as a recovery.

### 4. Persistent cues (inline JSX)

- **Status row:** prefix with a muted `Status` label and a
  `(showing {9 - hiddenStatuses.size} of 9)` counter so "highlighted = shown" is
  explicit before the user ever hits an empty list.
- **Reason picker:** always render the Reason group. Add an optional
  `disabled?: boolean` prop to `DiscardReasonPicker` (applies to the `<select>`,
  hides the `+ Add` button). When `!discardedVisible`, render it disabled,
  indented under the status row, with the hint
  `Show Discarded to filter by reason`. When Discarded is visible, behavior is
  unchanged.

### 5. DiscardReasonPicker change

Add `disabled?: boolean` to `Props`. Pass to the `<select disabled={disabled}>`;
when `disabled`, suppress the `+ Add` affordance. No other behavior change;
existing call sites omit the prop and are unaffected.

## Edge Cases

- **No applications at all** (`data` empty, no label filter): `diagnoseEmpty`
  returns `null` → normal empty list, no filter warning.
- **Label filter returns nothing** (`data` empty, labels active): `"labels"` →
  the only reason discoverable client-side since labels are server-filtered.
- **Multiple culprits**: if no single filter relaxation recovers results →
  `"mixed"` with a full reset.
- **Loading**: while `isLoading`, `emptyReason` is `null`; the existing
  `Loading…` branch renders.
- **Reason auto-clear**: unchanged — re-hiding Discarded still clears
  `reasonFilter` (existing effect). The picker then shows disabled.

## Testing

- **Primary — `frontend/src/lib/filterDiagnostics.test.ts`** (`node:test` +
  `node:assert/strict`, mirroring `search.test.ts`, importing `./filterDiagnostics.ts`).
  A small `app()` factory builds `Application` partials. One case per
  `EmptyReason`:
  - all statuses hidden → `"all-statuses-hidden"`
  - one status shown but no data matches it → `"no-status-match"`
  - reason filter excludes all discarded → `"reason"`
  - docs filter too strict → `"docs"`
  - search excludes all → `"search"`
  - `data` empty + labels active → `"labels"`
  - two filters needed to recover → `"mixed"`
  - non-empty result and no-apps cases → `null`
  - plus `applyFilters` parity tests for status/reason/docs/search predicates.
- **e2e (optional/manual)**: Playwright — deselect all statuses, assert the
  diagnostic hint + `Show all statuses` button appear and that clicking it
  restores the list. Run **outside** the nono sandbox; Playwright SIGSEGVs
  inside it (known issue), so this is not a blocker for the change.
