from app.crawler.httpx_fetcher import FetchResult, _html_to_text
from app.crawler.url_guard import validate_public_url


class PlaywrightFetcher:
    def __init__(self, timeout_ms: int = 20000):
        self.timeout_ms = timeout_ms

    def fetch(self, url: str) -> FetchResult:
        from playwright.sync_api import sync_playwright

        # Validate before any network activity (SSRF guard)
        validate_public_url(url)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                final_url = page.url
                # Re-validate after potential redirects
                validate_public_url(final_url)
                html = page.content()
            finally:
                browser.close()
        return FetchResult(url=final_url, status_code=200, html=html, text=_html_to_text(html))
