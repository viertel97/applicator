from pathlib import Path

from app.email_ingest.models import ParsedMessage, ParsedThread
from app.email_ingest.parser import (
    extract_top_message,
    html_to_text,
    parse_quote_header,
    split_quoted,
)

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


OUTLOOK_EN = """Thanks, talk soon.

From: Recruiter Anna <anna@acme.test>
Sent: Wednesday, April 30, 2026 4:00 PM
To: Me <me@self.test>
Subject: Re: Your application

Hi, we received your CV.

From: Me <me@self.test>
Sent: Wednesday, April 30, 2026 1:00 PM
To: Recruiter Anna <anna@acme.test>
Subject: Your application

Here is my application.
"""

GMAIL_EN = """Sounds good.

On Wed, Apr 30, 2026 at 4:00 PM Anna <anna@acme.test> wrote:
Thanks for applying, we will review.
"""

GERMAN = """Vielen Dank.

Am 30.04.2026 um 16:00 schrieb Anna <anna@acme.test>:
Wir haben Ihre Bewerbung erhalten.
"""


def test_split_quoted_outlook_two_quotes():
    segs = split_quoted(OUTLOOK_EN)
    assert len(segs) == 2
    assert "we received your CV" in segs[0].body
    assert "Here is my application" in segs[1].body
    assert segs[0].header.startswith("From: Recruiter Anna")


def test_split_quoted_gmail_attribution():
    segs = split_quoted(GMAIL_EN)
    assert len(segs) == 1
    assert "Thanks for applying" in segs[0].body
    assert "wrote:" in segs[0].header


def test_split_quoted_german_attribution():
    segs = split_quoted(GERMAN)
    assert len(segs) == 1
    assert "Bewerbung erhalten" in segs[0].body


def test_split_quoted_no_markers_returns_empty():
    assert split_quoted("Just a flat message.\nNo quotes here.") == []


def test_parse_quote_header_outlook_block():
    block = (
        "From: Recruiter Anna <anna@acme.test>\n"
        "Sent: Wednesday, April 30, 2026 4:00 PM\n"
        "To: Me <me@self.test>\n"
        "Subject: Re: Your application"
    )
    h = parse_quote_header(block)
    assert h["sender_email"] == "anna@acme.test"
    assert h["sender_name"] == "Recruiter Anna"
    assert h["to"] == ["me@self.test"]
    assert h["subject"] == "Re: Your application"
    assert h["date"] == "Wednesday, April 30, 2026 4:00 PM"


def test_parse_quote_header_attribution_line():
    h = parse_quote_header("On Wed, Apr 30, 2026 at 4:00 PM Anna <anna@acme.test> wrote:")
    assert h["sender_email"] == "anna@acme.test"
    assert "Apr 30, 2026" in h["date"]
