from typing import Protocol

from app.crawler.httpx_fetcher import FetchResult, HttpxFetcher
from app.crawler.playwright_fetcher import PlaywrightFetcher


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


_JS_MARKERS = ("Please enable JavaScript", "noscript", "loading...")
_MIN_TEXT_LEN = 500


def _looks_js_only(text: str) -> bool:
    if len(text) < _MIN_TEXT_LEN:
        return True
    lower = text.lower()
    return any(m.lower() in lower for m in _JS_MARKERS)


class HybridFetcher:
    def __init__(self, primary: Fetcher | None = None, fallback: Fetcher | None = None):
        self.primary = primary or HttpxFetcher()
        self.fallback = fallback or PlaywrightFetcher()

    def fetch(self, url: str) -> FetchResult:
        try:
            r = self.primary.fetch(url)
            if not _looks_js_only(r.text):
                return r
        except Exception:
            pass
        return self.fallback.fetch(url)
