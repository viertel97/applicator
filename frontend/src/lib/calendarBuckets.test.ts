import test from "node:test";
import assert from "node:assert/strict";
import { groupByDay, monthMatrix, eventsForDay, dayKey } from "./calendarBuckets.ts";

const ev = (id: string, starts_at: string) =>
  ({ id, starts_at } as { id: string; starts_at: string });

test("groupByDay buckets by local calendar day, sorted ascending", () => {
  const rows = [
    ev("b", "2026-09-02T09:00:00Z"),
    ev("a", "2026-09-01T14:00:00Z"),
    ev("c", "2026-09-01T08:00:00Z"),
  ];
  const groups = groupByDay(rows);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].items.map((r) => r.id).join(","), "c,a");
  assert.equal(groups[1].items[0].id, "b");
});

test("eventsForDay returns only rows matching the given local date", () => {
  const rows = [
    { id: "sep1", starts_at: "2026-09-01T08:00:00" },
    { id: "sep2", starts_at: "2026-09-02T08:00:00" },
  ];
  const result = eventsForDay(rows, new Date(2026, 8, 1));
  assert.equal(result.length, 1);
  assert.equal(result[0].id, "sep1");
});

test("dayKey formats a Date as YYYY-MM-DD using local calendar day", () => {
  assert.equal(dayKey(new Date(2026, 7, 17)), "2026-08-17");
});

test("monthMatrix returns 6 weeks of 7 days covering the month", () => {
  const weeks = monthMatrix(2026, 8); // 0-based month => September 2026
  assert.equal(weeks.length, 6);
  assert.equal(weeks[0].length, 7);
  const all = weeks.flat();
  assert.ok(all.some((d) => d.getMonth() === 8 && d.getDate() === 1));
  assert.ok(all.some((d) => d.getMonth() === 8 && d.getDate() === 30));
  assert.equal(weeks[0][0].getDay(), 1, "first cell must be Monday");
});
