import type { JobPosting } from "../api/applications";

type Contact = NonNullable<JobPosting["contact"]>;
type ContactField = keyof Contact;

type Props = {
  contact: JobPosting["contact"];
  disabled?: boolean;
  onChange: (field: ContactField, value: string | null) => void;
};

const FIELDS: Array<{ key: ContactField; label: string; type?: string }> = [
  { key: "name", label: "Name" },
  { key: "role", label: "Role" },
  { key: "email", label: "Email", type: "email" },
  { key: "phone", label: "Phone", type: "tel" },
];

export function ContactBlock({ contact, disabled, onChange }: Props) {
  return (
    <div className="mb-3">
      <label className="block text-xs uppercase text-muted">Contact</label>
      <div className="grid grid-cols-2 gap-2">
        {FIELDS.map((f) => (
          <input
            key={f.key}
            type={f.type ?? "text"}
            placeholder={f.label}
            disabled={disabled}
            value={contact?.[f.key] ?? ""}
            onChange={(e) => onChange(f.key, e.target.value || null)}
            className="border border-border rounded px-2 py-1 text-sm bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring"
          />
        ))}
      </div>
    </div>
  );
}
