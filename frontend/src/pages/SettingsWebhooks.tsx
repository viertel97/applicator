import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getWebhookRequest,
  listWebhookRequests,
  type WebhookRequestSummary,
} from "../api/webhooks";

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "created"
      ? "bg-emerald-100 text-emerald-700"
      : status === "not_found" || status === "rejected" || status === "error"
        ? "bg-rose-100 text-rose-700"
        : "bg-amber-100 text-amber-700";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${tone}`}>
      {status}
    </span>
  );
}

function prettyBody(raw: string | null): string {
  if (!raw) return "";
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function DetailModal({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["webhook-request", id],
    queryFn: () => getWebhookRequest(id),
  });
  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50"
      onClick={onClose}
      tabIndex={-1}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Webhook request details"
        className="bg-surface rounded-lg max-w-2xl w-full max-h-[85vh] overflow-auto p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-semibold">Webhook request</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted hover:text-fg"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
        {q.data && (
          <div className="space-y-3 text-sm">
            <div className="flex gap-2 items-center">
              <StatusBadge status={q.data.status} />
              {q.data.reason && (
                <span className="text-muted">{q.data.reason}</span>
              )}
            </div>
            <div className="text-muted">
              {new Date(q.data.created_at).toLocaleString()} · IP{" "}
              {q.data.source_ip ?? "—"}
            </div>
            <div>
              <div className="font-semibold mb-1">Headers</div>
              <pre className="bg-bg rounded p-2 text-xs overflow-auto max-h-40">
                {JSON.stringify(q.data.headers ?? {}, null, 2)}
              </pre>
            </div>
            <div>
              <div className="font-semibold mb-1">Body</div>
              <pre className="bg-bg rounded p-2 text-xs overflow-auto max-h-64">
                {prettyBody(q.data.raw_body)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SettingsWebhooks() {
  const [selected, setSelected] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["webhook-requests"],
    queryFn: () => listWebhookRequests(),
  });

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Webhook log</h1>
      {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
      {q.data && q.data.length === 0 && (
        <div className="text-muted text-sm">No requests received yet.</div>
      )}
      {q.data && q.data.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 pr-2">Time</th>
              <th className="py-2 pr-2">From</th>
              <th className="py-2 pr-2">Subject</th>
              <th className="py-2 pr-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((r: WebhookRequestSummary) => (
              <tr
                key={r.id}
                onClick={() => setSelected(r.id)}
                className="border-b border-border cursor-pointer hover:bg-bg"
              >
                <td className="py-2 pr-2 whitespace-nowrap">
                  {new Date(r.created_at).toLocaleString()}
                </td>
                <td className="py-2 pr-2">{r.from ?? "—"}</td>
                <td className="py-2 pr-2">{r.subject ?? "—"}</td>
                <td className="py-2 pr-2">
                  <StatusBadge status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {selected && (
        <DetailModal id={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
