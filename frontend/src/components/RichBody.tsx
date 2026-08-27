import { Linkify } from "./Linkify";
import { toDisplayBody } from "../lib/richtext";

/**
 * Render an interaction/event body. HTML bodies (Outlook invites) are flattened
 * to link-preserving text; plain-text bodies pass through unchanged. Links are
 * clickable via Linkify. Caller supplies layout (e.g. whitespace-pre-wrap).
 */
export function RichBody({ text }: { text: string }) {
  return <Linkify text={toDisplayBody(text)} />;
}
