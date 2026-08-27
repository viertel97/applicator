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

export type SyncCounts = {
  created: number;
  updated: number;
  deleted: number;
  skipped: number;
};

export type SyncStatus = {
  last_sync_at: string | null;
  last_status: "ok" | "skipped" | "error" | null;
  last_reason: string | null;
  last_trigger: "scheduled" | "manual" | null;
  last_counts: SyncCounts | null;
  last_error: string | null;
  oauth_enabled: boolean;
};

export type CalendarEntry = {
  id: string;
  external_id: string;
  subject: string | null;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  organizer_email: string | null;
  status: "pending" | "confirmed" | "dismissed";
  match_score: number | null;
  suggested_application: {
    id: string;
    display_id: number;
    company: string;
  } | null;
  interaction_id: string | null;
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
  syncStatus: () => api<SyncStatus>("/api/calendar/sync-status"),
  syncNow: () => api<SyncStatus>("/api/calendar/sync-now", { method: "POST" }),
  entries: () => api<CalendarEntry[]>("/api/calendar/entries"),
};
