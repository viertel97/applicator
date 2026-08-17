import test from "node:test";
import assert from "node:assert/strict";
import { detectMeetingUrl } from "./detectMeetingUrl.ts";

test("detects a Microsoft Teams URL", () => {
  const text =
    "Join the meeting: https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc123%40thread.v2/0?context=%7b%22Tid%22%3a%22abc%22%7d";
  const result = detectMeetingUrl(text);
  assert.equal(
    result,
    "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc123%40thread.v2/0?context=%7b%22Tid%22%3a%22abc%22%7d"
  );
});

test("detects a Zoom URL with subdomain", () => {
  const text =
    "Click here to join: <https://us02web.zoom.us/j/123456789?pwd=abc123XYZ>";
  const result = detectMeetingUrl(text);
  assert.equal(result, "https://us02web.zoom.us/j/123456789?pwd=abc123XYZ");
});

test("detects a Google Meet URL", () => {
  const text = "Google Meet link: https://meet.google.com/abc-defg-hij";
  const result = detectMeetingUrl(text);
  assert.equal(result, "https://meet.google.com/abc-defg-hij");
});

test("returns null when no meeting URL is present", () => {
  const text =
    "Please find the agenda attached. See you at 3pm. Call +1 555-123-4567 for questions.";
  const result = detectMeetingUrl(text);
  assert.equal(result, null);
});

test("returns the first meeting URL when multiple are present", () => {
  const text =
    "Primary: https://meet.google.com/abc-defg-hij — fallback: https://us02web.zoom.us/j/987654321";
  const result = detectMeetingUrl(text);
  assert.equal(result, "https://meet.google.com/abc-defg-hij");
});

test("does not capture trailing punctuation or angle brackets", () => {
  const text = "Join here: <https://meet.google.com/xyz-abcd-efg>.";
  const result = detectMeetingUrl(text);
  assert.equal(result, "https://meet.google.com/xyz-abcd-efg");
});

test("returns null for plain text with no URLs at all", () => {
  const text = "No links here whatsoever.";
  assert.equal(detectMeetingUrl(text), null);
});

test("returns null for same-domain but non-meeting URLs", () => {
  const text =
    "Visit https://teams.microsoft.com/ or https://zoom.us/ for account info.";
  assert.equal(detectMeetingUrl(text), null);
});
