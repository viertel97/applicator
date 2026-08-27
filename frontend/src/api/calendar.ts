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

export type CalendarSuggestion = {
  id: string;
  external_id: string;
  subject: string | null;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  organizer_email: string | null;
  match_score: number | null;
  suggested_application: {
    id: string;
    display_id: number;
    company: string;
  } | null;
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
  suggestions: () => api<CalendarSuggestion[]>("/api/calendar/suggestions"),
  confirmSuggestion: (id: string, application_id?: string) =>
    api<{ ok: boolean; interaction_id: string }>(
      `/api/calendar/suggestions/${id}/confirm`,
      { method: "POST", body: JSON.stringify(application_id ? { application_id } : {}) },
    ),
  dismissSuggestion: (id: string) =>
    api<{ ok: boolean }>(`/api/calendar/suggestions/${id}/dismiss`, { method: "POST" }),
};
