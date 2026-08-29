"""Which face the home screen is wearing, and the one thing to press.

The window never decides anything (spec §7.3): it renders a state and sends
commands back. So the decision lives here, in a pure function over facts read
from disk — which is what keeps it testable without a browser, an API key, or
a cent of spend, and what lets the shell be swapped later without moving any
judgement out of Python.

The order the faces are checked in is the whole design:

  running  →  logged out  →  brake  →  work to do  →  nothing new

A run in flight wins over everything, because while something is happening the
only honest offer is to stop it. A dead Instagram session wins over having
posts to judge, because with the session gone nothing new will ever arrive and
offering a recap sends the reader down a path that ends nowhere. The brake
comes before work for the same reason: the work would refuse to start.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from winnow.i18n import DEFAULT, STRINGS, t

READY = "ready"
NOTHING_NEW = "nothing_new"
BUSY = "busy"
LOGGED_OUT = "logged_out"
BRAKE = "brake"

# Past this, the daily job stopped and nobody noticed — which is the failure
# winnow itself exists to prevent, so it is said out loud rather than left to
# be inferred from a date.
STALE_AFTER = timedelta(hours=36)

# A findings file is named after its day. Anything else in that folder is not
# one, and must not become half of a date range.
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _stale(last_collect: str | None, now: datetime) -> bool:
    """Never collected and collected long ago are different sentences."""
    if not last_collect:
        return False
    try:
        when = datetime.fromisoformat(last_collect)
    except ValueError:
        return False
    return now - when > STALE_AFTER


def _span(facts: dict, lang: str) -> str:
    from winnow.harvest import say_day

    first, last = facts.get("pending_from"), facts.get("pending_to")
    if not first or not last:
        days = facts.get("pending_days", 0)
        key = "home.days_pending_one" if days == 1 else "home.days_pending"
        return t(key, lang, n=days)
    if first == last:
        return t("home.collected_on", lang, day=say_day(first, lang))
    a, b = say_day(first, lang), say_day(last, lang)
    # The month said once when both dates share it — and the month is at the
    # other end of the phrase in English, so «which word is the month» cannot
    # be a fixed index. `23 e 24 agosto`, `August 23 and 27`.
    month = (lambda d: d.split()[-1] if lang == "it" else d.split()[0])
    day = (lambda d: d.split()[0] if lang == "it" else d.split()[-1])
    if month(a) == month(b):
        if lang == "it":
            a = day(a)
        else:
            b = day(b)
    return t("home.collected_between", lang, a=a, b=b)


def home(facts: dict, now: datetime | None = None, lang: str = DEFAULT) -> dict:
    """One face, one sentence, one button. Never an empty screen."""
    now = now or datetime.now()
    out = {
        "spend_usd": round(facts.get("spend_usd", 0.0), 4),
        "stale": _stale(facts.get("last_collect"), now),
        "last_collect": facts.get("last_collect"),
        "pending_posts": facts.get("pending_posts", 0),
        "pending_days": facts.get("pending_days", 0),
        "pending_from": facts.get("pending_from"),
        "pending_to": facts.get("pending_to"),
    }

    running = facts.get("running")
    if running:
        # «22 su 0» — which is what a count of events over a total nobody
        # knows produces — is the sentence of a program that has lost track of
        # itself. What kind of run is going is a fact; how far along it is
        # is not, and the strip under the button says that part properly.
        kind = running.get("kind")
        key = (f"home.busy.{kind}" if f"home.busy.{kind}" in STRINGS
               else "home.busy.other")
        return {**out, "state": BUSY, "action": "stop",
                "button": t("home.stop", lang),
                "headline": t(key, lang),
                "detail": t("home.busy.spent", lang,
                            usd=f"{facts.get('spend_usd', 0):.2f}")}

    if not facts.get("logged_in", True):
        return {**out, "state": LOGGED_OUT, "action": "login",
                "button": t("home.login", lang),
                "headline": t("home.logged_out", lang),
                "detail": t("home.logged_out.detail", lang)}

    if facts.get("halted"):
        return {**out, "state": BRAKE, "action": "reset-halt",
                "button": t("home.restart", lang),
                "headline": t("home.brake", lang),
                "detail": facts.get("halt_reason")
                or t("home.brake.detail", lang)}

    posts = facts.get("pending_posts", 0)
    if posts:
        # One face, one sentence, one button — and one quiet way out of it.
        # The scheduled run is once a day, so somebody who has just saved
        # something has no way to say «now» except waiting until tomorrow;
        # before this, the only path was a terminal. It is a second action and
        # not a second button: it never competes with the one that matters.
        key = "home.ready.one" if posts == 1 else "home.ready"
        return {**out, "state": READY, "action": "recap",
                "button": t("home.recap", lang), "also": "collect",
                "also_button": t("home.collect_now", lang),
                "headline": t(key, lang, n=posts),
                "detail": _span(facts, lang)}

    # It used to say «Un recap adesso costerebbe e non direbbe niente»:
    # an argument against a thing nobody had asked to do, on the one screen
    # where there is nothing wrong. What a reader needs here is the state of
    # play and the one move available, which is the button right underneath.
    return {**out, "state": NOTHING_NEW, "action": "collect",
            "button": t("home.collect_now", lang),
            "headline": t("home.nothing", lang),
            "detail": t("home.nothing.detail", lang)}


def read_facts(state_dir: Path, findings_dir: Path, judged: Path,
               browser_profile: Path, now: datetime | None = None,
               running: dict | None = None) -> dict:
    """The only part of this module that touches the filesystem.

    Kept apart so `home()` stays pure: every face above is provable from a
    dict, with no directory to build first.
    """
    from winnow.budget import is_halted, weekly_spend
    from winnow.window import last_judged, pending_files

    now = now or datetime.now()
    files = pending_files(findings_dir, last_judged(judged))
    days = sorted(f.stem for f in files if DAY_RE.match(f.stem))
    posts = 0
    for f in files:
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A corrupt day is skipped, not fatal: the same tolerance
            # `load_days` already applies when building a bundle.
            continue
        posts += len(day.get("posts", []))

    everything = sorted(findings_dir.glob("*.json")) if findings_dir.is_dir() else []
    last_collect = None
    if everything:
        last_collect = datetime.fromtimestamp(
            everything[-1].stat().st_mtime).isoformat(timespec="seconds")

    return {
        "halted": is_halted(state_dir),
        # The saved browser profile *is* the session: no directory, no login.
        "logged_in": browser_profile.is_dir(),
        "running": running,
        "pending_posts": posts,
        "pending_days": len(files),
        "pending_from": days[0] if days else None,
        "pending_to": days[-1] if days else None,
        "last_collect": last_collect,
        "spend_usd": weekly_spend(state_dir / "spend.json", now),
    }
