import test from "node:test";
import assert from "node:assert/strict";
import type { Application, AppStatus, JobPosting } from "../api/applications";
import { applyFilters, diagnoseEmpty, type FilterState } from "./filterDiagnostics.ts";

const ALL_STATUSES: AppStatus[] = [
  "draft", "applied", "offer", "rejected", "accepted",
  "withdrawn", "discarded", "need_call", "apply_direct",
];

function app(o: {
  status?: AppStatus;
  discard_reason_id?: string | null;
  docs?: string[];
  title?: string;
  awaiting?: boolean;
} = {}): Application {
  const jp =
    o.title !== undefined || o.docs !== undefined
      ? ({
          title: o.title ?? null,
          company: null,
          location: null,
          required_documents: o.docs ?? null,
        } as JobPosting)
      : null;
  return {
    status: o.status ?? "draft",
    discard_reason_id: o.discard_reason_id ?? null,
    job_posting: jp,
    awaiting_response: o.awaiting ?? false,
  } as Application;
}

function fs(o: Partial<FilterState> = {}): FilterState {
  return {
    hiddenStatuses: new Set<AppStatus>(),
    reasonFilter: null,
    filterDocs: [],
    query: "",
    filterLabelIds: [],
    awaitingFilter: "all",
    ...o,
  };
}

// --- applyFilters parity ---

test("applyFilters hides items whose status is hidden", () => {
  const data = [app({ status: "draft" }), app({ status: "applied" })];
  const out = applyFilters(data, fs({ hiddenStatuses: new Set(["draft"]) }));
  assert.equal(out.length, 1);
  assert.equal(out[0].status, "applied");
});

test("applyFilters reason filter only affects discarded items", () => {
  const data = [
    app({ status: "discarded", discard_reason_id: "r1" }),
    app({ status: "discarded", discard_reason_id: "r2" }),
    app({ status: "draft" }),
  ];
  const out = applyFilters(data, fs({ reasonFilter: "r1" }));
  assert.equal(out.length, 2);
  assert.ok(out.every((a) => a.status !== "discarded" || a.discard_reason_id === "r1"));
});

test("applyFilters docs filter requires all selected documents", () => {
  const data = [app({ docs: ["cv", "portfolio"] }), app({ docs: ["cv"] })];
  const out = applyFilters(data, fs({ filterDocs: ["cv", "portfolio"] }));
  assert.equal(out.length, 1);
});

test("applyFilters applies search predicate", () => {
  const data = [app({ title: "Dev" }), app({ title: "Ops" })];
  const out = applyFilters(data, fs({ query: "dev" }));
  assert.equal(out.length, 1);
  assert.equal(out[0].job_posting?.title, "Dev");
});

// --- diagnoseEmpty ---

test("all statuses hidden -> all-statuses-hidden", () => {
  const data = [app({ status: "draft" })];
  const f = fs({ hiddenStatuses: new Set(ALL_STATUSES) });
  assert.equal(diagnoseEmpty(data, f), "all-statuses-hidden");
});

test("one status shown but no data matches -> no-status-match", () => {
  const data = [app({ status: "draft" })];
  const f = fs({ hiddenStatuses: new Set(["draft"]) });
  assert.equal(diagnoseEmpty(data, f), "no-status-match");
});

test("reason filter excludes all discarded -> reason", () => {
  const data = [app({ status: "discarded", discard_reason_id: "r1" })];
  const f = fs({ reasonFilter: "r2" });
  assert.equal(diagnoseEmpty(data, f), "reason");
});

test("docs filter too strict -> docs", () => {
  const data = [app({ docs: ["cv"] })];
  const f = fs({ filterDocs: ["portfolio"] });
  assert.equal(diagnoseEmpty(data, f), "docs");
});

test("search excludes all -> search", () => {
  const data = [app({ title: "Dev" })];
  const f = fs({ query: "zzz" });
  assert.equal(diagnoseEmpty(data, f), "search");
});

test("data empty with labels active -> labels", () => {
  assert.equal(diagnoseEmpty([], fs({ filterLabelIds: ["l1"] })), "labels");
});

test("two filters needed to recover -> mixed", () => {
  const data = [app({ status: "draft", title: "Dev" })];
  const f = fs({ hiddenStatuses: new Set(["draft"]), query: "zzz" });
  assert.equal(diagnoseEmpty(data, f), "mixed");
});

test("non-empty result -> null", () => {
  const data = [app({ status: "draft" })];
  assert.equal(diagnoseEmpty(data, fs()), null);
});

test("no applications at all (no label filter) -> null", () => {
  assert.equal(diagnoseEmpty([], fs()), null);
});

test("applyFilters awaitingFilter=awaiting keeps only awaiting apps", () => {
  const data = [app({ awaiting: true }), app({ awaiting: false })];
  const out = applyFilters(data, fs({ awaitingFilter: "awaiting" }));
  assert.equal(out.length, 1);
  assert.equal(out[0].awaiting_response, true);
});

test("applyFilters awaitingFilter=hide drops awaiting apps", () => {
  const data = [app({ awaiting: true }), app({ awaiting: false })];
  const out = applyFilters(data, fs({ awaitingFilter: "hide" }));
  assert.equal(out.length, 1);
  assert.equal(out[0].awaiting_response, false);
});

test("applyFilters awaitingFilter=all keeps both", () => {
  const data = [app({ awaiting: true }), app({ awaiting: false })];
  const out = applyFilters(data, fs({ awaitingFilter: "all" }));
  assert.equal(out.length, 2);
});

test("awaiting filter empties list -> awaiting", () => {
  const data = [app({ awaiting: false })];
  assert.equal(diagnoseEmpty(data, fs({ awaitingFilter: "awaiting" })), "awaiting");
});

test("hide-awaiting filter empties list -> awaiting", () => {
  const data = [app({ awaiting: true })];
  assert.equal(diagnoseEmpty(data, fs({ awaitingFilter: "hide" })), "awaiting");
});
