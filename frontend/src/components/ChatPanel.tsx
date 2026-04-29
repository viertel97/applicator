import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chat } from "../api/chat";

export function ChatPanel({ appId }: { appId: string }) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState("");
  const history = useQuery({
    queryKey: ["chat", appId],
    queryFn: () => chat.history(appId),
  });
  const m = useMutation({
    mutationFn: (text: string) => chat.refine(appId, text),
    onSuccess: () => {
      setMsg("");
      qc.invalidateQueries({ queryKey: ["chat", appId] });
      qc.invalidateQueries({ queryKey: ["application", appId] });
    },
  });
  return (
    <div className="border rounded bg-white p-3 mt-4">
      <div className="space-y-2 mb-3 max-h-64 overflow-y-auto">
        {(history.data ?? []).map((h) => (
          <div key={h.id} className={h.role === "user" ? "text-right" : ""}>
            <span
              className={`inline-block px-2 py-1 rounded ${
                h.role === "user" ? "bg-blue-100" : "bg-slate-100"
              }`}
            >
              {h.content}
            </span>
          </div>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (msg.trim()) m.mutate(msg.trim());
        }}
      >
        <input
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="Ask the assistant to refine the letter…"
          className="flex-1 border rounded px-3 py-2"
        />
        <button
          disabled={m.isPending}
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
