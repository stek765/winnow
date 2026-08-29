"""Ask for the model's judgment and know what is worth retrying."""
from __future__ import annotations

import httpx
import pytest

from winnow.judge import Fatal, ask, backoff, is_retryable


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("network is unreachable"),
    httpx.ReadTimeout("timed out"),
    httpx.RemoteProtocolError("server disconnected"),
])
def test_the_network_going_away_is_worth_waiting_for(exc):
    """Network goes down: it comes back. Waiting is the right answer."""
    assert is_retryable(exc) is True


def test_a_rate_limit_is_worth_waiting_for():
    assert is_retryable(RuntimeError("429 rate limit exceeded")) is True


def test_the_server_being_broken_is_worth_waiting_for():
    assert is_retryable(RuntimeError("503 service unavailable")) is True


@pytest.mark.parametrize("msg", [
    "401 invalid api key",
    "403 forbidden",
    "credit balance is too low",
])
def test_a_revoked_key_is_never_worth_waiting_for(msg):
    """Retrying a revoked key forever is the real problem: it will not pass
    on its own, and each attempt is wasted time on a frozen screen."""
    assert is_retryable(RuntimeError(msg)) is False


def test_the_wait_grows_so_it_does_not_hammer():
    waits = [backoff(n) for n in range(1, 5)]
    assert waits == sorted(waits) and waits[0] >= 1 and waits[-1] <= 120


def test_a_reply_that_arrives_is_returned_with_its_tokens():
    def ok(**kw):
        return "la risposta", 41000, 15000

    text, tin, tout = ask("il pacchetto", "anthropic", "m", None, complete=ok)
    assert text == "la risposta" and (tin, tout) == (41000, 15000)


def test_it_waits_and_tries_again_when_the_network_is_gone():
    calls, slept = [], []

    def flaky(**kw):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("network is unreachable")
        return "arrivata", 10, 5

    text, _, _ = ask("p", "anthropic", "m", None,
                     complete=flaky, sleep=slept.append)
    assert text == "arrivata"
    # Slept in slices now, so «Ferma» during a backoff is answered in a
    # second: what matters is the total waited, not how many naps it took.
    assert len(calls) == 3 and sum(slept) == 20


def test_it_says_it_is_waiting_instead_of_going_quiet():
    """A frozen screen for forty-five seconds is indistinguishable from a
    crashed program."""
    seen, calls = [], []

    def flaky(**kw):
        calls.append(1)
        if len(calls) < 2:
            raise httpx.ConnectError("down")
        return "ok", 1, 1

    ask("p", "anthropic", "m", None, complete=flaky, sleep=lambda s: None,
        on_event=lambda e, d: seen.append((e, d)))
    kinds = [e for e, _ in seen]
    assert "waiting" in kinds
    wait = dict(seen[kinds.index("waiting")][1])
    assert wait["seconds"] >= 1 and "attempt" in wait


def test_a_fatal_error_stops_at_once_without_waiting():
    calls, slept = [], []

    def dead(**kw):
        calls.append(1)
        raise RuntimeError("401 invalid api key")

    with pytest.raises(Fatal, match="invalid api key"):
        ask("p", "anthropic", "m", None, complete=dead, sleep=slept.append)
    assert len(calls) == 1 and slept == []


def test_it_gives_up_after_the_last_attempt_and_says_so():
    def always(**kw):
        raise httpx.ConnectError("still down")

    with pytest.raises(Fatal, match="3"):
        ask("p", "anthropic", "m", None, complete=always,
            sleep=lambda s: None, attempts=3)


def test_a_first_attempt_still_says_it_is_working():
    """A call that succeeds immediately must still announce itself: the model
    spends a minute reading forty thousand tokens, and a silent screen is
    indistinguishable from a hung one."""
    seen = []
    ask("p", "anthropic", "m", None, complete=lambda **k: ("ok", 1, 1),
        on_event=lambda e, d: seen.append(e))
    assert seen == ["asking"]


def test_a_stop_asked_before_the_call_is_not_a_failure():
    """«Ferma» pressed in the first second must not read as an error: nobody
    broke anything, they changed their mind."""
    from winnow.judge import Stopped, ask
    import pytest as _pytest

    with _pytest.raises(Stopped):
        ask("p", "anthropic", "m", None, should_stop=lambda: True,
            complete=lambda **kw: ("mai chiamato", 0, 0))


def test_a_stop_during_the_backoff_does_not_wait_out_the_backoff():
    """A two-minute wait answered in two minutes is a button that does not
    work. The sleep is sliced so the flag is seen within a second."""
    import httpx

    from winnow.judge import Stopped, ask
    import pytest as _pytest

    slept = []
    stop = {"now": False}

    def flaky(**kw):
        stop["now"] = True                 # the person presses while it waits
        raise httpx.ConnectError("network is unreachable")

    with _pytest.raises(Stopped):
        ask("p", "anthropic", "m", None, complete=flaky,
            sleep=slept.append, should_stop=lambda: stop["now"])
    assert sum(slept) <= 1                 # not the whole five seconds


def test_the_call_reports_what_has_arrived_so_far():
    """A recap of a backlog is minutes of one call. Without this the window
    said «le sto facendo leggere al modello» and then nothing at all, which is
    indistinguishable from a run that died."""
    from winnow.judge import ask

    said = []

    def slow(on_progress=None, **kw):
        for n in (500, 2600, 3000, 9000):
            on_progress(n)
        return "fatto", 10, 5

    ask("p", "anthropic", "m", None, complete=slow,
        on_event=lambda e, d: said.append((e, d)))
    # Every 2,000 characters, not every token: a log that scrolls once per
    # token is a log nobody can read.
    assert [d["chars"] for e, d in said if e == "writing"] == [2600, 9000]


def test_a_retry_does_not_carry_the_last_attempt_s_progress():
    """Counted from zero on each attempt, or the second try looks like it
    started three thousand characters in."""
    import httpx

    from winnow.judge import ask

    said = []
    calls = []

    def flaky(on_progress=None, **kw):
        calls.append(1)
        on_progress(2500)
        if len(calls) == 1:
            raise httpx.ConnectError("network is unreachable")
        return "fatto", 10, 5

    ask("p", "anthropic", "m", None, complete=flaky, sleep=lambda s: None,
        on_event=lambda e, d: said.append((e, d)))
    assert [d["chars"] for e, d in said if e == "writing"] == [2500, 2500]
