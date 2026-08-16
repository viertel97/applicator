import httpx
import pytest

from app.calendar_sync.graph import (
    DeltaExpired,
    GraphClient,
    GraphRateLimited,
)


def _client(handler) -> GraphClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://graph.microsoft.com")
    return GraphClient("AT", client=http, base_url="https://graph.microsoft.com/v1.0")


def test_resolve_calendar_id_matches_by_name():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer AT"
        return httpx.Response(200, json={"value": [
            {"id": "cal-1", "name": "Calendar"},
            {"id": "cal-2", "name": "Interviews"},
        ]})

    cid = _client(handler).resolve_calendar_id("Interviews")
    assert cid == "cal-2"


def test_resolve_calendar_id_follows_pagination():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={
                "value": [{"id": "cal-1", "name": "Other"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendars?page=2",
            })
        return httpx.Response(200, json={"value": [{"id": "cal-9", "name": "Interviews"}]})

    cid = _client(handler).resolve_calendar_id("Interviews")
    assert cid == "cal-9"
    assert calls["n"] == 2


def test_resolve_calendar_id_returns_none_when_absent():
    def handler(request):
        return httpx.Response(200, json={"value": [{"id": "x", "name": "Nope"}]})

    assert _client(handler).resolve_calendar_id("Interviews") is None


def test_delta_events_collects_pages_and_returns_delta_link():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={
                "value": [{"id": "e1"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
            })
        return httpx.Response(200, json={
            "value": [{"id": "e2"}],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta-token",
        })

    events, delta = _client(handler).delta_events("cal-2")
    assert [e["id"] for e in events] == ["e1", "e2"]
    assert delta == "https://graph.microsoft.com/v1.0/delta-token"


def test_delta_events_uses_stored_delta_link():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"value": [], "@odata.deltaLink": "d2"})

    _events, delta = _client(handler).delta_events("cal-2", delta_link="https://graph/stored-delta")
    assert seen["url"] == "https://graph/stored-delta"
    assert delta == "d2"


def test_delta_events_raises_on_410():
    def handler(request):
        return httpx.Response(410, json={"error": {"code": "syncStateExpired"}})

    with pytest.raises(DeltaExpired):
        _client(handler).delta_events("cal-2", delta_link="https://graph/stale")


def test_get_raises_rate_limited_with_retry_after():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "42"}, json={})

    with pytest.raises(GraphRateLimited) as exc:
        _client(handler).resolve_calendar_id("Interviews")
    assert exc.value.retry_after == 42
