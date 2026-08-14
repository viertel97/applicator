export type HasStart = { starts_at: string };
export type DayGroup<T> = { key: string; date: Date; items: T[] };

function dayKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function groupByDay<T extends HasStart>(rows: T[]): DayGroup<T>[] {
  const sorted = [...rows].sort(
    (a, b) => +new Date(a.starts_at) - +new Date(b.starts_at),
  );
  const map = new Map<string, DayGroup<T>>();
  for (const r of sorted) {
    const d = new Date(r.starts_at);
    const key = dayKey(d);
    let g = map.get(key);
    if (!g) {
      g = { key, date: new Date(d.getFullYear(), d.getMonth(), d.getDate()), items: [] };
      map.set(key, g);
    }
    g.items.push(r);
  }
  return [...map.values()];
}

// 6x7 matrix of Date objects; weeks start Monday.
export function monthMatrix(year: number, month: number): Date[][] {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7; // Mon=0
  const start = new Date(year, month, 1 - offset);
  const weeks: Date[][] = [];
  for (let w = 0; w < 6; w++) {
    const row: Date[] = [];
    for (let d = 0; d < 7; d++) {
      row.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7 + d));
    }
    weeks.push(row);
  }
  return weeks;
}

export function eventsForDay<T extends HasStart>(rows: T[], day: Date): T[] {
  const key = dayKey(day);
  return rows.filter((r) => dayKey(new Date(r.starts_at)) === key);
}
