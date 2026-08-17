import test from "node:test";
import assert from "node:assert/strict";
import { linkParts } from "./linkify.ts";

test("plain text yields a single non-link part", () => {
  assert.deepEqual(linkParts("no links here"), [
    { text: "no links here", href: null },
  ]);
});

test("splits a url out of surrounding text", () => {
  assert.deepEqual(linkParts("join https://meet.co/x now"), [
    { text: "join ", href: null },
    { text: "https://meet.co/x", href: "https://meet.co/x" },
    { text: " now", href: null },
  ]);
});

test("does not swallow trailing sentence punctuation", () => {
  assert.deepEqual(linkParts("see https://a.test/p."), [
    { text: "see ", href: null },
    { text: "https://a.test/p", href: "https://a.test/p" },
    { text: ".", href: null },
  ]);
});

test("handles multiple urls", () => {
  const parts = linkParts("a http://x.io b https://y.io");
  assert.deepEqual(parts.filter((p) => p.href).map((p) => p.href), [
    "http://x.io",
    "https://y.io",
  ]);
});
