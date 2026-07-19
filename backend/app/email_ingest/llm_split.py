from datetime import datetime

from pydantic import BaseModel, Field

from app.email_ingest.models import ParsedMessage
from app.llm.base import LLMClient

_SYSTEM = (
    "You split an email thread into individual messages, newest first. "
    "For each message return sender_name, sender_email, recipients (emails), "
    "date_text (the raw date string as written, or empty), subject, and body "
    "(that message's own text only, excluding quoted older messages). "
    "Do not invent addresses; use empty strings when unknown."
)


class LlmMessage(BaseModel):
    sender_name: str = ""
    sender_email: str = ""
    recipients: list[str] = Field(default_factory=list)
    date_text: str = ""
    subject: str = ""
    body: str = ""


class LlmThread(BaseModel):
    messages: list[LlmMessage] = Field(default_factory=list)


def _parse_date(text: str) -> datetime | None:
    if not text.strip():
        return None
    try:
        from dateutil import parser as dtparser
    except ImportError:
        return None
    try:
        # Parse twice with distinct sentinel defaults so we can tell which
        # fields the text actually supplied. dateutil silently fills missing
        # components from the default, so a year-less quote header
        # ("10. August 22:06", common in German Outlook replies) would inherit
        # the current year and land in the future. dayfirst=True matches
        # European numeric dates (30.04.2026 = 30 April).
        dt = dtparser.parse(text, fuzzy=True, dayfirst=True, default=datetime(2000, 1, 1))
        alt = dtparser.parse(text, fuzzy=True, dayfirst=True, default=datetime(2001, 6, 15))
    except (ValueError, OverflowError, TypeError):
        return None
    if dt.year != alt.year:  # year absent from text → dateutil defaulted it
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        dt = dt.replace(year=now.year)
        if dt > now:  # a past email can't be in the future → previous year
            dt = dt.replace(year=now.year - 1)
    return dt


def llm_split_thread(text: str, llm: LLMClient) -> list[ParsedMessage]:
    raw = llm.complete(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": text},
        ],
        json_schema=LlmThread.model_json_schema(),
        temperature=0.0,
    )
    thread = LlmThread.model_validate_json(raw)
    out: list[ParsedMessage] = []
    for m in thread.messages:
        out.append(
            ParsedMessage(
                sender_name=m.sender_name or None,
                sender_email=m.sender_email or None,
                recipients=[r for r in m.recipients if r],
                occurred_at=_parse_date(m.date_text),
                subject=m.subject or None,
                body=m.body,
            )
        )
    return out
