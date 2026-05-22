import type { JobPosting } from "../api/applications";

type Props = { contact: JobPosting["contact"] };

export function ContactBlock({ contact }: Props) {
  if (!contact) return null;
  const anyField = contact.name || contact.role || contact.email || contact.phone;
  if (!anyField) return null;
  return (
    <div className="mb-3">
      <label className="block text-xs uppercase text-slate-500">Contact</label>
      <div className="border rounded px-2 py-1 space-y-0.5 text-sm">
        {contact.name && <div>{contact.name}</div>}
        {contact.role && <div className="text-slate-600">{contact.role}</div>}
        {contact.email && (
          <div>
            <a
              className="text-blue-600 hover:underline"
              href={`mailto:${contact.email}`}
            >
              {contact.email}
            </a>
          </div>
        )}
        {contact.phone && (
          <div>
            <a className="text-blue-600 hover:underline" href={`tel:${contact.phone}`}>
              {contact.phone}
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
