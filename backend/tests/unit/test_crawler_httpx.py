import httpx
import pytest
import respx

import app.crawler.httpx_fetcher as httpx_fetcher_mod
from app.crawler.httpx_fetcher import FetchResult, HttpxFetcher


def _noop_validate(url: str) -> None:
    """Bypass SSRF guard for tests that use respx mocking."""


def test_httpx_success(monkeypatch):
    monkeypatch.setattr(httpx_fetcher_mod, "validate_public_url", _noop_validate)
    f = HttpxFetcher(timeout=2.0)
    with respx.mock(base_url="https://x.test") as mock:
        mock.get("/job/1").mock(return_value=httpx.Response(200, html="<h1>Hello</h1><p>Body</p>"))
        result = f.fetch("https://x.test/job/1")
    assert isinstance(result, FetchResult)
    assert result.status_code == 200
    assert "Hello" in result.text
    assert result.html.startswith("<")


def test_httpx_non_200_raises_for_status(monkeypatch):
    monkeypatch.setattr(httpx_fetcher_mod, "validate_public_url", _noop_validate)
    f = HttpxFetcher(timeout=2.0)
    with respx.mock(base_url="https://x.test") as mock:
        mock.get("/x").mock(return_value=httpx.Response(404, html=""))
        with pytest.raises(httpx.HTTPStatusError):
            f.fetch("https://x.test/x")
