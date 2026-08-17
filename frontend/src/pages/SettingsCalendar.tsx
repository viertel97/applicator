import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { calendar, type CalendarInterview } from "../api/calendar";
import { STAGE_LABEL } from "../lib/interviewSummary";

const STAGE_DOT: Record<string, string> = {
  phone_screen: "bg-blue-500",
  technical: "bg-violet-500",
  onsite: "bg-amber-500",
  hr: "bg-teal-500",
  final: "bg-emerald-600",
  other: "bg-slate-500",
};

function formatWhen(starts: string, ends: string | null): string {
  const s = new Date(starts);
  const date = s.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  const start = s.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (!ends) return `${date} · ${start}`;
  const end = new Date(ends).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${date} · ${start} – ${end}`;
}

// Renders the user's next confirmed interview exactly as Google Calendar shows
// it from the enriched ICS feed: title + time, the join link (LOCATION) with a
// Join button, and the Applicator deep-link. The event description also carries
// the invitation mail (subject + body), which the calendar list endpoint does
// not expose here — hence the note rather than the full body.
function PreviewCard({ ev }: { ev: CalendarInterview }) {
  const stage = ev.interview_stage ?? "other";
  const isUrl = !!ev.location && /^https?:\/\//i.test(ev.location);
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm max-w-sm">
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className={`inline-block w-2.5 h-2.5 rounded-full ${STAGE_DOT[stage] ?? "bg-slate-500"}`} />
        <span className="text-sm font-semibold text-fg">
          {ev.company} · {STAGE_LABEL[stage] ?? "interview"}
        </span>
      </div>
      <div className="text-xs text-muted mt-1">{formatWhen(ev.starts_at, ev.ends_at)}</div>

      {ev.location && (
        <div className="mt-3 flex items-center gap-2">
          <span aria-hidden="true">📍</span>
          {isUrl ? (
            <>
              <a
                href={ev.location}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-accent hover:underline truncate"
              >
                {ev.location.replace(/^https?:\/\//i, "")}
              </a>
              <span className="ml-auto px-2 py-0.5 rounded bg-accent text-accentFg text-xs">Join</span>
            </>
          ) : (
            <span className="text-xs text-fg truncate">{ev.location}</span>
          )}
        </div>
      )}

      <hr className="my-3 border-border" />

      <div className="text-xs text-muted">Your invitation mail appears in the event description.</div>
      <Link
        to={`/applications/${ev.application_id}#activity`}
        className="mt-2 inline-block text-xs text-accent hover:underline"
      >
        Open in Applicator ↗
      </Link>
    </div>
  );
}

function CalendarEntryPreview() {
  const q = useQuery({
    queryKey: ["calendar-preview"],
    queryFn: () => calendar.interviews(new Date().toISOString()),
  });
  // The list is ordered soonest-first; pick the next confirmed (non-review) one,
  // matching what the ICS feed actually publishes.
  const next = (q.data ?? []).find((ev) => !ev.needs_review) ?? null;

  return (
    <div className="mb-6">
      <div className="text-sm font-semibold mb-1">Your next interview in the calendar</div>
      {q.isPending ? (
        <div className="text-xs text-muted">Loading…</div>
      ) : next ? (
        <PreviewCard ev={next} />
      ) : (
        <div className="rounded-lg border border-dashed border-border bg-surface p-4 text-xs text-muted max-w-sm">
          No upcoming interviews yet — your next confirmed interview will show up here and in Google Calendar.
        </div>
      )}
    </div>
  );
}

function UrlRow({ label, url }: { label: string; url: string | null }) {
  return (
    <div className="mb-3">
      <div className="text-sm font-semibold mb-1">{label}</div>
      <div className="flex gap-2">
        <input
          readOnly
          value={url ?? ""}
          className="flex-1 px-2 py-1 rounded border border-border bg-surface text-xs text-fg"
        />
        <button
          type="button"
          aria-label={`Copy ${label}`}
          onClick={() => url && navigator.clipboard.writeText(url)}
          className="px-2 py-1 rounded bg-accent text-accentFg text-xs"
        >
          Copy
        </button>
      </div>
    </div>
  );
}

export default function SettingsCalendar() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["calendar-tokens"],
    queryFn: () => calendar.tokens(),
  });
  const regen = useMutation({
    mutationFn: (kind: "ingest" | "calendar") => calendar.regenerate(kind),
    onSuccess: (data) => qc.setQueryData(["calendar-tokens"], data),
  });

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Calendar &amp; Email</h1>

      <UrlRow
        label="iCal subscription URL (Google Calendar → From URL)"
        url={q.data?.calendar_url ?? null}
      />
      <button
        type="button"
        onClick={() => {
          if (window.confirm("This immediately invalidates the old URL. Any calendar subscriptions or email rules pointing at it will stop working. Continue?"))
            regen.mutate("calendar");
        }}
        disabled={regen.isPending}
        className="text-xs text-rose-600 mb-6 disabled:opacity-50"
      >
        Regenerate iCal URL
      </button>

      <CalendarEntryPreview />

      <UrlRow
        label="Forward-to-add email webhook URL"
        url={q.data?.ingest_url ?? null}
      />
      <button
        type="button"
        onClick={() => {
          if (window.confirm("This immediately invalidates the old URL. Any calendar subscriptions or email rules pointing at it will stop working. Continue?"))
            regen.mutate("ingest");
        }}
        disabled={regen.isPending}
        className="text-xs text-rose-600 disabled:opacity-50"
      >
        Regenerate webhook URL
      </button>

      <p className="text-xs text-muted mt-2">Regenerating invalidates the old URL.</p>
    </div>
  );
}
