import type { Application } from "../api/applications.ts";

const INACTIVE_STATUSES = new Set(["rejected", "discarded", "withdrawn", "accepted"]);

export function isActiveApplication(app: Application): boolean {
  return !INACTIVE_STATUSES.has(app.status);
}

export function applicationLabel(app: Application): string {
  const company = app.job_posting?.company || null;
  const title = app.job_posting?.title || null;
  if (company && title) return `${company} · ${title}`;
  if (company) return company;
  if (title) return title;
  return app.url;
}

export function buildOccurredAtISO(day: Date, time: string): string {
  const [hh, mm] = time.split(":").map(Number);
  return new Date(day.getFullYear(), day.getMonth(), day.getDate(), hh, mm).toISOString();
}
