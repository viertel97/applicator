import { api } from "./client";

export type InterviewKind = "phone" | "video" | "onsite" | "technical" | "final";
export type InterviewOutcome = "pending" | "passed" | "failed" | "cancelled";

export type Interview = {
  id: string;
  application_id: string;
  scheduled_at: string;
  kind: InterviewKind;
  notes: string | null;
  outcome: InterviewOutcome;
};

export const interviews = {
  list: (aid: string) => api<Interview[]>(`/api/applications/${aid}/interviews`),
  create: (aid: string, scheduled_at: string, kind: InterviewKind, notes?: string) =>
    api<Interview>(`/api/applications/${aid}/interviews`, {
      method: "POST",
      body: JSON.stringify({ scheduled_at, kind, notes }),
    }),
  update: (
    id: string,
    patch: Partial<Pick<Interview, "outcome" | "notes" | "scheduled_at" | "kind">>,
  ) => api<Interview>(`/api/interviews/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  remove: (id: string) => api<{ ok: true }>(`/api/interviews/${id}`, { method: "DELETE" }),
};
