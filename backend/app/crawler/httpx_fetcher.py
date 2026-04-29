from dataclasses import dataclass

import httpx


@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str
    text: str


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _html_to_text(html: str) -> str:
    import re
    no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    no_tags = re.sub(r"<[^>]+>", " ", no_scripts)
    return re.sub(r"\s+", " ", no_tags).strip()


class HttpxFetcher:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch(self, url: str) -> FetchResult:
        with httpx.Client(
            timeout=self.timeout, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            r = client.get(url)
            r.raise_for_status()
        return FetchResult(
            url=url, status_code=r.status_code, html=r.text, text=_html_to_text(r.text)
        )
