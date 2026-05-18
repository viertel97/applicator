import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";
import type { AppStatus } from "../api/applications";
import { cv as cvApi, anschreiben as anApi } from "../api/documents";
import { JobPostingPanel } from "../components/JobPostingPanel";
import { AnschreibenEditor } from "../components/AnschreibenEditor";
import { ChatPanel } from "../components/ChatPanel";
import { InterviewsList } from "../components/InterviewsList";
import { JobStateBadge, StatusBadge, OnlineBadge } from "../components/StatusBadge";
import { LabelEditor } from "../components/LabelEditor";

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
  const cvs = useQuery({ queryKey: ["cv-variants"], queryFn: () => cvApi.list() });
  const ans = useQuery({ queryKey: ["an-variants"], queryFn: () => anApi.list() });

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
  const setVariants = useMutation({
    mutationFn: (b: { cv_variant_id?: string; clear_cv?: boolean;
                       anschreiben_variant_id?: string; clear_anschreiben?: boolean }) =>
      applications.patchVariants(id!, b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });
  const generate = useMutation({
    mutationFn: () => applications.generate(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });

  if (q.isLoading || !q.data) return <div className="p-6">Loading…</div>;
  const a = q.data;
  const running = ["pending", "crawling", "extracting", "generating"].includes(a.job_state);
  const canGenerate =
    !!a.cv_variant_id &&
    !!a.anschreiben_variant_id &&
    !!a.job_posting &&
    (a.job_state === "extracted" ||
      a.job_state === "ready" ||
      (a.job_state === "failed" && a.failed_stage === "generate"));

  return (
    <div className="p-6 grid grid-cols-2 gap-6 max-w-7xl mx-auto">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h1 className="text-xl font-semibold flex-1 truncate">
            {a.job_posting?.title ?? a.url}
          </h1>
          <OnlineBadge online={a.posting_online} />
          <JobStateBadge state={a.job_state} failedStage={a.failed_stage} />
          <StatusBadge status={a.status} />
        </div>
        <div className="mb-3">
          <a
            href={a.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:underline flex items-center gap-1"
          >
            View original posting ↗
          </a>
        </div>
        <div className="mb-3">
          <div className="text-xs text-slate-500 mb-1 font-medium uppercase tracking-wide">Labels</div>
          <LabelEditor appId={a.id} assigned={a.labels} />
        </div>

        {a.job_state === "failed" && (
          <div className="bg-rose-50 border border-rose-200 p-3 rounded mb-3">
            <div className="text-rose-700 text-sm mb-2">
              Failed at {a.failed_stage}: {a.job_error}
            </div>
            <button
              onClick={() => retry.mutate()}
              className="bg-rose-600 text-white px-3 py-1 rounded"
            >
              Retry
            </button>
          </div>
        )}

        {a.job_posting_dirty && a.generated_md && (
          <div className="bg-amber-50 border border-amber-200 p-3 rounded mb-3 flex items-center justify-between">
            <span className="text-amber-800 text-sm">
              Job info changed — regenerate the Anschreiben?
            </span>
            <button
              onClick={() => generate.mutate()}
              disabled={!canGenerate || generate.isPending}
              className="bg-amber-600 text-white px-3 py-1 rounded disabled:opacity-50"
            >
              Regenerate
            </button>
          </div>
        )}

        <div className="bg-white border rounded p-3">
          <JobPostingPanel appId={a.id} jp={a.job_posting} disabled={running} />
        </div>

        <div className="mt-4 grid gap-2">
          <div className="grid grid-cols-2 gap-2">
            <select
              value={a.cv_variant_id ?? ""}
              disabled={a.job_state === "generating"}
              onChange={(e) =>
                setVariants.mutate(
                  e.target.value
                    ? { cv_variant_id: e.target.value }
                    : { clear_cv: true },
                )
              }
              className="border rounded px-2 py-1"
            >
              <option value="">CV — none</option>
              {(cvs.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
            <select
              value={a.anschreiben_variant_id ?? ""}
              disabled={a.job_state === "generating"}
              onChange={(e) =>
                setVariants.mutate(
                  e.target.value
                    ? { anschreiben_variant_id: e.target.value }
                    : { clear_anschreiben: true },
                )
              }
              className="border rounded px-2 py-1"
            >
              <option value="">Anschreiben — none</option>
              {(ans.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            disabled={!canGenerate || generate.isPending}
            onClick={() => generate.mutate()}
            className="bg-blue-600 text-white px-3 py-2 rounded disabled:opacity-50"
            title={
              !a.cv_variant_id || !a.anschreiben_variant_id
                ? "Pick a CV and an Anschreiben variant"
                : !a.job_posting
                  ? "Awaiting extraction"
                  : ""
            }
          >
            {a.generated_md ? "Regenerate Anschreiben" : "Generate Anschreiben"}
          </button>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <span>Status:</span>
          <select
            value={a.status}
            onChange={(e) => setStatus.mutate(e.target.value as AppStatus)}
            className="border rounded px-2 py-1"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
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
          <div className="text-slate-500">
            {a.job_state === "extracted"
              ? "Pick variants and click Generate to produce the Anschreiben."
              : "Anschreiben pending…"}
          </div>
        )}
      </div>
    </div>
  );
}
