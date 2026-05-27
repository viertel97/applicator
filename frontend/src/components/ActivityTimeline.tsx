import { useQuery } from "@tanstack/react-query";
import { timeline, type TimelineRow } from "../api/interactions";

function iconFor(row: TimelineRow) {
  if (row.kind === "interaction") {
    return row.data.direction === "out" ? "→" : "←";
  }
  if (row.kind === "interview") return "🎤";
  return "•";
}

function describe(row: TimelineRow): string {
  if (row.kind === "interaction") {
    const it = row.data;
    const dir = it.direction === "out" ? "Sent" : "Received";
    return `${dir} via ${it.channel}${it.subject ? ` — ${it.subject}` : ""}`;
  }
  if (row.kind === "interview") {
    return `Interview (${row.data.kind}) — ${row.data.outcome}`;
  }
  const ev = row.data;
  if (ev.kind === "status_change") return `Status: ${ev.from} → ${ev.to}`;
  return ev.kind;
}

export function ActivityTimeline({ appId }: { appId: string }) {
  const q = useQuery({
    queryKey: ["application-timeline", appId],
    queryFn: () => timeline.get(appId),
  });
  if (!q.data) return <div className="text-sm text-slate-500">Loading…</div>;
  if (q.data.length === 0)
    return <div className="text-sm text-slate-500">No activity yet.</div>;
  return (
    <ul className="divide-y border rounded">
      {q.data.map((row, i) => (
        <li key={i} className="p-2 flex gap-3">
          <span className="text-slate-400 w-5 text-center">{iconFor(row)}</span>
          <div className="flex-1">
            <div className="text-sm">{describe(row)}</div>
            <div className="text-xs text-slate-500">
              {new Date(row.at).toLocaleString()}
            </div>
            {row.kind === "interaction" && row.data.body && (
              <div className="text-sm text-slate-700 mt-1 whitespace-pre-wrap">
                {row.data.body}
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
