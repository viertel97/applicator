import { useState, useEffect, useRef, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import type { Application, AppStatus, LabelCategory } from "../api/applications";
import { applications } from "../api/applications";
import { labels as labelsApi } from "../api/labels";
import { discardReasons } from "../api/discardReasons";
import { AddApplicationForm } from "../components/AddApplicationForm";
import { JobStateBadge, StatusBadge, OnlineBadge } from "../components/StatusBadge";
import { CappedLabelChips } from "../components/CappedLabelChips";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardReasonPicker } from "../components/DiscardReasonPicker";
import { FilterEmptyState } from "../components/FilterEmptyState";
import {
  applyFilters,
  diagnoseEmpty,
  type EmptyReason,
  type FilterState,
  type AwaitingFilter,
} from "../lib/filterDiagnostics";
import { ALL_DOCS, DOC_LABEL, type RequiredDoc } from "../lib/docs";
import { Card } from "../components/ui/Card";

const LABEL_PANEL_KEY = "applicator.labelFilter.panelOpen";
const STATUS_FILTER_KEY = "applicator.statusFilter.hidden";
const DOCS_FILTER_KEY = "applicator.docsFilter.required";
const AWAITING_FILTER_KEY = "applicator.awaitingFilter";

const ALL_STATUSES: AppStatus[] = ["draft", "applied", "offer", "rejected", "accepted", "withdrawn", "discarded", "need_call", "apply_direct", "interview"];
const HIDDEN_BY_DEFAULT: AppStatus[] = ["rejected", "withdrawn", "discarded"];

const STATUS_LABEL: Record<AppStatus, string> = {
  draft: "Draft",
  applied: "Applied",
  offer: "Offer",
  rejected: "Rejected",
  accepted: "Accepted",
  withdrawn: "Withdrawn",
  discarded: "Discarded",
  need_call: "Need call",
  apply_direct: "Apply direct",
  interview: "Interview",
};

const CATEGORY_ORDER: LabelCategory[] = [
  "role", "tech", "domain", "seniority",
  "work_mode", "location", "company_size",
  "language", "company", "other",
];

const CATEGORY_LABEL: Record<LabelCategory, string> = {
  role: "Role",
  tech: "Tech",
  domain: "Domain",
  seniority: "Seniority",
  work_mode: "Work mode",
  location: "Location",
  company_size: "Company size",
  language: "Language",
  company: "Company",
  other: "Other",
};


function loadHiddenStatuses(): Set<AppStatus> {
  try {
    const raw = localStorage.getItem(STATUS_FILTER_KEY);
    if (raw === null) return new Set(HIDDEN_BY_DEFAULT);
    return new Set(JSON.parse(raw) as AppStatus[]);
  } catch {
    return new Set(HIDDEN_BY_DEFAULT);
  }
}

function saveHiddenStatuses(s: Set<AppStatus>) {
  localStorage.setItem(STATUS_FILTER_KEY, JSON.stringify([...s]));
}

function loadAwaitingFilter(): AwaitingFilter {
  const raw = localStorage.getItem(AWAITING_FILTER_KEY);
  if (raw === "awaiting" || raw === "hide" || raw === "all") return raw;
  if (raw === "true") return "awaiting"; // migrate legacy boolean
  return "all";
}

type DocFilter = "require" | "hide";

function loadDocFilters(): Record<string, DocFilter> {
  try {
    const raw = localStorage.getItem(DOCS_FILTER_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // migrate legacy "require all" array form
      const rec: Record<string, DocFilter> = {};
      for (const d of parsed) rec[d] = "require";
      return rec;
    }
    if (parsed && typeof parsed === "object") return parsed;
    return {};
  } catch {
    return {};
  }
}

