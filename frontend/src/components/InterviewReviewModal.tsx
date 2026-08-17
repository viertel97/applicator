import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { interactions, type InterviewStage } from "../api/interactions";
import { applications } from "../api/applications";
import { STAGE_LABEL } from "../lib/interviewSummary";
import { detectMeetingUrl } from "../lib/detectMeetingUrl";

const STAGES: InterviewStage[] = ["phone_screen", "technical", "onsite", "hr", "final", "other"];

function utcIsoToLocalInput(iso: string): string {
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function localInputToUtcIso(localValue: string): string {
  return new Date(localValue).toISOString();
}

export type InterviewModalData = {
  id: string;
  application_id: string;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  interview_stage: InterviewStage | null;
  subject?: string | null;
  body?: string | null;
};

export function InterviewReviewModal({
  ev,
  open,
  onClose,
  mode = "review",
}: {
  ev: InterviewModalData;
  open: boolean;
  onClose: () => void;
  mode?: "review" | "edit";
}) {
  const qc = useQueryClient();
  const [startsAt, setStartsAt] = useState(utcIsoToLocalInput(ev.starts_at));
  const [endsAt, setEndsAt] = useState(ev.ends_at ? utcIsoToLocalInput(ev.ends_at) : "");
  const [location, setLocation] = useState(ev.location ?? "");
  const [stage, setStage] = useState<InterviewStage>(ev.interview_stage ?? "other");
  const [appId, setAppId] = useState(ev.application_id);
  const [body, setBody] = useState(ev.body ?? "");

  const appList = useQuery({
    queryKey: ["applications-min"],
    queryFn: () => applications.list(),
    enabled: mode === "review",
  });

  const save = useMutation({
    mutationFn: () => {
      const loc = location.trim() || detectMeetingUrl(body) || null;

      const patch: Parameters<typeof interactions.update>[1] = {
        occurred_at: localInputToUtcIso(startsAt),
        ends_at: endsAt ? localInputToUtcIso(endsAt) : null,
        location: loc,
        interview_stage: stage,
        body: body || null,
        // subject has no edit field here; preserve the existing value when present
        // (CalendarInterview lacks subject → omit), never wipe it.
        ...(ev.subject !== undefined ? { subject: ev.subject } : {}),
        ...(mode === "review"
          ? { application_id: appId, needs_review: false }
          : {}),
      };

      return interactions.update(ev.id, patch);
    },
    onSuccess: () => {
      if (mode === "review") {
        qc.invalidateQueries({ queryKey: ["calendar-interviews"] });
        qc.invalidateQueries({ queryKey: ["calendar-review-count"] });
      } else {
        qc.invalidateQueries({ queryKey: ["application-timeline", ev.application_id] });
        qc.invalidateQueries({ queryKey: ["interactions", ev.application_id] });
      }
      onClose();
    },
  });

  if (!open) return null;

  const headerText = mode === "review" ? "Confirm interview" : "Edit interview";
  const confirmLabel = mode === "review" ? "Confirm" : "Save";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      tabIndex={-1}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={headerText}
        className="bg-surface rounded-lg p-4 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold mb-3">{headerText}</h2>
        <label className="block text-xs mb-2">
          Starts
          <input
            type="datetime-local"
            value={startsAt}
            onChange={(e) => setStartsAt(e.target.value)}
            className="w-full px-2 py-1 rounded border border-border bg-bg"
          />
        </label>
        <label className="block text-xs mb-2">
          Ends
          <input
            type="datetime-local"
            value={endsAt}
            onChange={(e) => setEndsAt(e.target.value)}
            className="w-full px-2 py-1 rounded border border-border bg-bg"
          />
        </label>
        <label className="block text-xs mb-2">
          Location
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="w-full px-2 py-1 rounded border border-border bg-bg"
          />
        </label>
        <label className="block text-xs mb-2">
          Description
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={4}
            className="w-full px-2 py-1 rounded border border-border bg-bg resize-y"
          />
        </label>
        <label className="block text-xs mb-2">
          Stage
          <select
            value={stage}
            onChange={(e) => setStage(e.target.value as InterviewStage)}
            className="w-full px-2 py-1 rounded border border-border bg-bg"
          >
            {STAGES.map((s) => (
              <option key={s} value={s}>
                {STAGE_LABEL[s] ?? s}
              </option>
            ))}
          </select>
        </label>
        {mode === "review" && (
          <label className="block text-xs mb-3">
            Application
            <select
              value={appId}
              onChange={(e) => setAppId(e.target.value)}
              disabled={appList.isPending}
              className="w-full px-2 py-1 rounded border border-border bg-bg"
            >
              {appList.isPending && <option value={appId}>Loading…</option>}
              {(appList.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  #{a.display_id} {a.job_posting?.company ?? a.url}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="flex gap-2 justify-end">
          {save.isError && (
            <p className="text-xs text-red-600 mr-auto self-center">Failed to save. Try again.</p>
          )}
          <button onClick={onClose} className="px-3 py-1 rounded text-sm">
            Cancel
          </button>
          <button
            onClick={() => save.mutate()}
            disabled={save.isPending}
            className="px-3 py-1 rounded bg-accent text-accentFg text-sm"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
