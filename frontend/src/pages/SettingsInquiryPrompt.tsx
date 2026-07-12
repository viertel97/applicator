import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { inquiryPrompt, type InquiryPrompt } from "../api/inquiry";
import InquiryPreview from "../components/InquiryPreview";

const DEFAULT_USER_PROMPT =
  "Zielsprache: {language}\n" +
  "Stelle: {title} bei {company}\n" +
  "{ref_line}" +
  "Ansprechpartner: {contact}\n\n" +
  "Fragen, die in der Mail vorkommen MUESSEN (in dieser Reihenfolge):\n" +
  "{questions}";

const DEFAULT_HO_DE =
  "Wie viele Tage Home Office pro Woche sind möglich, unter der Voraussetzung, dass Kundenprojekte und sonstige Anforderungen erfüllt sind?";
const DEFAULT_HO_EN =
  "How many days of home office per week are possible, assuming customer projects and other requirements are met?";
const DEFAULT_PT_DE = "Wäre eine 80%-Stelle (Montag bis Donnerstag) grundsätzlich denkbar?";
const DEFAULT_PT_EN = "Would an 80% position (Monday to Thursday) be possible in principle?";
const DEFAULT_BODY_TEMPLATE_DE =
  "{greeting},\n\n" +
  "ich interessiere mich sehr für Ihre Stellenausschreibung als „{title}{ref}“. " +
  "Bevor ich meine Bewerbung einreiche, hätte ich zwei kurze Fragen:\n\n" +
  "{questions}\n\n" +
  "Vielen Dank im Voraus für Ihre Rückmeldung und mit freundlichen Grüßen\n" +
  "Janik Viertel";
const DEFAULT_BODY_TEMPLATE_EN =
  "{greeting},\n\n" +
  'I am very interested in your job posting for the position of "{title}{ref}". ' +
  "Before submitting my application, I have a couple of questions:\n\n" +
  "{questions}\n\n" +
  "Thank you in advance for your reply.\n\n" +
  "Kind regards\n" +
  "Janik Viertel";

