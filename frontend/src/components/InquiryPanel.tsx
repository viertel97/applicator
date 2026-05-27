import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";
import type { Application } from "../api/applications";

type Props = { app: Application };

function mailto(to: string | null, subject: string, body: string): string {
  // normalize literal \n (2 chars) → real newline, then use CRLF per RFC 6068
  const normalized = body.replace(/\\n/g, "\n");
  const crlfBody = normalized.replace(/\r?\n/g, "\r\n");
  return `mailto:${to ?? ""}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(crlfBody)}`;
}

export function InquiryPanel({ app }: Props) {
  const qc = useQueryClient();
  const jp = app.job_posting;
  const pipelineReady = (["extracted", "ready"] as Application["job_state"][]).includes(app.job_state);

  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [hasDraft, setHasDraft] = useState(false);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["application", app.id] });
    qc.invalidateQueries({ queryKey: ["application-timeline", app.id] });
  };

  const draft = useMutation({
    mutationFn: () => applications.draftInquiry(app.id),
    onSuccess: (data) => {
      setSubject(data.subject);
      setBody(data.body);
      setHasDraft(true);
    },
  });
  const send = useMutation({
    mutationFn: () => applications.sendInquiry(app.id, subject, body),
    onSuccess: () => {
      setHasDraft(false);
      setSubject("");
      setBody("");
      invalidate();
    },
  });

  if (!jp || !pipelineReady) {
    return (
      <div className="bg-white border rounded p-3 mt-4 text-slate-500 text-sm">
        Pre-application inquiry will appear after extraction.
      </div>
    );
  }

  const recipient = jp.contact?.email ?? null;

  const onDraft = () => {
    if (hasDraft && !confirm("Overwrite the current draft?")) return;
    draft.mutate();
  };

  return (
    <div className="bg-white border rounded p-3 mt-4">
      <div className="flex items-center mb-2">
        <h2 className="font-semibold flex-1">Pre-application inquiry</h2>
      </div>

      {!hasDraft ? (
        <button
          type="button"
          className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
          disabled={draft.isPending}
          onClick={onDraft}
        >
          Draft inquiry
        </button>
      ) : (
        <>
          <label className="block text-xs uppercase text-slate-500 mt-1">Subject</label>
          <input
            className="border rounded px-2 py-1 w-full"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <label className="block text-xs uppercase text-slate-500 mt-2">Body</label>
          <textarea
            className="border rounded px-2 py-1 w-full font-mono text-sm"
            rows={10}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <a
              href={mailto(recipient, subject, body)}
              className={`px-3 py-1 rounded border ${
                recipient ? "border-blue-600 text-blue-700" : "border-slate-300 text-slate-400 pointer-events-none"
              }`}
              title={recipient ? "" : "No recipient on file"}
            >
              Open in mail
            </a>
            <button
              type="button"
              className="bg-emerald-600 text-white px-3 py-1 rounded disabled:opacity-50"
              disabled={send.isPending || !subject.trim() || !body.trim()}
              onClick={() => send.mutate()}
            >
              Send
            </button>
            <button
              type="button"
              className="bg-slate-200 text-slate-800 px-3 py-1 rounded disabled:opacity-50"
              disabled={draft.isPending}
              onClick={onDraft}
            >
              Regenerate
            </button>
          </div>
          {(draft.isError || send.isError) && (
            <div className="text-rose-600 text-sm mt-2">
              {((draft.error || send.error) as Error)?.toString()}
            </div>
          )}
        </>
      )}
    </div>
  );
}
