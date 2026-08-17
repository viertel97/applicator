import { linkParts } from "../lib/linkify";

/** Render text with http(s) URLs turned into clickable, new-tab links. */
export function Linkify({ text }: { text: string }) {
  return (
    <>
      {linkParts(text).map((p, i) =>
        p.href ? (
          <a
            key={i}
            href={p.href}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-accent underline break-all"
          >
            {p.text}
          </a>
        ) : (
          p.text
        )
      )}
    </>
  );
}
