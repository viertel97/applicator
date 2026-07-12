import type { AppStatus, FailedStage, InterviewSummary, JobState } from "../api/applications";
import { formatInterviewSummary } from "../lib/interviewSummary";

const STATUS_CLASS: Record<AppStatus, string> = {
  draft: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
  applied: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200",
  offer: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200",
  rejected: "bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-200",
  accepted: "bg-green-200 text-green-800 dark:bg-green-900 dark:text-green-200",
  withdrawn: "bg-slate-300 text-slate-600 dark:bg-slate-600 dark:text-slate-200",
  discarded: "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-200",
  need_call: "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-200",
  apply_direct: "bg-teal-100 text-teal-700 dark:bg-teal-900 dark:text-teal-200",
  interview: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200",
};

// Hex equivalents of STATUS_CLASS, for native <option> styling (Tailwind classes don't apply there).
export const STATUS_HEX: Record<AppStatus, { bg: string; text: string }> = {
  draft: { bg: "#e2e8f0", text: "#334155" },
  applied: { bg: "#dbeafe", text: "#1d4ed8" },
  offer: { bg: "#d1fae5", text: "#047857" },
  rejected: { bg: "#ffe4e6", text: "#be123c" },
  accepted: { bg: "#bbf7d0", text: "#166534" },
  withdrawn: { bg: "#cbd5e1", text: "#475569" },
  discarded: { bg: "#ffedd5", text: "#c2410c" },
  need_call: { bg: "#f3e8ff", text: "#7e22ce" },
  apply_direct: { bg: "#ccfbf1", text: "#0f766e" },
  interview: { bg: "#e0e7ff", text: "#4338ca" },
};

export function StatusBadge({
  status,
  title,
  summary,
}: {
  status: AppStatus;
  title?: string;
  summary?: InterviewSummary | null;
}) {
  const label =
    status === "interview" && summary ? formatInterviewSummary(summary) : status;
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_CLASS[status]}`}
      title={title}
    >
      {label}
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
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200"
      : state === "failed"
        ? "bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-200"
        : state === "extracted"
          ? "bg-sky-100 text-sky-700 dark:bg-sky-900 dark:text-sky-200"
          : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200";
  const label =
    state === "failed" && failedStage
      ? `Failed (${failedStage})`
      : JOB_STATE_LABEL[state];
  return <span className={`px-2 py-0.5 rounded text-xs ${cls}`}>{label}</span>;
}

export function OnlineBadge({ online }: { online: boolean | null }) {
  if (online === null || online === undefined) return null;
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
        online
          ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200"
          : "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200"
      }`}
    >
      {online ? "Online" : "Offline"}
    </span>
  );
}
