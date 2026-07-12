import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ActivityTimeline } from "./ActivityTimeline";
import { InteractionLogModal } from "./InteractionLogModal";
import { DeleteConfirmButton } from "./DeleteConfirmButton";
import { useToast } from "./Toast";
import { interactions, type Interaction, type Channel, type Direction } from "../api/interactions";
import type { Application } from "../api/applications";

type Tab = "timeline" | "interactions" | "notes";

export function ActivityPanel({
  appId, app, notes: _notes, onNotesBlur, notesValue, onNotesChange,
  logOpen, onCloseLog, onOpenLog, logPrefill,
}: {
  appId: string;
  app?: Application;
  notes: string | null;
  onNotesBlur: () => void;
  notesValue: string;
  onNotesChange: (v: string) => void;
  logOpen: boolean;
  onCloseLog: () => void;
  onOpenLog: (prefill?: { channel?: Channel; direction?: Direction }) => void;
  logPrefill?: { channel?: Channel; direction?: Direction };
}) {
  const [tab, setTab] = useState<Tab>("timeline");
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const toast = useToast();

  const ints = useQuery({
    queryKey: ["interactions", appId],
    queryFn: () => interactions.list(appId),
    enabled: tab === "interactions",
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["interactions", appId] });
    qc.invalidateQueries({ queryKey: ["application-timeline", appId] });
  };

  const undo = async (ids: string[]) => {
    await Promise.all(ids.map((id) => interactions.remove(id)));
    refresh();
  };

  const importEml = useMutation({
    mutationFn: (file: File) => interactions.importEml(appId, file),
    onSuccess: (resp) => {
      refresh();
      const ids = resp.interactions.map((it) => it.id);
      toast(`Imported ${resp.count} interaction${resp.count === 1 ? "" : "s"}`, {
        label: "Undo",
        onClick: () => undo(ids),
      });
    },
    onError: (err) => toast(`Import failed: ${(err as Error).message}`),
  });

  const del = useMutation({
    mutationFn: (it: Interaction) => interactions.remove(it.id),
    onSuccess: (_data, it) => {
      refresh();
      toast("Interaction deleted", {
        label: "Undo",
        onClick: async () => {
          await interactions.create(appId, {
            occurred_at: it.occurred_at,
            direction: it.direction,
            channel: it.channel,
            subject: it.subject,
            body: it.body,
            contact_name: it.contact_name,
            contact_handle: it.contact_handle,
            sentiment: it.sentiment,
          });
          refresh();
        },
      });
    },
    onError: (err) => toast(`Delete failed: ${(err as Error).message}`),
  });

  const onFiles = (files: FileList | null) => {
    const f = Array.from(files ?? []).find((x) => x.name.toLowerCase().endsWith(".eml"));
    if (f) importEml.mutate(f);
    else if (files && files.length) toast("Only .eml files are supported");
  };

  return (
    <div className="border border-border rounded bg-surface">
      <div className="border-b px-2 py-1 flex gap-2 items-center">
        {(["timeline", "interactions", "notes"] as Tab[]).map((t) => (
          <button key={t} type="button"
                  onClick={() => setTab(t)}
                  className={`px-2 py-1 text-sm ${tab === t ? "border-b-2 border-accent font-semibold" : "text-muted"}`}>
            {t}
          </button>
        ))}
        <button type="button"
                className="ml-auto bg-accent text-accentFg rounded px-2 py-1 text-xs"
                onClick={() => onOpenLog()}>
          + Log interaction
        </button>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); onFiles(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
        className={`mx-3 mt-3 border-2 border-dashed rounded p-3 text-center text-xs cursor-pointer ${
          dragging ? "border-accent bg-accent/20" : "border-border hover:bg-surface2"
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".eml"
          className="hidden"
          onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }}
        />
        <span className="text-muted">
          {importEml.isPending ? "Importing email…" : "Drop an .eml here, or click to import an email thread"}
        </span>
      </div>

      <div className="p-3">
        {tab === "timeline" && (
          <ActivityTimeline appId={appId} onDelete={(it) => del.mutate(it)} />
        )}
        {tab === "interactions" && (
          <ul className="divide-y">
            {(ints.data ?? []).map((it: Interaction) => (
              <li key={it.id} className="py-2 text-sm flex items-start gap-2">
                <div className="flex-1">
                  <span className="text-muted mr-2">
                    {it.direction === "out" ? "→" : "←"}
                  </span>
                  <span>{it.channel}</span>
                  {it.subject && <> — <strong>{it.subject}</strong></>}
                  <div className="text-xs text-muted">
                    {new Date(it.occurred_at).toLocaleString()}
                  </div>
                  {it.body && <div className="text-fg whitespace-pre-wrap">{it.body}</div>}
                </div>
                <DeleteConfirmButton
                  label="Delete interaction"
                  onConfirm={() => del.mutate(it)}
                />
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
      <InteractionLogModal appId={appId} app={app} open={logOpen} onClose={onCloseLog} prefill={logPrefill} />
    </div>
  );
}
