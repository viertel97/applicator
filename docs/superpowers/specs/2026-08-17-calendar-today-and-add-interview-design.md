# Calendar: highlight today + add interview from a day

Date: 2026-08-17

## Goal

Two small improvements to the desktop calendar month view:

1. Highlight the current day so it's easy to locate.
2. Let the user add a job interview directly from the calendar: click a day,
   pick the job position and a time, save.

## Scope

- Desktop `MonthGrid` path only. The mobile `AgendaList` is unchanged this pass.
- No backend changes. Interviews are `Interaction` rows with
  `channel = interview` on an `Application`; the existing
  `POST /api/applications/{aid}/interactions` endpoint already accepts them.

Out of scope (YAGNI): editing/deleting from the calendar, drag-to-reschedule,
end time / location / stage fields in the add dialog, mobile add flow.

## 1. Highlight today

File: `frontend/src/components/calendar/MonthGrid.tsx` (+ `calendarBuckets.ts`).

- Export the existing `dayKey(d: Date): string` helper from `calendarBuckets.ts`
  (currently module-private) so the grid can reuse the exact same day bucketing
  logic instead of duplicating it.
- In `MonthGrid`, compute `todayKey = dayKey(new Date())` once.
- For the cell where `dayKey(day) === todayKey`, render an accent treatment:
  a ring on the cell and the date number as a small accent badge. Must not
  shift layout (same cell height whether or not it's today).
- Uses the existing accent tokens (`accent` / `accentFg`, `ring`).

## 2. Add interview from a day

### MonthGrid changes

- Add an optional prop `onDayClick?: (day: Date) => void`.
- When provided, each day cell is clickable (button semantics: keyboard focus,
  `aria-label` describing the date) and calls `onDayClick(day)`.
- Interview chips already inside a cell get `stopPropagation` on their own
  interaction so clicking an existing chip does not trigger the add dialog.
- When `onDayClick` is not provided, cells behave exactly as today (no
  regression for any other caller — though Calendar is the only caller).

### New component: `frontend/src/components/calendar/AddInterviewDialog.tsx`

Props: `{ day: Date; onClose: () => void }`.

Styling mirrors `InteractionLogModal`:
`fixed inset-0 bg-black/40 flex items-center justify-center z-50`, inner
`bg-surface border border-border rounded shadow-lg p-4`, accent Save button
(`bg-accent text-accentFg`), border Cancel button.

Behavior:

- Heading shows the fixed date, e.g. `Add interview · Mon 18 Aug`.
- Loads applications via `useQuery(["applications"], applications.list)`.
- Filters client-side to **active** applications:
  `status ∉ { rejected, discarded, withdrawn, accepted }`.
- Renders them in a `<select>` labeled `company · title`
  (fallback to `url` when the posting has no company/title). Sorted by label.
- A `<input type="time">` for the start time (default a sensible value, e.g.
  `09:00`).
- Save builds `occurred_at` from the fixed day + chosen time in **local** time,
  converted to ISO (`new Date(year, month, date, hh, mm).toISOString()`), then
  calls `interactions.create(appId, { channel: "interview", direction: "in",
  occurred_at })` via a `useMutation`.
- onSuccess: `qc.invalidateQueries({ queryKey: ["calendar-interviews"] })` and
  `onClose()`.
- Guards:
  - Save disabled until a job is selected.
  - If there are no active applications, show an empty-state message instead of
    the form ("No active applications to schedule an interview for.").
  - Save disabled while the mutation is pending.

### Calendar.tsx changes

- Add state `const [addDay, setAddDay] = useState<Date | null>(null)`.
- Pass `onDayClick={setAddDay}` to `MonthGrid`.
- When `addDay` is set, render `<AddInterviewDialog day={addDay}
  onClose={() => setAddDay(null)} />`.

## Data flow

```
click day cell ──▶ Calendar.setAddDay(day)
                     └─▶ AddInterviewDialog(day)
                           ├─ load applications.list() → filter active → <select>
                           ├─ <input type=time>
                           └─ Save ──▶ interactions.create(appId, {
                                          channel: "interview",
                                          direction: "in",
                                          occurred_at: local(day+time) → ISO,
                                        })
                                        └─ invalidate ["calendar-interviews"]
                                        └─ onClose()  ──▶ grid refetches, chip appears
```

## Error handling

- `applications.list()` failure: show an inline error line in the dialog; keep
  Cancel usable.
- `interactions.create` failure: show an inline error line; leave the dialog
  open so the user can retry. Do not close on error.

## Testing

- `frontend/src/lib/calendarBuckets.test.ts`: add a case asserting `dayKey` is
  exported and stable (already covers month matrix / eventsForDay).
- New `AddInterviewDialog` component test:
  - Active-only filter: given apps of mixed statuses, only active ones appear in
    the select.
  - `occurred_at` construction: given a fixed day + a chosen time, the mutation
    is called with the correct local-time ISO string and
    `channel: "interview", direction: "in"`.
  - Save disabled until a job is selected.
  - Empty-state renders when no active apps.
- MonthGrid: today's cell gets the accent treatment (query for the badge/ring
  on the matching date), and clicking a day cell invokes `onDayClick` with that
  date while clicking a chip does not.

## Files touched

- `frontend/src/lib/calendarBuckets.ts` — export `dayKey`.
- `frontend/src/components/calendar/MonthGrid.tsx` — today highlight, clickable
  days, `onDayClick` prop.
- `frontend/src/components/calendar/AddInterviewDialog.tsx` — new.
- `frontend/src/pages/Calendar.tsx` — dialog state + wiring.
- Tests as above.
