import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, CartesianGrid,
} from "recharts";
import { stats } from "../api/stats";

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="border rounded p-3 bg-white">
      <div className="text-xs text-slate-500 uppercase">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}

export default function Stats() {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["stats-funnel"], queryFn: () => stats.funnel() });
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
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
