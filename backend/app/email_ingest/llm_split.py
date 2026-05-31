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

        return dtparser.parse(text, fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None


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
