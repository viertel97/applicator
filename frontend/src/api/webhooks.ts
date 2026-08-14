import { api } from "./client";

export type WebhookRequestSummary = {
  id: string;
  created_at: string;
  status: string;
  reason: string | null;
  source_ip: string | null;
  matched_application_id: string | null;
  from: string | null;
  subject: string | null;
};

export type CreatedInteraction = {
  id: string;
  application_id: string;
  display_id: number;
  company: string;
  starts_at: string | null;
  ends_at: string | null;
  location: string | null;
  interview_stage: string | null;
  needs_review: boolean;
};

export type WebhookRequestDetail = WebhookRequestSummary & {
  headers: Record<string, string> | null;
  raw_body: string | null;
  created_interaction: CreatedInteraction | null;
};

export const listWebhookRequests = () =>
  api<WebhookRequestSummary[]>("/api/webhooks/requests");

export const getWebhookRequest = (id: string) =>
  api<WebhookRequestDetail>(`/api/webhooks/requests/${id}`);
