import { useState } from "react";
import type { InquiryPreviewOut } from "../api/inquiry";
import { highlightSegments } from "../lib/inquiryHighlight";

const SAMPLE_NOTE =
  "Preview uses a fixed sample job: Data Engineer @ Acme GmbH, contact Frau Müller, Ref 7. " +
  "Greeting is illustrative — the real one is generated per job.";

function Highlighted({
  text,
  greeting,
  questions,
}: {
  text: string;
  greeting: string;
  questions: string[];
}) {
  const segs = highlightSegments(text, [
    { text: greeting, kind: "greeting" },
    ...questions.map((q) => ({ text: q, kind: "questions" as const })),
  ]);
  return (
    <>
      {segs.map((s, i) =>
        s.kind === null ? (
          <span key={i}>{s.text}</span>
        ) : (
          <mark
            key={i}
            className={s.kind === "greeting" ? "bg-amber-200" : "bg-blue-200"}
          >
            {s.text}
          </mark>
        ),
      )}
    </>
  );
}

export default function InquiryPreview({
  data,
  loading,
  error,
}: {
  data: InquiryPreviewOut | undefined;
  loading: boolean;
  error: string | null;
}) {
  const [lang, setLang] = useState<"de" | "en">("de");
  const [showPrompt, setShowPrompt] = useState(false);
  const block = data?.[lang];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Live preview{loading ? " · updating…" : ""}
        </span>
        <div className="inline-flex rounded border border-slate-300 text-xs font-semibold overflow-hidden">
          {(["de", "en"] as const).map((l) => (
            <button
              key={l}
              type="button"
              aria-pressed={l === lang}
              className={
                l === lang
                  ? "px-3 py-1 bg-slate-900 text-white"
                  : "px-3 py-1 bg-white text-slate-500"
              }
              onClick={() => setLang(l)}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="text-rose-600 text-sm">{error}</div>}
      {!block && !error && (
        <div className="text-slate-400 text-sm">Loading preview…</div>
      )}

      {block && (
        <>
          <div className="border rounded-lg p-3">
            <button
              type="button"
              aria-expanded={showPrompt}
              className="text-xs font-bold text-slate-900"
              onClick={() => setShowPrompt((v) => !v)}
            >
              {showPrompt ? "▾" : "▸"} ① Prompt sent to the LLM
            </button>
            {showPrompt && (
              <div className="mt-2 space-y-2">
                <div className="text-[11px] uppercase text-slate-400">system</div>
                <pre className="whitespace-pre-wrap font-mono text-xs text-slate-600">
                  {block.system_prompt}
                </pre>
                <div className="text-[11px] uppercase text-slate-400">user</div>
                <pre className="whitespace-pre-wrap font-mono text-xs text-slate-600">
                  <Highlighted
                    text={block.user_prompt}
                    greeting={block.greeting}
                    questions={block.questions}
                  />
                </pre>
              </div>
            )}
          </div>

          <div className="text-center text-slate-400">↓</div>

          <div className="border rounded-lg p-3">
            <div className="text-xs font-bold text-slate-900 mb-2">
              ② LLM returns <span className="font-normal text-slate-400">(sample)</span>
            </div>
            <pre className="whitespace-pre-wrap font-mono text-xs text-slate-600">
              {"subject:  "}
              {block.subject}
              {"\ngreeting: "}
              <mark className="bg-amber-200">{block.greeting}</mark>
            </pre>
          </div>

          <div className="text-center text-slate-400">↓</div>

          <div className="border rounded-lg p-3">
            <div className="text-xs font-bold text-slate-900 mb-2">
              ③ Final email{" "}
              <span className="font-normal text-slate-400">(assembled in code)</span>
            </div>
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
              <Highlighted
                text={block.email}
                greeting={block.greeting}
                questions={block.questions}
              />
            </div>
          </div>

          <div className="text-[11px] text-slate-500">
            <mark className="bg-amber-200">greeting</mark> = LLM output ·{" "}
            <mark className="bg-blue-200">questions</mark> = your Question-texts fields
          </div>
          <div className="text-[11px] text-slate-400">{SAMPLE_NOTE}</div>
        </>
      )}
    </div>
  );
}
