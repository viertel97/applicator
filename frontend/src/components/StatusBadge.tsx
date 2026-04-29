import type { AppStatus, FailedStage, JobState } from "../api/applications";

const STATUS_CLASS: Record<AppStatus, string> = {
  draft: "bg-slate-200 text-slate-700",
  applied: "bg-blue-100 text-blue-700",
  offer: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
  accepted: "bg-green-200 text-green-800",
  withdrawn: "bg-slate-300 text-slate-600",
};

export function StatusBadge({ status }: { status: AppStatus }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_CLASS[status]}`}>
      {status}
    </span>
  );
}

const JOB_STATE_LABEL: Record<JobState, string> = {
  pending: "Queued",
  crawling: "Crawling…",
  extracting: "Extracting…",
  extracted: "Extracted",
  generating: "Generating…",
  ready: "Ready",
  failed: "Failed",
};

export function JobStateBadge({
  state,
  failedStage,
}: {
  state: JobState;
  failedStage?: FailedStage | null;
}) {
  const cls =
    state === "ready"
      ? "bg-emerald-100 text-emerald-700"
      : state === "failed"
        ? "bg-rose-100 text-rose-700"
        : state === "extracted"
          ? "bg-sky-100 text-sky-700"
          : "bg-amber-100 text-amber-700";
  const label =
    state === "failed" && failedStage
      ? `Failed (${failedStage})`
      : JOB_STATE_LABEL[state];
  return <span className={`px-2 py-0.5 rounded text-xs ${cls}`}>{label}</span>;
}
