import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { Application } from "../api/applications";
import { applications } from "../api/applications";
import { labels as labelsApi } from "../api/labels";
import { AddApplicationForm } from "../components/AddApplicationForm";
import { JobStateBadge, StatusBadge, OnlineBadge } from "../components/StatusBadge";
import { LabelChip } from "../components/LabelChip";
import { ConfirmDialog } from "../components/ConfirmDialog";

export default function ApplicationsList() {
  const [filterLabelIds, setFilterLabelIds] = useState<string[]>([]);
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

  const toggleLabel = (id: string) =>
    setFilterLabelIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">Applications</h1>
      <AddApplicationForm />
      {(allLabels.data ?? []).length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {(allLabels.data ?? []).map((lbl) => (
            <button
              key={lbl.id}
              onClick={() => toggleLabel(lbl.id)}
              className={`rounded-full transition-shadow ${
                filterLabelIds.includes(lbl.id) ? "ring-2 ring-offset-1 ring-slate-700" : ""
              }`}
            >
              <LabelChip label={lbl} />
            </button>
          ))}
        </div>
      )}
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
