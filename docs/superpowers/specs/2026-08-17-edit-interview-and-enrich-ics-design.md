# Edit interview interactions + enrich the ICS feed

Date: 2026-08-17

## Problem

An interview interaction is created (manually, via Outlook sync, or email
webhook) but there is no way to **edit** it afterwards to attach the details
the user actually cares about: the full invitation mail and the meeting
(Teams/Zoom/Meet) join link.

The user subscribes to the Applicator ICS feed from Google Calendar. They want
**one** calendar entry — the Applicator one — that carries everything: the mail
info, a clickable join link, and a link back to the Applicator app. Today the
ICS event only contains `subject` + the Applicator deep-link in its
description, and `location` is whatever was captured (often empty). The mail
body never reaches the calendar.

Separately, clicking an interview on the in-app Calendar page lands at the top
of the application detail page; the timeline/interactions live at the bottom.

## Goals

1. Edit an existing interview interaction from the application detail page.
2. Capture the full mail (in `body`) and the meeting join link (in `location`).
3. Auto-detect a Teams/Zoom/Meet link from the pasted mail and use it as the
   location when none is set.
4. Enrich the single ICS event so Google Calendar shows the mail info +
   a Join link + the Applicator deep-link.
5. Clicking a (non-review) interview on the Calendar page scrolls straight to
   the activity panel on the detail page.

## Non-goals / deferred

- Full-width layout for `/applications/:id` (a later session).
- Editing non-interview interactions (only the interview step is editable here).
- Adding a separate "join" button to the in-app calendar chip — the user
  consumes the join link via Google Calendar, from the enriched ICS entry.
- No DB migration and no new API endpoints.

## Existing plumbing (confirmed)

- `Interaction` already has `subject`, `body`, `location`, `ends_at`,
  `interview_stage`, `needs_review` columns.
- `interactions.update` (PATCH `/api/interactions/:id`) already accepts all of
  these (`PatchInteractionInput = Partial<CreateInteractionInput> & {location,
  ends_at, needs_review, application_id}`; `CreateInteractionInput` carries
  `subject`/`body`). So editing needs **no** API or model change.
- `InterviewReviewModal` already edits start/end/location/stage/app of a
  `CalendarInterview` and saves via `interactions.update`, but only opens for
  `needs_review` chips and cannot edit `body`.
- `ics_feed` (`backend/app/api/calendar.py`) already builds
  `DESCRIPTION = subject + "/applications/{id}"` and `LOCATION = it.location`.

## Design

### 1. Generalize the interview modal (frontend)

Refactor `InterviewReviewModal` into a modal that works in two modes:

- Add a `mode: "review" | "edit"` prop (default keeps current review behavior).
- Accept the fields it edits from a plain object rather than only a
  `CalendarInterview`, so it can be opened with a full `Interaction` from the
  detail page. Keep the `CalendarInterview` call-site working.
- Add a **description textarea** bound to `body` (the full mail text).
- Save path (both modes) calls `interactions.update` with
  `occurred_at`, `ends_at`, `location`, `interview_stage`, `subject?`, `body`.
  - **review** mode: keeps the application-reassign `<select>` and sets
    `needs_review: false` (unchanged behavior).
  - **edit** mode: no app-reassign, no `needs_review` change; invalidates the
    detail queries (`application-timeline`, `interactions`) instead of the
    calendar ones.

Invalidation is chosen per mode so each call-site refreshes what it shows.

### 2. Edit affordance on interview rows (frontend)

In `ActivityTimeline`, interview interaction rows (`row.kind ===
"interaction" && row.data.channel === "interview"`) get an **Edit** button next
to the existing delete control. Clicking opens the modal in `edit` mode
pre-filled from `row.data`. On save the timeline refetches.

### 3. Meeting-link auto-detect (frontend, pure helper + tests)

New `frontend/src/lib/detectMeetingUrl.ts`:

```
detectMeetingUrl(text: string): string | null
```

Regex matches the first Teams / Zoom / Google Meet URL in the text
(`teams.microsoft.com/l/meetup-join/...`, `*.zoom.us/j/...`,
`meet.google.com/...`). Returns the URL or `null`.

On save in the modal: if the `location` field is empty and `body` contains a
detected URL, set `location` to that URL before PATCH. The user can always
override the location field by hand. Covered by `detectMeetingUrl.test.ts`.

### 4. Enrich the ICS event (backend)

In `ics_feed`, build the description from `subject`, `body`, and the deep-link,
joined by blank lines and skipping empties:

```
description="\n\n".join(filter(None, [it.subject, it.body, deep]))
```

`LOCATION` stays `it.location` (now typically the detected join link), so
Google Calendar renders a Join button. This keeps a single entry carrying the
mail info + join link + Applicator link. Add/extend a test in the ICS feed test
module asserting the body appears in `DESCRIPTION`.

### 5. Calendar → scroll deep-link (frontend)

- `InterviewChip`: non-review click navigates to
  `/applications/:id#activity` (review click unchanged).
- `ApplicationDetail`: wrap the `ActivityPanel` in a container with
  `id="activity"` and a `ref`. An effect reads `location.hash`; when it is
  `#activity`, call `scrollIntoView({ behavior: "smooth", block: "start" })`
  after the query data has loaded. Default tab (Timeline) is unchanged.

## Data flow

```
paste mail into edit modal (body)
      │  detectMeetingUrl(body) → location (if empty)
      ▼
interactions.update PATCH  ──►  interactions table (subject/body/location/…)
      │                                   │
      ▼                                   ▼
detail timeline/interactions          ics_feed  ──►  Google Calendar
(shows body/location)                 DESCRIPTION = subject+body+deep-link
                                      LOCATION    = join link → Join button
```

## Testing

- `detectMeetingUrl.test.ts`: Teams / Zoom / Meet matches, no-match → null,
  first-match-wins.
- ICS feed test: interview with a `body` renders that text inside
  `DESCRIPTION`; existing subject + deep-link assertions still pass.
- Manual: edit an interview, confirm body + detected location persist on the
  detail timeline; refetch the `.ics` feed and confirm the enriched
  DESCRIPTION/LOCATION; click a Calendar chip and confirm the page scrolls to
  the activity panel.

## Affected files

- `frontend/src/components/InterviewReviewModal.tsx` — generalize (mode, body).
- `frontend/src/components/ActivityTimeline.tsx` — Edit button on interview rows.
- `frontend/src/components/calendar/InterviewChip.tsx` — `#activity` hash.
- `frontend/src/pages/ApplicationDetail.tsx` — activity anchor + scroll effect.
- `frontend/src/lib/detectMeetingUrl.ts` (+ `.test.ts`) — new helper.
- `backend/app/api/calendar.py` — description includes `body`.
- ICS feed test module — assert body in description.
