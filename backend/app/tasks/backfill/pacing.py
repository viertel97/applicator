"""Adaptive inter-row pacing driven by Groq rate-limit headers."""

import time

_LOW_REMAINING_FRACTION = 0.10
_MAX_ADAPTIVE_SLEEP_S = 60.0


def _adaptive_sleep(llm) -> None:
    last = getattr(llm, "last_rate_limit", None)
    if not callable(last):
        return
    rl = last()
    if rl is None:
        return
    if (
        rl.remaining_tokens is None
        or not rl.limit_tokens
        or rl.reset_tokens_s is None
    ):
        return
    if rl.remaining_tokens / rl.limit_tokens >= _LOW_REMAINING_FRACTION:
        return
    time.sleep(min(rl.reset_tokens_s + 0.5, _MAX_ADAPTIVE_SLEEP_S))
