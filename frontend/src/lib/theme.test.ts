import test from "node:test";
import assert from "node:assert/strict";
import { resolveTheme } from "./theme.ts";

test("stored 'dark' wins over system preference", () => {
  assert.equal(resolveTheme("dark", false), "dark");
});

test("stored 'light' wins over system preference", () => {
  assert.equal(resolveTheme("light", true), "light");
});

test("no stored value falls back to system: dark", () => {
  assert.equal(resolveTheme(null, true), "dark");
});

test("no stored value falls back to system: light", () => {
  assert.equal(resolveTheme(null, false), "light");
});

test("unrecognized stored value falls back to system", () => {
  assert.equal(resolveTheme("bogus", true), "dark");
});
