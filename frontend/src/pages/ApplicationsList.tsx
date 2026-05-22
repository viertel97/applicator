import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { Application, LabelCategory } from "../api/applications";
import { applications } from "../api/applications";
import { labels as labelsApi } from "../api/labels";
import { AddApplicationForm } from "../components/AddApplicationForm";
import { JobStateBadge, StatusBadge, OnlineBadge } from "../components/StatusBadge";
import { LabelChip } from "../components/LabelChip";

const FILTER_OPEN_KEY = "applicator.labelFilter.openCategories";

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

function loadOpenCategories(): Set<LabelCategory> {
  try {
    const raw = localStorage.getItem(FILTER_OPEN_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as LabelCategory[];
    return new Set(arr);
  } catch {
    return new Set();
  }
}

function saveOpenCategories(s: Set<LabelCategory>) {
  localStorage.setItem(FILTER_OPEN_KEY, JSON.stringify([...s]));
}

export default function ApplicationsList() {
  const [filterLabelIds, setFilterLabelIds] = useState<string[]>([]);

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

  const toggleLabel = (id: string) =>
    setFilterLabelIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  const [openCats, setOpenCats] = useState<Set<LabelCategory>>(() => loadOpenCategories());

  function toggleCat(cat: LabelCategory) {
    setOpenCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat); else next.add(cat);
      saveOpenCategories(next);
      return next;
    });
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">Applications</h1>
      <AddApplicationForm />
      {(allLabels.data ?? []).length > 0 && (() => {
        const allLabelsList = allLabels.data ?? [];
        const grouped = new Map<LabelCategory, typeof allLabelsList>();
        for (const lab of allLabelsList) {
          const arr = grouped.get(lab.category) ?? [];
          arr.push(lab);
          grouped.set(lab.category, arr);
        }
        return (
          <div className="space-y-1 mb-3">
            {CATEGORY_ORDER.map((cat) => {
              const items = grouped.get(cat);
              if (!items || items.length === 0) return null;
              const open = openCats.has(cat);
              return (
                <div key={cat} className="border rounded">
                  <button
                    type="button"
                    onClick={() => toggleCat(cat)}
                    className="w-full flex justify-between items-center px-2 py-1 text-sm"
                  >
                    <span>{CATEGORY_LABEL[cat]}</span>
                    <span className="text-slate-500">{items.length} {open ? "▾" : "▸"}</span>
                  </button>
                  {open && (
                    <div className="flex flex-wrap gap-1 p-2">
                      {items.map((lab) => (
                        <button
                          key={lab.id}
                          type="button"
                          className={`text-xs rounded px-2 py-0.5 border ${
                            filterLabelIds.includes(lab.id) ? "bg-indigo-100 border-indigo-300" : "bg-white"
                          }`}
                          onClick={() => toggleLabel(lab.id)}
                        >
                          {lab.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })()}
      {isLoading && <div>Loading…</div>}
      <ul className="divide-y border rounded bg-white">
        {(data ?? []).map((a: Application) => (
          <li key={a.id} className="p-3 flex items-center gap-3 hover:bg-slate-50">
            <Link to={`/applications/${a.id}`} className="flex-1 truncate min-w-0">
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
            <OnlineBadge online={a.posting_online} />
            <JobStateBadge state={a.job_state} />
            <StatusBadge status={a.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
