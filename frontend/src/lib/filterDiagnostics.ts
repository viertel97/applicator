import type { Application, AppStatus } from "../api/applications";
import { matchesSearch } from "./search.ts";

const ALL_STATUSES: AppStatus[] = [
  "draft", "applied", "offer", "rejected", "accepted",
  "withdrawn", "discarded", "need_call", "apply_direct",
];

export interface FilterState {
  hiddenStatuses: Set<AppStatus>;
  reasonFilter: string | null;
  requireDocs: string[];
  hideDocs: string[];
  query: string;
  filterLabelIds: string[];
  awaitingFilter: AwaitingFilter;
}

export type AwaitingFilter = "all" | "awaiting" | "hide";

export type EmptyReason =
  | "all-statuses-hidden"
  | "no-status-match"
  | "reason"
  | "docs"
  | "search"
  | "awaiting"
  | "labels"
  | "mixed"
  | null;

export function applyFilters(data: Application[], f: FilterState): Application[] {
  return data.filter((a) => {
    if (f.hiddenStatuses.has(a.status)) return false;
    if (f.reasonFilter && a.status === "discarded" && a.discard_reason_id !== f.reasonFilter)
      return false;
    if (f.requireDocs.length > 0) {
      const docs = a.job_posting?.required_documents ?? [];
      if (!f.requireDocs.every((d) => docs.includes(d))) return false;
    }
    if (f.hideDocs.length > 0) {
      const docs = a.job_posting?.required_documents ?? [];
      if (f.hideDocs.some((d) => docs.includes(d))) return false;
    }
    if (f.awaitingFilter === "awaiting" && !a.awaiting_response) return false;
    if (f.awaitingFilter === "hide" && a.awaiting_response) return false;
    if (!matchesSearch(a, f.query)) return false;
    return true;
  });
}

export function diagnoseEmpty(data: Application[], f: FilterState): EmptyReason {
  if (data.length === 0) {
    return f.filterLabelIds.length > 0 ? "labels" : null;
  }

  if (applyFilters(data, f).length > 0) return null;

  if (ALL_STATUSES.every((s) => f.hiddenStatuses.has(s))) return "all-statuses-hidden";

  const relaxations: { kind: Exclude<EmptyReason, null>; state: FilterState }[] = [
    { kind: "no-status-match", state: { ...f, hiddenStatuses: new Set() } },
    { kind: "reason", state: { ...f, reasonFilter: null } },
    { kind: "docs", state: { ...f, requireDocs: [], hideDocs: [] } },
    { kind: "search", state: { ...f, query: "" } },
    { kind: "awaiting", state: { ...f, awaitingFilter: "all" } },
  ];

  const recovers = relaxations.filter((r) => applyFilters(data, r.state).length > 0);
  return recovers.length === 1 ? recovers[0].kind : "mixed";
}
