from app.crawler.httpx_fetcher import FetchResult, _html_to_text


class PlaywrightFetcher:
    def __init__(self, timeout_ms: int = 20000):
        self.timeout_ms = timeout_ms

    def fetch(self, url: str) -> FetchResult:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                html = page.content()
            finally:
                browser.close()
        return FetchResult(url=url, status_code=200, html=html, text=_html_to_text(html))
