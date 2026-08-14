from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.llm.base import LLMClient

_STAGES = ["phone_screen", "technical", "onsite", "hr", "final", "other"]

_SYSTEM = (
    "You extract structured interview details from a forwarded email. "
    "Return starts_at/ends_at as ISO-8601 UTC (or null if unknown). "
    "location is a physical address or video link. "
    f"interview_stage is one of {_STAGES} or null. "
    "Return null for any field you cannot determine. Do not invent values."
)


class _LlmInterview(BaseModel):
    starts_at: str | None = None
    ends_at: str | None = None
    location: str | None = None
    interview_stage: str | None = None
    contact_name: str | None = None
    contact_handle: str | None = None


class ExtractedInterview(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    interview_stage: str | None = None
    contact_name: str | None = None
    contact_handle: str | None = None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_interview(subject: str, body: str, llm: LLMClient) -> ExtractedInterview:
    raw = llm.complete(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Subject: {subject}\n\n{body}"},
        ],
        json_schema=_LlmInterview.model_json_schema(),
        temperature=0.0,
    )
    parsed = _LlmInterview.model_validate_json(raw)
    stage = parsed.interview_stage if parsed.interview_stage in _STAGES else None
    return ExtractedInterview(
        starts_at=_parse_dt(parsed.starts_at),
        ends_at=_parse_dt(parsed.ends_at),
        location=parsed.location or None,
        interview_stage=stage,
        contact_name=parsed.contact_name or None,
        contact_handle=parsed.contact_handle or None,
    )
