import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ActivityTimeline } from "./ActivityTimeline";
import { InteractionLogModal } from "./InteractionLogModal";
import { InterviewsList } from "./InterviewsList";
import { interactions, type Interaction } from "../api/interactions";

type Tab = "timeline" | "interactions" | "notes";

export function ActivityPanel({
  appId, notes: _notes, onNotesBlur, notesValue, onNotesChange,
}: {
  appId: string;
  notes: string | null;
  onNotesBlur: () => void;
  notesValue: string;
  onNotesChange: (v: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("timeline");
  const [showLog, setShowLog] = useState(false);
  const ints = useQuery({
    queryKey: ["interactions", appId],
    queryFn: () => interactions.list(appId),
    enabled: tab === "interactions",
  });

  return (
    <div className="border rounded bg-white">
      <div className="border-b px-2 py-1 flex gap-2 items-center">
        {(["timeline", "interactions", "notes"] as Tab[]).map((t) => (
          <button key={t} type="button"
                  onClick={() => setTab(t)}
                  className={`px-2 py-1 text-sm ${tab === t ? "border-b-2 border-blue-600 font-semibold" : "text-slate-600"}`}>
            {t}
          </button>
        ))}
        <button type="button"
                className="ml-auto bg-blue-600 text-white rounded px-2 py-1 text-xs"
                onClick={() => setShowLog(true)}>
          + Log interaction
        </button>
      </div>
      <div className="p-3">
        {tab === "timeline" && <ActivityTimeline appId={appId} />}
        {tab === "interactions" && (
          <ul className="divide-y">
            {(ints.data ?? []).map((it: Interaction) => (
              <li key={it.id} className="py-2 text-sm">
                <span className="text-slate-400 mr-2">
                  {it.direction === "out" ? "→" : "←"}
                </span>
                <span>{it.channel}</span>
                {it.subject && <> — <strong>{it.subject}</strong></>}
                <div className="text-xs text-slate-500">
                  {new Date(it.occurred_at).toLocaleString()}
                </div>
                {it.body && <div className="text-slate-700 whitespace-pre-wrap">{it.body}</div>}
              </li>
            ))}
          </ul>
        )}
        {tab === "notes" && (
          <textarea
            className="w-full border rounded px-2 py-1 text-sm resize-none"
            rows={6}
            placeholder="Long-form notes…"
            value={notesValue}
            onChange={(e) => onNotesChange(e.target.value)}
            onBlur={onNotesBlur}
          />
        )}
      </div>
      <InteractionLogModal appId={appId} open={showLog} onClose={() => setShowLog(false)} />
      <div className="border-t p-3">
        <InterviewsList appId={appId} />
      </div>
    </div>
  );
}
