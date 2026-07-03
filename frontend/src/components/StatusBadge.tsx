import type { AppStatus, FailedStage, JobState } from "../api/applications";

const STATUS_CLASS: Record<AppStatus, string> = {
  draft: "bg-slate-200 text-slate-700",
  applied: "bg-blue-100 text-blue-700",
  offer: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
  accepted: "bg-green-200 text-green-800",
  withdrawn: "bg-slate-300 text-slate-600",
  discarded: "bg-orange-100 text-orange-700",
  need_call: "bg-purple-100 text-purple-700",
  apply_direct: "bg-teal-100 text-teal-700",
  interview: "bg-indigo-100 text-indigo-700",
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

export function StatusBadge({ status, title }: { status: AppStatus; title?: string }) {
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_CLASS[status]}`}
      title={title}
    >
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

export function OnlineBadge({ online }: { online: boolean | null }) {
  if (online === null || online === undefined) return null;
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
        online ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
      }`}
    >
      {online ? "Online" : "Offline"}
    </span>
  );
}
