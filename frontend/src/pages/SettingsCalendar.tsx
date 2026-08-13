import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { calendar } from "../api/calendar";

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
