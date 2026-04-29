from app.crawler.httpx_fetcher import FetchResult


class FakeFetcher:
    def __init__(self, result: FetchResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result
