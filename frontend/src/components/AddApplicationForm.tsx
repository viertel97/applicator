import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";

export function AddApplicationForm() {
  const [url, setUrl] = useState("");
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (u: string) => applications.create(u),
    onSuccess: () => {
      setUrl("");
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });
  return (
    <form
      className="flex gap-2 mb-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (url.trim()) m.mutate(url.trim());
      }}
    >
      <input
        type="url"
        required
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste job posting URL"
        className="border rounded px-3 py-2 flex-1"
      />
      <button
        type="submit"
        disabled={m.isPending}
        className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
      >
        Add
      </button>
      {m.isError && (
        <span className="text-rose-600 self-center">{(m.error as Error).message}</span>
      )}
    </form>
  );
}
