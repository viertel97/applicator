import { useNavigate } from "react-router-dom";
import type { CalendarInterview } from "../../api/calendar";

const STAGE_COLOR: Record<string, string> = {
  phone_screen: "bg-blue-500",
  technical: "bg-violet-500",
  onsite: "bg-amber-500",
  hr: "bg-teal-500",
  final: "bg-emerald-600",
  other: "bg-slate-500",
};

export function InterviewChip({ ev }: { ev: CalendarInterview }) {
  const navigate = useNavigate();
  const time = new Date(ev.starts_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  const dot = STAGE_COLOR[ev.interview_stage ?? "other"] ?? "bg-slate-500";
  return (
    <button
      onClick={() => navigate(`/applications/${ev.application_id}`)}
      className={`w-full flex items-center gap-1 text-left text-xs px-1 py-0.5 rounded hover:bg-surface2 ${ev.needs_review ? "opacity-60" : ""}`}
      title={ev.needs_review ? "Needs review" : undefined}
    >
      <span aria-hidden="true" className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
      <span className="truncate">
        {time} {ev.company}
      </span>
      {ev.needs_review && (
        <span className="ml-auto text-[10px] text-amber-600">review</span>
      )}
    </button>
  );
}
