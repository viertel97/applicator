import json
from datetime import timedelta
from app.email_ingest.interview_extract import extract_interview, ExtractedInterview


class _FakeLLM:
    def __init__(self, payload): self._payload = payload; self.calls = []
    def complete(self, messages, *, json_schema=None, temperature=0.2):
        self.calls.append((messages, json_schema))
        return json.dumps(self._payload)


def test_extract_parses_fields_and_passes_schema():
    llm = _FakeLLM({
        "starts_at": "2026-09-01T14:00:00Z", "ends_at": "2026-09-01T15:00:00Z",
        "location": "https://meet.example/abc", "interview_stage": "technical",
        "contact_name": "Jane Doe", "contact_handle": "jane@acme.example",
    })
    out = extract_interview("Interview invite", "Let's meet...", llm)
    assert isinstance(out, ExtractedInterview)
    assert out.interview_stage == "technical"
    assert out.location == "https://meet.example/abc"
    assert llm.calls[0][1] is not None  # json_schema was provided


def test_extract_tolerates_nulls():
    llm = _FakeLLM({"starts_at": None, "ends_at": None, "location": None,
                    "interview_stage": None, "contact_name": None, "contact_handle": None})
    out = extract_interview("s", "b", llm)
    assert out.starts_at is None
    assert out.interview_stage is None


def test_invalid_stage_becomes_none():
    llm = _FakeLLM({
        "starts_at": None, "ends_at": None, "location": None,
        "interview_stage": "screening", "contact_name": None, "contact_handle": None,
    })
    out = extract_interview("s", "b", llm)
    assert out.interview_stage is None


def test_bad_datetime_becomes_none():
    llm = _FakeLLM({
        "starts_at": "sometime next week", "ends_at": None, "location": None,
        "interview_stage": None, "contact_name": None, "contact_handle": None,
    })
    out = extract_interview("s", "b", llm)
    assert out.starts_at is None


def test_valid_z_datetime_parses_aware():
    llm = _FakeLLM({
        "starts_at": "2026-09-01T14:00:00Z", "ends_at": None, "location": None,
        "interview_stage": None, "contact_name": None, "contact_handle": None,
    })
    out = extract_interview("s", "b", llm)
    assert out.starts_at is not None and out.starts_at.utcoffset() == timedelta(0)
