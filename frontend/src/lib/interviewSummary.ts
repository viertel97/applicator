import type { InterviewStage, InterviewSummary } from "../api/applications";

export const STAGE_LABEL: Record<InterviewStage, string> = {
  phone_screen: "Phone screen",
  technical: "Technical",
  onsite: "Onsite",
  hr: "HR",
  final: "Final",
  other: "Other",
};

// Locale intentionally undefined — formatted for the user's locale in the browser.
function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// Prefer the next upcoming interview; otherwise describe the latest past one.
export function formatInterviewSummary(summary: InterviewSummary): string {
  const ref = summary.next ?? summary.last;
  if (!ref) return "interview";
  const stage = ref.stage ? ` ${STAGE_LABEL[ref.stage]}` : "";
  const isUpcoming = summary.next !== null;
  const timing = isUpcoming ? ` · upcoming ${shortDate(ref.at)}` : " · done";
  return `interview · R${ref.round}${stage}${timing}`;
}
