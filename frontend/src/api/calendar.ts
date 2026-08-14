import { api } from "./client";
import type { InterviewStage } from "./interactions";

export type CalendarInterview = {
  id: string;
  application_id: string;
  display_id: number;
  company: string;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  interview_stage: InterviewStage | null;
  needs_review: boolean;
};

export type CalendarTokens = {
  ingest_url: string | null;
  calendar_url: string | null;
};

export const calendar = {
  interviews: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    const qs = q.toString();
    return api<CalendarInterview[]>(`/api/calendar/interviews${qs ? `?${qs}` : ""}`);
  },
  tokens: () => api<CalendarTokens>("/api/calendar/tokens"),
  regenerate: (kind: "ingest" | "calendar") =>
    api<CalendarTokens>(`/api/calendar/tokens/regenerate?kind=${kind}`, { method: "POST" }),
  reviewCount: () => api<{ count: number }>("/api/calendar/review-count"),
};
