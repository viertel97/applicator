import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { GlobalTimeline } from "../components/GlobalTimeline";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, CartesianGrid,
  PieChart, Pie, Cell,
} from "recharts";
import { stats } from "../api/stats";
import { statsDetail } from "../api/statsDetail";
import type { DetailStats } from "../api/statsDetail";
import { useTheme } from "../hooks/useTheme";
import { Card } from "../components/ui/Card";

// Categorical palette for multi-series/donut charts — readable in both themes
// on a bg-surface card background.
const DONUT_COLORS = ["#2563eb", "#16a34a", "#0891b2", "#dc2626", "#d97706", "#64748b"];

function tokenColor(name: string): string {
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return v ? `rgb(${v})` : "#64748b";
}

function Kpi({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <Card className="p-3">
      <div className="text-xs text-muted uppercase">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
      {sub && <div className="text-xs text-muted mt-0.5">{sub}</div>}
    </Card>
  );
}

function fmtHours(h: number | null): string {
  if (h == null) return "—";
  return `${h.toFixed(1)}h`;
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

function kindBadge(kind: string): string {
  if (kind === "rejected") return "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200";
  if (kind === "withdrawn") return "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200";
  return "bg-surface2 text-muted";
}

function DetailSections({ d, weeklyVolume, funnel }: {
  d: DetailStats;
  weeklyVolume: { week: string; applied: number; discarded: number; responses: number; inquiries: number }[];
  funnel: { stage: string; count: number }[];
}) {
  // --- Outcomes donut data (skip zero-value slices) ---
  const { outcomes } = d;
  const donutData = [
    { name: "Active", value: outcomes.active },
    { name: "Accepted", value: outcomes.accepted },
    { name: "Offer", value: outcomes.offer },
    { name: "Rejected", value: outcomes.rejected },
    { name: "Withdrawn", value: outcomes.withdrawn },
    { name: "Discarded", value: outcomes.discarded },
  ].filter((entry) => entry.value > 0);

  // --- Funnel conversion rates (derived from existing funnel data) ---
  const stageOrder = ["applied", "responded", "interview", "offer", "accepted"];
  const funnelMap = Object.fromEntries(funnel.map((f) => [f.stage, f.count]));
  const conversionPairs: { label: string; pct: string }[] = [
    { label: "Applied→Response", from: "applied", to: "responded" },
    { label: "Response→Interview", from: "responded", to: "interview" },
    { label: "Interview→Offer", from: "interview", to: "offer" },
    { label: "Offer→Accepted", from: "offer", to: "accepted" },
  ].map(({ label, from, to }) => {
    const fromVal = funnelMap[from] ?? 0;
    const toVal = funnelMap[to] ?? 0;
    const pct = fromVal > 0 ? `${Math.round(100 * toVal / fromVal)}%` : "—";
    return { label, pct };
  });

  // Funnel chart data with conversion annotation
  const funnelChartData = stageOrder.map((stage) => ({
    stage,
    count: funnelMap[stage] ?? 0,
  }));

  // --- Cadence trend (from existing weekly_volume) ---
  // NOTE: weekly_volume buckets are event-weeks (weeks with activity), not calendar
  // weeks — gap weeks are absent, so slice(-4) may span more than 4 calendar weeks.
  const vol = [...weeklyVolume].sort((a, b) => a.week.localeCompare(b.week));
  const last4 = vol.slice(-4);
  const prior4 = vol.slice(-8, -4);
  const avg = (arr: { applied: number }[]) =>
    arr.length > 0 ? arr.reduce((s, w) => s + w.applied, 0) / arr.length : null;
  const last4Avg = avg(last4);
  const prior4Avg = avg(prior4);
  const cadenceValue = last4Avg != null ? last4Avg.toFixed(1) : "—";
  let cadenceSub = "";
  if (last4.length === 4 && prior4.length === 4 && last4Avg != null && prior4Avg != null) {
    const delta = last4Avg - prior4Avg;
    const arrow = delta >= 0 ? "▲" : "▼";
    cadenceSub = `${arrow} ${Math.abs(delta).toFixed(1)} vs prior 4w`;
  } else if (vol.length > 0) {
    cadenceSub = `${vol.length} week(s) of data`;
  }

  // --- Interview win rate ---
  const { interview } = d;
  const winRateValue = interview.win_rate == null
    ? "—"
    : `${Math.round(interview.win_rate * 100)}%`;
  const winRateSub = `${interview.won}W / ${interview.lost}L`;

  // Chart color helpers — read after theme class has flipped so colors are current
  const accentColor = tokenColor("--accent");
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
    <>
      {/* Section A — Outcomes & conversion */}
      <section>
        <h2 className="text-md font-semibold mb-2">Outcomes &amp; conversion</h2>
        <div className="grid grid-cols-2 gap-4">
          {/* Donut */}
          <Card>
            <div className="text-xs text-muted px-3 pt-3 font-medium">Outcome distribution</div>
            <div className="h-64">
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={donutData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius="50%"
                    outerRadius="80%"
                    paddingAngle={2}
                  >
                    {donutData.map((entry, i) => (
                      <Cell key={entry.name} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ color: mutedColor }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </Card>
          {/* Funnel conversion rates */}
          <Card className="flex flex-col">
            <div className="text-xs text-muted px-3 pt-3 font-medium">Stage conversion</div>
            <div className="h-48">
              <ResponsiveContainer>
                <BarChart data={funnelChartData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={borderColor} />
                  <XAxis type="number" tick={{ fill: mutedColor }} />
                  <YAxis type="category" dataKey="stage" width={80} tick={{ fill: mutedColor }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="count" fill={accentColor} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="px-3 pb-3 mt-auto">
              <div className="text-xs text-muted mb-1 font-medium">Step conversion rates</div>
              <div className="grid grid-cols-2 gap-1">
                {conversionPairs.map((c) => (
                  <div key={c.label} className="flex justify-between text-xs border border-border rounded px-2 py-1 bg-bg">
                    <span className="text-muted">{c.label}</span>
                    <span className="font-semibold">{c.pct}</span>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </section>

      {/* Section B — Declines */}
      <section>
        <h2 className="text-md font-semibold mb-2">Declines</h2>
        <div className="grid grid-cols-2 gap-4">
          {/* Weekly stacked bar */}
          <div>
            <div className="text-xs text-muted mb-1 font-medium">Weekly declines</div>
            <Card className="h-64">
              <ResponsiveContainer>
                <BarChart data={d.declines_weekly}>
                  <CartesianGrid strokeDasharray="3 3" stroke={borderColor} />
                  <XAxis dataKey="week" tick={{ fontSize: 10, fill: mutedColor }} />
                  <YAxis tick={{ fill: mutedColor }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ color: mutedColor }} />
                  <Bar dataKey="rejected" stackId="a" fill="#dc2626" />
                  <Bar dataKey="withdrawn" stackId="a" fill="#d97706" />
                  <Bar dataKey="discarded" stackId="a" fill="#64748b" />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
          {/* Rejection by stage */}
          <div>
            <div className="text-xs text-muted mb-1 font-medium">Rejections by stage reached</div>
            <Card className="h-64">
              <ResponsiveContainer>
                <BarChart data={d.rejection_stage} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={borderColor} />
                  <XAxis type="number" tick={{ fill: mutedColor }} />
                  <YAxis type="category" dataKey="stage" width={70} tick={{ fill: mutedColor }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="count" fill="#dc2626" />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </div>
        {/* Recent decline timeline */}
        <div className="mt-3">
          <div className="text-xs text-muted mb-1 font-medium">Recent declines</div>
          {d.decline_timeline.length === 0 ? (
            <p className="text-sm text-muted">No declines yet.</p>
          ) : (
            <Card className="overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-surface2">
                  <tr>
                    <th className="text-left px-3 py-2 text-xs font-medium text-muted">Date</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-muted">Company</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-muted">Role</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-muted">Kind</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-muted">Stage</th>
                  </tr>
                </thead>
                <tbody>
                  {d.decline_timeline.map((ev) => (
                    <tr key={ev.app_id} className="border-t border-border">
                      <td className="px-3 py-1.5 text-muted">{fmtDate(ev.occurred_at)}</td>
                      <td className="px-3 py-1.5">{ev.company ?? "—"}</td>
                      <td className="px-3 py-1.5 text-muted">{ev.role ?? "—"}</td>
                      <td className="px-3 py-1.5">
                        <span className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ${kindBadge(ev.kind)}`}>
                          {ev.kind}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-muted">{ev.stage_reached}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      </section>

      {/* Section C — Velocity & health */}
      <section>
        <h2 className="text-md font-semibold mb-2">Velocity &amp; health</h2>
        <div className="grid grid-cols-4 gap-3">
          <Kpi
            label="Applied→Response"
            value={fmtHours(d.velocity.applied_to_response_h.mean)}
            sub={d.velocity.applied_to_response_h.median != null
              ? `median ${fmtHours(d.velocity.applied_to_response_h.median)}`
              : undefined}
          />
          <Kpi
            label="Response→Interview"
            value={fmtHours(d.velocity.response_to_interview_h.mean)}
            sub={d.velocity.response_to_interview_h.median != null
              ? `median ${fmtHours(d.velocity.response_to_interview_h.median)}`
              : undefined}
          />
          <Kpi
            label="Interview→Offer"
            value={fmtHours(d.velocity.interview_to_offer_h.mean)}
            sub={d.velocity.interview_to_offer_h.median != null
              ? `median ${fmtHours(d.velocity.interview_to_offer_h.median)}`
              : undefined}
          />
          <Kpi
            label="Offer→Decision"
            value={fmtHours(d.velocity.offer_to_decision_h.mean)}
            sub={d.velocity.offer_to_decision_h.median != null
              ? `median ${fmtHours(d.velocity.offer_to_decision_h.median)}`
              : undefined}
          />
          <Kpi
            label={`Ghosted (≥${d.ghost.threshold_days}d)`}
            value={d.ghost.count}
          />
          <Kpi
            label="Interview win rate"
            value={winRateValue}
            sub={winRateSub}
          />
          <Kpi
            label="Applied/week (last 4w)"
            value={cadenceValue}
            sub={cadenceSub || undefined}
          />
        </div>
      </section>
    </>
  );
}

export default function Stats() {
  // Reference theme so the component re-renders on toggle, causing tokenColor
  // calls in the render body to re-read CSS vars after the class flips.
  const { theme } = useTheme();
  // Suppress unused-variable lint — theme is intentionally referenced for reactivity
  void theme;

  const navigate = useNavigate();
  const [tab, setTab] = useState<"overview" | "timeline">("overview");
  const [volumeGran, setVolumeGran] = useState<"week" | "day">("week");
  const q = useQuery({ queryKey: ["stats-funnel"], queryFn: () => stats.funnel() });
  const d = useQuery({ queryKey: ["stats-detail"], queryFn: () => statsDetail.detail() });

  const tabBar = (
    <div className="flex gap-2 mb-4">
      {(["overview", "timeline"] as const).map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => setTab(t)}
          className={
            tab === t
              ? "text-sm px-3 py-1 rounded border bg-accent text-accentFg border-accent"
              : "text-sm px-3 py-1 rounded border bg-surface text-muted border-border"
          }
        >
          {t === "overview" ? "Overview" : "Timeline"}
        </button>
      ))}
    </div>
  );

  if (tab === "timeline") {
    return (
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <h1 className="text-xl font-semibold">Stats</h1>
        {tabBar}
        <GlobalTimeline />
      </div>
    );
  }

  if (!q.data) {
    return (
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <h1 className="text-xl font-semibold">Stats</h1>
        {tabBar}
        <div>Loading…</div>
      </div>
    );
  }
  const s = q.data;
  const overallResp =
    s.totals.applied > 0
      ? Math.round(
          100 *
            (s.funnel.find((f) => f.stage === "responded")?.count ?? 0) /
            s.totals.applied,
        )
      : 0;

  // Chart colors — re-evaluated each render so they track the current theme
  const accentColor = tokenColor("--accent");
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
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <h1 className="text-xl font-semibold">Stats</h1>
      {tabBar}
      <div className="grid grid-cols-4 gap-3">
        <Kpi label="Active" value={s.totals.active} />
        <Kpi label="Response rate" value={`${overallResp}%`} />
        <Kpi label="Avg reply (h, mail)"
             value={s.avg_time_to_reply_hours.mail ?? "—"} />
        <Kpi label="Interview conv."
             value={`${
               s.totals.applied
                 ? Math.round(
                     100 *
                       (s.funnel.find((f) => f.stage === "interview")?.count ?? 0) /
                       s.totals.applied,
                   )
                 : 0
             }%`} />
      </div>
      <section>
        <h2 className="text-md font-semibold mb-2">Funnel</h2>
        <Card className="h-64">
          <ResponsiveContainer>
            <BarChart data={s.funnel} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke={borderColor} />
              <XAxis type="number" tick={{ fill: mutedColor }} />
              <YAxis type="category" dataKey="stage" tick={{ fill: mutedColor }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" fill={accentColor} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </section>
      <section>
        <h2 className="text-md font-semibold mb-2">Response rate by channel</h2>
        <Card className="w-full text-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface2">
              <tr>
                <th className="text-left px-2 py-1 text-muted">Channel</th>
                <th className="text-left px-2 py-1 text-muted">Sent</th>
                <th className="text-left px-2 py-1 text-muted">Replies</th>
                <th className="text-left px-2 py-1 text-muted">Rate</th>
              </tr>
            </thead>
            <tbody>
              {s.response_rate_by_channel.map((r) => (
                <tr key={r.channel} className="border-t border-border">
                  <td className="px-2 py-1">{r.channel}</td>
                  <td className="px-2 py-1">{r.outgoing}</td>
                  <td className="px-2 py-1">{r.responses}</td>
                  <td className="px-2 py-1">{Math.round(r.rate * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>
      <section>
        <h2 className="text-md font-semibold mb-2">Discard breakdown</h2>
        <Card className="h-64">
          <ResponsiveContainer>
            <BarChart data={s.discard_breakdown} layout="vertical"
                      onClick={(e: any) => {
                        const slug = e?.activePayload?.[0]?.payload?.slug;
                        if (slug)
                          navigate(`/applications?status=discarded&reason=${slug}`);
                      }}>
              <CartesianGrid strokeDasharray="3 3" stroke={borderColor} />
              <XAxis type="number" tick={{ fill: mutedColor }} />
              <YAxis type="category" dataKey="label" width={150} tick={{ fill: mutedColor }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" fill="#dc2626" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </section>
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-md font-semibold">Volume</h2>
          <div className="flex gap-1">
            {(["day", "week"] as const).map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setVolumeGran(g)}
                className={
                  volumeGran === g
                    ? "text-xs px-2 py-1 rounded border bg-accent text-accentFg border-accent"
                    : "text-xs px-2 py-1 rounded border bg-surface text-muted border-border"
                }
              >
                {g === "day" ? "Daily" : "Weekly"}
              </button>
            ))}
          </div>
        </div>
        <Card className="h-64">
          <ResponsiveContainer>
            <LineChart data={volumeGran === "day" ? s.daily_volume : s.weekly_volume}>
              <CartesianGrid strokeDasharray="3 3" stroke={borderColor} />
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: mutedColor }} />
              <YAxis tick={{ fill: mutedColor }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ color: mutedColor }} />
              <Line type="monotone" dataKey="applied" stroke="#2563eb" />
              <Line type="monotone" dataKey="discarded" stroke="#dc2626" />
              <Line type="monotone" dataKey="responses" stroke="#16a34a" />
              <Line type="monotone" dataKey="inquiries" stroke="#d97706" />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </section>
      {d.data && (
        <DetailSections
          d={d.data}
          weeklyVolume={s.weekly_volume}
          funnel={s.funnel}
        />
      )}
    </div>
  );
}
