from collections.abc import Callable


class FakeLLM:
    def __init__(self, handler: Callable[[list[dict], dict | None], str] | None = None):
        self.calls: list[tuple[list[dict], dict | None, float]] = []
        self.handler = handler or (lambda msgs, schema: "FAKE_RESPONSE")

    def complete(self, messages, *, json_schema=None, temperature=0.2):
        self.calls.append((messages, json_schema, temperature))
        return self.handler(messages, json_schema)
