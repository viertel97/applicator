import { useQuery } from "@tanstack/react-query";
import { DeleteConfirmButton } from "./DeleteConfirmButton";
import { timeline, type Interaction, type TimelineRow } from "../api/interactions";
import { STAGE_LABEL } from "../lib/interviewSummary";

function iconFor(row: TimelineRow) {
  if (row.kind === "interaction") {
    if (row.data.channel === "interview") return "🎤";
    return row.data.direction === "out" ? "→" : "←";
  }
  return "•";
}

function describe(row: TimelineRow): string {
  if (row.kind === "interaction") {
    const it = row.data;
    if (it.channel === "interview") {
      const stage = it.interview_stage ? STAGE_LABEL[it.interview_stage] : null;
      const tail = stage ?? it.subject;
      return `Interview${tail ? ` — ${tail}` : ""}`;
    }
    const dir = it.direction === "out" ? "Sent" : "Received";
    return `${dir} via ${it.channel}${it.subject ? ` — ${it.subject}` : ""}`;
  }
  const ev = row.data;
  if (ev.kind === "status_change") return `Status: ${ev.from} → ${ev.to}`;
  return ev.kind;
}

export function ActivityTimeline({
  appId,
  onDelete,
}: {
  appId: string;
  onDelete?: (it: Interaction) => void;
}) {
  const q = useQuery({
    queryKey: ["application-timeline", appId],
    queryFn: () => timeline.get(appId),
  });
  if (!q.data) return <div className="text-sm text-muted">Loading…</div>;
  if (q.data.length === 0)
    return <div className="text-sm text-muted">No activity yet.</div>;
  return (
    <ul className="divide-y border rounded">
      {q.data.map((row, i) => (
        <li key={i} className="p-2 flex gap-3">
          <span className="text-muted w-5 text-center">{iconFor(row)}</span>
          <div className="flex-1">
            <div className="text-sm">{describe(row)}</div>
            <div className="text-xs text-muted">
              {new Date(row.at).toLocaleString()}
            </div>
            {row.kind === "interaction" && row.data.body && (
              <div className="text-sm text-fg mt-1 whitespace-pre-wrap">
                {row.data.body}
              </div>
            )}
          </div>
          {row.kind === "interaction" && onDelete && (
            <DeleteConfirmButton
              label="Delete interaction"
              onConfirm={() => onDelete(row.data)}
            />
          )}
        </li>
      ))}
    </ul>
  );
}
