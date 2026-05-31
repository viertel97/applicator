# Job Posting Search Bar — Design

**Date:** 2026-05-31
**Status:** Approved

## Goal

Add a search bar at the top of the applications list to filter job postings by
free-text query. Lets the user quickly narrow a long list without clicking
through the status / label / docs filters.

## Scope

- **Match against:** `job_posting.title`, `job_posting.company`,
  `job_posting.location`. Case-insensitive substring match.
- **Persistence:** Ephemeral. Search text lives in component state only; it
  clears on reload and is not synced to URL or localStorage.
- **Combination:** ANDs with the existing status / docs / label / reason
  filters — it narrows the already-filtered set, not replaces it.

Out of scope: backend search endpoint, full-text matching of description /
requirements / tech stack, fuzzy matching, search history.

## Where

All changes in `frontend/src/pages/ApplicationsList.tsx`. No new files, no API
or backend changes.

The component already filters client-side via the `visible` useMemo
(currently line ~214) and shows a `{visible.length} of {data.length}` counter
(line ~355). The search reuses both.

## Implementation

### State

One new state hook in `ApplicationsList`:

```tsx
const [query, setQuery] = useState("");
```

### Filter predicate

Extend the existing `visible` useMemo. Add `query` to its dependency array and
add a predicate. Null-safe because absent fields are dropped by
`filter(Boolean)`:

```tsx
const q = query.trim().toLowerCase();
if (q) {
  const hay = [a.job_posting?.title, a.job_posting?.company, a.job_posting?.location]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (!hay.includes(q)) return false;
}
```

Empty/whitespace-only query means no search filtering applied.

### UI

A text input rendered above the status-filter row (after `<AddApplicationForm />`,
before the status buttons at line ~232). Tailwind styling consistent with the
existing slate palette:

- Full-width text input.
- Placeholder: `Search title, company, location…`.
- A clear (✕) button shown only when the query is non-empty, which resets
  `query` to `""`.

### Counter

No change needed. The existing
`{visible.length} {…} {data.length !== visible.length && \` of ${data.length}\`}`
line already reflects the post-search match count.

## Edge Cases

- **Null fields:** A posting with a null title still shows its URL in the row,
  but search only covers title/company/location; `filter(Boolean)` keeps the
  match safe.
- **Whitespace query:** Trimmed; treated as empty (no filtering).
- **No matches:** List renders empty; counter shows `0 of N`.
- **Interaction with other filters:** A row must pass status, reason, docs,
  label *and* search predicates to be visible (logical AND).

## Testing

Playwright spec (new or appended to existing list spec under
`frontend/tests/`):

1. Seed / load the list with several applications.
2. Type a query matching a subset; assert only matching rows remain and the
   counter updates.
3. Clear the search (✕ or empty the field); assert the full filtered list
   returns.
4. Type a query matching nothing; assert empty list and `0 of N` counter.
