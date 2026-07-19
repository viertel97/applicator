import test from "node:test";
import assert from "node:assert/strict";
import { parseCalendarPaste } from "./parseCalendarPaste.ts";

const NOW = new Date("2026-03-01T00:00:00");

test("parses google-calendar copy format, takes start time, assumes current year", () => {
  const out = parseCalendarPaste("Wednesday, July 15⋅13:30 – 14:30", NOW);
  assert.equal(out, "2026-07-15T13:30");
});

test("weekday prefix is optional", () => {
  assert.equal(parseCalendarPaste("July 15 13:30", NOW), "2026-07-15T13:30");
});

test("explicit year in string wins over current year", () => {
  const out = parseCalendarPaste("Monday, December 1, 2025 09:05", NOW);
  assert.equal(out, "2025-12-01T09:05");
});

test("normalizes non-breaking spaces", () => {
  const out = parseCalendarPaste("July 15 13:30", NOW);
  assert.equal(out, "2026-07-15T13:30");
});

test("case-insensitive month names", () => {
  assert.equal(parseCalendarPaste("JULY 15 13:30", NOW), "2026-07-15T13:30");
});

test("pads single-digit month, day, hour", () => {
  assert.equal(parseCalendarPaste("March 5 9:07", NOW), "2026-03-05T09:07");
});

test("returns null on unrecognized text", () => {
  assert.equal(parseCalendarPaste("lunch with team", NOW), null);
});

test("returns null on bad month name", () => {
  assert.equal(parseCalendarPaste("Smarch 5 09:07", NOW), null);
});

test("returns null on out-of-range time", () => {
  assert.equal(parseCalendarPaste("March 5 25:07", NOW), null);
});

test("returns null on out-of-range day", () => {
  assert.equal(parseCalendarPaste("March 40 09:07", NOW), null);
});

test("returns null on empty input", () => {
  assert.equal(parseCalendarPaste("", NOW), null);
});
