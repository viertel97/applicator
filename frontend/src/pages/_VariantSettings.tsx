import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import MDEditor from "@uiw/react-md-editor";
import type { Variant } from "../api/documents";

type CrudApi = {
  list: () => Promise<Variant[]>;
  create: (name: string, md: string, is_default?: boolean) => Promise<Variant>;
  update: (id: string, patch: Partial<Variant>) => Promise<Variant>;
  remove: (id: string) => Promise<unknown>;
};

export function VariantSettings({
  title,
  api: crudApi,
  queryKey,
}: {
  title: string;
  api: CrudApi;
  queryKey: string;
}) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: [queryKey], queryFn: crudApi.list });
  const [name, setName] = useState("");
  const [md, setMd] = useState("");
  const [editing, setEditing] = useState<Variant | null>(null);
  const create = useMutation({
    mutationFn: () => crudApi.create(name, md, list.data?.length === 0),
    onSuccess: () => {
      setName("");
      setMd("");
      qc.invalidateQueries({ queryKey: [queryKey] });
    },
  });
  const save = useMutation({
    mutationFn: (v: Variant) => crudApi.update(v.id, { name: v.name, source_md: v.source_md }),
    onSuccess: () => {
      setEditing(null);
      qc.invalidateQueries({ queryKey: [queryKey] });
    },
  });
  const setDefault = useMutation({
    mutationFn: (id: string) => crudApi.update(id, { is_default: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [queryKey] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => crudApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [queryKey] }),
  });
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">{title}</h1>
      <ul className="space-y-2 mb-6">
        {(list.data ?? []).map((v) =>
          editing?.id === v.id ? (
            <li key={v.id} className="border rounded p-3 bg-white">
              <input
                value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                className="border rounded px-2 py-1 mb-2 w-full"
              />
              <MDEditor
                value={editing.source_md}
                onChange={(s) => setEditing({ ...editing, source_md: s ?? "" })}
                height={400}
              />
              <div className="flex gap-2 mt-2">
                <button
                  className="bg-blue-600 text-white px-3 py-1 rounded"
                  onClick={() => save.mutate(editing)}
                >
                  Save
                </button>
                <button className="px-3 py-1" onClick={() => setEditing(null)}>
                  Cancel
                </button>
              </div>
            </li>
          ) : (
            <li
              key={v.id}
              className="border rounded p-3 bg-white flex items-center gap-2"
            >
              <span className="flex-1">
                {v.name}{" "}
                {v.is_default && (
                  <span className="text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">
                    default
                  </span>
                )}
              </span>
              {!v.is_default && (
                <button
                  onClick={() => setDefault.mutate(v.id)}
                  className="text-sm text-blue-600"
                >
                  Make default
                </button>
              )}
              <button onClick={() => setEditing(v)} className="text-sm">
                Edit
              </button>
              <button
                onClick={() => remove.mutate(v.id)}
                className="text-sm text-rose-600"
              >
                Delete
              </button>
            </li>
          ),
        )}
      </ul>
      <h2 className="text-lg font-medium mb-2">New</h2>
      <input
        placeholder="Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="border rounded px-2 py-1 mb-2 w-full"
      />
      <MDEditor value={md} onChange={(v) => setMd(v ?? "")} height={300} />
      <button
        disabled={!name || !md}
        onClick={() => create.mutate()}
        className="bg-blue-600 text-white px-4 py-2 rounded mt-2 disabled:opacity-50"
      >
        Add
      </button>
    </div>
  );
}
