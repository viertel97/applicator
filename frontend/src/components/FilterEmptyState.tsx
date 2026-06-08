import type { EmptyReason } from "../lib/filterDiagnostics";

type Reason = Exclude<EmptyReason, null>;

type Props = {
  reason: Reason;
  onFix: (reason: Reason) => void;
};

const COPY: Record<Reason, { message: string; fix: string }> = {
  "all-statuses-hidden": { message: "All statuses deselected — nothing to show.", fix: "Show all statuses" },
  "no-status-match": { message: "No items match the selected statuses.", fix: "Show all statuses" },
  reason: { message: "Reason filter excludes every discarded item.", fix: "Clear reason" },
  docs: { message: "No items have all the selected documents.", fix: "Clear document filters" },
  search: { message: "No items match your search.", fix: "Clear search" },
  labels: { message: "No items have all the selected labels.", fix: "Clear labels" },
  mixed: { message: "Active filters exclude all items.", fix: "Reset all filters" },
};

export function FilterEmptyState({ reason, onFix }: Props) {
  const { message, fix } = COPY[reason];
  return (
    <div className="border border-amber-200 bg-amber-50 rounded p-4 flex items-center justify-between gap-3 text-sm">
      <span className="text-amber-800">{message}</span>
      <button
        type="button"
        onClick={() => onFix(reason)}
        className="text-xs px-2 py-1 rounded border border-amber-300 bg-white text-amber-800 hover:bg-amber-100 flex-shrink-0"
      >
        {fix}
      </button>
    </div>
  );
}
