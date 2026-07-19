import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { timeline, type GlobalTimelineRow, type TimelineCategory } from "../api/interactions";
import { groupByDay } from "../lib/timelineGroup";
import { interactionIcon, interactionDescribe, eventDescribe } from "../lib/timelineRender";

const FILTERS: { key: TimelineCategory; label: string }[] = [
  { key: "application", label: "Applications" },
  { key: "interaction", label: "Interactions" },
  { key: "status", label: "Status" },
  { key: "discard", label: "Discards" },
];

function iconFor(row: GlobalTimelineRow): string {
  if (row.category === "application") return "📮";
  if (row.category === "interaction") {
    return interactionIcon({ channel: row.data.channel ?? "other", direction: row.data.direction ?? "in" });
  }
  return row.category === "discard" ? "🗑" : "•";
}

function describe(row: GlobalTimelineRow): string {
  if (row.category === "application") return "Application created";
  if (row.category === "interaction") {
    return interactionDescribe({
      channel: row.data.channel ?? "other",
      direction: row.data.direction ?? "in",
      subject: row.data.subject ?? null,
      interview_stage: row.data.interview_stage ?? null,
    });
  }
  return eventDescribe({
    kind: row.data.kind ?? "status_change",
    from: row.data.from ?? null,
    to: row.data.to ?? null,
  });
}

function label(row: GlobalTimelineRow): string {
  return [row.company, row.title].filter(Boolean).join(" · ") || "Untitled application";
}

export function GlobalTimeline() {
  const navigate = useNavigate();
  const [active, setActive] = useState<Set<TimelineCategory>>(
    () => new Set(FILTERS.map((f) => f.key)),
  );

  const q = useQuery({
    queryKey: ["global-timeline"],
    queryFn: () => timeline.getGlobal(),
  });

  function toggle(key: TimelineCategory) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  if (!q.data) return <div className="text-sm text-muted">Loading…</div>;
  if (q.data.length === 0)
    return <div className="text-sm text-muted">No activity yet.</div>;

  const visible = q.data.filter((r) => active.has(r.category));
  const groups = groupByDay(visible, new Date());

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => {
          const on = active.has(f.key);
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => toggle(f.key)}
              className={
                on
                  ? "text-xs px-2 py-1 rounded border bg-accent text-accentFg border-accent"
                  : "text-xs px-2 py-1 rounded border bg-surface text-muted border-border"
              }
            >
              {f.label}
            </button>
          );
        })}
      </div>

      {groups.length === 0 ? (
        <div className="text-sm text-muted">Nothing matches the current filters.</div>
      ) : (
        groups.map((g) => (
          <div key={g.key}>
            <div className="text-xs font-semibold text-muted uppercase mb-1">{g.label}</div>
            <ul className="divide-y border rounded">
              {g.rows.map((row, i) => (
                <li
                  key={i}
                  className="p-2 flex gap-3 cursor-pointer hover:bg-surface"
                  onClick={() => navigate(`/applications/${row.application_id}`)}
                >
                  <span className="text-muted w-5 text-center">{iconFor(row)}</span>
                  <div className="flex-1">
                    <div className="text-sm">{describe(row)}</div>
                    <div className="text-xs text-muted">{label(row)}</div>
                  </div>
                  <div className="text-xs text-muted whitespace-nowrap">
                    {new Date(row.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}
