export interface LinkPart {
  text: string;
  href: string | null;
}

const URL_RE = /https?:\/\/[^\s<]+/g;

/** Split text into plain and URL parts so callers can render anchors.
 *  Trailing sentence punctuation (.,;:!?)]) is left out of the link. */
export function linkParts(text: string): LinkPart[] {
  const out: LinkPart[] = [];
  let pos = 0;
  for (const m of text.matchAll(URL_RE)) {
    const start = m.index;
    let url = m[0];
    const trail = url.match(/[.,;:!?)\]]+$/);
    if (trail) url = url.slice(0, url.length - trail[0].length);
    if (start > pos) out.push({ text: text.slice(pos, start), href: null });
    out.push({ text: url, href: url });
    pos = start + url.length; // trailing punctuation flows into the next plain part
  }
  if (pos < text.length) out.push({ text: text.slice(pos), href: null });
  return out;
}
