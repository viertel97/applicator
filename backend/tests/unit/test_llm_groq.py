import json

import httpx
import respx

from app.llm.groq import GroqClient


def test_groq_plain():
    client = GroqClient(api_key="k", model="gpt-oss", base_url="https://api.groq.com/openai/v1")
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "hello"}}],
                },
            )
        )
        out = client.complete([{"role": "user", "content": "hi"}])
    assert out == "hello"
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "gpt-oss"


def test_groq_json_schema():
    client = GroqClient(api_key="k", model="gpt-oss", base_url="https://api.groq.com/openai/v1")
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"a":1}'}}]},
            )
        )
        out = client.complete(
            [{"role": "user", "content": "hi"}],
            json_schema={"type": "object", "properties": {"a": {"type": "integer"}}},
        )
    assert out == '{"a":1}'
    body = json.loads(route.calls.last.request.content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "additionalProperties": False,
        "required": ["a"],
    }


def test_groq_parse_duration():
    from app.llm.groq import _parse_duration

    assert _parse_duration("7.66s") == 7.66
    assert _parse_duration("2m59.56s") == 179.56
    assert _parse_duration("250ms") == 0.25
    assert _parse_duration("1h2m3s") == 3723.0
    assert _parse_duration(None) is None
    assert _parse_duration("garbage") is None
    assert _parse_duration("") is None


def test_groq_parses_rate_limit_headers():
    client = GroqClient(api_key="k", model="m", base_url="https://api.groq.com/openai/v1")
    headers = {
        "x-ratelimit-limit-requests": "14400",
        "x-ratelimit-remaining-requests": "14370",
        "x-ratelimit-reset-requests": "2m59.56s",
        "x-ratelimit-limit-tokens": "8000",
        "x-ratelimit-remaining-tokens": "7997",
        "x-ratelimit-reset-tokens": "7.66s",
    }
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                headers=headers,
                json={"choices": [{"message": {"content": "x"}}]},
            )
        )
        client.complete([{"role": "user", "content": "hi"}])
    rl = client.last_rate_limit()
    assert rl is not None
    assert rl.limit_requests == 14400
    assert rl.remaining_requests == 14370
    assert rl.reset_requests_s == 179.56
    assert rl.limit_tokens == 8000
    assert rl.remaining_tokens == 7997
    assert rl.reset_tokens_s == 7.66
    assert rl.retry_after_s is None


def test_last_rate_limit_none_before_first_call():
    client = GroqClient(api_key="k", model="m", base_url="https://api.groq.com/openai/v1")
    assert client.last_rate_limit() is None


def test_groq_429_retries_once_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.llm.groq.time.sleep", lambda s: sleeps.append(s))

    client = GroqClient(api_key="k", model="m", base_url="https://api.groq.com/openai/v1")
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/chat/completions").mock(
            side_effect=[
                httpx.Response(429, headers={"retry-after": "1"}, text="rl"),
                httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
            ]
        )
        out = client.complete([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert sleeps == [1.0]


def test_groq_429_twice_raises(monkeypatch):
    monkeypatch.setattr("app.llm.groq.time.sleep", lambda s: None)

    client = GroqClient(api_key="k", model="m", base_url="https://api.groq.com/openai/v1")
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(429, headers={"retry-after": "1"}, text="rl"),
        )
        try:
            client.complete([{"role": "user", "content": "hi"}])
        except httpx.HTTPStatusError as e:
            assert e.response.status_code == 429
        else:
            raise AssertionError("expected HTTPStatusError")


def test_groq_429_respects_max_wait(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.llm.groq.time.sleep", lambda s: sleeps.append(s))

    client = GroqClient(
        api_key="k", model="m",
        base_url="https://api.groq.com/openai/v1",
        max_429_wait_s=5.0,
    )
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(429, headers={"retry-after": "999"}, text="rl"),
        )
        try:
            client.complete([{"role": "user", "content": "hi"}])
        except httpx.HTTPStatusError:
            pass
        else:
            raise AssertionError("expected HTTPStatusError")
    assert sleeps == []  # never slept because indicated wait exceeded the cap


def test_groq_429_falls_back_to_reset_tokens(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.llm.groq.time.sleep", lambda s: sleeps.append(s))

    client = GroqClient(api_key="k", model="m", base_url="https://api.groq.com/openai/v1")
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/chat/completions").mock(
            side_effect=[
                httpx.Response(
                    429,
                    headers={"x-ratelimit-reset-tokens": "2.5s"},
                    text="rl",
                ),
                httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
            ]
        )
        out = client.complete([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert sleeps == [2.5]
