import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { calendar } from "../api/calendar";

// Illustrative mock of a confirmed interview as Google Calendar renders it from
// the enriched ICS feed: title + time, the join link (LOCATION) with a Join
// button, and a DESCRIPTION carrying subject + mail body + the Applicator link.
// Static example data — it does not reflect the user's real interviews.
function CalendarEntryPreview() {
  return (
    <div className="mb-6">
      <div className="text-sm font-semibold mb-1">What a calendar entry looks like</div>
      <div className="rounded-lg border border-border bg-surface p-4 shadow-sm max-w-sm">
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="inline-block w-2.5 h-2.5 rounded-full bg-violet-500" />
          <span className="text-sm font-semibold text-fg">Acme · technical</span>
        </div>
        <div className="text-xs text-muted mt-1">Tue, Sep 1 · 14:00 – 15:00</div>

        <div className="mt-3 flex items-center gap-2">
          <span aria-hidden="true">📍</span>
          <a
            href="https://meet.google.com/abc-defg-hij"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-accent hover:underline truncate"
          >
            meet.google.com/abc-defg-hij
          </a>
          <span className="ml-auto px-2 py-0.5 rounded bg-accent text-accentFg text-xs">Join</span>
        </div>

        <hr className="my-3 border-border" />

        <div className="text-xs text-fg whitespace-pre-wrap">
          {"Technical interview – Acme\n\nHi Janik, here's the Teams link for your interview…"}
        </div>
        <div className="mt-2 text-xs text-accent hover:underline">Open in Applicator ↗</div>
      </div>
      <p className="text-xs text-muted mt-1">Example — illustrative only, not your real data.</p>
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
