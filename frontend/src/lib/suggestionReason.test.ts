import test from "node:test";
import assert from "node:assert/strict";
import { suggestionReasonLabel } from "./suggestionReason.ts";

test("known http codes map to German labels", () => {
  assert.equal(suggestionReasonLabel("http_404"), "Seite nicht gefunden");
  assert.equal(suggestionReasonLabel("http_403"), "Zugriff verweigert");
  assert.equal(suggestionReasonLabel("http_410"), "Anzeige entfernt");
});

test("redirect codes map to German labels", () => {
  assert.equal(suggestionReasonLabel("redirect_root"), "Weiterleitung zur Startseite");
  assert.equal(suggestionReasonLabel("redirect_offhost"), "Weiterleitung zu anderer Seite");
});

test("llm and keyword reasons map to labels", () => {
  assert.equal(suggestionReasonLabel("llm_inactive"), "Vermutlich nicht mehr aktiv");
  assert.equal(
    suggestionReasonLabel("keyword:bereits besetzt"),
    "Stelle besetzt oder abgelaufen",
  );
});

test("null and unknown reasons fall back to Offline", () => {
  assert.equal(suggestionReasonLabel(null), "Offline");
  assert.equal(suggestionReasonLabel("something_new"), "Offline");
});
