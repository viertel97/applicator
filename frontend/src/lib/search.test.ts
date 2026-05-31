import test from "node:test";
import assert from "node:assert/strict";
import type { Application, JobPosting } from "../api/applications";
import { matchesSearch } from "./search.ts";

function app(jp: Partial<JobPosting> | null): Application {
  return {
    job_posting: jp === null ? null : ({
      title: null,
      company: null,
      location: null,
      ...jp,
    } as JobPosting),
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

test("null fields are safe and do not match", () => {
  assert.equal(matchesSearch(app({ title: null, company: null, location: "Munich" }), "munich"), true);
  assert.equal(matchesSearch(app(null), "anything"), false);
  assert.equal(matchesSearch(app(null), ""), true);
});
