from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str | None, max_len: int = 40) -> str:
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    hyphenated = _NON_ALNUM.sub("-", lowered).strip("-")
    if len(hyphenated) <= max_len:
        return hyphenated
    truncated = hyphenated[:max_len].rstrip("-")
    return truncated
