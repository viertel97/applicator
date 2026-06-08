export type SegmentKind = "greeting" | "questions";

export interface Segment {
  text: string;
  kind: SegmentKind | null;
}

export interface HighlightTarget {
  text: string;
  kind: SegmentKind;
}

export function highlightSegments(text: string, targets: HighlightTarget[]): Segment[] {
  const ranges: { start: number; end: number; kind: SegmentKind }[] = [];
  for (const t of targets) {
    if (!t.text) continue;
    let from = 0;
    let i = text.indexOf(t.text, from);
    while (i !== -1) {
      ranges.push({ start: i, end: i + t.text.length, kind: t.kind });
      from = i + t.text.length;
      i = text.indexOf(t.text, from);
    }
  }
  // earliest start first; on a tie prefer the longer match
  ranges.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start));

  const out: Segment[] = [];
  let pos = 0;
  for (const r of ranges) {
    if (r.start < pos) continue; // overlaps an already-emitted highlight
    if (r.start > pos) out.push({ text: text.slice(pos, r.start), kind: null });
    out.push({ text: text.slice(r.start, r.end), kind: r.kind });
    pos = r.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), kind: null });
  return out;
}
