import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer,
} from "recharts";
import { timeline, type GlobalTimelineRow, type TimelineCategory } from "../api/interactions";
import { groupByDay, bucketByDay } from "../lib/timelineGroup";
import { interactionIcon, interactionDescribe, eventDescribe } from "../lib/timelineRender";
import { useTheme } from "../hooks/useTheme";

const FILTERS: { key: TimelineCategory; label: string; color: string }[] = [
  // "Applications" = record created / added to the tool (bookkeeping);
  // "Applied" = the day you actually submitted the application (the real signal).
  { key: "application", label: "Applications", color: "#64748b" },
  { key: "applied", label: "Applied", color: "#2563eb" },
  { key: "interaction", label: "Interactions", color: "#16a34a" },
  { key: "status", label: "Status", color: "#0891b2" },
  { key: "discard", label: "Discards", color: "#dc2626" },
];

function tokenColor(name: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v ? `rgb(${v})` : "#64748b";
}

function iconFor(row: GlobalTimelineRow): string {
  if (row.category === "application") return "📮";
  if (row.category === "applied") return "📨";
  if (row.category === "interaction") {
    return interactionIcon({ channel: row.data.channel ?? "other", direction: row.data.direction ?? "in" });
  }
  return row.category === "discard" ? "🗑" : "•";
}

function describe(row: GlobalTimelineRow): string {
  if (row.category === "application") return "Application created";
  if (row.category === "applied") return "Application submitted";
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
  const { theme } = useTheme();
  void theme; // referenced so tokenColor re-reads CSS vars after theme flips
  const [view, setView] = useState<"list" | "chart">("list");
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
  const chartData = bucketByDay(visible);

  const mutedColor = tokenColor("--muted");
  const borderColor = tokenColor("--border");
  const surfaceColor = tokenColor("--surface");
  const fgColor = tokenColor("--fg");
  const tooltipStyle = {
    background: surfaceColor,
    border: `1px solid ${borderColor}`,
    color: fgColor,
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
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
        <div className="ml-auto flex gap-1">
          {(["chart", "list"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={
                view === v
                  ? "text-xs px-2 py-1 rounded border bg-accent text-accentFg border-accent"
                  : "text-xs px-2 py-1 rounded border bg-surface text-muted border-border"
              }
            >
              {v === "chart" ? "Chart" : "List"}
            </button>
          ))}
        </div>
      </div>

      {view === "chart" ? (
        chartData.length === 0 ? (
          <div className="text-sm text-muted">Nothing matches the current filters.</div>
        ) : (
          <div className="h-72 border rounded p-2">
            <ResponsiveContainer>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={borderColor} />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: mutedColor }} />
                <YAxis allowDecimals={false} tick={{ fill: mutedColor }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ color: mutedColor }} />
                {FILTERS.filter((f) => active.has(f.key)).map((f) => (
                  <Line
                    key={f.key}
                    type="monotone"
                    dataKey={f.key}
                    name={f.label}
                    stroke={f.color}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )
      ) : groups.length === 0 ? (
        <div className="text-sm text-muted">Nothing matches the current filters.</div>
      ) : (
        groups.map((g) => (
          <div key={g.key}>
            <div className="text-xs font-semibold text-muted uppercase mb-1">{g.label}</div>
            <ul className="divide-y border rounded">
              {g.rows.map((row) => (
                <li
                  key={`${row.category}-${row.application_id}-${row.at}`}
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
