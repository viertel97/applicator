import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
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
import { ConfirmDialog } from "../components/ConfirmDialog";
import { InquiryPanel } from "../components/InquiryPanel";

const STATUSES: AppStatus[] = ["draft", "applied", "offer", "rejected", "accepted", "withdrawn", "discarded", "need_call", "apply_direct"];

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [confirmOpen, setConfirmOpen] = useState(false);
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

  const prevTitle = useRef(document.title);
  useEffect(() => {
    const prev = prevTitle.current;
    if (q.data) {
      const jp = q.data.job_posting;
      const parts = [jp?.company, jp?.title].filter(Boolean);
      document.title = parts.length > 0 ? `${parts.join(" – ")} | Applicator` : "Applicator";
    }
    return () => { document.title = prev; };
  }, [q.data]);

  const [discardReason, setDiscardReason] = useState("");
  const [showDiscard, setShowDiscard] = useState(false);
  const [showPaste, setShowPaste] = useState(false);
  const [pasteText, setPasteText] = useState("");

  const setStatus = useMutation({
    mutationFn: ({ status, reason }: { status: AppStatus; reason?: string }) =>
      applications.setStatus(id!, status, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });
  const retry = useMutation({
    mutationFn: () => applications.retry(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });
  const extractFromText = useMutation({
    mutationFn: (raw_text: string) => applications.extractFromText(id!, raw_text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", id] });
      setShowPaste(false);
      setPasteText("");
    },
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
  const remove = useMutation({
    mutationFn: () => applications.remove(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      navigate("/applications");
    },
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
            <span className="text-slate-400 font-mono mr-2">
              #{String(a.display_id).padStart(4, "0")}
            </span>
            {a.job_posting?.title ?? a.url}
          </h1>
          <OnlineBadge online={a.posting_online} />
          <JobStateBadge state={a.job_state} failedStage={a.failed_stage} />
          <StatusBadge status={a.status} />
          <button
            type="button"
            className="text-rose-600 border border-rose-300 rounded px-2 py-1 text-sm"
            onClick={() => setConfirmOpen(true)}
          >
            Delete
          </button>
        </div>
        <div className="mb-3 flex items-center gap-2 flex-wrap">
          <a
            href={a.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:underline flex items-center gap-1"
          >
            View original posting ↗
          </a>
          <span className="text-slate-300">|</span>
          <select
            value={a.status}
            onChange={(e) => {
              const s = e.target.value as AppStatus;
              if (s !== "discarded") {
                setDiscardReason("");
                setStatus.mutate({ status: s });
              }
            }}
            className="border rounded px-2 py-1 text-sm"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          {a.status !== "discarded" && (
            <button
              type="button"
              className="text-orange-600 border border-orange-300 rounded px-2 py-0.5 text-sm"
              onClick={() => { setDiscardReason(""); setShowDiscard(true); }}
            >
              Discard…
            </button>
          )}
        </div>
        {(showDiscard || a.status === "discarded") && (
          <div className="mb-3 flex items-center gap-2">
            <input
              type="text"
              placeholder="Reason for discarding…"
              defaultValue={a.discard_reason ?? ""}
              onChange={(e) => setDiscardReason(e.target.value)}
              className="border rounded px-2 py-1 text-sm flex-1"
              onKeyDown={(e) => {
                if (e.key === "Enter")
                  setStatus.mutate({ status: "discarded", reason: discardReason });
              }}
            />
            <button
              type="button"
              className="bg-orange-600 text-white rounded px-3 py-1 text-sm disabled:opacity-50"
              disabled={setStatus.isPending}
              onClick={() => setStatus.mutate({ status: "discarded", reason: discardReason })}
            >
              {a.status === "discarded" ? "Update" : "Confirm discard"}
            </button>
            {a.status === "discarded" ? (
              <button
                type="button"
                className="border rounded px-2 py-1 text-sm text-slate-600"
                onClick={() => { setShowDiscard(false); setStatus.mutate({ status: "draft" }); }}
              >
                Restore
              </button>
            ) : (
              <button
                type="button"
                className="border rounded px-2 py-1 text-sm text-slate-500"
                onClick={() => setShowDiscard(false)}
              >
                Cancel
              </button>
            )}
          </div>
        )}
        <div className="mb-3">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wide mr-2">Folder</span>
          <code className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded select-all">{a.folder_name}</code>
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
            <div className="flex gap-2">
              <button
                onClick={() => retry.mutate()}
                className="bg-rose-600 text-white px-3 py-1 rounded"
              >
                Retry
              </button>
              <button
                type="button"
                onClick={() => setShowPaste((v) => !v)}
                className="border border-rose-300 text-rose-700 px-3 py-1 rounded text-sm"
              >
                Paste content
              </button>
            </div>
          </div>
        )}

        {!running && (
          <div className="mb-3">
            {!showPaste ? (
              a.job_state !== "failed" && (
                <button
                  type="button"
                  onClick={() => setShowPaste(true)}
                  className="text-xs text-slate-400 hover:text-slate-600"
                >
                  + Paste page content manually
                </button>
              )
            ) : (
              <div className="border rounded p-3 bg-slate-50">
                <div className="text-sm font-medium text-slate-700 mb-1">Paste page content</div>
                <textarea
                  className="w-full border rounded px-2 py-1 font-mono text-xs"
                  rows={8}
                  placeholder="Paste the raw text or HTML of the job posting here…"
                  value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                />
                <div className="flex gap-2 mt-2">
                  <button
                    type="button"
                    disabled={!pasteText.trim() || extractFromText.isPending}
                    onClick={() => extractFromText.mutate(pasteText)}
                    className="bg-blue-600 text-white px-3 py-1 rounded text-sm disabled:opacity-50"
                  >
                    {extractFromText.isPending ? "Extracting…" : "Extract"}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowPaste(false); setPasteText(""); }}
                    className="border rounded px-3 py-1 text-sm text-slate-600"
                  >
                    Cancel
                  </button>
                </div>
                {extractFromText.isError && (
                  <div className="text-rose-600 text-xs mt-1">
                    {(extractFromText.error as Error)?.message}
                  </div>
                )}
              </div>
            )}
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

        <InterviewsList appId={a.id} />
        <InquiryPanel app={a} />
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
      <ConfirmDialog
        open={confirmOpen}
        title="Delete application"
        body={`Delete application to ${a.job_posting?.company ?? "this company"}? This hides it from your list.`}
        busy={remove.isPending}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}
