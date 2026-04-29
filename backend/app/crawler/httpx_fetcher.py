from dataclasses import dataclass

import httpx

from app.crawler.url_guard import validate_public_url

_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_REDIRECTS = 5


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
        # Validate before any network activity (SSRF guard)
        validate_public_url(url)

        current_url = url
        hops = 0

        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=False,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            while True:
                r = client.get(current_url)
                if r.is_redirect:
                    hops += 1
                    if hops > _MAX_REDIRECTS:
                        raise ValueError(f"Too many redirects (>{_MAX_REDIRECTS}) for {url}")
                    next_url = r.headers.get("location", "")
                    # Re-validate each redirect destination
                    validate_public_url(next_url)
                    current_url = next_url
                    continue
                break

        r.raise_for_status()

        # Enforce max body size (read already-buffered content)
        if len(r.content) > _MAX_BODY_BYTES:
            raise ValueError(
                f"Response body exceeds {_MAX_BODY_BYTES // (1024 * 1024)} MB limit for {url}"
            )

        html = r.text
        return FetchResult(
            url=current_url, status_code=r.status_code, html=html, text=_html_to_text(html)
        )
