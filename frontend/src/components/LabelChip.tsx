type Props = {
  label: { name: string; color: string };
  onRemove?: () => void;
};

export function LabelChip({ label, onRemove }: Props) {
  return (
    <span
      className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-medium text-white"
      style={{ backgroundColor: label.color }}
    >
      {label.name}
      {onRemove && (
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemove(); }}
          className="ml-0.5 hover:opacity-75 leading-none"
          aria-label={`Remove ${label.name}`}
        >
          ×
        </button>
      )}
    </span>
  );
}
