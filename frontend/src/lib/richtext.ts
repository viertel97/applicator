/**
 * Turn an Outlook/Graph event body (HTML) into readable, link-preserving plain
 * text. We deliberately avoid rendering the raw HTML (untrusted invite content =
 * XSS risk): DOMParser lets us read only textContent plus anchor hrefs, so a
 * "Click here to join the meeting" link surfaces as visible, clickable text.
 */

/** Cheap check: does this string contain HTML markup worth parsing? */
export function looksLikeHtml(s: string): boolean {
  return /<[a-z!][\s\S]*>/i.test(s);
}

/**
 * Flatten HTML to text while keeping links: block boundaries become newlines
 * and each anchor's href is appended in parentheses (unless already visible) so
 * the URL is preserved for Linkify to turn back into a clickable link.
 *
 * Browser-only (needs DOMParser). Falls back to the raw input off-DOM.
 */
export function htmlToLinkableText(html: string): string {
  if (typeof DOMParser === "undefined") return html;
  const doc = new DOMParser().parseFromString(html, "text/html");

  // Drop non-content nodes; their text is included by textContent otherwise.
  doc.querySelectorAll("script, style, noscript, template, head").forEach(
    (el) => el.remove(),
  );

  // Reveal href URLs that aren't already spelled out in the link text.
  doc.querySelectorAll("a[href]").forEach((a) => {
    const href = a.getAttribute("href") ?? "";
    const text = a.textContent ?? "";
    if (/^(https?:|mailto:)/i.test(href) && !text.includes(href)) {
      a.textContent = text.trim() ? `${text} (${href})` : href;
    }
  });

  // Force a line break after block-level elements so text doesn't run together.
  doc.querySelectorAll("br, p, div, li, tr, h1, h2, h3, h4, h5, h6").forEach(
    (el) => el.append("\n"),
  );

  const text = doc.body.textContent ?? "";
  // Collapse runs of blank lines and trim trailing whitespace per line.
  return text
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Body ready for <Linkify>: HTML flattened to link-preserving text, else raw. */
export function toDisplayBody(body: string): string {
  return looksLikeHtml(body) ? htmlToLinkableText(body) : body;
}