function Field({
  label,
  placeholder,
  value,
  rows,
  onChange,
}: {
  label: string;
  placeholder: string;
  value: string;
  rows?: number;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-fg mb-1">{label}</label>
      <textarea
        className="border border-border rounded p-2 w-full font-mono text-sm bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring"
        rows={rows ?? 3}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

export default function SettingsInquiryPrompt() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["inquiry-prompt"],
    queryFn: () => inquiryPrompt.get(),
  });

  const [draft, setDraft] = useState<InquiryPrompt>({
    source_md: "",
    user_prompt_md: null,
    question_home_office_de: null,
    question_home_office_en: null,
    question_part_time_de: null,
    question_part_time_en: null,
    body_template_de: null,
    body_template_en: null,
  });
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (q.data && !dirty) setDraft(q.data);
  }, [q.data, dirty]);

  function set<K extends keyof InquiryPrompt>(key: K, value: string) {
    setDraft((prev) => ({ ...prev, [key]: value || null }));
    setDirty(true);
  }

  const save = useMutation({
    mutationFn: (s: InquiryPrompt) => inquiryPrompt.put(s),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["inquiry-prompt"] });
    },
  });

  const [debounced, setDebounced] = useState<InquiryPrompt>(draft);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(draft), 400);
    return () => clearTimeout(t);
  }, [draft]);

  const preview = useQuery({
    queryKey: ["inquiry-preview", debounced],
    queryFn: () => inquiryPrompt.preview(debounced),
    enabled: !q.isLoading,
    placeholderData: (prev) => prev,
  });

  if (q.isLoading) return <div className="p-6">Loading…</div>;

  return (
    <div className="p-6 max-w-6xl mx-auto lg:grid lg:grid-cols-2 lg:gap-8">
      <div className="space-y-8">
        <div>
          <h1 className="text-xl font-semibold mb-2">Pre-application inquiry prompt</h1>
          <p className="text-sm text-muted mb-4">
            Configure the full prompt sent to the LLM when drafting inquiry emails. Questions
            are only included when not already covered by the job posting.
          </p>
        </div>

      <section className="space-y-3">
        <h2 className="font-medium text-fg">System prompt</h2>
        <p className="text-xs text-muted">
          High-level instructions: tone, format, output rules.
        </p>
        <textarea
          className="border border-border rounded p-2 w-full font-mono text-sm bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring"
          rows={14}
          value={draft.source_md}
          onChange={(e) => set("source_md", e.target.value)}
        />
      </section>

      <section className="space-y-3">
        <h2 className="font-medium text-fg">User prompt template</h2>
        <p className="text-xs text-muted">
          The message sent as the user turn. Available placeholders:{" "}
          <code className="bg-surface2 px-1 rounded">{"{language}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{title}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{company}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{contact}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{ref_line}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{reference_number}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{questions}"}</code>
          . Leave blank to use the default.
        </p>
        <textarea
          className="border border-border rounded p-2 w-full font-mono text-sm bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring"
          rows={8}
          value={draft.user_prompt_md ?? ""}
          placeholder={DEFAULT_USER_PROMPT}
          onChange={(e) => set("user_prompt_md", e.target.value)}
        />
      </section>

      <section className="space-y-3">
        <h2 className="font-medium text-fg">Question texts</h2>
        <p className="text-xs text-muted">
          Overrides for the question texts injected into <code className="bg-surface2 px-1 rounded">{"{questions}"}</code>.
          Leave blank to use the default wording.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            label="Home office — DE"
            placeholder={DEFAULT_HO_DE}
            value={draft.question_home_office_de ?? ""}
            onChange={(v) => set("question_home_office_de", v)}
          />
          <Field
            label="Home office — EN"
            placeholder={DEFAULT_HO_EN}
            value={draft.question_home_office_en ?? ""}
            onChange={(v) => set("question_home_office_en", v)}
          />
          <Field
            label="Part-time — DE"
            placeholder={DEFAULT_PT_DE}
            value={draft.question_part_time_de ?? ""}
            onChange={(v) => set("question_part_time_de", v)}
          />
          <Field
            label="Part-time — EN"
            placeholder={DEFAULT_PT_EN}
            value={draft.question_part_time_en ?? ""}
            onChange={(v) => set("question_part_time_en", v)}
          />
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-medium text-fg">Request mail body</h2>
        <p className="text-xs text-muted">
          The full inquiry email body. Available placeholders:{" "}
          <code className="bg-surface2 px-1 rounded">{"{greeting}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{title}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{ref}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{questions}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{company}"}</code>{" "}
          <code className="bg-surface2 px-1 rounded">{"{reference_number}"}</code>
          . Leave blank to use the default wording.
        </p>
        <div className="grid grid-cols-1 gap-3">
          <Field
            label="Body — DE"
            placeholder={DEFAULT_BODY_TEMPLATE_DE}
            value={draft.body_template_de ?? ""}
            rows={12}
            onChange={(v) => set("body_template_de", v)}
          />
          <Field
            label="Body — EN"
            placeholder={DEFAULT_BODY_TEMPLATE_EN}
            value={draft.body_template_en ?? ""}
            rows={12}
            onChange={(v) => set("body_template_en", v)}
          />
        </div>
      </section>

      <div className="flex gap-2 items-center">
        <button
          type="button"
          className="bg-accent text-accentFg px-3 py-1 rounded disabled:opacity-50"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate(draft)}
        >
          Save
        </button>
        {save.isError && (
          <span className="text-rose-600 text-sm">{(save.error as Error).message}</span>
        )}
      </div>
      </div>

      <div className="mt-8 lg:mt-0">
        <div className="lg:sticky lg:top-6">
          <InquiryPreview
            data={preview.data}
            loading={preview.isFetching}
            error={preview.isError ? (preview.error as Error).message : null}
          />
        </div>
      </div>
    </div>
  );
}
