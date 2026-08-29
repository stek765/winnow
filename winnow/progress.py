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

    # --- il recap --------------------------------------------------------
    if event == "sliced":
        return (f"  slicing    {data.get('days', 0)} of {data.get('of', 0)} "
                f"days · {data.get('left', 0)} things left for next time")

    if event == "bundling":
        days = data.get("days", 0)
        day_word = "day" if days == 1 else "days"
        return (f"  bundling   {days} {day_word} · {data.get('posts', 0)} "
                f"posts · {data.get('things', 0)} things")
    if event == "asking":
        attempt = data.get("attempt", 1)
        # Show attempt number only when it is not the first: saying it always
        # signals a problem that did not happen on the first run.
        if attempt <= 1:
            return "  asking     the model is reading it…"
        return f"  asking     attempt {attempt} of {data.get('of', '?')}"
    if event == "writing":
        return f"  writing    {data.get('chars', 0):,} characters so far"

    if event == "waiting":
        secs = data.get("seconds", 0)
        return (f"  waiting    {secs:.0f}s before trying again "
                f"({data.get('why', 'no reason given')})")
    if event == "judged":
        binned = data.get("binned")
        tail = f" · {binned} binned" if binned is not None else ""
        return (f"  judged     {data.get('kept', 0)} of "
                f"{data.get('of', 0)}{tail} · USD {data.get('usd', 0):.2f}")
    # --- le idee ---------------------------------------------------------
    if event == "drawing":
        return (f"  drawing    {data.get('drawn', 0)} things out of "
                f"{data.get('of', 0)}, at random")
    if event == "dreamt":
        return (f"  ideas      {data.get('ideas', 0)} from "
                f"{data.get('of', 0)} things · USD {data.get('usd', 0):.2f}")

    # Said, not only printed. The CLI reads the reason off stdout; the window
    # cannot, and a run that ends with a code and no sentence leaves a spinner
    # turning over a thing that already gave up.
    if event == "failed":
        # Two different things share this name: a run that gave up (`why`) and
        # one post of fifty that could not be read (`shortcode`). Printing the
        # first wording for the second turned a skipped post into «the run
        # failed», which is a lie in the only place a reader trusts.
        if data.get("why"):
            return f"  failed     {data['why']}"
        return (f"    ✗          {data.get('shortcode', '?')} — "
                f"{data.get('error', 'unreadable')}, post skipped")

    if event == "stopped":
        done, of = data.get("done"), data.get("of")
        where = f" at {done} of {of}" if done is not None else ""
        return f"  stopped    you asked it to stop{where}"

    if event == "rendered":
        return f"  → {data.get('path', '')}"

    return ""
