import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { interactions, type InterviewStage } from "../api/interactions";
import { applications } from "../api/applications";
import type { CalendarInterview } from "../api/calendar";
import { STAGE_LABEL } from "../lib/interviewSummary";

const STAGES: InterviewStage[] = ["phone_screen", "technical", "onsite", "hr", "final", "other"];

function utcIsoToLocalInput(iso: string): string {
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function localInputToUtcIso(localValue: string): string {
  return new Date(localValue).toISOString();
}

export function InterviewReviewModal({
  ev,
  open,
  onClose,
}: {
  ev: CalendarInterview;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [startsAt, setStartsAt] = useState(utcIsoToLocalInput(ev.starts_at));
  const [endsAt, setEndsAt] = useState(ev.ends_at ? utcIsoToLocalInput(ev.ends_at) : "");
  const [location, setLocation] = useState(ev.location ?? "");
  const [stage, setStage] = useState<InterviewStage>(ev.interview_stage ?? "other");
  const [appId, setAppId] = useState(ev.application_id);

  const appList = useQuery({
    queryKey: ["applications-min"],
    queryFn: () => applications.list(),
  });

  const save = useMutation({
    mutationFn: () =>
      interactions.update(ev.id, {
        occurred_at: localInputToUtcIso(startsAt),
        ends_at: endsAt ? localInputToUtcIso(endsAt) : null,
        location: location || null,
        interview_stage: stage,
        application_id: appId,
        needs_review: false,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calendar-interviews"] });
      qc.invalidateQueries({ queryKey: ["calendar-review-count"] });
      onClose();
    },
  });

  if (!open) return null;

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
        aria-label="Confirm interview"
        className="bg-surface rounded-lg p-4 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold mb-3">Confirm interview</h2>
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
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
