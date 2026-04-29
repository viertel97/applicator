from collections.abc import Callable
from typing import Any


class FakeLLM:
    def __init__(self, handler: Callable[[list[dict], dict | None], str] | None = None):
        self.calls: list[tuple[list[dict], dict | None]] = []
        self.handler = handler or (lambda msgs, schema: "FAKE_RESPONSE")

    def complete(self, messages, *, json_schema=None, temperature=0.2):
        self.calls.append((messages, json_schema))
        return self.handler(messages, json_schema)
