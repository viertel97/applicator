import test from "node:test";
import assert from "node:assert/strict";
import { dayLabel, groupByDay, bucketByDay } from "./timelineGroup.ts";

const NOW = new Date("2026-07-17T10:00:00");

test("dayLabel returns Today for same calendar day", () => {
  assert.equal(dayLabel("2026-07-17T08:30:00", NOW), "Today");
});

test("dayLabel returns Yesterday for previous calendar day", () => {
  assert.equal(dayLabel("2026-07-16T23:00:00", NOW), "Yesterday");
});

test("dayLabel returns a formatted date for older days", () => {
  const label = dayLabel("2026-07-10T12:00:00", NOW);
  assert.notEqual(label, "Today");
  assert.notEqual(label, "Yesterday");
  assert.match(label, /2026/);
});

test("groupByDay buckets rows newest-day-first, preserving row order within a day", () => {
  const rows = [
    { at: "2026-07-17T09:00:00", id: "a" },
    { at: "2026-07-17T08:00:00", id: "b" },
    { at: "2026-07-16T20:00:00", id: "c" },
  ];
  const groups = groupByDay(rows, NOW);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].label, "Today");
  assert.deepEqual(groups[0].rows.map((r) => r.id), ["a", "b"]);
  assert.equal(groups[1].label, "Yesterday");
  assert.deepEqual(groups[1].rows.map((r) => r.id), ["c"]);
});

test("bucketByDay counts rows per category per calendar day, oldest-first", () => {
  const rows = [
    { at: "2026-07-17T09:00:00", category: "application" },
    { at: "2026-07-17T11:00:00", category: "interaction" },
    { at: "2026-07-17T12:00:00", category: "application" },
    { at: "2026-07-15T20:00:00", category: "status" },
  ];
  const data = bucketByDay(rows);
  assert.equal(data.length, 2);
  // oldest day first (ascending) so the line reads left→right in time
  assert.equal(data[0].day, "2026-07-15");
  assert.deepEqual(
    { application: data[0].application, interaction: data[0].interaction, status: data[0].status, discard: data[0].discard },
    { application: 0, interaction: 0, status: 1, discard: 0 },
  );
  assert.equal(data[1].day, "2026-07-17");
  assert.deepEqual(
    { application: data[1].application, interaction: data[1].interaction, status: data[1].status, discard: data[1].discard },
    { application: 2, interaction: 1, status: 0, discard: 0 },
  );
});

test("bucketByDay returns empty array for no rows", () => {
  assert.deepEqual(bucketByDay([]), []);
});
