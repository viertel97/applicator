from pathlib import Path

from app.email_ingest.models import ParsedMessage, ParsedThread
from app.email_ingest.parser import extract_top_message, html_to_text

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "eml"


def _read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_parsed_message_defaults():
    m = ParsedMessage()
    assert m.sender_name is None
    assert m.sender_email is None
    assert m.recipients == []
    assert m.occurred_at is None
    assert m.subject is None
    assert m.body == ""


def test_parsed_thread_holds_messages():
    t = ParsedThread(messages=[ParsedMessage(body="hi")])
    assert len(t.messages) == 1
    assert t.messages[0].body == "hi"
    assert t.used_llm is False


def test_extract_top_message_plain():
    msg, text = extract_top_message(_read("single_plain.eml"))
    assert msg["Subject"] == "Your application"
    assert msg["From"] == "Recruiter Anna <anna@acme.test>"
    assert "thanks for applying" in text


def test_extract_top_message_html_is_converted():
    msg, text = extract_top_message(_read("html_only.eml"))
    assert "Hello there." in text
    assert "Second line" in text
    assert "<p>" not in text


def test_html_to_text_strips_tags_and_unescapes():
    out = html_to_text("<p>A&amp;B</p><br><div>C</div>")
    assert "A&B" in out
    assert "C" in out
    assert "<" not in out
