import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { JobPosting } from "../api/applications";
import { applications } from "../api/applications";
import { ContactBlock } from "./ContactBlock";
import { ALL_DOCS, DOC_LABEL } from "../lib/docs";

type Props = {
  appId: string;
  jp: JobPosting | null;
  disabled: boolean;
};

const TEXT_FIELDS: Array<{ key: keyof JobPosting; label: string; multiline?: boolean }> = [
  { key: "title", label: "Title" },
  { key: "company", label: "Company" },
  { key: "location", label: "Location" },
  { key: "work_mode", label: "Work mode" },
  { key: "seniority", label: "Seniority" },
  { key: "salary", label: "Salary" },
  { key: "deadline", label: "Deadline" },
  { key: "language", label: "Language" },
  { key: "requirements", label: "Requirements", multiline: true },
  { key: "description", label: "Description", multiline: true },
];

const LIST_FIELDS: Array<{ key: keyof JobPosting; label: string }> = [
  { key: "tech_stack", label: "Tech stack (comma-separated)" },
  { key: "benefits", label: "Benefits (comma-separated)" },
];

export function JobPostingPanel({ appId, jp, disabled }: Props) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Partial<JobPosting>>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (jp) {
      setDraft({});
      setDirty(false);
    }
  }, [jp?.title, jp?.company]);

  const save = useMutation({
    mutationFn: () => applications.patchJobPosting(appId, draft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", appId] });
      setDraft({});
      setDirty(false);
    },
  });

  if (!jp) return <div className="text-muted">Awaiting extraction…</div>;

  const update = (key: keyof JobPosting, value: unknown) => {
    setDraft((d) => ({ ...d, [key]: value }));
    setDirty(true);
  };

  const value = <K extends keyof JobPosting>(key: K): JobPosting[K] =>
    (draft[key] !== undefined ? draft[key] : jp[key]) as JobPosting[K];

  const updateContact = (
    field: keyof NonNullable<JobPosting["contact"]>,
    val: string | null,
  ) => {
    setDraft((d) => {
      const base = d.contact ?? jp.contact ?? { name: null, role: null, email: null, phone: null };
      return { ...d, contact: { ...base, [field]: val } };
    });
    setDirty(true);
  };

  return (
    <div>
      <ContactBlock
        contact={draft.contact ?? jp.contact}
        disabled={disabled}
        onChange={updateContact}
      />
      {TEXT_FIELDS.map((f) => (
        <div className="mb-3" key={f.key}>
          <label className="block text-xs uppercase text-muted">{f.label}</label>
          {f.multiline ? (
            <textarea
              className="border border-border rounded px-2 py-1 w-full bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring"
              rows={4}
              disabled={disabled}
              value={(value(f.key) as string | null) ?? ""}
              onChange={(e) => update(f.key, e.target.value || null)}
            />
          ) : (
            <input
              className="border border-border rounded px-2 py-1 w-full bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring"
              disabled={disabled}
              value={(value(f.key) as string | null) ?? ""}
              onChange={(e) => update(f.key, e.target.value || null)}
            />
          )}
        </div>
      ))}
      {LIST_FIELDS.map((f) => (
        <div className="mb-3" key={f.key}>
          <label className="block text-xs uppercase text-muted">{f.label}</label>
          <input
            className="border border-border rounded px-2 py-1 w-full bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring"
            disabled={disabled}
            value={((value(f.key) as string[] | null) ?? []).join(", ")}
            onChange={(e) =>
              update(
                f.key,
                e.target.value
                  ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                  : null,
              )
            }
          />
        </div>
      ))}
      <div className="mt-3">
        <div className="text-xs font-medium text-muted uppercase tracking-wide mb-1">
          Required documents
        </div>
        <div className="flex flex-wrap gap-1">
          {ALL_DOCS.map((doc) => {
            const selected = (value("required_documents") ?? []).includes(doc);
            return (
              <button
                key={doc}
                type="button"
                disabled={disabled}
                onClick={() => {
                  const current = value("required_documents") ?? [];
                  const next = selected
                    ? current.filter((d) => d !== doc)
                    : ALL_DOCS.filter((d) => [...current, doc].includes(d));
                  update("required_documents", next);
                }}
                className={
                  selected
                    ? "text-xs px-2 py-0.5 rounded border bg-accent text-accentFg border-accent disabled:opacity-50"
                    : "text-xs px-2 py-0.5 rounded border bg-surface text-muted border-border disabled:opacity-50"
                }
              >
                {DOC_LABEL[doc]}
              </button>
            );
          })}
        </div>
      </div>
      <button
        type="button"
        disabled={!dirty || disabled || save.isPending}
        onClick={() => save.mutate()}
        className="bg-accent text-accentFg px-3 py-1 rounded disabled:opacity-50"
      >
        Save changes
      </button>
      {save.isError && (
        <span className="text-rose-600 ml-2 text-sm">
          {(save.error as Error).message}
        </span>
      )}
    </div>
  );
}
