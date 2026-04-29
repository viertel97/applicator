from app.crawler.fetcher import HybridFetcher
from app.crawler.httpx_fetcher import FetchResult
from tests.fakes.fetcher import FakeFetcher


def _result(text: str = "x" * 1000) -> FetchResult:
    return FetchResult(url="u", status_code=200, html=f"<p>{text}</p>", text=text)


def test_uses_primary_when_ok():
    primary = FakeFetcher(result=_result())
    fallback = FakeFetcher(result=_result("fallback"))
    out = HybridFetcher(primary=primary, fallback=fallback).fetch("u")
    assert out.text.startswith("x")
    assert primary.calls == ["u"]
    assert fallback.calls == []


def test_falls_back_when_primary_short():
    primary = FakeFetcher(result=FetchResult(url="u", status_code=200, html="x", text="short"))
    fallback = FakeFetcher(result=_result("fallback ok " * 100))
    out = HybridFetcher(primary=primary, fallback=fallback).fetch("u")
    assert "fallback ok" in out.text


def test_falls_back_when_primary_raises():
    primary = FakeFetcher(error=RuntimeError("boom"))
    fallback = FakeFetcher(result=_result("fb " * 200))
    out = HybridFetcher(primary=primary, fallback=fallback).fetch("u")
    assert out.text.startswith("fb")
