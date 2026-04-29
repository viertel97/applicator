import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { interviews } from "../api/interviews";
import type { Interview, InterviewKind, InterviewOutcome } from "../api/interviews";

const KINDS: InterviewKind[] = ["phone", "video", "onsite", "technical", "final"];
const OUTCOMES: InterviewOutcome[] = ["pending", "passed", "failed", "cancelled"];

export function InterviewsList({ appId }: { appId: string }) {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["interviews", appId],
    queryFn: () => interviews.list(appId),
  });
  const [when, setWhen] = useState("");
  const [kind, setKind] = useState<InterviewKind>("phone");
  const create = useMutation({
    mutationFn: () => interviews.create(appId, when, kind),
    onSuccess: () => {
      setWhen("");
      qc.invalidateQueries({ queryKey: ["interviews", appId] });
    },
  });
  const update = useMutation({
    mutationFn: (args: { id: string; outcome: InterviewOutcome }) =>
      interviews.update(args.id, { outcome: args.outcome }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["interviews", appId] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => interviews.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["interviews", appId] }),
  });
  return (
    <div className="border rounded bg-white p-3 mt-4">
      <h3 className="font-medium mb-2">Interviews</h3>
      <div className="flex gap-2 mb-3">
        <input
          type="datetime-local"
          value={when}
          onChange={(e) => setWhen(e.target.value)}
          className="border rounded px-2 py-1"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as InterviewKind)}
          className="border rounded px-2 py-1"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <button
          onClick={() => when && create.mutate()}
          className="bg-blue-600 text-white px-3 py-1 rounded"
        >
          Add
        </button>
      </div>
      <ul className="space-y-1">
        {(list.data ?? []).map((iv: Interview) => (
          <li key={iv.id} className="flex items-center gap-2">
            <span className="flex-1">
              {new Date(iv.scheduled_at).toLocaleString()} — {iv.kind}
            </span>
            <select
              value={iv.outcome}
              onChange={(e) =>
                update.mutate({ id: iv.id, outcome: e.target.value as InterviewOutcome })
              }
              className="border rounded px-1 py-0.5"
            >
              {OUTCOMES.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <button
              onClick={() => remove.mutate(iv.id)}
              className="text-rose-600 text-sm"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
