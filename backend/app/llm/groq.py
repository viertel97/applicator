import re
import time
from typing import Any

import httpx

from app.llm.base import RateLimit


_DURATION_RE = re.compile(
    r"^(?:(?P<h>\d+(?:\.\d+)?)h)?"
    r"(?:(?P<m>\d+(?:\.\d+)?)m(?!s))?"
    r"(?:(?P<s>\d+(?:\.\d+)?)s)?"
    r"(?:(?P<ms>\d+(?:\.\d+)?)ms)?$"
)


def _parse_duration(value: str | None) -> float | None:
    if not value:
        return None
    match = _DURATION_RE.match(value.strip())
    if not match:
        return None
    parts = match.groupdict()
    if not any(parts.values()):
        return None
    total = 0.0
    if parts["h"]:
        total += float(parts["h"]) * 3600
    if parts["m"]:
        total += float(parts["m"]) * 60
    if parts["s"]:
        total += float(parts["s"])
    if parts["ms"]:
        total += float(parts["ms"]) / 1000
    return total


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _rate_limit_from_headers(headers: httpx.Headers) -> RateLimit:
    return RateLimit(
        limit_requests=_parse_int(headers.get("x-ratelimit-limit-requests")),
        remaining_requests=_parse_int(headers.get("x-ratelimit-remaining-requests")),
        reset_requests_s=_parse_duration(headers.get("x-ratelimit-reset-requests")),
        limit_tokens=_parse_int(headers.get("x-ratelimit-limit-tokens")),
        remaining_tokens=_parse_int(headers.get("x-ratelimit-remaining-tokens")),
        reset_tokens_s=_parse_duration(headers.get("x-ratelimit-reset-tokens")),
        retry_after_s=_parse_duration(headers.get("retry-after"))
        or _parse_int_as_seconds(headers.get("retry-after")),
    )


def _parse_int_as_seconds(value: str | None) -> float | None:
    """`retry-after` may be a bare integer (seconds) per RFC 7231."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


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
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 60.0,
        max_429_wait_s: float = 30.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_429_wait_s = max_429_wait_s
        self._last_rate_limit: RateLimit | None = None

    def last_rate_limit(self) -> RateLimit | None:
        return self._last_rate_limit

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
            r = self._post(client, payload)
            if r.status_code == 429:
                wait = self._pick_retry_wait(r)
                if wait is None or wait > self.max_429_wait_s:
                    self._raise(r)
                time.sleep(wait)
                r = self._post(client, payload)
            if r.is_error:
                self._raise(r)
            data = r.json()
        return data["choices"][0]["message"]["content"]

    def _post(self, client: httpx.Client, payload: dict) -> httpx.Response:
        r = client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        self._last_rate_limit = _rate_limit_from_headers(r.headers)
        return r

    def _pick_retry_wait(self, r: httpx.Response) -> float | None:
        rl = self._last_rate_limit
        if rl is None:
            return None
        candidates = [
            v for v in (rl.retry_after_s, rl.reset_tokens_s, rl.reset_requests_s)
            if v is not None
        ]
        if not candidates:
            return None
        return min(candidates)

    @staticmethod
    def _raise(r: httpx.Response) -> None:
        raise httpx.HTTPStatusError(
            f"{r.status_code} {r.reason_phrase}: {r.text}",
            request=r.request,
            response=r,
        )
