import enum
import re

from app.email_ingest.models import ParsedMessage

_MARKER_RE = re.compile(
    r"(?i)(\bwrote:|\bschrieb\b|^\s*(From|Von):|-{2,}\s*Original|Forwarded message)",
    re.MULTILINE,
)


class Confidence(str, enum.Enum):
    HIGH = "high"
    LOW = "low"


def score(det_messages: list[ParsedMessage], body_text: str) -> Confidence:
    has_marker = bool(_MARKER_RE.search(body_text))
    quoted_count = max(len(det_messages) - 1, 0)
    if has_marker and quoted_count == 0:
        return Confidence.LOW
    for m in det_messages:
        if not m.sender_email and m.occurred_at is None:
            return Confidence.LOW
    return Confidence.HIGH
