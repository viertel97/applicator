import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, CartesianGrid,
  PieChart, Pie, Cell,
} from "recharts";
import { stats } from "../api/stats";
import { statsDetail } from "../api/statsDetail";
import type { DetailStats } from "../api/statsDetail";

const DONUT_COLORS = ["#2563eb", "#16a34a", "#0891b2", "#dc2626", "#d97706", "#64748b"];

function Kpi({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="border rounded p-3 bg-white">
      <div className="text-xs text-slate-500 uppercase">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function fmtHours(h: number | null): string {
  if (h == null) return "—";
  return `${h.toFixed(1)}h`;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

function kindBadge(kind: string): string {
  if (kind === "rejected") return "bg-red-100 text-red-700";
  if (kind === "withdrawn") return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-600";
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
  const vol = [...weeklyVolume].sort((a, b) => a.week.localeCompare(b.week));
  const last4 = vol.slice(-4);
  const prior4 = vol.slice(-8, -4);
  const avg = (arr: { applied: number }[]) =>
    arr.length > 0 ? arr.reduce((s, w) => s + w.applied, 0) / arr.length : null;
  const last4Avg = avg(last4);
  const prior4Avg = avg(prior4);
  let cadenceValue = last4Avg != null ? last4Avg.toFixed(1) : "—";
  let cadenceSub = "";
  if (last4Avg != null && prior4Avg != null) {
    const delta = last4Avg - prior4Avg;
    const arrow = delta >= 0 ? "▲" : "▼";
    cadenceSub = `${arrow} ${Math.abs(delta).toFixed(1)} vs prior 4w`;
  } else if (last4.length < 4) {
    cadenceSub = `${last4.length} week(s) of data`;
  }

  // --- Interview win rate ---
  const { interview } = d;
  const winRateValue = interview.win_rate == null
    ? "—"
    : `${Math.round(interview.win_rate * 100)}%`;
  const winRateSub = `${interview.won}W / ${interview.lost}L`;

  return (
    <>
      {/* Section A — Outcomes & conversion */}
      <section>
        <h2 className="text-md font-semibold mb-2">Outcomes &amp; conversion</h2>
        <div className="grid grid-cols-2 gap-4">
          {/* Donut */}
          <div className="bg-white border rounded">
            <div className="text-xs text-slate-500 px-3 pt-3 font-medium">Outcome distribution</div>
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
                    {donutData.map((_, i) => (
                      <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
          {/* Funnel conversion rates */}
          <div className="bg-white border rounded flex flex-col">
            <div className="text-xs text-slate-500 px-3 pt-3 font-medium">Stage conversion</div>
            <div className="h-48">
              <ResponsiveContainer>
                <BarChart data={funnelChartData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="stage" width={80} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#2563eb" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="px-3 pb-3 mt-auto">
              <div className="text-xs text-slate-500 mb-1 font-medium">Step conversion rates</div>
              <div className="grid grid-cols-2 gap-1">
                {conversionPairs.map((c) => (
                  <div key={c.label} className="flex justify-between text-xs border rounded px-2 py-1 bg-slate-50">
                    <span className="text-slate-600">{c.label}</span>
                    <span className="font-semibold">{c.pct}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Section B — Declines */}
      <section>
        <h2 className="text-md font-semibold mb-2">Declines</h2>
        <div className="grid grid-cols-2 gap-4">
          {/* Weekly stacked bar */}
          <div>
            <div className="text-xs text-slate-500 mb-1 font-medium">Weekly declines</div>
            <div className="h-64 bg-white border rounded">
              <ResponsiveContainer>
                <BarChart data={d.declines_weekly}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="week" tick={{ fontSize: 10 }} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="rejected" stackId="a" fill="#dc2626" />
                  <Bar dataKey="withdrawn" stackId="a" fill="#d97706" />
                  <Bar dataKey="discarded" stackId="a" fill="#64748b" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          {/* Rejection by stage */}
          <div>
            <div className="text-xs text-slate-500 mb-1 font-medium">Rejections by stage reached</div>
            <div className="h-64 bg-white border rounded">
              <ResponsiveContainer>
                <BarChart data={d.rejection_stage} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="stage" width={70} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#dc2626" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
        {/* Recent decline timeline */}
        <div className="mt-3">
          <div className="text-xs text-slate-500 mb-1 font-medium">Recent declines</div>
          {d.decline_timeline.length === 0 ? (
            <p className="text-sm text-slate-400">No declines yet.</p>
          ) : (
            <div className="bg-white border rounded overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Date</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Company</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Role</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Kind</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Stage</th>
                  </tr>
                </thead>
                <tbody>
                  {d.decline_timeline.map((ev) => (
                    <tr key={ev.app_id} className="border-t">
                      <td className="px-3 py-1.5 text-slate-600">{fmtDate(ev.occurred_at)}</td>
                      <td className="px-3 py-1.5">{ev.company ?? "—"}</td>
                      <td className="px-3 py-1.5 text-slate-600">{ev.role ?? "—"}</td>
                      <td className="px-3 py-1.5">
                        <span className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ${kindBadge(ev.kind)}`}>
                          {ev.kind}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-slate-500">{ev.stage_reached}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["stats-funnel"], queryFn: () => stats.funnel() });
  const d = useQuery({ queryKey: ["stats-detail"], queryFn: () => statsDetail.detail() });
  if (!q.data) return <div className="p-6">Loading…</div>;
  const s = q.data;
  const overallResp =
    s.totals.applied > 0
      ? Math.round(
          100 *
            (s.funnel.find((f) => f.stage === "responded")?.count ?? 0) /
            s.totals.applied,
        )
      : 0;
  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <h1 className="text-xl font-semibold">Stats</h1>
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
        <div className="h-64 bg-white border rounded">
          <ResponsiveContainer>
            <BarChart data={s.funnel} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis type="category" dataKey="stage" />
              <Tooltip />
              <Bar dataKey="count" fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section>
        <h2 className="text-md font-semibold mb-2">Response rate by channel</h2>
        <table className="w-full text-sm border bg-white">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left px-2 py-1">Channel</th>
              <th className="text-left px-2 py-1">Sent</th>
              <th className="text-left px-2 py-1">Replies</th>
              <th className="text-left px-2 py-1">Rate</th>
            </tr>
          </thead>
          <tbody>
            {s.response_rate_by_channel.map((r) => (
              <tr key={r.channel} className="border-t">
                <td className="px-2 py-1">{r.channel}</td>
                <td className="px-2 py-1">{r.outgoing}</td>
                <td className="px-2 py-1">{r.responses}</td>
                <td className="px-2 py-1">{Math.round(r.rate * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2 className="text-md font-semibold mb-2">Discard breakdown</h2>
        <div className="h-64 bg-white border rounded">
          <ResponsiveContainer>
            <BarChart data={s.discard_breakdown} layout="vertical"
                      onClick={(e: any) => {
                        const slug = e?.activePayload?.[0]?.payload?.slug;
                        if (slug)
                          navigate(`/applications?status=discarded&reason=${slug}`);
                      }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis type="category" dataKey="label" width={150} />
              <Tooltip />
              <Bar dataKey="count" fill="#dc2626" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section>
        <h2 className="text-md font-semibold mb-2">Weekly volume</h2>
        <div className="h-64 bg-white border rounded">
          <ResponsiveContainer>
            <LineChart data={s.weekly_volume}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="week" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="applied" stroke="#2563eb" />
              <Line type="monotone" dataKey="discarded" stroke="#dc2626" />
              <Line type="monotone" dataKey="responses" stroke="#16a34a" />
              <Line type="monotone" dataKey="inquiries" stroke="#d97706" />
            </LineChart>
          </ResponsiveContainer>
        </div>
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
