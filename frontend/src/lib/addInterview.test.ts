import test from "node:test";
import assert from "node:assert/strict";
import { isActiveApplication, applicationLabel, buildOccurredAtISO } from "./addInterview.ts";
import type { Application } from "../api/applications.ts";

// Minimal helper — only status, job_posting, url matter for these helpers
function app(
  status: Application["status"],
  url: string,
  company: string | null,
  title: string | null,
): Application {
  return {
    id: "1",
    display_id: 1,
    url,
    status,
    job_state: "ready",
    job_error: null,
    failed_stage: null,
    language: null,
    generated_md: null,
    has_docx: false,
    cv_variant_id: null,
    anschreiben_variant_id: null,
    job_posting_dirty: false,
    posting_online: null,
    posting_offline_reason: null,
    labels: [],
    job_posting: { title, company, location: null, description: null, requirements: null, contact: null, deadline: null, salary: null, tech_stack: null, seniority: null, work_mode: null, benefits: null, language: null, required_documents: null, reference_number: null, mentions_home_office_policy: null, mentions_part_time: null },
    folder_name: "",
    notes: null,
    awaiting_response: false,
    discard_note: null,
    discard_reason_id: null,
    discard_interaction_id: null,
    interview_summary: null,
  };
}

function appNoPosting(status: Application["status"], url: string): Application {
  return { ...app(status, url, null, null), job_posting: null };
}

// --- isActiveApplication ---

test("isActiveApplication: 'applied' is active", () => {
  assert.equal(isActiveApplication(app("applied", "http://x.com", null, null)), true);
});

test("isActiveApplication: 'rejected' is NOT active", () => {
  assert.equal(isActiveApplication(app("rejected", "http://x.com", null, null)), false);
});

test("isActiveApplication: 'discarded' is NOT active", () => {
  assert.equal(isActiveApplication(app("discarded", "http://x.com", null, null)), false);
});

test("isActiveApplication: 'withdrawn' is NOT active", () => {
  assert.equal(isActiveApplication(app("withdrawn", "http://x.com", null, null)), false);
});

test("isActiveApplication: 'accepted' is NOT active", () => {
  assert.equal(isActiveApplication(app("accepted", "http://x.com", null, null)), false);
});

test("isActiveApplication: 'interview' is active", () => {
  assert.equal(isActiveApplication(app("interview", "http://x.com", null, null)), true);
});

test("isActiveApplication: 'offer' is active", () => {
  assert.equal(isActiveApplication(app("offer", "http://x.com", null, null)), true);
});

// --- applicationLabel ---

test("applicationLabel: company + title → 'Company · Title'", () => {
  assert.equal(applicationLabel(app("applied", "http://x.com", "Acme", "Engineer")), "Acme · Engineer");
});

test("applicationLabel: only company → company", () => {
  assert.equal(applicationLabel(app("applied", "http://x.com", "Acme", null)), "Acme");
});

test("applicationLabel: only title → title", () => {
  assert.equal(applicationLabel(app("applied", "http://x.com", null, "Engineer")), "Engineer");
});

test("applicationLabel: neither → falls back to url", () => {
  assert.equal(applicationLabel(app("applied", "http://x.com/job/42", null, null)), "http://x.com/job/42");
});

test("applicationLabel: no job_posting → falls back to url", () => {
  assert.equal(applicationLabel(appNoPosting("applied", "http://x.com/job/99")), "http://x.com/job/99");
});

// --- buildOccurredAtISO ---

test("buildOccurredAtISO: produces valid ISO string ending in Z", () => {
  const result = buildOccurredAtISO(new Date(2026, 7, 18), "09:30");
  assert.ok(result.endsWith("Z"), `Expected Z-terminated ISO string, got: ${result}`);
  assert.doesNotThrow(() => new Date(result));
});

test("buildOccurredAtISO: matches local-time Date construction", () => {
  const day = new Date(2026, 7, 18); // 18 Aug 2026 local
  const result = buildOccurredAtISO(day, "09:30");
  const expected = new Date(2026, 7, 18, 9, 30).toISOString();
  assert.equal(result, expected);
});

test("buildOccurredAtISO: midnight '00:00' works", () => {
  const result = buildOccurredAtISO(new Date(2026, 0, 1), "00:00");
  const expected = new Date(2026, 0, 1, 0, 0).toISOString();
  assert.equal(result, expected);
});
