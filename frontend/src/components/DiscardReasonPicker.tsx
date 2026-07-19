import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { discardReasons, type DiscardReason } from "../api/discardReasons";

type Props = {
  value: string | null;
  onChange: (id: string | null, reason: DiscardReason | null) => void;
  includeArchived?: boolean;
  disabled?: boolean;
};

export function DiscardReasonPicker({ value, onChange, includeArchived, disabled }: Props) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["discard-reasons", includeArchived],
    queryFn: () => discardReasons.list(includeArchived),
  });
  const [showAdd, setShowAdd] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const create = useMutation({
    mutationFn: (label: string) => discardReasons.create(label),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["discard-reasons"] });
      onChange(r.id, r);
      setShowAdd(false);
      setNewLabel("");
    },
  });

  if (!q.data) return <select disabled className="border border-border bg-surface text-fg rounded px-2 py-1 text-sm" />;
  return (
    <div className="flex gap-1 items-center">
      <select
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => {
          const id = e.target.value || null;
          onChange(id, id ? q.data.find((r) => r.id === id) ?? null : null);
        }}
        className="border border-border bg-surface text-fg rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <option value="">— no reason —</option>
        {q.data.map((r) => (
          <option key={r.id} value={r.id}>{r.label}</option>
        ))}
      </select>
      {disabled ? null : !showAdd ? (
        <button
          type="button"
          className="text-xs text-accent hover:underline"
          onClick={() => setShowAdd(true)}
        >+ Add</button>
      ) : (
        <>
          <input
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Label"
            className="border border-border bg-surface text-fg placeholder:text-muted rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="button"
            disabled={!newLabel.trim() || create.isPending}
            onClick={() => create.mutate(newLabel.trim())}
            className="text-xs bg-accent text-accentFg rounded px-2 py-1 disabled:opacity-50"
          >Save</button>
          <button
            type="button"
            onClick={() => { setShowAdd(false); setNewLabel(""); }}
            className="text-xs text-muted"
          >×</button>
        </>
      )}
    </div>
  );
}
