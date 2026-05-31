import html as _html
import re
from email import message_from_bytes, policy
from email.message import EmailMessage

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
