import test from "node:test";
import assert from "node:assert/strict";
import type { Application, JobPosting } from "../api/applications";
import { matchesSearch } from "./search.ts";

function app(jp: Partial<JobPosting> | null, extra: Partial<Application> = {}): Application {
  return {
    job_posting: jp === null ? null : ({
      title: null,
      company: null,
      location: null,
      ...jp,
    } as JobPosting),
    ...extra,
  } as Application;
}

test("empty query matches everything", () => {
  assert.equal(matchesSearch(app({ title: "Dev" }), ""), true);
});

test("whitespace-only query matches everything", () => {
  assert.equal(matchesSearch(app({ title: "Dev" }), "   "), true);
});

test("matches title case-insensitively", () => {
  assert.equal(matchesSearch(app({ title: "Frontend Engineer" }), "frontend"), true);
  assert.equal(matchesSearch(app({ title: "Frontend Engineer" }), "ENGINEER"), true);
});

test("matches company", () => {
  assert.equal(matchesSearch(app({ company: "Globex" }), "globex"), true);
});

test("matches location", () => {
  assert.equal(matchesSearch(app({ location: "Berlin" }), "berl"), true);
});

test("non-matching query returns false", () => {
  assert.equal(matchesSearch(app({ title: "Dev", company: "Acme" }), "zzz"), false);
});

test("matches application GUID (from 'already exists' message)", () => {
  const id = "daf2f3fd-ea24-416a-b117-6d5ed88a8e82";
  assert.equal(matchesSearch(app({ title: "Dev" }, { id }), id), true);
  assert.equal(matchesSearch(app({ title: "Dev" }, { id }), "DAF2F3FD"), true);
  assert.equal(matchesSearch(app({ title: "Dev" }, { id }), "b117"), true);
});

test("matches display_id with or without # and padding", () => {
  const a = app({ title: "Dev" }, { display_id: 7 });
  assert.equal(matchesSearch(a, "#0007"), true);
  assert.equal(matchesSearch(a, "0007"), true);
  assert.equal(matchesSearch(a, "7"), true);
});

test("null fields are safe and do not match", () => {
  assert.equal(matchesSearch(app({ title: null, company: null, location: "Munich" }), "munich"), true);
  assert.equal(matchesSearch(app(null), "anything"), false);
  assert.equal(matchesSearch(app(null), ""), true);
});
