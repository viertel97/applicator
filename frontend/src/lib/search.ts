import type { Application } from "../api/applications";

export function matchesSearch(app: Application, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const jp = app.job_posting;
  const hay = [jp?.title, jp?.company, jp?.location]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}
