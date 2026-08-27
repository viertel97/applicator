import type { Application } from "../api/applications";

export function matchesSearch(app: Application, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const jp = app.job_posting;
  const displayId =
    app.display_id != null
      ? [`#${String(app.display_id).padStart(4, "0")}`, String(app.display_id)]
      : [];
  const hay = [jp?.title, jp?.company, jp?.location, app.id, ...displayId]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}
