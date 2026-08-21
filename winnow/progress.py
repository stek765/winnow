"""What a run says about itself while it is running.

A collection run spends money and takes minutes, most of it waiting on GitHub's
rate limit. Saying nothing until the end is how you end up unable to tell a
working run from a hung one.

This module is pure: it turns an event into a line of text. `run.py` emits the
events, `cli.py` prints them. That split is what makes the wording testable
without a browser, an API key, or a cent of spend.
"""
from __future__ import annotations

MAX_NAMES = 4


def _names(names: list[str]) -> str:
    if not names:
        return "no concrete name"
    shown = ", ".join(names[:MAX_NAMES])
    rest = len(names) - MAX_NAMES
    return f"{shown} (+{rest})" if rest > 0 else shown


def line(event: str, data: dict) -> str:
    """One event -> one line, or "" for an event this version doesn't print.

    Unknown events are ignored on purpose: a run that already cost money must
    not die because a newer caller emitted something this function never saw.
    """
    if event == "folder":
        return (f"  folder     {data['name']} · {data['found']} posts, "
                f"{data['new']} new")

    if event == "folder_skipped":
        return f"  folder     {data['name']} · skipped, the run is already full"

    if event == "post":
        n = data["slides"]
        return (f"\n  {data['i']}/{data['n']}  @{data['account']} · "
                f"{n} slide{'' if n == 1 else 's'}")

    if event == "extracted":
        shape = {"list": "list", "news": "news"}.get(data.get("shape"), "")
        tag = f"[{shape}] " if shape else ""
        return f"    read       {tag}{_names(data['names'])}"

    if event == "verified":
        name = data["name"]
        if not data.get("checked"):
            # Never a tick and never a cross: nobody asked a source.
            return f"    ?          {name} — {data.get('note') or 'not checkable'}"
        if not data.get("exists"):
            return f"    ✗          {name} — absent at the source"
        stars = data.get("stars")
        tail = f"{stars} ★" if stars is not None else "found"
        return f"    ✓          {name} — {tail}"

    if event == "written":
        return (f"\n  written    {data['path']} · {data['entities']} entities, "
                f"{data['verified']} verified · USD {data['usd']:.4f}")

    if event == "halted":
        return f"  HALTED     {data.get('reason', '')}"

    return ""
