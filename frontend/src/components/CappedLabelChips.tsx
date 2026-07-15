import type { Label, LabelCategory } from "../api/applications";
import { LabelChip } from "./LabelChip";

type Props = {
  labels: Label[];
  max?: number;
};

// Display priority: identity-defining categories win visible slots over
// generic skill tags (tech) when the list is capped.
const DISPLAY_PRIORITY: LabelCategory[] = [
  "role", "seniority", "work_mode", "location",
  "domain", "company_size", "language", "company",
  "tech", "other",
];

function rank(cat: LabelCategory): number {
  const i = DISPLAY_PRIORITY.indexOf(cat);
  return i === -1 ? DISPLAY_PRIORITY.length : i;
}

export function CappedLabelChips({ labels, max = 6 }: Props) {
  if (labels.length === 0) return null;

  const sorted = [...labels].sort((a, b) => rank(a.category) - rank(b.category));
  const visible = sorted.slice(0, max);
  const hidden = sorted.length - visible.length;

  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {visible.map((lbl) => (
        <LabelChip key={lbl.id} label={lbl} />
      ))}
      {hidden > 0 && (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-surface2 text-muted">
          +{hidden}
        </span>
      )}
    </div>
  );
}
