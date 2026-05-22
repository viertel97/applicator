import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";
import type { Application } from "../api/applications";

type Props = { app: Application };

function mailto(to: string | null, subject: string, body: string): string {
  const params = new URLSearchParams();
  params.set("subject", subject);
  params.set("body", body);
  return `mailto:${to ?? ""}?${params.toString()}`;
}

export function InquiryPanel({ app }: Props) {
  const qc = useQueryClient();
  const jp = app.job_posting;
  const ho = jp?.mentions_home_office_policy === true;
  const pt = jp?.mentions_part_time === true;
  const bothCovered = ho && pt;
  const pipelineReady = (["extracted", "ready"] as Application["job_state"][]).includes(app.job_state);
  const hasDraft = app.inquiry_subject != null || app.inquiry_body != null;

  const [subject, setSubject] = useState(app.inquiry_subject ?? "");
  const [body, setBody] = useState(app.inquiry_body ?? "");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!dirty) {
      setSubject(app.inquiry_subject ?? "");
      setBody(app.inquiry_body ?? "");
    }
  }, [app.inquiry_subject, app.inquiry_body, dirty]);

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["application", app.id] });

  const draft = useMutation({
    mutationFn: () => applications.draftInquiry(app.id),
    onSuccess: () => {
      setDirty(false);
      invalidate();
    },
  });
  const save = useMutation({
    mutationFn: () => applications.patchInquiry(app.id, { subject, body }),
    onSuccess: () => {
      setDirty(false);
      invalidate();
    },
  });
  const markSent = useMutation({
    mutationFn: () => applications.markInquirySent(app.id),
    onSuccess: invalidate,
  });

  if (!jp || !pipelineReady) {
    return (
      <div className="bg-white border rounded p-3 mt-4 text-slate-500 text-sm">
        Pre-application inquiry will appear after extraction.
      </div>
    );
  }

  if (bothCovered && !hasDraft) {
    return (
      <div className="bg-white border rounded p-3 mt-4 text-slate-500 text-sm">
        Posting covers home office and part-time — no inquiry needed.
      </div>
    );
  }

  const recipient = jp.contact?.email ?? null;
  const isSent = app.inquiry_sent_at != null;

  const onDraft = () => {
    if (hasDraft && !confirm("Overwrite the current draft?")) return;
    draft.mutate();
  };

  return (
    <div className="bg-white border rounded p-3 mt-4">
      <div className="flex items-center mb-2">
        <h2 className="font-semibold flex-1">Pre-application inquiry</h2>
        {app.inquiry_sent_at && (
          <span className="text-xs bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded">
            Sent {new Date(app.inquiry_sent_at).toLocaleDateString()}
          </span>
        )}
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
            readOnly={isSent}
            onChange={(e) => {
              setSubject(e.target.value);
              setDirty(true);
            }}
          />
          <label className="block text-xs uppercase text-slate-500 mt-2">Body</label>
          <textarea
            className="border rounded px-2 py-1 w-full font-mono text-sm"
            rows={10}
            value={body}
            readOnly={isSent}
            onChange={(e) => {
              setBody(e.target.value);
              setDirty(true);
            }}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
              disabled={isSent || !dirty || save.isPending}
              onClick={() => save.mutate()}
            >
              Save
            </button>
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
              disabled={markSent.isPending}
              onClick={() => markSent.mutate()}
            >
              Mark sent
            </button>
            <button
              type="button"
              className="bg-slate-200 text-slate-800 px-3 py-1 rounded disabled:opacity-50"
              disabled={isSent || draft.isPending}
              onClick={onDraft}
            >
              Regenerate
            </button>
          </div>
          {(save.isError || draft.isError || markSent.isError) && (
            <div className="text-rose-600 text-sm mt-2">
              {((save.error || draft.error || markSent.error) as Error)?.toString()}
            </div>
          )}
        </>
      )}
    </div>
  );
}
