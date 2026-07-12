import test from "node:test";
import assert from "node:assert/strict";
import { formatInterviewSummary } from "./interviewSummary.ts";

test("upcoming round shows round + stage + upcoming", () => {
  const s = {
    rounds_logged: 2,
    next: { round: 2, stage: "technical" as const, at: "2999-01-02T10:00:00" },
    last: { round: 1, stage: "phone_screen" as const, at: "2020-01-01T10:00:00" },
  };
  const out = formatInterviewSummary(s);
  assert.match(out, /^interview · R2 Technical · upcoming /);
});

test("past-only round shows round + stage + done", () => {
  const s = {
    rounds_logged: 1,
    next: null,
    last: { round: 1, stage: "onsite" as const, at: "2020-01-01T10:00:00" },
  };
  assert.equal(formatInterviewSummary(s), "interview · R1 Onsite · done");
});

test("missing stage omits the stage segment", () => {
  const s = {
    rounds_logged: 1,
    next: null,
    last: { round: 1, stage: null, at: "2020-01-01T10:00:00" },
  };
  assert.equal(formatInterviewSummary(s), "interview · R1 · done");
});

test("empty summary falls back to plain interview", () => {
  const s = { rounds_logged: 0, next: null, last: null };
  assert.equal(formatInterviewSummary(s), "interview");
});
