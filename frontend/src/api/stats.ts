import { api } from "./client";

export type FunnelStats = {
  totals: { applications: number; applied: number; discarded: number; active: number };
  funnel: { stage: string; count: number }[];
  response_rate_by_channel: { channel: string; outgoing: number; responses: number; rate: number }[];
  avg_time_to_reply_hours: Record<string, number>;
  discard_breakdown: { slug: string; label: string; count: number }[];
  weekly_volume: { week: string; applied: number; discarded: number; responses: number; inquiries: number }[];
};

export const stats = {
  funnel: (from?: string, to?: string) => {
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    const qs = params.toString();
    return api<FunnelStats>(`/api/stats/funnel${qs ? `?${qs}` : ""}`);
  },
};
