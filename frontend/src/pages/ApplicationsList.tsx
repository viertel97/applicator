import { useState, useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { Application, AppStatus, LabelCategory } from "../api/applications";
import { applications } from "../api/applications";
import { labels as labelsApi } from "../api/labels";
import { AddApplicationForm } from "../components/AddApplicationForm";
import { JobStateBadge, StatusBadge, OnlineBadge } from "../components/StatusBadge";
import { LabelChip } from "../components/LabelChip";
import { ConfirmDialog } from "../components/ConfirmDialog";

const LABEL_PANEL_KEY = "applicator.labelFilter.panelOpen";
const STATUS_FILTER_KEY = "applicator.statusFilter.hidden";
const MAIL_SENT_FILTER_KEY = "applicator.statusFilter.showMailSent";
const DOCS_FILTER_KEY = "applicator.docsFilter.required";

const ALL_DOCS = ["cv", "cover_letter", "portfolio", "references", "certificates", "other"] as const;
type RequiredDoc = typeof ALL_DOCS[number];
const DOC_LABEL: Record<RequiredDoc, string> = {
  cv: "CV",
  cover_letter: "Cover letter",
  portfolio: "Portfolio",
  references: "References",
  certificates: "Certificates",
  other: "Other",
};

const ALL_STATUSES: AppStatus[] = ["draft", "applied", "offer", "rejected", "accepted", "withdrawn", "discarded", "need_call", "apply_direct"];
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

function loadShowMailSent(): boolean {
  const raw = localStorage.getItem(MAIL_SENT_FILTER_KEY);
  return raw === null ? true : raw === "true";
}

export default function ApplicationsList() {
  const scrollKey = "applicator.list.scrollY";
  const restoredRef = useRef(false);

  const [filterLabelIds, setFilterLabelIds] = useState<string[]>([]);
  const [hiddenStatuses, setHiddenStatuses] = useState<Set<AppStatus>>(() => loadHiddenStatuses());
  const [showMailSent, setShowMailSent] = useState<boolean>(() => loadShowMailSent());
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

  const { data, isLoading } = useQuery<Application[]>({
    queryKey: ["applications", filterLabelIds],
    queryFn: () => applications.list(filterLabelIds),
    refetchInterval: (q) => {
      const arr = q.state.data;
      if (!arr) return false;
      return arr.some((a) => !["ready", "failed"].includes(a.job_state)) ? 2000 : false;
    },
  });

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

  const [filterDocs, setFilterDocs] = useState<RequiredDoc[]>(() => {
    try { return JSON.parse(localStorage.getItem(DOCS_FILTER_KEY) ?? "[]"); } catch { return []; }
  });

  const toggleDoc = (d: RequiredDoc) =>
    setFilterDocs((prev) => {
      const next = prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d];
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

  const visible = (data ?? []).filter((a) => {
    if (hiddenStatuses.has(a.status)) return false;
    // TODO(Task 16): re-implement "mail sent" filter against interactions table
    void showMailSent;
    if (filterDocs.length > 0) {
      const docs = a.job_posting?.required_documents ?? [];
      if (!filterDocs.every((d) => docs.includes(d))) return false;
    }
    return true;
  });

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">Applications</h1>
      <AddApplicationForm />

      {/* Status filter */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {ALL_STATUSES.map((s) => {
          const hidden = hiddenStatuses.has(s);
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggleStatus(s)}
              className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                hidden
                  ? "bg-white text-slate-400 border-slate-200"
                  : "bg-slate-700 text-white border-slate-700"
              }`}
            >
              {STATUS_LABEL[s]}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => {
            const next = !showMailSent;
            setShowMailSent(next);
            localStorage.setItem(MAIL_SENT_FILTER_KEY, String(next));
          }}
          className={`text-xs px-2 py-0.5 rounded border transition-colors ${
            showMailSent
              ? "bg-blue-600 text-white border-blue-600"
              : "bg-white text-slate-400 border-slate-200"
          }`}
        >
          ✉ Mail sent
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {ALL_DOCS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => toggleDoc(d)}
            className={`text-xs px-2 py-0.5 rounded border transition-colors ${
              filterDocs.includes(d)
                ? "bg-amber-100 text-amber-800 border-amber-300"
                : "bg-white text-slate-400 border-slate-200 hover:border-slate-400"
            }`}
          >
            {DOC_LABEL[d]}
          </button>
        ))}
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
                  ? "bg-indigo-100 border-indigo-300 text-indigo-800"
                  : "bg-white border-slate-200 text-slate-500 hover:border-slate-400"
              }`}
            >
              Labels{activeCount > 0 ? ` (${activeCount})` : ""} {labelPanelOpen ? "▾" : "▸"}
            </button>
            {activeCount > 0 && !labelPanelOpen && (
              <button
                type="button"
                onClick={() => setFilterLabelIds([])}
                className="ml-2 text-xs text-slate-400 hover:text-slate-600"
              >
                clear
              </button>
            )}
            {labelPanelOpen && (
              <div className="mt-2 border rounded bg-white p-3 space-y-2">
                {CATEGORY_ORDER.map((cat) => {
                  const items = grouped.get(cat);
                  if (!items || items.length === 0) return null;
                  return (
                    <div key={cat}>
                      <div className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-1">
                        {CATEGORY_LABEL[cat]}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {items.map((lab) => (
                          <button
                            key={lab.id}
                            type="button"
                            className={`text-xs rounded px-2 py-0.5 border transition-colors ${
                              filterLabelIds.includes(lab.id)
                                ? "bg-indigo-100 border-indigo-300 text-indigo-800"
                                : "bg-white border-slate-200 hover:border-slate-400"
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
                    className="text-xs text-slate-400 hover:text-slate-600 pt-1"
                  >
                    Clear all filters
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })()}
      {isLoading && <div>Loading…</div>}
      {!isLoading && (
        <div className="text-xs text-slate-400 mb-1">
          {visible.length} {visible.length === 1 ? "position" : "positions"}
          {(data ?? []).length !== visible.length && ` of ${(data ?? []).length}`}
        </div>
      )}
      <ul className="divide-y border rounded bg-white">
        {visible.map((a: Application) => (
          <li key={a.id} className="p-3 flex items-center gap-3 hover:bg-slate-50">
            <Link
              to={`/applications/${a.id}`}
              className="flex-1 truncate min-w-0"
              onClick={() => sessionStorage.setItem(scrollKey, String(window.scrollY))}
            >
              <div className="font-medium truncate">
                <span className="text-slate-400 font-mono mr-2">
                  #{String(a.display_id).padStart(4, "0")}
                </span>
                {a.job_posting?.title ?? a.url}
              </div>
              <div className="text-sm text-slate-500 flex items-center gap-1">
                {a.job_posting?.company}
                {a.job_posting?.location && (
                  <span className="text-slate-400">· {a.job_posting.location}</span>
                )}
              </div>
              {a.labels.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {a.labels.map((lbl) => (
                    <LabelChip key={lbl.id} label={lbl} />
                  ))}
                </div>
              )}
            </Link>
            <a
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-slate-400 hover:text-slate-600 flex-shrink-0"
              title="Open original posting"
            >
              ↗
            </a>
            {/* TODO(Task 14/16): show mail-sent badge from interactions */}
            <OnlineBadge online={a.posting_online} />
            <JobStateBadge state={a.job_state} />
            <StatusBadge status={a.status} />
            <button
              type="button"
              className="text-slate-400 hover:text-rose-600 px-2"
              onClick={(e) => { e.stopPropagation(); setPendingDelete(a); }}
              aria-label="delete"
              data-testid="delete-button"
            >
              🗑
            </button>
          </li>
        ))}
      </ul>
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
