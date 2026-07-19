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
