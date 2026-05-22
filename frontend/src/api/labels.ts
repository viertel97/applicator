import { api } from "./client";
import type { Label, LabelCategory } from "./applications";

export type { Label };

export const labels = {
  list: () => api<Label[]>("/api/labels"),
  create: (body: { name: string; color: string; category: LabelCategory }) =>
    api<Label>("/api/labels", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<{ name: string; color: string; category: LabelCategory }>) =>
    api<Label>(`/api/labels/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  assign: (appId: string, labelId: string) =>
    api<void>(`/api/applications/${appId}/labels/${labelId}`, { method: "POST" }),
  remove: (appId: string, labelId: string) =>
    api<void>(`/api/applications/${appId}/labels/${labelId}`, { method: "DELETE" }),
};
