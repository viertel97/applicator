import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";
import { cv as cvApi, anschreiben as anApi } from "../api/documents";

export function AddApplicationForm() {
  const [url, setUrl] = useState("");
  const [cvId, setCvId] = useState<string>("");
  const [anId, setAnId] = useState<string>("");
  const qc = useQueryClient();

  const cvs = useQuery({ queryKey: ["cv-variants"], queryFn: () => cvApi.list() });
  const ans = useQuery({ queryKey: ["an-variants"], queryFn: () => anApi.list() });

  const m = useMutation({
    mutationFn: () =>
      applications.create({
        url: url.trim(),
        cv_variant_id: cvId || undefined,
        anschreiben_variant_id: anId || undefined,
      }),
    onSuccess: () => {
      setUrl("");
      setCvId("");
      setAnId("");
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });

  return (
    <form
      className="grid gap-2 mb-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (url.trim()) m.mutate();
      }}
    >
      <input
        type="url"
        required
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste job posting URL"
        className="border border-border rounded px-3 py-2 bg-surface text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <div className="grid grid-cols-2 gap-2">
        <select
          value={cvId}
          onChange={(e) => setCvId(e.target.value)}
          className="border border-border rounded px-3 py-2 bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">CV — skip, add later</option>
          {(cvs.data ?? []).map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
        <select
          value={anId}
          onChange={(e) => setAnId(e.target.value)}
          className="border border-border rounded px-3 py-2 bg-surface text-fg focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Anschreiben — skip, add later</option>
          {(ans.data ?? []).map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={m.isPending}
          className="bg-accent text-accentFg px-4 py-2 rounded disabled:opacity-50"
        >
          Add
        </button>
        {m.isError && (
          <span className="text-rose-600">{(m.error as Error).message}</span>
        )}
      </div>
    </form>
  );
}
