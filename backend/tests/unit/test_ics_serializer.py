from datetime import datetime, timezone
from app.calendar_feed.ics import IcsEvent, render_calendar


def _ev(**kw):
    base = dict(
        uid="11111111-1111-1111-1111-111111111111",
        summary="Acme · technical",
        starts_at=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc),
        location="https://meet.example/abc",
        description="Onsite loop\nhttps://app.example/applications/1",
        updated_at=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
    )
    base.update(kw)
    return IcsEvent(**base)


def test_render_wraps_vcalendar_and_vevent():
    out = render_calendar([_ev()])
    assert out.startswith("BEGIN:VCALENDAR\r\n")
    assert out.rstrip().endswith("END:VCALENDAR")
    assert "VERSION:2.0" in out
    assert "PRODID:" in out
    assert "BEGIN:VEVENT\r\n" in out
    assert "UID:11111111-1111-1111-1111-111111111111\r\n" in out
    assert "DTSTART:20260901T140000Z\r\n" in out
    assert "DTEND:20260901T150000Z\r\n" in out
    assert "STATUS:CONFIRMED\r\n" in out
    assert "SUMMARY:Acme" in out


def test_default_end_is_start_plus_60min():
    out = render_calendar([_ev(ends_at=None)])
    assert "DTEND:20260901T150000Z\r\n" in out


def test_escapes_special_chars_and_folds_long_lines():
    ev = _ev(summary="A, B; C\\D", description="line1\nline2")
    out = render_calendar([ev])
    assert "SUMMARY:A\\, B\\; C\\\\D\r\n" in out
    assert "line1\\nline2" in out
    # 75-octet line folding: every physical line <= 75 octets before CRLF
    for line in out.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75 or line == ""


def test_dtstamp_and_last_modified_match_updated_at():
    out = render_calendar([_ev()])
    assert "DTSTAMP:20260820T090000Z\r\n" in out
    assert "LAST-MODIFIED:20260820T090000Z\r\n" in out


def test_optional_fields_omitted_when_none():
    out = render_calendar([_ev(location=None, description=None)])
    assert "LOCATION:" not in out
    assert "DESCRIPTION:" not in out


def _unfold(out: str) -> str:
    return out.replace("\r\n ", "")


def _ics_unescape(s: str) -> str:
    # reverse RFC5545 TEXT escaping so we can assert on the HTML payload
    return (
        s.replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def test_html_alt_description_links_urls():
    out = render_calendar([_ev(description="Onsite loop\nhttps://app.example/applications/1")])
    assert "X-ALT-DESC;FMTTYPE=text/html:" in out
    unfolded = _unfold(out)
    assert '<a href="https://app.example/applications/1">' in unfolded
    assert "<br>" in unfolded  # newline preserved as a break


def test_html_alt_description_escapes_markup():
    out = render_calendar([_ev(description="a <b> & c")])
    payload = _ics_unescape(_unfold(out))
    assert "&lt;b&gt;" in payload
    assert "&amp;" in payload


def test_html_alt_desc_link_drops_trailing_period():
    out = render_calendar([_ev(description="see https://a.test/p.")])
    unfolded = _unfold(out)
    assert '<a href="https://a.test/p">https://a.test/p</a>' in unfolded


def test_no_alt_desc_without_description():
    out = render_calendar([_ev(description=None)])
    assert "X-ALT-DESC" not in out


def _has_raw_control_char(out: str) -> bool:
    # Any C0 control char (except TAB) or DEL surviving inside a physical line —
    # i.e. not the CRLF line separators — is a Google-rejecting corruption.
    import re

    for line in out.split("\r\n"):
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", line):
            return True
    return False


def test_lone_cr_normalized_not_left_raw():
    # Mac/Outlook line endings (lone CR) must not survive as a raw control byte.
    out = render_calendar([_ev(summary="Co\rMangled", description="a\rb")])
    assert not _has_raw_control_char(out)
    assert "SUMMARY:Co\\nMangled\r\n" in out


def test_strips_forbidden_control_chars():
    # Vertical tab / form feed / NUL from scraped email bodies get dropped;
    # TAB is allowed and preserved.
    out = render_calendar([_ev(description="x\x0by\x0cz\x00w\tkeep")])
    assert not _has_raw_control_char(out)
    assert "DESCRIPTION:xyzw\tkeep\r\n" in out


def test_multibyte_char_at_fold_boundary():
    out = render_calendar([_ev(summary="A" * 73 + "中")])
    # Every physical line must be <= 75 octets when UTF-8 encoded
    for line in out.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75 or line == ""
    # After unfolding (remove "\r\n "), the character must still be present
    unfolded = out.replace("\r\n ", "")
    assert "中" in unfolded
