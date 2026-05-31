import html as _html
import re
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

from app.email_ingest.confidence import Confidence, score
from app.email_ingest.models import ParsedMessage, ParsedThread
from app.llm.base import LLMClient

MAX_MESSAGES = 20

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_BR_RE = re.compile(r"(?i)<br\s*/?>")
_BLOCK_END_RE = re.compile(r"(?i)</(p|div|tr|li|h[1-6]|table)>")
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    s = _SCRIPT_STYLE_RE.sub("", html)
    s = _BR_RE.sub("\n", s)
    s = _BLOCK_END_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _best_body(msg: EmailMessage) -> str:
    if msg.is_multipart():
        plain = None
        html = None
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = part.get_content()
            elif ctype == "text/html" and html is None:
                html = part.get_content()
        if plain:
            return plain
        if html:
            return html_to_text(html)
        return ""
    content = msg.get_content()
    if msg.get_content_type() == "text/html":
        return html_to_text(content)
    return content


def extract_top_message(raw: bytes) -> tuple[EmailMessage, str]:
    msg = message_from_bytes(raw, policy=policy.default)
    return msg, _best_body(msg)


@dataclass
class Segment:
    header: str
    body: str
    kind: str = "outlook"


_OUTLOOK_FROM_RE = re.compile(r"(?im)^[ \t>]*(From|Von):[ \t]*\S")
_HEADER_LINE_RE = re.compile(
    r"(?im)^[ \t>]*(From|Von|Sent|Gesendet|To|An|Cc|Subject|Betreff):[ \t]*.*$"
)
_ATTRIB_EN_RE = re.compile(r"(?im)^[ \t>]*On\b.+?\bwrote:[ \t]*$")
_ATTRIB_DE_RE = re.compile(r"(?im)^[ \t>]*Am\b.+?\bschrieb\b.+?:[ \t]*$")
_FORWARD_RE = re.compile(
    r"(?im)^[ \t>]*(-{2,}\s*Original Message\s*-{2,}|-{2,}\s*Forwarded message\s*-{2,})[ \t]*$"
)


def _dequote(line: str) -> str:
    return re.sub(r"^[ \t]*>+[ \t]?", "", line)


