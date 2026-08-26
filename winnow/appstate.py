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
from datetime import datetime, timedelta
from pathlib import Path

READY = "ready"
NOTHING_NEW = "nothing_new"
BUSY = "busy"
LOGGED_OUT = "logged_out"
BRAKE = "brake"

# Past this, the daily job stopped and nobody noticed — which is the failure
# winnow itself exists to prevent, so it is said out loud rather than left to
# be inferred from a date.
STALE_AFTER = timedelta(hours=36)


def _stale(last_collect: str | None, now: datetime) -> bool:
    """Never collected and collected long ago are different sentences."""
    if not last_collect:
        return False
    try:
        when = datetime.fromisoformat(last_collect)
    except ValueError:
        return False
    return now - when > STALE_AFTER


def home(facts: dict, now: datetime | None = None) -> dict:
    """One face, one sentence, one button. Never an empty screen."""
    now = now or datetime.now()
    out = {
        "spend_usd": round(facts.get("spend_usd", 0.0), 4),
        "stale": _stale(facts.get("last_collect"), now),
        "last_collect": facts.get("last_collect"),
        "pending_posts": facts.get("pending_posts", 0),
        "pending_days": facts.get("pending_days", 0),
        # The chain, so the screen can show what winnow *did* and not only how
        # much is queued. The middle number is the one that matters: a count of
        # posts describes a bookmark folder, a count of names checked at the
        # source describes this tool.
        "pending_things": facts.get("pending_things", 0),
        "pending_checked": facts.get("pending_checked", 0),
        "last_recap": facts.get("last_recap"),
    }

    running = facts.get("running")
    if running:
        done, of = running.get("done", 0), running.get("of", 0)
        return {**out, "state": BUSY, "action": "stop", "button": "Ferma",
                "headline": f"{done} su {of}",
                "detail": f"${facts.get('spend_usd', 0):.2f} finora",
                "consequence": "Quello che ha già fatto resta: "
                               "riprende da dove si ferma."}

    if not facts.get("logged_in", True):
        return {**out, "state": LOGGED_OUT, "action": "login",
                "button": "Rientra",
                "headline": "Instagram ha chiuso la sessione",
                "detail": "Finché non rientri non arriva niente di nuovo.",
                "consequence": "Apre Instagram in una finestra: entri a mano, "
                               "una volta, e winnow riusa quella sessione."}

    if facts.get("halted"):
        return {**out, "state": BRAKE, "action": "reset-halt",
                "button": "Riparti", "headline": "Freno tirato",
                "detail": facts.get("halt_reason")
                or "La spesa ha superato il limite della settimana.",
                "consequence": "Toglie il fermo e rimette winnow in moto. "
                               "La spesa già fatta resta contata."}

    posts = facts.get("pending_posts", 0)
    if posts:
        days = facts.get("pending_days", 0)
        day_word = "giorno" if days == 1 else "giorni"
        return {**out, "state": READY, "action": "recap",
                "button": "Fai il recap",
                "headline": f"{posts} post da giudicare",
                "detail": f"{days} {day_word} non ancora giudicati",
                "consequence": f"Manda a un modello i fatti di {days} "
                               f"{day_word} insieme al tuo profilo, e apre "
                               "una pagina con cosa passa e cosa no."}

    return {**out, "state": NOTHING_NEW, "action": "collect",
            "button": "Raccogli ora",
            "headline": "Niente di nuovo dall'ultimo recap",
            "detail": "Un recap adesso costerebbe e non direbbe niente.",
            "consequence": "Apre i post che hai salvato su Instagram, legge "
                           "le slide e cerca alla fonte i nomi che trova."}


def read_facts(state_dir: Path, findings_dir: Path, judged: Path,
               browser_profile: Path, now: datetime | None = None,
               running: dict | None = None,
               recaps: Path | None = None) -> dict:
    """The only part of this module that touches the filesystem.

    Kept apart so `home()` stays pure: every face above is provable from a
    dict, with no directory to build first.
    """
    from winnow.budget import is_halted, weekly_spend
    from winnow.window import last_judged, pending_files

    now = now or datetime.now()
    files = pending_files(findings_dir, last_judged(judged))
    posts = things = checked = 0
    for f in files:
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A corrupt day is skipped, not fatal: the same tolerance
            # `load_days` already applies when building a bundle.
            continue
        for post in day.get("posts", []):
            posts += 1
            for thing in post.get("entities") or []:
                things += 1
                # Only a real answer from a source counts. A rate limit and a
                # 404 are both "not checked" here, which is the same line the
                # rest of winnow refuses to blur.
                if (thing.get("verification") or {}).get("checked"):
                    checked += 1

    everything = sorted(findings_dir.glob("*.json")) if findings_dir.is_dir() else []
    last_collect = None
    if everything:
        last_collect = datetime.fromtimestamp(
            everything[-1].stat().st_mtime).isoformat(timespec="seconds")

    # Named by its week, not by its mtime: the file name is the week that was
    # judged, while the timestamp is when the file happened to be written.
    last_recap = None
    if recaps and recaps.is_dir():
        pages = sorted(recaps.glob("*.answer.html"))
        if pages:
            last_recap = pages[-1].name.replace(".answer.html", "")

    return {
        "halted": is_halted(state_dir),
        # The saved browser profile *is* the session: no directory, no login.
        "logged_in": browser_profile.is_dir(),
        "running": running,
        "pending_posts": posts,
        "pending_days": len(files),
        "pending_things": things,
        "pending_checked": checked,
        "last_recap": last_recap,
        "last_collect": last_collect,
        "spend_usd": weekly_spend(state_dir / "spend.json", now),
    }
