import { api } from "./client";

export type Variant = { id: string; name: string; source_md: string; is_default: boolean };

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
  };
}

export const cv = crud("cv-variants");
export const anschreiben = crud("anschreiben-variants");
