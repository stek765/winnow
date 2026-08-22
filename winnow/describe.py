"""What a thing is, and what we are not sure about — as data, not as opinion.

Two lines that every entity needs before anyone can judge it:

  `what_it_is`   a plain sentence, and **where that sentence came from**. The
                 source's own description if there is one, the post's claim if
                 there is not — never silently mixed, because one is checked
                 and the other is marketing.

  `doubts`       everything the data itself says is shaky: three projects with
                 the same name, a "current" tool last touched in 2024, a
                 registry that answered nothing. Handed over, not resolved.

Both are derived, so both live here, in pure functions with no I/O — and not in
the prompt. A description a model paraphrases weekly is a different description
weekly, and cannot be checked against anything.
"""
from __future__ import annotations

from dataclasses import asdict

# A repo nobody has touched in this long is not what a post presents as new.
STALE_DAYS = 400
# A display-name match this small is far more often a homonym of a known
# project than the project itself. Measured: `NautilusTrader` resolved to a
# 3-star repo while the real one has 26,930.
SMALL_STARS = 50


def source_of(kind: str) -> str:
    return {"repo": "GitHub", "model": "HuggingFace"}.get(kind, "the source")


def what_it_is(entity: dict, verification: dict) -> dict:
    """One sentence about the thing, plus where the sentence came from."""
    checked = bool(verification.get("checked"))
    exists = verification.get("exists")
    described = (verification.get("description") or "").strip()
    claimed = (entity.get("blurb") or "").strip()
    kind = entity.get("kind", "")

    if checked and exists and described:
        return {"text": described, "from": source_of(kind), "trusted": True}
    if claimed:
        # Say it is the post talking. A caption is written to be saved, not to
        # be accurate, and the reader has to know which one they are reading.
        return {"text": claimed, "from": "the post", "trusted": False}
    if checked and exists:
        return {"text": f"no description at {source_of(kind)}",
                "from": source_of(kind), "trusted": True}
    return {"text": "", "from": "", "trusted": False}


def _age_days(last_commit: str | None, today: str) -> int | None:
    """Days between two YYYY-MM-DD strings. None when either is unusable."""
    from datetime import date

    def parse(text: str | None):
        try:
            y, m, d = (text or "")[:10].split("-")
            return date(int(y), int(m), int(d))
        except (ValueError, AttributeError):
            return None

    a, b = parse(last_commit), parse(today)
    return (b - a).days if a and b else None


def doubts(entity: dict, verification: dict, today: str = "") -> list[str]:
    """Everything the data says is shaky. Never a judgement of worth."""
    out: list[str] = []
    kind = entity.get("kind", "")
    name = entity.get("name", "?")
    checked = bool(verification.get("checked"))
    exists = verification.get("exists")
    stars = verification.get("stars")
    candidates = list(verification.get("candidates") or ())

    if not checked:
        out.append(f"not checked: {verification.get('note') or 'no source asked'}")
    elif exists is False:
        out.append(f"{source_of(kind)} has nothing under the name {name!r}")

    if candidates:
        out.append(f"{len(candidates) + 1} different things answer to this "
                   f"name — the numbers may belong to another project: "
                   f"{', '.join(candidates)}")

    if checked and exists:
        if "/" not in name and isinstance(stars, int) and stars < SMALL_STARS:
            out.append(f"matched by name only, and it is small ({stars}★): "
                       "more likely a homonym than the thing the post meant")
        age = _age_days(verification.get("last_commit"), today)
        if age is not None and age > STALE_DAYS:
            out.append(f"last touched {verification.get('last_commit')} "
                       f"({age // 30} months ago), while the post presents it "
                       "as current")
        if verification.get("archived"):
            out.append("archived by its author: it is finished, not maintained")

    if not (entity.get("blurb") or "").strip() and not verification.get("description"):
        out.append("nothing anywhere says what this is")
    return out


def describe(entity: dict, verification: dict, today: str = "") -> dict:
    """The entity, plus the two derived lines. Nothing removed."""
    return {**entity,
            "what_it_is": what_it_is(entity, verification),
            "doubts": doubts(entity, verification, today),
            "verification": verification}
