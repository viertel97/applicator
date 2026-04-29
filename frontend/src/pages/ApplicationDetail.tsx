import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";
import type { AppStatus } from "../api/applications";
import { JobPostingPanel } from "../components/JobPostingPanel";
import { AnschreibenEditor } from "../components/AnschreibenEditor";
import { ChatPanel } from "../components/ChatPanel";
import { InterviewsList } from "../components/InterviewsList";
import { JobStateBadge, StatusBadge } from "../components/StatusBadge";

const STATUSES: AppStatus[] = ["draft", "applied", "offer", "rejected", "accepted", "withdrawn"];

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["application", id],
    queryFn: () => applications.get(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const a = query.state.data;
      if (!a) return false;
      return ["pending", "crawling", "extracting", "generating"].includes(a.job_state)
        ? 2000
        : false;
    },
  });
  const [md, setMd] = useState("");
  useEffect(() => {
    if (q.data?.generated_md != null) setMd(q.data.generated_md);
  }, [q.data?.generated_md]);

  const setStatus = useMutation({
    mutationFn: (s: AppStatus) => applications.setStatus(id!, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });
  const retry = useMutation({
    mutationFn: () => applications.retry(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });

  if (q.isLoading || !q.data) return <div className="p-6">Loading…</div>;
  const a = q.data;
  return (
    <div className="p-6 grid grid-cols-2 gap-6 max-w-7xl mx-auto">
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h1 className="text-xl font-semibold flex-1 truncate">
            {a.job_posting?.title ?? a.url}
          </h1>
          <JobStateBadge state={a.job_state} />
          <StatusBadge status={a.status} />
        </div>
        {a.job_state === "failed" && (
          <div className="bg-rose-50 border border-rose-200 p-3 rounded mb-3">
            <div className="text-rose-700 text-sm mb-2">Failed: {a.job_error}</div>
            <button
              onClick={() => retry.mutate()}
              className="bg-rose-600 text-white px-3 py-1 rounded"
            >
              Retry
            </button>
          </div>
        )}
        <div className="bg-white border rounded p-3">
          <JobPostingPanel
            appId={a.id}
            jp={a.job_posting}
            disabled={["crawling", "extracting", "generating"].includes(a.job_state)}
          />
        </div>
        <div className="mt-4 flex items-center gap-2">
          <span>Status:</span>
          <select
            value={a.status}
            onChange={(e) => setStatus.mutate(e.target.value as AppStatus)}
            className="border rounded px-2 py-1"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <InterviewsList appId={a.id} />
      </div>
      <div>
        {a.generated_md != null ? (
          <>
            <AnschreibenEditor appId={a.id} md={md} onChange={setMd} hasDocx={a.has_docx} />
            <ChatPanel appId={a.id} />
          </>
        ) : (
          <div className="text-slate-500">Anschreiben pending…</div>
        )}
      </div>
    </div>
  );
}
