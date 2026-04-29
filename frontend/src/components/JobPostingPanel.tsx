import type { ReactNode } from "react";
import type { JobPosting } from "../api/applications";

function Field({ label, value }: { label: string; value: ReactNode }) {
  if (!value) return null;
  return (
    <div className="mb-3">
      <div className="text-xs uppercase text-slate-500">{label}</div>
      <div>{value}</div>
    </div>
  );
}

export function JobPostingPanel({ jp }: { jp: JobPosting | null }) {
  if (!jp) return <div className="text-slate-500">Awaiting extraction…</div>;
  return (
    <div>
      <Field label="Title" value={jp.title} />
      <Field label="Company" value={jp.company} />
      <Field label="Location" value={jp.location} />
      <Field label="Work mode" value={jp.work_mode} />
      <Field label="Seniority" value={jp.seniority} />
      <Field label="Salary" value={jp.salary} />
      <Field label="Deadline" value={jp.deadline} />
      <Field label="Contact" value={jp.contact_person} />
      <Field label="Email" value={jp.application_email} />
      <Field label="Tech stack" value={jp.tech_stack?.join(", ")} />
      <Field label="Benefits" value={jp.benefits?.join(", ")} />
      <Field
        label="Requirements"
        value={jp.requirements ? <pre className="whitespace-pre-wrap">{jp.requirements}</pre> : null}
      />
      <Field
        label="Description"
        value={jp.description ? <pre className="whitespace-pre-wrap">{jp.description}</pre> : null}
      />
    </div>
  );
}
