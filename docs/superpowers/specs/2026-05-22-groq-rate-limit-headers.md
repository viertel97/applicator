# Groq Rate-Limit Header Awareness — Design Spec
Date: 2026-05-22

## Motivation

`GroqClient.complete()` currently ignores Groq's rate-limit response
headers. The backfill worker therefore throttles itself with a fixed
`_RATE_LIMIT_SLEEP = 1.0` between rows and has no defense against HTTP
429. Two concrete problems follow:

1. Under-utilisation — on a small TPM budget the fixed sleep is too
   slow; on a large budget it is too cautious. Either way we leave
   throughput on the floor.
2. No graceful 429 handling — when a burst (e.g. a large backfill
   over many empty fields) trips Groq's per-minute window, requests
   fail loudly instead of waiting `retry-after` seconds and retrying.

This spec covers parsing the documented Groq rate-limit headers,
exposing them to callers, and using them to drive adaptive throttling
and 429 retry in the backfill loop.

---

## 1. Reference: Groq Headers

Source: https://console.groq.com/docs/rate-limits

| Header                          | Meaning                                  |
|---------------------------------|------------------------------------------|
| `retry-after`                   | Seconds to wait after a 429              |
| `x-ratelimit-limit-requests`    | RPD (Requests Per Day) cap               |
| `x-ratelimit-limit-tokens`      | TPM (Tokens Per Minute) cap              |
| `x-ratelimit-remaining-requests`| RPD remaining                            |
| `x-ratelimit-remaining-tokens`  | TPM remaining                            |
| `x-ratelimit-reset-requests`    | Time until RPD window resets (e.g. `2m59.56s`) |
| `x-ratelimit-reset-tokens`      | Time until TPM window resets (e.g. `7.66s`)    |

Reset values are duration strings: `<m>m<s>s` or `<s>s` or `<ms>ms`.

---

## 2. LLM Client Changes

### `app/llm/base.py`

Introduce a small value object so all clients (Groq, future ones) can
return rate-limit context without changing the existing `complete()`
return type for callers that don't care:

```python
@dataclass(frozen=True)
class RateLimit:
    limit_requests: int | None
    remaining_requests: int | None
    reset_requests_s: float | None
    limit_tokens: int | None
    remaining_tokens: int | None
    reset_tokens_s: float | None
    retry_after_s: float | None  # only set on 429
```

Add to the `LLMClient` protocol:

```python
def last_rate_limit(self) -> RateLimit | None: ...
```

Default implementation (other providers): always `None`. No behaviour
change.

### `app/llm/groq.py`

After every `httpx` response (success or error) parse the headers and
store the result on the instance:

- `_parse_duration("7.66s") -> 7.66`
- `_parse_duration("2m59.56s") -> 179.56`
- `_parse_duration("250ms") -> 0.25`
- Missing / malformed header → `None`

`complete()` keeps returning `str` as today. `last_rate_limit()`
returns the freshly-parsed `RateLimit` from the most recent call.

### 429 handling inside `complete()`

When the server returns 429:

1. Parse `retry-after`. If absent fall back to `reset_tokens_s` or
   `reset_requests_s` (whichever is shorter and present), else 5 s.
2. Sleep that duration.
3. Retry once. A second 429 raises an exception.

Maximum total wait per call is bounded by an instance attribute
`max_429_wait_s = 30.0`. If the indicated wait exceeds the bound the
client raises immediately so callers can decide whether to defer.

---

## 3. Backfill Loop Adaptation

`app/tasks/backfill.py::_run` currently does
`time.sleep(_RATE_LIMIT_SLEEP)` between every row. Replace with a
helper that consults the client after each successful call:

```python
def _adaptive_sleep(llm) -> None:
    rl = llm.last_rate_limit()
    if rl is None:
        return  # provider doesn't expose limits
    # Conservative: when fewer than 10% tokens remain, sleep until reset.
    if (
        rl.remaining_tokens is not None
        and rl.limit_tokens
        and rl.remaining_tokens / rl.limit_tokens < 0.10
        and rl.reset_tokens_s is not None
    ):
        time.sleep(min(rl.reset_tokens_s + 0.5, 60.0))
        return
    # Otherwise no sleep — let the client's 429 retry handle bursts.
```

Remove the hard-coded `_RATE_LIMIT_SLEEP` constant.

Behaviour:
- Small worker, plenty of headroom → no sleeps, fast drain.
- Approaching TPM ceiling → wait through one reset window then continue.
- Exceeded → client retries once on 429; second 429 surfaces as the
  existing per-row `try/except` already handles (logged + skip).

---

## 4. Test Plan

Unit tests, all using `respx` to mock httpx:

- `test_groq_parses_rate_limit_headers` — happy path, all headers
  present, assert `RateLimit` fields decoded.
- `test_groq_duration_formats` — `"7.66s"`, `"2m59.56s"`, `"250ms"`,
  malformed → `None`.
- `test_groq_429_retries_once_then_succeeds` — first response 429 with
  `retry-after: 1`, second 200; assert one retry, total wait close to 1 s.
- `test_groq_429_twice_raises` — both 429 → raises.
- `test_groq_429_respects_max_wait` — `retry-after: 999` and
  `max_429_wait_s=30` → raises immediately, no sleep.
- `test_last_rate_limit_returns_none_before_first_call`.
- `test_backfill_adaptive_sleep_triggers_at_low_remaining` — mock
  `last_rate_limit()` to return `<10%` remaining → asserts `time.sleep`
  was called with the reset value.

Integration: extend `tests/integration/test_backfill.py` with a
respx-mocked Groq endpoint to verify the loop survives one injected 429.

---

## 5. Non-Goals

- No per-tenant accounting. One worker process, one Groq key.
- No persistent state. Rate-limit info is in-memory on the client only.
- No proactive token estimation on the request side — we react to
  server-reported remaining tokens rather than predicting cost.
- Other providers untouched. Only `GroqClient` parses headers; the
  protocol method exists so a future OpenAI/Anthropic client can opt in.

---

## 6. Rollout

Single backend deploy. No DB or migration changes. Backwards-compatible
for any caller using `complete()` — they ignore the new method.
