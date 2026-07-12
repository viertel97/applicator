import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  interactions, type CreateInteractionInput, type Channel, type Direction, type Sentiment,
} from "../api/interactions";
import { applications, type Application, type DiscardPayload } from "../api/applications";
import { DiscardReasonPicker } from "./DiscardReasonPicker";

type Props = {
  appId: string;
  open: boolean;
  onClose: () => void;
  app?: Application;
  prefill?: { channel?: Channel; direction?: Direction };
};

const CHANNELS: Channel[] = ["mail", "linkedin", "phone", "portal", "xing", "interview", "other"];

function mailto(to: string | null, subject: string, body: string): string {
  const normalized = body.replace(/\\n/g, "\n");
  const crlfBody = normalized.replace(/\r?\n/g, "\r\n");
  return `mailto:${to ?? ""}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(crlfBody)}`;
}

export function InteractionLogModal({ appId, open, onClose, app, prefill }: Props) {
  const qc = useQueryClient();
  const [direction, setDirection] = useState<Direction>("out");
  const [channel, setChannel] = useState<Channel>("mail");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactHandle, setContactHandle] = useState("");
  const [sentiment, setSentiment] = useState<Sentiment>(null);
  const [occurredAt, setOccurredAt] = useState(() =>
    new Date().toISOString().slice(0, 16)
  );

  const [showDiscard, setShowDiscard] = useState(false);
  const [reasonId, setReasonId] = useState<string | null>(null);
  const [discardNote, setDiscardNote] = useState("");
  const [pendingDiscardIid, setPendingDiscardIid] = useState<string | null>(null);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open) return;
    setChannel(prefill?.channel ?? "mail");
    setDirection(prefill?.direction ?? "out");
  }, [open]);

  const create = useMutation({
    mutationFn: (payload: CreateInteractionInput) =>
      interactions.create(appId, payload),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["application-timeline", appId] });
      qc.invalidateQueries({ queryKey: ["interactions", appId] });
      const email = contactHandle.trim();
      if (channel === "mail" && direction === "out" && email && app?.job_posting) {
        saveContactEmail.mutate(email);
      }
      if (r.suggest_discard) {
        setPendingDiscardIid(r.suggest_discard.interaction_id);
        setShowDiscard(true);
      } else {
        reset();
        onClose();
      }
    },
  });

  const draft = useMutation({
    mutationFn: () => applications.draftInquiry(appId),
    onSuccess: (data) => {
      setSubject(data.subject);
      setBody(data.body);
      if (data.recipient) setContactHandle(data.recipient);
      const cname = app?.job_posting?.contact?.name;
      if (cname) setContactName(cname);
    },
  });

  const saveContactEmail = useMutation({
    mutationFn: (email: string) => {
      const cur = app?.job_posting?.contact ?? {
        name: null, role: null, email: null, phone: null,
      };
      return applications.patchJobPosting(appId, { contact: { ...cur, email } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", appId] });
    },
  });

  const discardApp = useMutation({
    mutationFn: (payload: DiscardPayload) => applications.setStatus(appId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", appId] });
      reset();
      onClose();
    },
  });

  function reset() {
    setSubject(""); setBody(""); setContactName(""); setContactHandle("");
    setSentiment(null); setShowDiscard(false); setReasonId(null);
    setDiscardNote(""); setPendingDiscardIid(null);
  }

  if (!open) return null;
  const pipelineReady =
    app != null &&
    (app.job_state === "extracted" || app.job_state === "ready") &&
    app.job_posting != null;
  const recipient =
    contactHandle.trim() || (app?.job_posting?.contact?.email ?? null);
  const canDraft =
    channel === "mail" && direction === "out" && pipelineReady;
  const showMailActions = channel === "mail" && direction === "out";
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-surface border border-border rounded shadow-lg p-4 w-[520px] max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-semibold mb-3">Log interaction</h2>
        {!showDiscard ? (
          <>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <select value={direction} onChange={(e) => setDirection(e.target.value as Direction)}
                      className="border border-border rounded px-2 py-1 text-sm bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring">
                <option value="out">Outgoing</option>
                <option value="in">Incoming</option>
              </select>
              <select value={channel} onChange={(e) => setChannel(e.target.value as Channel)}
                      className="border border-border rounded px-2 py-1 text-sm bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring">
                {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <input type="datetime-local" value={occurredAt}
                   onChange={(e) => setOccurredAt(e.target.value)}
                   className="border border-border rounded px-2 py-1 text-sm w-full mb-2 bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring" />
            <div className="grid grid-cols-2 gap-2 mb-2">
              <input placeholder="Contact name" value={contactName}
                     onChange={(e) => setContactName(e.target.value)}
                     className="border border-border rounded px-2 py-1 text-sm bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring" />
              <input placeholder="email / URL / phone" value={contactHandle}
                     onChange={(e) => setContactHandle(e.target.value)}
                     className="border border-border rounded px-2 py-1 text-sm bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring" />
            </div>
            {(channel === "mail" || channel === "interview") && (
              <input
                placeholder={channel === "interview" ? "Round / type (e.g. Technical screen)" : "Subject"}
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="border border-border rounded px-2 py-1 text-sm w-full mb-2 bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring"
              />
            )}
            <textarea
              placeholder={channel === "interview" ? "Comment (how it went, notes)" : "Body"}
              value={body}
              onChange={(e) => setBody(e.target.value)} rows={5}
              className="border border-border rounded px-2 py-1 text-sm w-full mb-2 bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring" />
            {direction === "in" && (
              <select value={sentiment ?? ""}
                      onChange={(e) => setSentiment((e.target.value || null) as Sentiment)}
                      className="border border-border rounded px-2 py-1 text-sm w-full mb-2 bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring">
                <option value="">No sentiment</option>
                <option value="positive">positive</option>
                <option value="neutral">neutral</option>
                <option value="negative">negative</option>
                <option value="rejection">rejection</option>
              </select>
            )}
            {showMailActions && (
              <div className="flex flex-wrap gap-2 mb-3 border-t pt-3">
                <button
                  type="button"
                  disabled={!canDraft || draft.isPending}
                  onClick={() => {
                    if ((subject || body) && !confirm("Overwrite current draft?")) return;
                    draft.mutate();
                  }}
                  title={canDraft ? "Generate inquiry via LLM" : "Available after extraction"}
                  className="bg-violet-600 text-white rounded px-3 py-1 text-sm disabled:opacity-50">
                  {draft.isPending ? "Drafting…" : "Draft inquiry"}
                </button>
                <a
                  href={mailto(recipient, subject, body)}
                  className={`px-3 py-1 rounded border text-sm ${
                    recipient ? "border-accent text-accent" : "border-border text-muted pointer-events-none"
                  }`}
                  title={recipient ? "" : "No recipient on file"}>
                  Open in mail
                </a>
                {draft.isError && (
                  <span className="text-rose-600 text-xs self-center">
                    {(draft.error as Error)?.toString()}
                  </span>
                )}
                {saveContactEmail.isError && (
                  <span className="text-amber-600 text-xs self-center">
                    saved interaction; contact not updated
                  </span>
                )}
              </div>
            )}
            <div className="flex justify-end gap-2 mt-3">
              <button type="button" onClick={onClose}
                      className="border border-border rounded px-3 py-1 text-sm text-fg">Cancel</button>
              <button type="button" disabled={create.isPending}
                      onClick={() => create.mutate({
                        direction, channel, subject: subject || null, body: body || null,
                        contact_name: contactName || null, contact_handle: contactHandle || null,
                        sentiment, occurred_at: new Date(occurredAt).toISOString(),
                      })}
                      className="bg-accent text-accentFg rounded px-3 py-1 text-sm disabled:opacity-50">
                Save
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-fg mb-2">
              This was a rejection. Discard the application?
            </p>
            <div className="mb-2">
              <label className="text-xs uppercase text-muted">Reason</label>
              <DiscardReasonPicker value={reasonId} onChange={(id) => setReasonId(id)} />
            </div>
            <textarea placeholder="Optional note" value={discardNote}
                      onChange={(e) => setDiscardNote(e.target.value)} rows={2}
                      className="border border-border rounded px-2 py-1 text-sm w-full mb-2 bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring" />
            <div className="flex justify-end gap-2">
              <button type="button"
                      onClick={() => { reset(); onClose(); }}
                      className="border border-border rounded px-3 py-1 text-sm text-fg">Skip</button>
              <button type="button" disabled={discardApp.isPending}
                      onClick={() => discardApp.mutate({
                        status: "discarded",
                        discard_reason_id: reasonId ?? undefined,
                        discard_interaction_id: pendingDiscardIid ?? undefined,
                        discard_note: discardNote || undefined,
                      })}
                      className="bg-orange-600 text-white rounded px-3 py-1 text-sm disabled:opacity-50">
                Discard app
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