export default function ApplicationsList() {
  const scrollKey = "applicator.list.scrollY";
  const restoredRef = useRef(false);
  const [searchParams, setSearchParams] = useSearchParams();

  const [query, setQuery] = useState("");
  const [filterLabelIds, setFilterLabelIds] = useState<string[]>([]);
  const [hiddenStatuses, setHiddenStatuses] = useState<Set<AppStatus>>(() => loadHiddenStatuses());
  const [reasonFilter, setReasonFilter] = useState<string | null>(null);
  const qc = useQueryClient();
  const [pendingDelete, setPendingDelete] = useState<Application | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => applications.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      setPendingDelete(null);
    },
  });

  const allLabels = useQuery({ queryKey: ["labels"], queryFn: labelsApi.list });
  const reasonsQ = useQuery({
    queryKey: ["discard-reasons"],
    queryFn: () => discardReasons.list(),
  });
  const reasonMap = useMemo(
    () => Object.fromEntries((reasonsQ.data ?? []).map((r) => [r.id, r.label])),
    [reasonsQ.data],
  );

  const { data, isLoading } = useQuery<Application[]>({
    queryKey: ["applications", filterLabelIds],
    queryFn: () => applications.list(filterLabelIds),
    refetchInterval: (q) => {
      const arr = q.state.data;
      if (!arr) return false;
      return arr.some((a) => !["ready", "failed"].includes(a.job_state)) ? 2000 : false;
    },
  });

  // Sync URL query params (?status=discarded&reason=<slug>) into local state.
  // Runs once when params or reasons become available.
  const urlSyncedRef = useRef(false);
  useEffect(() => {
    if (urlSyncedRef.current) return;
    const statusParam = searchParams.get("status");
    const reasonParam = searchParams.get("reason");
    if (!statusParam && !reasonParam) {
      urlSyncedRef.current = true;
      return;
    }
    // For reason resolution we need the reasons list.
    if (reasonParam && !reasonsQ.data) return;

    if (statusParam && (ALL_STATUSES as string[]).includes(statusParam)) {
      // Show only the requested status.
      const next = new Set<AppStatus>(ALL_STATUSES.filter((s) => s !== statusParam));
      setHiddenStatuses(next);
      saveHiddenStatuses(next);
    }
    if (reasonParam && reasonsQ.data) {
      const match = reasonsQ.data.find((r) => r.slug === reasonParam || r.id === reasonParam);
      if (match) setReasonFilter(match.id);
    }
    urlSyncedRef.current = true;
  }, [searchParams, reasonsQ.data]);

  const discardedVisible = !hiddenStatuses.has("discarded");

  // Clear the reason filter if the user re-hides the discarded status.
  useEffect(() => {
    if (!discardedVisible && reasonFilter) setReasonFilter(null);
  }, [discardedVisible, reasonFilter]);

  // Keep URL in sync with the reason picker so it stays shareable.
  useEffect(() => {
    if (!urlSyncedRef.current) return;
    const current = searchParams.get("reason");
    if (reasonFilter && reasonsQ.data) {
      const r = reasonsQ.data.find((x) => x.id === reasonFilter);
      if (r && current !== r.slug) {
        const next = new URLSearchParams(searchParams);
        next.set("reason", r.slug);
        setSearchParams(next, { replace: true });
      }
    } else if (!reasonFilter && current) {
      const next = new URLSearchParams(searchParams);
      next.delete("reason");
      setSearchParams(next, { replace: true });
    }
  }, [reasonFilter, reasonsQ.data]);

  useEffect(() => {
    if (isLoading || restoredRef.current) return;
    restoredRef.current = true;
    const saved = sessionStorage.getItem(scrollKey);
    if (saved) {
      sessionStorage.removeItem(scrollKey);
      window.scrollTo(0, parseInt(saved, 10));
    }
  }, [isLoading]);

  const toggleLabel = (id: string) =>
    setFilterLabelIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  const toggleStatus = (s: AppStatus) => {
    setHiddenStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s); else next.add(s);
      saveHiddenStatuses(next);
      return next;
    });
  };

  const [docFilters, setDocFilters] = useState<Record<string, DocFilter>>(loadDocFilters);

  const [awaitingFilter, setAwaitingFilter] = useState<AwaitingFilter>(loadAwaitingFilter);

  const cycleAwaiting = () =>
    setAwaitingFilter((v) => {
      const next: AwaitingFilter = v === "all" ? "awaiting" : v === "awaiting" ? "hide" : "all";
      localStorage.setItem(AWAITING_FILTER_KEY, next);
      return next;
    });

  const cycleDoc = (d: RequiredDoc) =>
    setDocFilters((prev) => {
      const next = { ...prev };
      const cur = prev[d];
      if (cur === undefined) next[d] = "require";
      else if (cur === "require") next[d] = "hide";
      else delete next[d];
      localStorage.setItem(DOCS_FILTER_KEY, JSON.stringify(next));
      return next;
    });

  const [labelPanelOpen, setLabelPanelOpen] = useState<boolean>(
    () => localStorage.getItem(LABEL_PANEL_KEY) === "true",
  );

  function toggleLabelPanel() {
    setLabelPanelOpen((v) => {
      localStorage.setItem(LABEL_PANEL_KEY, String(!v));
      return !v;
    });
  }

  const filterState: FilterState = useMemo(() => {
    const requireDocs = ALL_DOCS.filter((d) => docFilters[d] === "require");
    const hideDocs = ALL_DOCS.filter((d) => docFilters[d] === "hide");
    return { hiddenStatuses, reasonFilter, requireDocs, hideDocs, query, filterLabelIds, awaitingFilter };
  }, [hiddenStatuses, reasonFilter, docFilters, query, filterLabelIds, awaitingFilter]);

  const visible = useMemo(
    () => applyFilters(data ?? [], filterState),
    [data, filterState],
  );

  const emptyReason = isLoading ? null : diagnoseEmpty(data ?? [], filterState);

  function handleFix(reason: Exclude<EmptyReason, null>) {
    switch (reason) {
      case "all-statuses-hidden":
      case "no-status-match": {
        const next = new Set<AppStatus>();
        setHiddenStatuses(next);
        saveHiddenStatuses(next);
        break;
      }
      case "reason":
        setReasonFilter(null);
        break;
      case "docs":
        setDocFilters({});
        localStorage.setItem(DOCS_FILTER_KEY, "{}");
        break;
      case "search":
        setQuery("");
        break;
      case "labels":
        setFilterLabelIds([]);
        break;
      case "awaiting":
        setAwaitingFilter("all");
        localStorage.setItem(AWAITING_FILTER_KEY, "all");
        break;
      case "mixed": {
        const next = new Set<AppStatus>();
        setHiddenStatuses(next);
        saveHiddenStatuses(next);
        setReasonFilter(null);
        setDocFilters({});
        localStorage.setItem(DOCS_FILTER_KEY, "{}");
        setQuery("");
        setFilterLabelIds([]);
        setAwaitingFilter("all");
        localStorage.setItem(AWAITING_FILTER_KEY, "all");
        break;
      }
    }
  }

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6">
      <h1 className="text-2xl font-semibold mb-4">Applications</h1>
      <AddApplicationForm />

      <div className="relative mb-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search title, company, location…"
          className="bg-surface border border-border rounded px-3 py-2 pr-8 text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring w-full text-sm"
        />
        {query && (
          <button
            type="button"
            onClick={() => setQuery("")}
            aria-label="clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-fg"
          >
            ✕
          </button>
        )}
      </div>

      {/* Status filter */}
      <div className="flex flex-wrap gap-1.5 mb-3 items-center">
        <span className="text-xs text-muted mr-1">
          Status{" "}
          <span className="text-muted">
            (showing {ALL_STATUSES.length - hiddenStatuses.size} of {ALL_STATUSES.length})
          </span>
        </span>
        {ALL_STATUSES.map((s) => {
          const hidden = hiddenStatuses.has(s);
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggleStatus(s)}
              className={`text-xs px-2 py-1 rounded border transition-colors ${hidden ? "bg-surface text-muted border-border" : "bg-accent text-accentFg border-accent"}`}
            >
              {STATUS_LABEL[s]}
            </button>
          );
        })}
        {discardedVisible && (
          <div className="flex items-center gap-1 ml-2">
            <span className="text-xs text-muted">Reason:</span>
            <DiscardReasonPicker
              value={reasonFilter}
              onChange={(id) => setReasonFilter(id)}
            />
          </div>
        )}
      </div>
      {!discardedVisible && (
        <div className="flex items-center gap-1 mb-3 ml-4">
          <span className="text-xs text-muted">Select Discarded to filter by reason</span>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 mb-3 items-center">
        <button
          type="button"
          onClick={cycleAwaiting}
          title="Click to cycle: all → awaiting only → hide awaiting"
          className={`text-xs px-2 py-0.5 rounded border transition-colors ${
            awaitingFilter === "awaiting"
              ? "bg-sky-100 text-sky-800 border-sky-300 dark:bg-sky-900 dark:text-sky-200 dark:border-sky-700"
              : awaitingFilter === "hide"
                ? "bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-900 dark:text-rose-200 dark:border-rose-700"
                : "bg-surface text-muted border-border hover:border-muted"
          }`}
        >
          {awaitingFilter === "hide" ? "Hide awaiting" : "Awaiting reply"}
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3 items-center">
        <span className="text-xs text-muted mr-1">Documents</span>
        {ALL_DOCS.map((d) => {
          const state = docFilters[d];
          return (
            <button
              key={d}
              type="button"
              onClick={() => cycleDoc(d)}
              title="Click to cycle: any → requires → hides"
              className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                state === "require"
                  ? "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900 dark:text-amber-200 dark:border-amber-700"
                  : state === "hide"
                    ? "bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-900 dark:text-rose-200 dark:border-rose-700"
                    : "bg-surface text-muted border-border hover:border-muted"
              }`}
            >
              {state === "hide" ? `Not ${DOC_LABEL[d]}` : DOC_LABEL[d]}
            </button>
          );
        })}
      </div>

      {(allLabels.data ?? []).length > 0 && (() => {
        const allLabelsList = allLabels.data ?? [];
        const grouped = new Map<LabelCategory, typeof allLabelsList>();
        for (const lab of allLabelsList) {
          const arr = grouped.get(lab.category) ?? [];
          arr.push(lab);
          grouped.set(lab.category, arr);
        }
        const activeCount = filterLabelIds.length;
        return (
          <div className="mb-3">
            <button
              type="button"
              onClick={toggleLabelPanel}
              className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                activeCount > 0
                  ? "bg-indigo-100 border-indigo-300 text-indigo-800 dark:bg-indigo-900 dark:border-indigo-700 dark:text-indigo-200"
                  : "bg-surface border-border text-muted hover:border-muted"
              }`}
            >
              Labels · any of{activeCount > 0 ? ` (${activeCount})` : ""} {labelPanelOpen ? "▾" : "▸"}
            </button>
            {activeCount > 0 && !labelPanelOpen && (
              <button
                type="button"
                onClick={() => setFilterLabelIds([])}
                className="ml-2 text-xs text-muted hover:text-fg"
              >
                clear
              </button>
            )}
            {labelPanelOpen && (
              <div className="mt-2 border border-border rounded bg-surface p-3 space-y-2">
                {CATEGORY_ORDER.map((cat) => {
                  const items = grouped.get(cat);
                  if (!items || items.length === 0) return null;
                  return (
                    <div key={cat}>
                      <div className="text-xs font-medium text-muted uppercase tracking-wide mb-1">
                        {CATEGORY_LABEL[cat]}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {items.map((lab) => (
                          <button
                            key={lab.id}
                            type="button"
                            className={`text-xs rounded px-2 py-0.5 border transition-colors ${
                              filterLabelIds.includes(lab.id)
                                ? "bg-indigo-100 border-indigo-300 text-indigo-800 dark:bg-indigo-900 dark:border-indigo-700 dark:text-indigo-200"
                                : "bg-surface border-border hover:border-muted"
                            }`}
                            onClick={() => toggleLabel(lab.id)}
                          >
                            {lab.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
                {activeCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setFilterLabelIds([])}
                    className="text-xs text-muted hover:text-fg pt-1"
                  >
                    Clear all filters
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })()}
      <div className="text-xs text-muted mb-2">
        Sections combine with AND. Documents: amber = requires all, rose = hides any. Labels = any.
      </div>
      {isLoading && <div>Loading…</div>}
      {!isLoading && (
        <div className="text-xs text-muted mb-1">
          {visible.length} {visible.length === 1 ? "position" : "positions"}
          {(data ?? []).length !== visible.length && ` of ${(data ?? []).length}`}
        </div>
      )}
      {!isLoading && visible.length === 0 && emptyReason ? (
        <FilterEmptyState reason={emptyReason} onFix={handleFix} />
      ) : (
      <div>
        {visible.map((a: Application) => (
          <Card key={a.id} className="mb-2 p-3 hover:bg-surface2 transition-colors">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
              <Link
                to={`/applications/${a.id}`}
                className="flex-1 min-w-0 py-1.5 text-fg hover:text-accent"
                onClick={() => sessionStorage.setItem(scrollKey, String(window.scrollY))}
              >
                <div className="font-medium truncate">
                  <span className="text-muted font-mono mr-2">
                    #{String(a.display_id).padStart(4, "0")}
                  </span>
                  {a.job_posting?.title ?? a.url}
                </div>
                <div className="text-sm text-muted truncate">
                  {a.job_posting?.company}
                  {a.job_posting?.location && (
                    <span className="text-muted"> · {a.job_posting.location}</span>
                  )}
                </div>
                <CappedLabelChips labels={a.labels} />
              </Link>
              <div className="flex items-center gap-2 flex-wrap justify-end sm:flex-nowrap sm:flex-shrink-0">
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-muted hover:text-fg flex-shrink-0 p-2 -m-1"
                  title="Open original posting"
                >
                  ↗
                </a>
                <OnlineBadge online={a.posting_online} />
                <JobStateBadge state={a.job_state} />
                <StatusBadge
                  status={a.status}
                  summary={a.interview_summary}
                  title={a.discard_reason_id ? reasonMap[a.discard_reason_id] : undefined}
                />
                <button
                  type="button"
                  className="text-muted hover:text-rose-600 p-2 -m-1"
                  onClick={(e) => { e.stopPropagation(); setPendingDelete(a); }}
                  aria-label="delete"
                  data-testid="delete-button"
                >
                  🗑
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
      )}
      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete application"
        body={
          pendingDelete
            ? `Delete application to ${pendingDelete.job_posting?.company ?? "this company"}? This hides it from your list.`
            : ""
        }
        busy={remove.isPending}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete.id)}
      />
    </div>
  );
}
