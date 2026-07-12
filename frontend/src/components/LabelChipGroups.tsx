import type { Label, LabelCategory } from "../api/applications";
import { LabelChip } from "./LabelChip";

const CATEGORY_ORDER: LabelCategory[] = [
  "role", "tech", "domain", "seniority",
  "work_mode", "location", "company_size",
  "language", "company", "other",
];

const CATEGORY_LABEL: Record<LabelCategory, string> = {
  role: "Role",
  tech: "Tech",
  domain: "Domain",
  seniority: "Seniority",
  work_mode: "Work mode",
  location: "Location",
  company_size: "Company size",
  language: "Language",
  company: "Company",
  other: "Other",
};

type Props = {
  labels: Label[];
  onRemove?: (labelId: string) => void;
};

export function LabelChipGroups({ labels, onRemove }: Props) {
  if (labels.length === 0) return null;

  const groups = new Map<LabelCategory, Label[]>();
  for (const lab of labels) {
    const arr = groups.get(lab.category) ?? [];
    arr.push(lab);
    groups.set(lab.category, arr);
  }

  return (
    <div className="space-y-2">
      {CATEGORY_ORDER.map((cat) => {
        const items = groups.get(cat);
        if (!items || items.length === 0) return null;
        return (
          <div key={cat}>
            <div className="text-xs uppercase text-muted mb-1">
              {CATEGORY_LABEL[cat]}
            </div>
            <div className="flex flex-wrap gap-1">
              {items.map((lab) => (
                <LabelChip
                  key={lab.id}
                  label={lab}
                  onRemove={onRemove ? () => onRemove(lab.id) : undefined}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
