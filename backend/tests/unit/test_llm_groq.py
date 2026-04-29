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
        mock.post("/chat/completions").mock(
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
