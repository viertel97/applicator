import { api } from "./client";

export type OutcomeCounts = {
  active: number;
  accepted: number;
  offer: number;
  rejected: number;
  withdrawn: number;
  discarded: number;
  total: number;
};

export type WeeklyDecline = {
  week: string;
  rejected: number;
  withdrawn: number;
  discarded: number;
};

export type DeclineEvent = {
  app_id: string;
  company: string | null;
  role: string | null;
  kind: string;
  occurred_at: string;
  stage_reached: string;
};

export type RejectionStage = {
  stage: string;
  count: number;
};

export type VelocityWindow = {
  mean: number | null;
  median: number | null;
};

export type Velocity = {
  applied_to_response_h: VelocityWindow;
  response_to_interview_h: VelocityWindow;
  interview_to_offer_h: VelocityWindow;
  offer_to_decision_h: VelocityWindow;
};

export type GhostStats = {
  count: number;
  threshold_days: number;
};

export type InterviewStats = {
  reached: number;
  won: number;
  lost: number;
  win_rate: number | null;
};

export type DetailStats = {
  outcomes: OutcomeCounts;
  declines_weekly: WeeklyDecline[];
  decline_timeline: DeclineEvent[];
  rejection_stage: RejectionStage[];
  velocity: Velocity;
  ghost: GhostStats;
  interview: InterviewStats;
};

export const statsDetail = {
  detail: (from?: string, to?: string, ghostDays?: number) => {
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    if (ghostDays != null) params.set("ghost_days", String(ghostDays));
    const qs = params.toString();
    return api<DetailStats>(`/api/stats/detail${qs ? `?${qs}` : ""}`);
  },
};
