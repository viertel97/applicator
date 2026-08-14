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

export type WebhookRequestDetail = WebhookRequestSummary & {
  headers: Record<string, string> | null;
  raw_body: string | null;
};

export const listWebhookRequests = () =>
  api<WebhookRequestSummary[]>("/api/webhooks/requests");

export const getWebhookRequest = (id: string) =>
  api<WebhookRequestDetail>(`/api/webhooks/requests/${id}`);
