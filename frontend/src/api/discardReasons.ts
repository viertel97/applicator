import { api } from "./client";

export type DiscardReason = {
  id: string;
  slug: string;
  label: string;
  is_system: boolean;
  is_archived: boolean;
  sort_order: number;
  usage_count: number;
};

export const discardReasons = {
  list: (includeArchived = false) =>
    api<DiscardReason[]>(
      `/api/discard-reasons${includeArchived ? "?include_archived=1" : ""}`,
    ),
  create: (label: string, slug?: string) =>
    api<DiscardReason>("/api/discard-reasons", {
      method: "POST",
      body: JSON.stringify({ label, slug }),
    }),
  patch: (
    id: string,
    body: Partial<Pick<DiscardReason, "label" | "is_archived" | "sort_order">>,
  ) =>
    api<DiscardReason>(`/api/discard-reasons/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) =>
    api<void>(`/api/discard-reasons/${id}`, { method: "DELETE" }),
};
