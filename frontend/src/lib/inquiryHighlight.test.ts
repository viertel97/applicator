import test from "node:test";
import assert from "node:assert/strict";
import { highlightSegments } from "./inquiryHighlight.ts";

test("wraps greeting and questions, leaves rest plain", () => {
  const segs = highlightSegments("Hi NAME, see Q1 and Q2 end", [
    { text: "NAME", kind: "greeting" },
    { text: "Q1", kind: "questions" },
    { text: "Q2", kind: "questions" },
  ]);
  assert.deepEqual(segs, [
    { text: "Hi ", kind: null },
    { text: "NAME", kind: "greeting" },
    { text: ", see ", kind: null },
    { text: "Q1", kind: "questions" },
    { text: " and ", kind: null },
    { text: "Q2", kind: "questions" },
    { text: " end", kind: null },
  ]);
});

test("missing target produces no highlight", () => {
  const segs = highlightSegments("plain text", [{ text: "ZZZ", kind: "greeting" }]);
  assert.deepEqual(segs, [{ text: "plain text", kind: null }]);
});

test("empty target is ignored", () => {
  const segs = highlightSegments("abc", [{ text: "", kind: "greeting" }]);
  assert.deepEqual(segs, [{ text: "abc", kind: null }]);
});

test("overlapping matches: first wins, no double-wrap", () => {
  const segs = highlightSegments("abcdef", [
    { text: "abcd", kind: "greeting" },
    { text: "cdef", kind: "questions" },
  ]);
  assert.deepEqual(segs, [
    { text: "abcd", kind: "greeting" },
    { text: "ef", kind: null },
  ]);
});
