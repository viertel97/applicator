import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applications, type Suggestion } from "../api/applications";
import { suggestionReasonLabel } from "../lib/suggestionReason";
import { useToast } from "../components/Toast";
import { DiscardReasonPicker } from "../components/DiscardReasonPicker";

function checkedLabel(iso: string | null): string {
  if (!iso) return "noch nicht geprüft";
  return `zuletzt geprüft ${new Date(iso).toLocaleString()}`;
}

function SuggestionRow({ s }: { s: Suggestion }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [discarding, setDiscarding] = useState(false);
  const [reasonId, setReasonId] = useState<string | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["suggestions"] });
    qc.invalidateQueries({ queryKey: ["applications"] });
  };

  const dismiss = useMutation({
    mutationFn: () => applications.dismissOffline(s.id),
    onSuccess: () => {
      invalidate();
      toast("Vorschlag ausgeblendet");
    },
  });

  const discard = useMutation({
    mutationFn: () =>
      applications.setStatus(s.id, {
        status: "discarded",
        ...(reasonId ? { discard_reason_id: reasonId } : {}),
      }),
    onSuccess: () => {
      invalidate();
      toast("Bewerbung verworfen");
    },
  });

  const busy = dismiss.isPending || discard.isPending;

  return (
    <li className="border border-border rounded-lg p-4 bg-surface flex flex-col gap-2">
      <div className="flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-fg truncate">
            {s.title ?? "(ohne Titel)"}
            {s.company && <span className="text-muted font-normal"> · {s.company}</span>}
          </div>
          <a
            href={s.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-accent hover:underline break-all"
          >
            {s.url} ↗
          </a>
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200">
          {suggestionReasonLabel(s.posting_offline_reason)}
        </span>
      </div>
      <div className="text-xs text-muted">{checkedLabel(s.posting_checked_at)}</div>

      {discarding ? (
        <div className="flex items-center gap-2 flex-wrap">
          <DiscardReasonPicker value={reasonId} onChange={(id) => setReasonId(id)} />
          <button
            type="button"
            className="bg-orange-600 text-white rounded px-3 py-1 text-sm disabled:opacity-50"
            disabled={busy}
            onClick={() => discard.mutate()}
          >
            Verwerfen bestätigen
          </button>
          <button
            type="button"
            className="border border-border rounded px-2 py-1 text-sm text-muted"
            onClick={() => setDiscarding(false)}
          >
            Abbrechen
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            to={`/applications/${s.id}`}
            className="border border-border rounded px-3 py-1 text-sm text-fg hover:bg-surface2"
          >
            Öffnen
          </Link>
          <button
            type="button"
            className="text-orange-600 border border-orange-300 rounded px-3 py-1 text-sm disabled:opacity-50"
            disabled={busy}
            onClick={() => setDiscarding(true)}
          >
            Verwerfen…
          </button>
          <button
            type="button"
            className="border border-border rounded px-3 py-1 text-sm text-muted hover:text-fg disabled:opacity-50"
            disabled={busy}
            onClick={() => dismiss.mutate()}
          >
            Ausblenden
          </button>
        </div>
      )}
    </li>
  );
}

export default function Suggestions() {
  const q = useQuery({
    queryKey: ["suggestions"],
    queryFn: () => applications.getSuggestions(),
  });

  return (
    <div className="max-w-3xl mx-auto p-4 md:p-6">
      <h1 className="text-xl font-bold text-fg mb-1">Vorschläge</h1>
      <p className="text-sm text-muted mb-4">
        Entwürfe, deren Stellenanzeige offline gegangen ist. Die App ändert
        nichts von selbst — du entscheidest.
      </p>
      {q.isLoading ? (
        <div className="text-muted">Lädt…</div>
      ) : q.isError ? (
        <div className="text-red-600">Konnte Vorschläge nicht laden.</div>
      ) : (q.data?.length ?? 0) === 0 ? (
        <div className="text-muted border border-border rounded-lg p-6 text-center">
          Keine offenen Vorschläge. 🎉
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {q.data!.map((s) => (
            <SuggestionRow key={s.id} s={s} />
          ))}
        </ul>
      )}
    </div>
  );
}
