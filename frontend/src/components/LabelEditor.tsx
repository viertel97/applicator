import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { labels as labelsApi } from "../api/labels";
import type { Label, LabelCategory } from "../api/applications";
import { LabelChip } from "./LabelChip";

const CATEGORIES: { value: LabelCategory; label: string }[] = [
  { value: "role", label: "Role" },
  { value: "tech", label: "Tech" },
  { value: "domain", label: "Domain" },
  { value: "seniority", label: "Seniority" },
  { value: "work_mode", label: "Work mode" },
  { value: "location", label: "Location" },
  { value: "company_size", label: "Company size" },
  { value: "language", label: "Language" },
  { value: "company", label: "Company" },
  { value: "other", label: "Other" },
];

const DEFAULT_COLORS = [
  "#6366f1", "#3b82f6", "#10b981", "#f59e0b",
  "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6",
];

type Props = {
  appId: string;
  assigned: Label[];
};

export function LabelEditor({ appId, assigned }: Props) {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [colorPick, setColorPick] = useState(DEFAULT_COLORS[0]);
  const [newCategory, setNewCategory] = useState<LabelCategory | "">("");
  const [creating, setCreating] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setSearch("");
        setCreating(false);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const allLabels = useQuery({ queryKey: ["labels"], queryFn: labelsApi.list });

  const assign = useMutation({
    mutationFn: (labelId: string) => labelsApi.assign(appId, labelId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", appId] });
      setSearch("");
      setAssignError(null);
    },
    onError: () => setAssignError("Failed to assign label"),
  });

  const remove = useMutation({
    mutationFn: (labelId: string) => labelsApi.remove(appId, labelId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", appId] }),
  });

  const create = useMutation({
    mutationFn: (body: { name: string; color: string; category: LabelCategory }) =>
      labelsApi.create(body),
    onSuccess: (newLabel) => {
      qc.invalidateQueries({ queryKey: ["labels"] });
      assign.mutate(newLabel.id);
      setCreating(false);
      setSearch("");
      setNewCategory("");
    },
  });

  const assignedIds = new Set(assigned.map((l) => l.id));
  const filtered = (allLabels.data ?? []).filter(
    (l) =>
      !assignedIds.has(l.id) &&
      l.name.toLowerCase().includes(search.toLowerCase()),
  );
  const exactMatch = (allLabels.data ?? []).some(
    (l) => l.name.toLowerCase() === search.toLowerCase(),
  );

  return (
    <div className="space-y-2" ref={containerRef}>
      <div className="flex flex-wrap gap-1">
        {assigned.map((lbl) => (
          <LabelChip
            key={lbl.id}
            label={lbl}
            onRemove={() => remove.mutate(lbl.id)}
          />
        ))}
      </div>
      <div className="relative">
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setCreating(false); }}
          placeholder="Add label…"
          className="w-full border rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        {search && (
          <div className="absolute z-10 mt-1 w-full bg-white border rounded shadow-md text-sm">
            {filtered.map((l) => (
              <button
                key={l.id}
                onClick={() => assign.mutate(l.id)}
                className="w-full text-left px-3 py-1.5 hover:bg-slate-50 flex items-center gap-2"
              >
                <span
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ backgroundColor: l.color }}
                />
                {l.name}
              </button>
            ))}
            {!exactMatch && search.trim() && (
              <button
                onClick={() => setCreating(true)}
                className="w-full text-left px-3 py-1.5 hover:bg-slate-50 text-blue-600"
              >
                Create "{search.trim()}"
              </button>
            )}
          </div>
        )}
      </div>
      {creating && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-500">Color:</span>
          {DEFAULT_COLORS.map((c) => (
            <button
              key={c}
              onClick={() => setColorPick(c)}
              className={`w-5 h-5 rounded-full border-2 ${colorPick === c ? "border-slate-700" : "border-transparent"}`}
              style={{ backgroundColor: c }}
              aria-label={c}
            />
          ))}
          <select
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value as LabelCategory)}
            className="border rounded px-1 py-0.5 text-sm"
          >
            <option value="">Category…</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          <button
            onClick={() => create.mutate({ name: search.trim(), color: colorPick, category: newCategory as LabelCategory })}
            disabled={!search.trim() || !newCategory || create.isPending}
            className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Create
          </button>
          <button
            onClick={() => setCreating(false)}
            className="text-xs text-slate-500 hover:text-slate-700"
          >
            Cancel
          </button>
        </div>
      )}
      {assignError && (
        <p className="text-xs text-red-600">{assignError}</p>
      )}
    </div>
  );
}
