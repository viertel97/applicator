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
    <div className="border border-border rounded bg-surface p-3 mt-4">
      <div className="space-y-2 mb-3 max-h-64 overflow-y-auto">
        {(history.data ?? []).map((h) => (
          <div key={h.id} className={h.role === "user" ? "text-right" : ""}>
            <span
              className={`inline-block px-2 py-1 rounded ${
                h.role === "user" ? "bg-accent/20 text-fg dark:bg-accent/30" : "bg-surface2 text-fg"
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
          className="flex-1 border border-border rounded px-3 py-2 bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          disabled={m.isPending}
          className="bg-accent text-accentFg px-4 py-2 rounded disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
