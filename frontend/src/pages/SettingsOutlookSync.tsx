import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  calendar,
  type CalendarEntry,
  type SyncStatus,
} from "../api/calendar";

function StatusBadge({ status }: { status: string | null }) {
  const tone =
    status === "ok"
      ? "bg-emerald-100 text-emerald-700"
      : status === "error"
        ? "bg-rose-100 text-rose-700"
        : "bg-amber-100 text-amber-700";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${tone}`}>
      {status ?? "—"}
    </span>
  );
}

const ENTRY_STATUS_LABEL: Record<CalendarEntry["status"], string> = {
  pending: "Ausstehend",
  confirmed: "Bestätigt",
  dismissed: "Ausgeblendet",
};

function EntryStatusBadge({ status }: { status: CalendarEntry["status"] }) {
  const tone =
    status === "confirmed"
      ? "bg-emerald-100 text-emerald-700"
      : status === "dismissed"
        ? "bg-rose-100 text-rose-700"
        : "bg-amber-100 text-amber-700";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${tone}`}>
      {ENTRY_STATUS_LABEL[status]}
    </span>
  );
}

function ConnectionCard() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["outlook-sync-status"],
    queryFn: () => calendar.syncStatus(),
  });
  const sync = useMutation({
    mutationFn: () => calendar.syncNow(),
    onSuccess: (data: SyncStatus) => {
      qc.setQueryData(["outlook-sync-status"], data);
      qc.invalidateQueries({ queryKey: ["calendar-entries"] });
      qc.invalidateQueries({ queryKey: ["calendar-suggestions"] });
      qc.invalidateQueries({ queryKey: ["suggestions"] });
    },
  });

  const s = q.data;
  return (
    <div className="border border-border rounded p-4 space-y-3 mb-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Outlook-Verbindung</h2>
        <button
          type="button"
          disabled={sync.isPending || (s ? !s.oauth_enabled : false)}
          onClick={() => sync.mutate()}
          className="px-3 py-1 rounded text-sm font-medium bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-50"
        >
          {sync.isPending ? "Synchronisiere…" : "Jetzt synchronisieren"}
        </button>
      </div>
      {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
      {s && !s.oauth_enabled && (
        <p className="text-sm text-muted">Outlook-Integration ist deaktiviert.</p>
      )}
      {s && (
        <div className="space-y-1 text-sm">
          <div className="flex gap-2 items-center">
            <StatusBadge status={s.last_status} />
            {s.last_reason && <span className="text-muted">{s.last_reason}</span>}
            {s.last_trigger && (
              <span className="text-muted">· {s.last_trigger}</span>
            )}
          </div>
          <div className="text-muted">
            Letzte Synchronisation:{" "}
            {s.last_sync_at ? new Date(s.last_sync_at).toLocaleString() : "—"}
          </div>
          {s.last_counts && (
            <div className="text-muted">
              +{s.last_counts.created} · ~{s.last_counts.updated} · −
              {s.last_counts.deleted} · {s.last_counts.skipped} übersprungen
            </div>
          )}
          {s.last_error && (
            <div className="text-rose-600 text-xs break-words">{s.last_error}</div>
          )}
        </div>
      )}
      {sync.isError && (
        <p className="text-xs text-red-600">Synchronisation fehlgeschlagen.</p>
      )}
    </div>
  );
}

function EntriesTable() {
  const q = useQuery({
    queryKey: ["calendar-entries"],
    queryFn: () => calendar.entries(),
  });
  return (
    <div>
      <h2 className="text-lg font-semibold mb-3">Kalender-Einträge</h2>
      {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
      {q.data && q.data.length === 0 && (
        <div className="text-muted text-sm">
          Noch keine Kalender-Einträge übernommen.
        </div>
      )}
      {q.data && q.data.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 pr-2">Zeit</th>
              <th className="py-2 pr-2">Betreff</th>
              <th className="py-2 pr-2">Zuordnung</th>
              <th className="py-2 pr-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((e: CalendarEntry) => (
              <tr key={e.id} className="border-b border-border">
                <td className="py-2 pr-2 whitespace-nowrap">
                  {new Date(e.starts_at).toLocaleString()}
                </td>
                <td className="py-2 pr-2">{e.subject ?? "—"}</td>
                <td className="py-2 pr-2">
                  {e.suggested_application ? (
                    <Link
                      to={`/applications/${e.suggested_application.id}`}
                      className="text-accent hover:underline"
                    >
                      #{e.suggested_application.display_id}{" "}
                      {e.suggested_application.company}
                    </Link>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="py-2 pr-2">
                  <EntryStatusBadge status={e.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function SettingsOutlookSync() {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Outlook sync</h1>
      <ConnectionCard />
      <EntriesTable />
    </div>
  );
}
