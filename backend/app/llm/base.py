from dataclasses import dataclass
from typing import Any, Protocol


class LLMMessage(dict):
    """Just a dict with role/content keys."""


@dataclass(frozen=True)
class RateLimit:
    """Snapshot of provider-reported rate-limit state after one call."""

    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests_s: float | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens_s: float | None = None
    retry_after_s: float | None = None


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Return assistant text. If json_schema given, response is valid JSON for it."""
        ...

    def last_rate_limit(self) -> RateLimit | None:
        """Most recent rate-limit snapshot, or None if provider doesn't expose it."""
        ...
