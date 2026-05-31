import { useState } from "react";

export function DeleteConfirmButton({
  onConfirm,
  label = "Delete",
  className = "",
}: {
  onConfirm: () => void;
  label?: string;
  className?: string;
}) {
  const [armed, setArmed] = useState(false);

  if (armed) {
    return (
      <span className={`inline-flex items-center gap-1 text-xs ${className}`}>
        <button
          type="button"
          onClick={() => {
            setArmed(false);
            onConfirm();
          }}
          className="text-red-600 hover:underline"
        >
          Confirm?
        </button>
        <button
          type="button"
          onClick={() => setArmed(false)}
          className="text-slate-400 hover:text-slate-600"
          aria-label="Cancel"
        >
          ✕
        </button>
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setArmed(true)}
      className={`text-slate-400 hover:text-red-600 ${className}`}
      aria-label={label}
      title={label}
    >
      🗑
    </button>
  );
}
