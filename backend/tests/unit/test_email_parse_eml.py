import json
from pathlib import Path

from app.email_ingest.parser import parse_eml
from tests.fakes.llm import FakeLLM

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "eml"


def _read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_parse_eml_single_message_no_llm():
    thread = parse_eml(_read("single_plain.eml"), llm=None)
    assert thread.used_llm is False
    assert len(thread.messages) == 1
    top = thread.messages[0]
    assert top.sender_email == "anna@acme.test"
    assert top.subject == "Your application"
    assert top.occurred_at is not None  # from RFC822 Date header
    assert "thanks for applying" in top.body.lower()


def test_parse_eml_outlook_thread_splits_high_confidence():
    thread = parse_eml(_read("outlook_thread.eml"), llm=None)
    assert thread.used_llm is False
    assert len(thread.messages) == 2
    assert thread.messages[0].sender_email == "anna@acme.test"
    assert "received your CV" in thread.messages[0].body
    assert thread.messages[1].sender_email == "me@self.test"
    assert "my application" in thread.messages[1].body
    # top message keeps the real RFC822 date
    assert thread.messages[0].occurred_at.year == 2026


def test_parse_eml_low_confidence_uses_llm_and_overrides_top():
    def handler(_m, _s):
        return json.dumps(
            {
                "messages": [
                    {"sender_name": "WRONG", "sender_email": "wrong@x.test",
                     "recipients": [], "date_text": "", "subject": "WRONG",
                     "body": "newest"},
                    {"sender_name": "Old", "sender_email": "old@x.test",
                     "recipients": [], "date_text": "Apr 29 2026", "subject": "Older",
                     "body": "older"},
                ]
            }
        )

    llm = FakeLLM(handler=handler)
    # html_only triggers a marker-free single message; force LOW by using a
    # body that has a marker but no parseable split:
    raw = _read("html_marker_no_split.eml")
    thread = parse_eml(raw, llm=llm)
    assert thread.used_llm is True
    # message[0] sender/subject/date OVERRIDDEN by authoritative top headers
    assert thread.messages[0].sender_email == "anna@acme.test"
    assert thread.messages[0].subject == "Quote but no split"
    assert thread.messages[0].sender_name == "Recruiter Anna"


def test_parse_eml_llm_unavailable_degrades_gracefully():
    raw = _read("html_marker_no_split.eml")
    thread = parse_eml(raw, llm=None)
    assert thread.used_llm is False
    assert len(thread.messages) >= 1  # best-effort deterministic result


def test_parse_eml_llm_raises_degrades_gracefully():
    def boom(_m, _s):
        raise RuntimeError("llm down")

    raw = _read("html_marker_no_split.eml")
    thread = parse_eml(raw, llm=FakeLLM(handler=boom))
    assert thread.used_llm is False
    assert len(thread.messages) >= 1
