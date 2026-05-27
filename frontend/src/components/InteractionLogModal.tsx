import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  interactions, type CreateInteractionInput, type Channel, type Direction, type Sentiment,
} from "../api/interactions";
import { applications, type DiscardPayload } from "../api/applications";
import { DiscardReasonPicker } from "./DiscardReasonPicker";

type Props = {
  appId: string;
  open: boolean;
  onClose: () => void;
};

const CHANNELS: Channel[] = ["mail", "linkedin", "phone", "portal", "xing", "other"];

export function InteractionLogModal({ appId, open, onClose }: Props) {
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

  const create = useMutation({
    mutationFn: (payload: CreateInteractionInput) =>
      interactions.create(appId, payload),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["application-timeline", appId] });
      qc.invalidateQueries({ queryKey: ["interactions", appId] });
      if (r.suggest_discard) {
        setPendingDiscardIid(r.suggest_discard.interaction_id);
        setShowDiscard(true);
      } else {
        reset();
        onClose();
      }
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
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded shadow-lg p-4 w-[520px] max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-semibold mb-3">Log interaction</h2>
        {!showDiscard ? (
          <>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <select value={direction} onChange={(e) => setDirection(e.target.value as Direction)}
                      className="border rounded px-2 py-1 text-sm">
                <option value="out">Outgoing</option>
                <option value="in">Incoming</option>
              </select>
              <select value={channel} onChange={(e) => setChannel(e.target.value as Channel)}
                      className="border rounded px-2 py-1 text-sm">
                {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <input type="datetime-local" value={occurredAt}
                   onChange={(e) => setOccurredAt(e.target.value)}
                   className="border rounded px-2 py-1 text-sm w-full mb-2" />
            <div className="grid grid-cols-2 gap-2 mb-2">
              <input placeholder="Contact name" value={contactName}
                     onChange={(e) => setContactName(e.target.value)}
                     className="border rounded px-2 py-1 text-sm" />
              <input placeholder="email / URL / phone" value={contactHandle}
                     onChange={(e) => setContactHandle(e.target.value)}
                     className="border rounded px-2 py-1 text-sm" />
            </div>
            {channel === "mail" && (
              <input placeholder="Subject" value={subject}
                     onChange={(e) => setSubject(e.target.value)}
                     className="border rounded px-2 py-1 text-sm w-full mb-2" />
            )}
            <textarea placeholder="Body" value={body}
                      onChange={(e) => setBody(e.target.value)} rows={5}
                      className="border rounded px-2 py-1 text-sm w-full mb-2" />
            {direction === "in" && (
              <select value={sentiment ?? ""}
                      onChange={(e) => setSentiment((e.target.value || null) as Sentiment)}
                      className="border rounded px-2 py-1 text-sm w-full mb-2">
                <option value="">No sentiment</option>
                <option value="positive">positive</option>
                <option value="neutral">neutral</option>
                <option value="negative">negative</option>
                <option value="rejection">rejection</option>
              </select>
            )}
            <div className="flex justify-end gap-2 mt-3">
              <button type="button" onClick={onClose}
                      className="border rounded px-3 py-1 text-sm">Cancel</button>
              <button type="button" disabled={create.isPending}
                      onClick={() => create.mutate({
                        direction, channel, subject: subject || null, body: body || null,
                        contact_name: contactName || null, contact_handle: contactHandle || null,
                        sentiment, occurred_at: new Date(occurredAt).toISOString(),
                      })}
                      className="bg-blue-600 text-white rounded px-3 py-1 text-sm disabled:opacity-50">
                Save
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-700 mb-2">
              This was a rejection. Discard the application?
            </p>
            <div className="mb-2">
              <label className="text-xs uppercase text-slate-500">Reason</label>
              <DiscardReasonPicker value={reasonId} onChange={(id) => setReasonId(id)} />
            </div>
            <textarea placeholder="Optional note" value={discardNote}
                      onChange={(e) => setDiscardNote(e.target.value)} rows={2}
                      className="border rounded px-2 py-1 text-sm w-full mb-2" />
            <div className="flex justify-end gap-2">
              <button type="button"
                      onClick={() => { reset(); onClose(); }}
                      className="border rounded px-3 py-1 text-sm">Skip</button>
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
