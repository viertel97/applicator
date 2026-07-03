import { useEffect, useRef, useState } from "react";
import type { AppStatus } from "../api/applications";
import { STATUS_HEX } from "./StatusBadge";

// Custom dropdown showing each status in its own color. Native <option> ignores
// background/text colors on macOS browsers, so we render our own list.
export function StatusSelect({
  value,
  options,
  onChange,
}: {
  value: AppStatus;
  options: AppStatus[];
  onChange: (status: AppStatus) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="border rounded px-2 py-1 text-sm font-medium flex items-center gap-1"
        style={{ backgroundColor: STATUS_HEX[value].bg, color: STATUS_HEX[value].text }}
      >
        {value}
        <span aria-hidden className="text-[0.6rem] opacity-70">▼</span>
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute z-20 mt-1 min-w-full rounded border border-slate-200 bg-white shadow-lg p-1 max-h-72 overflow-auto"
        >
          {options.map((s) => (
            <li key={s}>
              <button
                type="button"
                role="option"
                aria-selected={s === value}
                onClick={() => {
                  setOpen(false);
                  if (s !== value) onChange(s);
                }}
                className={`w-full text-left px-2 py-1 my-0.5 rounded text-sm font-medium ${
                  s === value ? "ring-2 ring-slate-400" : ""
                }`}
                style={{ backgroundColor: STATUS_HEX[s].bg, color: STATUS_HEX[s].text }}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
