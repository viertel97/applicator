from typing import Any, Protocol


class LLMMessage(dict):
    """Just a dict with role/content keys."""


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
