import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { JobPosting } from "../api/applications";
import { applications } from "../api/applications";
import { ContactBlock } from "./ContactBlock";

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

  if (!jp) return <div className="text-slate-500">Awaiting extraction…</div>;

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
          <label className="block text-xs uppercase text-slate-500">{f.label}</label>
          {f.multiline ? (
            <textarea
              className="border rounded px-2 py-1 w-full"
              rows={4}
              disabled={disabled}
              value={(value(f.key) as string | null) ?? ""}
              onChange={(e) => update(f.key, e.target.value || null)}
            />
          ) : (
            <input
              className="border rounded px-2 py-1 w-full"
              disabled={disabled}
              value={(value(f.key) as string | null) ?? ""}
              onChange={(e) => update(f.key, e.target.value || null)}
            />
          )}
        </div>
      ))}
      {LIST_FIELDS.map((f) => (
        <div className="mb-3" key={f.key}>
          <label className="block text-xs uppercase text-slate-500">{f.label}</label>
          <input
            className="border rounded px-2 py-1 w-full"
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
      {jp?.required_documents && jp.required_documents.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
            Required documents
          </div>
          <div className="flex flex-wrap gap-1">
            {jp.required_documents.map((doc) => (
              <span
                key={doc}
                className="px-2 py-0.5 bg-slate-100 text-slate-700 text-xs rounded-full capitalize"
              >
                {doc.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      )}
      <button
        type="button"
        disabled={!dirty || disabled || save.isPending}
        onClick={() => save.mutate()}
        className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
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
