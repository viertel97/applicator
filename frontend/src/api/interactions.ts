import { api } from "./client";

export type Direction = "out" | "in";
export type Channel = "mail" | "linkedin" | "phone" | "portal" | "xing" | "other";
export type Sentiment = "positive" | "neutral" | "negative" | "rejection" | null;

export type Interaction = {
  id: string;
  application_id: string;
  occurred_at: string;
  direction: Direction;
  channel: Channel;
  subject: string | null;
  body: string | null;
  contact_name: string | null;
  contact_handle: string | null;
  sentiment: Sentiment;
  created_from: "manual" | "inquiry_migration" | "graph_sync";
  created_at: string;
  updated_at: string;
};

export type CreateInteractionInput = {
  occurred_at?: string;
  direction: Direction;
  channel: Channel;
  subject?: string | null;
  body?: string | null;
  contact_name?: string | null;
  contact_handle?: string | null;
  sentiment?: Sentiment;
};

export type CreateInteractionResp = {
  interaction: Interaction;
  suggest_discard: { reason_slug: string; interaction_id: string } | null;
};

export type TimelineRow =
  | { kind: "interaction"; at: string; data: Interaction }
  | { kind: "interview"; at: string; data: { id: string; kind: string; notes: string | null; outcome: string } }
  | { kind: "event"; at: string; data: { kind: string; from: string | null; to: string | null; meta: unknown } };

export const interactions = {
  list: (appId: string) =>
    api<Interaction[]>(`/api/applications/${appId}/interactions`),
  create: (appId: string, body: CreateInteractionInput) =>
    api<CreateInteractionResp>(`/api/applications/${appId}/interactions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: Partial<CreateInteractionInput>) =>
    api<Interaction>(`/api/interactions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) =>
    api<void>(`/api/interactions/${id}`, { method: "DELETE" }),
};

export const timeline = {
  get: (appId: string) =>
    api<TimelineRow[]>(`/api/applications/${appId}/timeline`),
};
