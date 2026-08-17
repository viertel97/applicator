import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DeleteConfirmButton } from "./DeleteConfirmButton";
import { InterviewReviewModal } from "./InterviewReviewModal";
import { timeline, type Interaction, type TimelineRow } from "../api/interactions";
import { interactionIcon, interactionDescribe, eventDescribe } from "../lib/timelineRender";

function iconFor(row: TimelineRow) {
  if (row.kind === "interaction") return interactionIcon(row.data);
  return "•";
}

function describe(row: TimelineRow): string {
  if (row.kind === "interaction") return interactionDescribe(row.data);
  return eventDescribe(row.data);
}

export function ActivityTimeline({
  appId,
  onDelete,
}: {
  appId: string;
  onDelete?: (it: Interaction) => void;
}) {
  const [editing, setEditing] = useState<Interaction | null>(null);

  const q = useQuery({
    queryKey: ["application-timeline", appId],
    queryFn: () => timeline.get(appId),
  });
  if (!q.data) return <div className="text-sm text-muted">Loading…</div>;
  if (q.data.length === 0)
    return <div className="text-sm text-muted">No activity yet.</div>;
  return (
    <>
      <ul className="divide-y border rounded">
        {q.data.map((row) => (
          <li
            key={row.kind === "interaction" ? row.data.id : row.at}
            className="p-2 flex gap-3"
          >
            <span className="text-muted w-5 text-center">{iconFor(row)}</span>
            <div className="flex-1">
              <div className="text-sm">{describe(row)}</div>
              <div className="text-xs text-muted">
                {new Date(row.at).toLocaleString()}
              </div>
              {row.kind === "interaction" && row.data.body && (
                <div className="text-sm text-fg mt-1 whitespace-pre-wrap">
                  {row.data.body}
                </div>
              )}
            </div>
            {row.kind === "interaction" && row.data.channel === "interview" && (
              <button
                type="button"
                aria-label="Edit interview"
                className="text-xs text-muted hover:text-fg"
                onClick={() => setEditing(row.data)}
              >
                Edit
              </button>
            )}
            {row.kind === "interaction" && onDelete && (
              <DeleteConfirmButton
                label="Delete interaction"
                onConfirm={() => onDelete(row.data)}
              />
            )}
          </li>
        ))}
      </ul>
      {editing && (
        <InterviewReviewModal
          key={editing.id}
          mode="edit"
          open
          ev={{
            id: editing.id,
            application_id: editing.application_id,
            starts_at: editing.occurred_at,
            ends_at: editing.ends_at,
            location: editing.location,
            interview_stage: editing.interview_stage,
            subject: editing.subject,
            body: editing.body,
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}
