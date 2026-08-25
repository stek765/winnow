"""Ask the model for its judgment and know what is worth retrying.

The copy-paste loop is gone: it was the only point where things could fail
without understanding why, and on 2026-08-25 it ate a real response — copied
from terminal scrollback, which wraps and truncates long lines, it was broken
on arrival.

One loop, and the distinction that keeps it honest: **network goes down and
rate limits pass on their own; a revoked key does not.** Retrying the latter
forever is the real problem — screen frozen and no hope. On that we stop at
once and say why.
"""
from __future__ import annotations

import time
from pathlib import Path

from winnow import providers


class Fatal(RuntimeError):
    """Will not pass on its own: stopping is the right answer."""


# What time fixes. Compared on message text because the three providers
# raise different exceptions for the identical situation.
RETRY_MARKS = ("429", "rate limit", "500", "502", "503", "504",
               "timeout", "timed out", "connection", "connect", "network",
               "temporarily", "overloaded", "disconnect")

# What time does not fix, and it wins over the first list: "401
# connection refused" is a bad key, not a network coming back.
FATAL_MARKS = ("401", "403", "invalid api key", "invalid_api_key",
               "authentication", "permission", "credit balance",
               "quota exceeded", "billing")


def is_retryable(exc: Exception) -> bool:
    msg = f"{type(exc).__name__} {exc}".lower()
    if any(m in msg for m in FATAL_MARKS):
        return False
    return any(m in msg for m in RETRY_MARKS)


def backoff(attempt: int) -> float:
    """5s, 15s, 45s, 120s. Grows because hammering a broken service keeps it
    broken, and stops because beyond two minutes might as well retry by hand."""
    return min(5.0 * (3 ** (attempt - 1)), 120.0)


def ask(bundle: str, provider: str, model: str, base_url: str | None,
        on_event=None, sleep=time.sleep, complete=None,
        attempts: int = 5) -> tuple[str, int, int]:
    """The model's response and the tokens it cost.

    `complete` and `sleep` are injected: that is what makes every branch of
    this function testable without network, without keys, and without waiting.
    """
    call = complete or (lambda **kw: providers.complete(**kw))

    def say(event: str, **data) -> None:
        if on_event:
            on_event(event, data)

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            say("asking", attempt=attempt, of=attempts)
        try:
            return call(provider=provider, model=model, base_url=base_url,
                        system="", text=bundle, images=[],
                        max_tokens=16000, temperature=0.0)
        except Exception as exc:              # noqa: BLE001 — sorted later
            if not is_retryable(exc):
                raise Fatal(str(exc)) from exc
            last = exc
            if attempt == attempts:
                break
            wait = backoff(attempt)
            # Said, not silent: a frozen screen for forty-five seconds is
            # indistinguishable from a crashed program.
            say("waiting", seconds=wait, attempt=attempt, why=str(exc)[:120])
            sleep(wait)
    raise Fatal(f"{attempts} attempts, still failing: {last}")
