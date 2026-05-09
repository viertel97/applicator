from typing import Any

import httpx


def _enforce_strict(schema: Any) -> Any:
    if isinstance(schema, dict):
        out = {k: _enforce_strict(v) for k, v in schema.items()}
        if out.get("type") == "object" and isinstance(out.get("properties"), dict):
            out.setdefault("additionalProperties", False)
            out["required"] = list(out["properties"].keys())
        return out
    if isinstance(schema, list):
        return [_enforce_strict(v) for v in schema]
    return schema


class GroqClient:
    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "schema",
                    "schema": _enforce_strict(json_schema),
                    "strict": True,
                },
            }
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            if r.is_error:
                raise httpx.HTTPStatusError(
                    f"{r.status_code} {r.reason_phrase}: {r.text}",
                    request=r.request,
                    response=r,
                )
            data = r.json()
        return data["choices"][0]["message"]["content"]
