import { ApiError, api } from "./client";

export type Variant = { id: string; name: string; source_md: string; is_default: boolean };

async function uploadDocx(path: string, file: File): Promise<Variant> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`/api/${path}/upload`, {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* ignore */ }
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as Variant;
}

function crud(path: "cv-variants" | "anschreiben-variants") {
  return {
    list: () => api<Variant[]>(`/api/${path}`),
    create: (name: string, source_md: string, is_default = false) =>
      api<Variant>(`/api/${path}`, {
        method: "POST",
        body: JSON.stringify({ name, source_md, is_default }),
      }),
    update: (id: string, patch: Partial<Variant>) =>
      api<Variant>(`/api/${path}/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    remove: (id: string) => api<{ ok: true }>(`/api/${path}/${id}`, { method: "DELETE" }),
    upload: (file: File) => uploadDocx(path, file),
  };
}

export const cv = crud("cv-variants");
export const anschreiben = crud("anschreiben-variants");
