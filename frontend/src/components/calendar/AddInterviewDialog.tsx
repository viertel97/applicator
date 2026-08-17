import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { applications } from "../../api/applications";
import { interactions } from "../../api/interactions";
import {
  isActiveApplication,
  applicationLabel,
  buildOccurredAtISO,
} from "../../lib/addInterview";

type Props = {
  day: Date;
  onClose: () => void;
};

export function AddInterviewDialog({ day, onClose }: Props) {
  const qc = useQueryClient();
  const [selectedAppId, setSelectedAppId] = useState("");
  const [time, setTime] = useState("09:00");
  const [mutationError, setMutationError] = useState<string | null>(null);

  const heading =
    "Add interview · " +
    day.toLocaleDateString(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short",
    });

  const appsQuery = useQuery({
    queryKey: ["applications"],
    queryFn: () => applications.list(),
  });

  const create = useMutation({
    mutationFn: ({ appId, occurred_at }: { appId: string; occurred_at: string }) =>
      interactions.create(appId, {
        channel: "interview",
        direction: "in",
        occurred_at,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calendar-interviews"] });
      onClose();
    },
    onError: (err: unknown) => {
      setMutationError(
        err instanceof Error ? err.message : "Failed to save interview."
      );
    },
  });

  const activeApps = appsQuery.data
    ? appsQuery.data
        .filter(isActiveApplication)
        .sort((a, b) =>
          applicationLabel(a).localeCompare(applicationLabel(b))
        )
    : [];

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Add interview"
        className="bg-surface border border-border rounded shadow-lg p-4 w-[420px] max-h-[90vh] overflow-y-auto"
      >
        <h2 className="text-lg font-semibold mb-3">{heading}</h2>

        {appsQuery.isLoading && (
          <p className="text-sm text-muted mb-2">Loading applications…</p>
        )}

        {appsQuery.isError && (
          <p className="text-rose-600 text-xs mb-2">
            Failed to load applications.
          </p>
        )}

        {appsQuery.isSuccess && activeApps.length === 0 && (
          <p className="text-sm text-muted mb-2">
            No active applications to schedule an interview for.
          </p>
        )}

        {appsQuery.isSuccess && activeApps.length > 0 && (
          <>
            <label htmlFor="add-interview-job" className="text-xs uppercase text-muted">Job</label>
            <select
              id="add-interview-job"
              value={selectedAppId}
              onChange={(e) => setSelectedAppId(e.target.value)}
              className="border border-border rounded px-2 py-1 text-sm w-full mb-2 bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Select a job…</option>
              {activeApps.map((app) => (
                <option key={app.id} value={app.id}>
                  {applicationLabel(app)}
                </option>
              ))}
            </select>

            <label htmlFor="add-interview-time" className="text-xs uppercase text-muted">Time</label>
            <input
              id="add-interview-time"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="border border-border rounded px-2 py-1 text-sm w-full mb-2 bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </>
        )}

        {mutationError && (
          <p className="text-rose-600 text-xs mb-2">{mutationError}</p>
        )}

        <div className="flex justify-end gap-2 mt-3">
          <button
            type="button"
            onClick={onClose}
            className="border border-border rounded px-3 py-1 text-sm text-fg"
          >
            Cancel
          </button>
          {appsQuery.isSuccess && activeApps.length > 0 && (
            <button
              type="button"
              disabled={!selectedAppId || !time || create.isPending}
              onClick={() => {
                setMutationError(null);
                create.mutate({
                  appId: selectedAppId,
                  occurred_at: buildOccurredAtISO(day, time),
                });
              }}
              className="bg-accent text-accentFg rounded px-3 py-1 text-sm disabled:opacity-50"
            >
              Save
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