def _find_separators(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return (start_line, header_end_line_exclusive, kind) for each separator."""
    seps: list[tuple[int, int, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if _FORWARD_RE.match(line):
            seps.append((i, i + 1, "forward"))
            i += 1
            continue
        if _ATTRIB_EN_RE.match(line) or _ATTRIB_DE_RE.match(line):
            seps.append((i, i + 1, "attrib"))
            i += 1
            continue
        if _OUTLOOK_FROM_RE.match(line):
            j = i
            while j < n and _HEADER_LINE_RE.match(lines[j]):
                j += 1
            seps.append((i, j, "outlook"))
            i = j
            continue
        i += 1
    return seps


def split_quoted(text: str) -> list[Segment]:
    lines = text.splitlines()
    seps = _find_separators(lines)
    if not seps:
        return []
    segs: list[Segment] = []
    for idx, (start, hdr_end, kind) in enumerate(seps):
        header = "\n".join(_dequote(line) for line in lines[start:hdr_end]).strip()
        body_start = hdr_end
        body_end = seps[idx + 1][0] if idx + 1 < len(seps) else len(lines)
        body = "\n".join(_dequote(line) for line in lines[body_start:body_end]).strip()
        segs.append(Segment(header=header, body=body, kind=kind))
    return segs


_HDR_FIELD_RE = {
    "from": re.compile(r"(?i)^(From|Von):[ \t]*(.+)$"),
    "date": re.compile(r"(?i)^(Sent|Gesendet):[ \t]*(.+)$"),
    "to": re.compile(r"(?i)^(To|An):[ \t]*(.+)$"),
    "subject": re.compile(r"(?i)^(Subject|Betreff):[ \t]*(.+)$"),
}
_ATTRIB_EN_PARSE = re.compile(
    r"(?i)^On\s+(?P<date>.+?\b\d{4}\b(?:\s+at\s+\d{1,2}:\d{2}(?:\s*[ap]m)?)?)\s+"
    r"(?P<who>.+?)\s+wrote:"
)
_ATTRIB_DE_PARSE = re.compile(r"(?i)^Am\s+(?P<date>.+?)\s+schrieb\s+(?P<who>.+?):")


def parse_quote_header(block: str) -> dict:
    out: dict = {}
    block = block.strip()
    m = _ATTRIB_EN_PARSE.match(block) or _ATTRIB_DE_PARSE.match(block)
    if m:
        name, email = parseaddr(m.group("who").strip())
        out["sender_name"] = name or (None if email else m.group("who").strip())
        out["sender_email"] = email or None
        out["date"] = m.group("date").strip()
        return out
    for line in block.splitlines():
        line = line.strip()
        if _HDR_FIELD_RE["from"].match(line):
            name, email = parseaddr(_HDR_FIELD_RE["from"].match(line).group(2))
            out["sender_name"] = name or None
            out["sender_email"] = email or None
        elif _HDR_FIELD_RE["date"].match(line):
            out["date"] = _HDR_FIELD_RE["date"].match(line).group(2).strip()
        elif _HDR_FIELD_RE["to"].match(line):
            addrs = [a for _, a in getaddresses([_HDR_FIELD_RE["to"].match(line).group(2)]) if a]
            out["to"] = addrs
        elif _HDR_FIELD_RE["subject"].match(line):
            out["subject"] = _HDR_FIELD_RE["subject"].match(line).group(2).strip()
    return out


def _top_message(msg: EmailMessage, body: str) -> ParsedMessage:
    name, email = parseaddr(msg.get("From", ""))
    recipients = [a for _, a in getaddresses(msg.get_all("To", [])) if a]
    occurred = None
    date_hdr = msg.get("Date")
    if date_hdr:
        try:
            occurred = parsedate_to_datetime(date_hdr)
        except (TypeError, ValueError):
            occurred = None
    return ParsedMessage(
        sender_name=name or None,
        sender_email=email or None,
        recipients=recipients,
        occurred_at=occurred,
        subject=msg.get("Subject") or None,
        body=body.strip(),
    )


def _segment_to_message(seg: Segment, top_subject: str | None) -> ParsedMessage:
    from app.email_ingest.llm_split import _parse_date  # reuse dateutil helper

    h = parse_quote_header(seg.header)
    return ParsedMessage(
        sender_name=h.get("sender_name"),
        sender_email=h.get("sender_email"),
        recipients=h.get("to", []),
        occurred_at=_parse_date(h.get("date", "")) if h.get("date") else None,
        subject=h.get("subject") or top_subject,
        body=seg.body,
    )


def parse_eml(raw: bytes, *, llm: LLMClient | None) -> ParsedThread:
    msg, top_text = extract_top_message(raw)
    top = _top_message(msg, top_text)
    quoted = split_quoted(top_text)
    det = [top] + [_segment_to_message(s, top.subject) for s in quoted]

    conf = score(det, top_text)
    if conf == Confidence.LOW and llm is not None:
        try:
            from app.email_ingest.llm_split import llm_split_thread

            llm_msgs = llm_split_thread(top_text, llm)
            if llm_msgs:
                # message[0] is newest: override with authoritative top headers
                llm_msgs[0].sender_name = top.sender_name
                llm_msgs[0].sender_email = top.sender_email
                llm_msgs[0].occurred_at = top.occurred_at
                llm_msgs[0].subject = top.subject
                if not llm_msgs[0].recipients:
                    llm_msgs[0].recipients = top.recipients
                return ParsedThread(messages=llm_msgs[:MAX_MESSAGES], used_llm=True)
        except Exception:  # noqa: BLE001 — graceful degrade, never hard-fail
            pass

    return ParsedThread(messages=det[:MAX_MESSAGES], used_llm=False)
