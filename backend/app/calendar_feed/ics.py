from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_URL_RE = re.compile(r"https?://[^\s<]+")
_TRAIL = ".,;:!?)]"

PRODID = "-//Applicator//Interview Calendar//EN"


@dataclass
class IcsEvent:
    uid: str
    summary: str
    starts_at: datetime
    ends_at: datetime | None
    location: str | None
    description: str | None
    updated_at: datetime


def _utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# RFC5545 forbids C0 control chars in TEXT values except HTAB. Real interview
# data (email bodies, Outlook-synced events) carries lone CR, vertical tabs, and
# other control chars that a strict parser like Google Calendar rejects — one
# raw CR mid-value breaks line structure and the whole feed silently imports
# nothing. Drop them, keeping only TAB and normalized line breaks.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize(text: str) -> str:
    # Normalize every line-ending flavor (CRLF, lone CR, LF) to LF, then strip
    # remaining control chars so no bare control byte survives into the output.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CTRL_RE.sub("", text)


def _escape(text: str) -> str:
    return (
        _sanitize(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    # RFC5545 content-line folding at 75 octets; continuation lines start with a space.
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    out = []
    while len(data) > 75:
        cut = 75
        while (data[cut] & 0xC0) == 0x80:  # don't split a multibyte char
            cut -= 1
        out.append(data[:cut].decode("utf-8"))
        data = b" " + data[cut:]
    out.append(data.decode("utf-8"))
    return "\r\n".join(out)


def _prop(name: str, value: str) -> str:
    return _fold(f"{name}:{value}")


def _html_description(text: str) -> str:
    # HTML alt-description so calendar clients (Apple, Outlook) render URLs as
    # real anchors. Google autolinks the plaintext DESCRIPTION on its own.
    text = _sanitize(text)
    parts: list[str] = []
    pos = 0
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(_TRAIL)  # keep trailing punctuation out of the link
        parts.append(_html.escape(text[pos:m.start()]))
        safe = _html.escape(url, quote=True)
        parts.append(f'<a href="{safe}">{safe}</a>')
        pos = m.start() + len(url)
    parts.append(_html.escape(text[pos:]))
    return "".join(parts).replace("\n", "<br>")


def render_event(ev: IcsEvent) -> list[str]:
    end = ev.ends_at or (ev.starts_at + timedelta(minutes=60))
    lines = [
        "BEGIN:VEVENT",
        _prop("UID", ev.uid),
        # DTSTAMP uses updated_at (not generation time) so the feed is
        # deterministic — identical output across fetches unless the event changes.
        _prop("DTSTAMP", _utc(ev.updated_at)),
        _prop("LAST-MODIFIED", _utc(ev.updated_at)),
        _prop("DTSTART", _utc(ev.starts_at)),
        _prop("DTEND", _utc(end)),
        _prop("SUMMARY", _escape(ev.summary)),
        "STATUS:CONFIRMED",
    ]
    if ev.location:
        lines.append(_prop("LOCATION", _escape(ev.location)))
    if ev.description:
        lines.append(_prop("DESCRIPTION", _escape(ev.description)))
        html_desc = _html_description(ev.description)
        lines.append(_fold(f"X-ALT-DESC;FMTTYPE=text/html:{_escape(html_desc)}"))
    lines.append("END:VEVENT")
    return lines


def render_calendar(events: list[IcsEvent]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        f"PRODID:{PRODID}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for ev in events:
        lines.extend(render_event(ev))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
