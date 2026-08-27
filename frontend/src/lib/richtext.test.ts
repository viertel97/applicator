import { test } from "node:test";
import assert from "node:assert/strict";
import { looksLikeHtml, toDisplayBody } from "./richtext.ts";

test("looksLikeHtml detects markup", () => {
  assert.equal(looksLikeHtml('<a href="x">y</a>'), true);
  assert.equal(looksLikeHtml("<html><body>hi</body></html>"), true);
  assert.equal(looksLikeHtml("<br>"), true);
});

test("looksLikeHtml leaves plain text alone", () => {
  assert.equal(looksLikeHtml("See you then"), false);
  assert.equal(looksLikeHtml("meet at 3 < 4 o'clock"), false);
  assert.equal(looksLikeHtml("https://teams.microsoft.com/l/x"), false);
});

test("toDisplayBody passes plain text through unchanged (no DOM needed)", () => {
  // node --test has no DOMParser; plain text must not require it.
  assert.equal(toDisplayBody("plain note with link https://x/y"), "plain note with link https://x/y");
});
