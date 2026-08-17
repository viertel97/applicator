/**
 * Detects the first meeting URL (Teams, Zoom, Google Meet) in a block of text.
 * Returns the URL string, or null if none is found.
 *
 * Trailing punctuation and enclosing characters like `>`, `)`, `"` are excluded
 * from the match so that URLs embedded in HTML or Markdown are returned cleanly.
 */

// Matches the first https:// URL whose host+path identifies a meeting platform:
//   - Microsoft Teams:  teams.microsoft.com/l/meetup-join/...
//   - Zoom:             *.zoom.us/j/...
//   - Google Meet:      meet.google.com/...
//
// The character class for the URL body excludes common trailing delimiters
// (`>`, `<`, `"`, `'`, `)`, whitespace) so that bracketed/quoted URLs are
// captured without their surrounding markup.
const MEETING_URL_RE =
  /https:\/\/(?:teams\.microsoft\.com\/l\/meetup-join|(?:[a-z0-9-]+\.)?zoom\.us\/j|meet\.google\.com)\/[^\s<>"')]+/i;

export function detectMeetingUrl(text: string): string | null {
  const match = MEETING_URL_RE.exec(text);
  if (!match) return null;

  // Strip any trailing punctuation that slipped through (e.g. a lone period
  // or closing parenthesis at the very end of the matched string).
  const url = match[0].replace(/[.,;:!?)]+$/, "");
  return url;
}
