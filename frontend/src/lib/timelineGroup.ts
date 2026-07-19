function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

export function dayLabel(iso: string, now: Date): string {
  const d = new Date(iso);
  const dayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / dayMs);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function dayKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export type DayBucket = {
  day: string;
  label: string;
  application: number;
  interaction: number;
  status: number;
  discard: number;
};

// Counts timeline rows per category per calendar day, sorted oldest-first so a
// line chart reads left→right in chronological order.
export function bucketByDay(
  rows: { at: string; category: string }[],
): DayBucket[] {
  const buckets = new Map<string, DayBucket>();
  for (const row of rows) {
    const d = new Date(row.at);
    const key = dayKey(d);
    let b = buckets.get(key);
    if (!b) {
      b = {
        day: key,
        label: d.toLocaleDateString(undefined, { day: "numeric", month: "short" }),
        application: 0,
        interaction: 0,
        status: 0,
        discard: 0,
      };
      buckets.set(key, b);
    }
    if (row.category in b) {
      (b as unknown as Record<string, number>)[row.category] += 1;
    }
  }
  return [...buckets.values()].sort((a, b) => a.day.localeCompare(b.day));
}

export type DayGroup<T> = { key: string; label: string; rows: T[] };

export function groupByDay<T extends { at: string }>(
  rows: T[],
  now: Date,
): DayGroup<T>[] {
  const groups: DayGroup<T>[] = [];
  let current: DayGroup<T> | null = null;
  for (const row of rows) {
    const label = dayLabel(row.at, now);
    if (!current || current.label !== label) {
      current = { key: label, label, rows: [] };
      groups.push(current);
    }
    current.rows.push(row);
  }
  return groups;
}
