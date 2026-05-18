import { api } from "./client";
import type { Label } from "./applications";

export type { Label };

export const labels = {
  list: () => api<Label[]>("/api/labels"),
  create: (body: { name: string; color: string }) =>
    api<Label>("/api/labels", { method: "POST", body: JSON.stringify(body) }),
  assign: (appId: string, labelId: string) =>
    api<unknown>(`/api/applications/${appId}/labels/${labelId}`, { method: "POST" }),
  remove: (appId: string, labelId: string) =>
    api<unknown>(`/api/applications/${appId}/labels/${labelId}`, { method: "DELETE" }),
};
