import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { discardReasons, type DiscardReason } from "../api/discardReasons";

export default function SettingsDiscardReasons() {
  const qc = useQueryClient();
  const [includeArchived, setIncludeArchived] = useState(false);
  const q = useQuery({
    queryKey: ["discard-reasons", includeArchived],
    queryFn: () => discardReasons.list(includeArchived),
  });
  const [newLabel, setNewLabel] = useState("");

  const create = useMutation({
    mutationFn: (label: string) => discardReasons.create(label),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["discard-reasons"] });
      setNewLabel("");
    },
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<DiscardReason> }) =>
      discardReasons.patch(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["discard-reasons"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => discardReasons.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["discard-reasons"] }),
    onError: (e: any) => alert(e?.message ?? "delete failed"),
  });

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-3">Discard reasons</h1>
      <div className="flex gap-2 mb-3">
        <input value={newLabel} onChange={(e) => setNewLabel(e.target.value)}
               placeholder="New reason label"
               className="border border-border rounded px-2 py-1 text-sm flex-1 bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring" />
        <button type="button" disabled={!newLabel.trim() || create.isPending}
                onClick={() => create.mutate(newLabel.trim())}
                className="bg-accent text-accentFg rounded px-3 py-1 text-sm disabled:opacity-50">
          Add
        </button>
      </div>
      <label className="text-sm text-muted mb-2 flex items-center gap-1">
        <input type="checkbox" checked={includeArchived}
               onChange={(e) => setIncludeArchived(e.target.checked)} />
        Show archived
      </label>
      <table className="w-full text-sm border">
        <thead className="bg-surface2">
          <tr>
            <th className="text-left px-2 py-1">Label</th>
            <th className="text-left px-2 py-1">Slug</th>
            <th className="text-left px-2 py-1">Usage</th>
            <th className="text-left px-2 py-1">Archived</th>
            <th className="text-left px-2 py-1"></th>
          </tr>
        </thead>
        <tbody>
          {(q.data ?? []).map((r) => (
            <tr key={r.id} className="border-t">
              <td className="px-2 py-1">
                <input defaultValue={r.label}
                       onBlur={(e) => {
                         if (e.target.value !== r.label)
                           patch.mutate({ id: r.id, body: { label: e.target.value } });
                       }}
                       className="border border-border rounded px-1 w-full bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring" />
              </td>
              <td className="px-2 py-1 font-mono text-xs text-muted">{r.slug}</td>
              <td className="px-2 py-1">{r.usage_count}</td>
              <td className="px-2 py-1">
                <input type="checkbox" checked={r.is_archived}
                       onChange={(e) =>
                         patch.mutate({ id: r.id, body: { is_archived: e.target.checked } })} />
              </td>
              <td className="px-2 py-1">
                <button type="button"
                        disabled={r.usage_count > 0}
                        title={r.usage_count > 0 ? "archive instead" : ""}
                        onClick={() => remove.mutate(r.id)}
                        className="text-rose-600 text-xs disabled:opacity-50">
                  delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
