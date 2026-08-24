"""Block 1 of the recap: the week's facts, arranged.

The findings on disk are one file per day, one entry per post, and the same
project named on four different days is four entries. Handed over raw that is
360 KB of JSON in which the same twenty things repeat, and the part that
actually has to be read — what a thing is and whether it is real — is buried
in a field somewhere down the middle.

So this module rearranges. It does not weigh: nothing is scored, nothing is
dropped for being uninteresting, and the order inside a section is decided by
*how well checked* a thing is, never by how good it looks. What it does:

  * one entry per thing, not one per mention (merged by the source URL when
    there is one, by name when there is not — so `NautilusTrader` and
    `nautechsystems/nautilus_trader` are one entry);
  * grouped by what kind of thing it is, because "a repo with 26k stars" and
    "a sentence in a caption" cannot be read the same way;
  * every entry states what it is, where that sentence came from, what the
    source said, and what is shaky about it;
  * a thing repeated by one account in post after post is *named as such* —
    that is a fixed promo slide, not a find, and saying so is an observation
    about the data, not a verdict on the thing.
"""
from __future__ import annotations

import re

from winnow.describe import describe

# Sections, in the order they are printed. A kind the extractor invents later
# still gets a section — it lands in `SECTIONS[None]` rather than vanishing.
SECTIONS: list[tuple[str | None, str, str]] = [
    ("repo", "Code you can run", "Every one of these was looked up on GitHub."),
    ("model", "Models", "Every one of these was looked up on HuggingFace."),
    ("platform", "Products, services and apps",
     "No public registry to ask: what these are rests on the post that "
     "named them."),
    ("item", "Entries of a list",
     "Named inside a list post, not presented as products: there is nothing "
     "to look up."),
    ("news", "News and announcements",
     "An announcement is not an artefact: nothing here was checked at a "
     "source, and none of it can be."),
    ("claim", "Claims, with no artefact behind them",
     "A sentence somebody wrote. Nothing to check, and nothing checked."),
]
OTHER = ("Everything else", "A kind of thing this version does not know how "
         "to check.")

# The two kinds that have a registry behind them. For the others, "not
# checked" is the normal state and not news — saying it once per section
# beats repeating it under 226 entries, which teaches the reader to skip it.
CHECKABLE = {"repo", "model"}

# How many posts one account has to repeat a name in before it stops being a
# find and starts being their letterhead. Measured: `OmniGet` appeared in 29
# posts, all from the same account, off a fixed final slide.
BOILERPLATE_POSTS = 5


def _slug(text: str) -> str:
    """`Lobe Chat`, `lobe-chat` and `LobeChat` are one word.

    A list post names the entry as a human would write it and the slide next
    to it carries the repo path, so the same thing arrives twice, spelled two
    ways — once unchecked as an entry of a list, once verified as a repo.
    """
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _name(entity: dict) -> str:
    return (entity.get("name") or "").strip().lower()


def resolve_names(days: list[dict]) -> dict[str, str]:
    """name → source URL, for every name a source ever resolved.

    Built in a pass of its own, before anything is merged, because the same
    name can be checked in one post and unchecked in the next — a rate limit,
    a network blip. Keyed on whichever mention happened to be checked, those
    two become two entries: one with the stars and one with a shrug. Deciding
    identity first, and only then merging, is what stops that.
    """
    alias: dict[str, str] = {}
    for day in days:
        for post in day.get("posts", []):
            for e in post.get("entities", []):
                v = e.get("verification") or {}
                url = (v.get("url") or "").strip().lower()
                if url and v.get("checked") and v.get("exists"):
                    alias.setdefault(_slug(_name(e)), url)
                    # ...and under the project's own name, so the plain
                    # `RAGFlow` of the caption finds `infiniflow/ragflow`.
                    alias.setdefault(_slug(url.rstrip("/").rsplit("/", 1)[-1]), url)
    return alias


def _key(entity: dict, verification: dict, alias: dict[str, str]) -> str:
    """What makes two mentions the same thing.

    The source URL when there is one: it is the only identifier that survives
    someone writing the bare project name in one post and the full
    `owner/name` in the next. Otherwise the name, lowercased.
    """
    name = _name(entity)
    url = (verification.get("url") or "").strip().lower()
    return alias.get(_slug(name)) or url or name


def _rank_verification(v: dict) -> int:
    """Which of two verifications of the same thing to keep. Checked and found
    beats checked and absent beats never checked — a later run that hit a rate
    limit must not erase what an earlier one confirmed."""
    if v.get("checked") and v.get("exists"):
        return 2
    if v.get("checked"):
        return 1
    return 0


def gather(days: list[dict], today: str = "") -> dict:
    """Every mention in the week, merged into one entry per thing."""
    things: dict[str, dict] = {}
    alias = resolve_names(days)
    posts = spend = 0.0
    failed: list[dict] = []
    empty: list[dict] = []

    for day in days:
        spend += day.get("spend_usd", 0.0)
        failed += list(day.get("failed", []))
        for post in day.get("posts", []):
            posts += 1
            if not post.get("entities"):
                empty.append({"account": post.get("account", "?"),
                              "url": post.get("url", "")})
            for raw in post.get("entities", []):
                v = raw.get("verification") or {}
                # Derived here, not read from the file: findings written before
                # describe.py existed have no `what_it_is`, and a week is only
                # as good as its oldest day.
                e = describe({k: val for k, val in raw.items()
                              if k != "verification"}, v, today)
                k = _key(e, v, alias)
                cur = things.get(k)
                if cur is None:
                    things[k] = cur = {
                        "kind": e.get("kind", ""), "name": e.get("name", "?"),
                        "what_it_is": e["what_it_is"], "doubts": [],
                        "verification": v, "seen": [],
                    }
                # A checked description replaces the post's claim; the reverse
                # never happens.
                if (e["what_it_is"].get("trusted")
                        and not cur["what_it_is"].get("trusted")):
                    cur["what_it_is"] = e["what_it_is"]
                if _rank_verification(v) > _rank_verification(cur["verification"]):
                    cur["verification"] = v
                    # The kind travels with the verification: merged with a
                    # checked repo, `RAGFlow` stops being a list entry and
                    # belongs in the section where it can be checked.
                    cur["kind"] = e.get("kind", cur["kind"])
                    cur["name"] = e.get("name", cur["name"])
                for d in e["doubts"]:
                    if d not in cur["doubts"]:
                        cur["doubts"].append(d)
                cur["seen"].append({"account": post.get("account", "?"),
                                    "url": post.get("url", ""),
                                    "shortcode": post.get("shortcode", ""),
                                    "slide": e.get("slide", 0),
                                    "said": (e.get("blurb") or "").strip()})

    for t in things.values():
        accounts = {s["account"] for s in t["seen"]}
        t["accounts"] = sorted(accounts)
        t["posts"] = len(t["seen"])
        # One account, many posts, same name: their letterhead, not a find.
        t["boilerplate"] = (len(accounts) == 1
                            and t["posts"] >= BOILERPLATE_POSTS)

    return {"posts": int(posts), "spend_usd": round(spend, 6),
            "things": list(things.values()), "failed": failed, "empty": empty}


def sort_key(t: dict) -> tuple:
    """Best-checked first, watermarks last, and then *alphabetically* — because
    position in a long list is read as a recommendation whether or not one was
    meant.

    This used to sort by star count, defended as "a measurement, not a
    judgement". It was a measurement and it was still a judgement: fame is the
    one property that makes a repo *not* worth reporting, since the reader
    already knows it. Measured on the week of 2026-08-24 — 120 repos, 48 of
    them from a single "50 GitHub repos" listicle — the order put **28 of the
    top 30** entries in that one post's hands, all of them the most-starred
    repositories on GitHub. Everything from the other 22 posts, each saved for
    one specific thing, began at rank 32; the post about reverse-engineering
    tools began at rank 82. The judge answered from the head of the list: it
    binned the listicle *and* kept four of its entries as finds.

    How many posts named a thing is gone for the same reason, and the mentality
    already says why — seven accounts posting the same list is one source, not
    seven. Ordering by it contradicted the block that teaches the reader to
    ignore it.

    What is left is epistemic state, not quality: whether anybody could check
    it, and whether it is an account's watermark. Inside a group, the name — so
    that being printed first means nothing at all.
    """
    v = t["verification"]
    return (-_rank_verification(v), 0 if not t["boilerplate"] else 1,
            t["name"].lower())


def state_line(t: dict) -> str:
    """One line of source truth: found or not, and the numbers if found."""
    v = t["verification"]
    if not v.get("checked"):
        return f"? not checked — {v.get('note') or 'no source asked'}"
    if not v.get("exists"):
        return f"✗ the source has nothing under this name{_note(v)}"
    bits = []
    if isinstance(v.get("stars"), int):
        # HuggingFace counts likes, GitHub counts stars. Printing a star next
        # to a like is a small lie that makes the two look comparable.
        bits.append(f"{v['stars']:,} likes" if t["kind"] == "model"
                    else f"{v['stars']:,}★")
    if v.get("last_commit"):
        bits.append(f"last commit {v['last_commit'][:10]}")
    if v.get("license"):
        bits.append(str(v["license"]))
    if v.get("archived"):
        bits.append("ARCHIVED")
    if v.get("url"):
        bits.append(str(v["url"]))
    return "✓ found at the source · " + " · ".join(bits) if bits else "✓ found at the source"


def _note(v: dict) -> str:
    return f" ({v['note']})" if v.get("note") else ""


def _origin(t: dict) -> str:
    # Instagram does not always give the account back — `from @ ·` reads like
    # a bug in winnow rather than a gap in what the page said.
    named = [a for a in t["accounts"] if a and a != "?"]
    who = ", ".join("@" + a for a in named[:3])
    if len(named) > 3:
        who += f" +{len(named) - 3}"
    who = f"from {who} · " if who else ""
    times = "1 post" if t["posts"] == 1 else f"{t['posts']} posts"
    first = t["seen"][0]
    # The shortcode and the slide are what let the recap show the picture the
    # reader would have seen on Instagram, instead of describing it to them.
    where = f"post {first.get('shortcode', '')} slide {first.get('slide', 0)}"
    return f"{who}{times} · {where} · {first['url']}"


def answered_under(t: dict) -> str:
    """The path the source answered under, when it is not the one written.

    GitHub follows renames, so asking for `ggerganov/llama.cpp` returns
    `ggml-org/llama.cpp` and asking for a project that was handed to someone
    else returns the new owner. Both are worth knowing and neither is visible
    from the numbers: a transfer and a wrong match look identical once the
    stars are printed next to the name from the caption.
    """
    v = t["verification"]
    url = v.get("url") or ""
    if not (v.get("checked") and v.get("exists")) or "github.com/" not in url:
        return ""
    path = url.split("github.com/", 1)[1].strip("/")
    # A bare name always resolves to some `owner/name`; that is not news.
    if "/" not in t["name"] or _slug(path) == _slug(t["name"]):
        return ""
    return path


def render_thing(t: dict) -> list[str]:
    w = t["what_it_is"]
    said = f" — {w['text']}" if w.get("text") else ""
    source = f" _(said by {w['from']})_" if w.get("from") else ""
    out = [f"- **{t['name']}**{said}{source}"]
    # Silence only where the section heading already said it: an unchecked
    # repo is a failure worth naming, an unchecked claim is just a claim.
    if t["kind"] in CHECKABLE or t["verification"].get("checked"):
        out.append(f"  - {state_line(t)}")
    out.append(f"  - {_origin(t)}")
    moved = answered_under(t)
    if moved:
        out.append(f"  - ⚠ the post wrote `{t['name']}`; the source answered "
                   f"under `{moved}` — a rename, or a different project")
    if t["boilerplate"]:
        out.append(f"  - ⚠ named in all {t['posts']} posts by the same "
                   "account: a fixed slide, not something that post was about")
    for d in t["doubts"]:
        # The state line above already says this, in the same words.
        if d.startswith("not checked:"):
            continue
        out.append(f"  - ⚠ {d}")
    return out


def render(d: dict, days: int) -> str:
    """The digest as markdown. One heading per kind, one entry per thing."""
    n = len(d["things"])
    day_word = "day" if days == 1 else "days"
    out = [f"{d['posts']} saved posts over {days} {day_word} · {n} distinct "
           f"things · collected for ${d['spend_usd']:.2f}.",
           "",
           "Every entry below: what it is (and who said so — the source or the "
           "post), what the source answered, where it came from, and what is "
           "shaky about it. Nothing here has been ranked or filtered.",
           ""]

    by_kind: dict[str, list[dict]] = {}
    for t in d["things"]:
        by_kind.setdefault(t["kind"], []).append(t)

    known = {k for k, _, _ in SECTIONS}
    sections = list(SECTIONS)
    leftover = sorted(k for k in by_kind if k not in known)
    if leftover:
        sections.append((None, *OTHER))

    for kind, title, note in sections:
        group = (by_kind.get(kind, []) if kind is not None
                 else [t for k in leftover for t in by_kind[k]])
        if not group:
            continue
        out += [f"### {title} ({len(group)})", "", f"_{note}_", ""]
        for t in sorted(group, key=sort_key):
            out += render_thing(t)
        out.append("")

    if d["empty"]:
        out += [f"### Posts that named nothing ({len(d['empty'])})", "",
                "Read, and no concrete thing in them — or the model declined "
                "to summarise them.", ""]
        out += [f"- @{e['account']} · {e['url']}" for e in d["empty"]] + [""]

    if d["failed"]:
        out += [f"### Posts that could not be read ({len(d['failed'])})", ""]
        out += [f"- {f.get('shortcode', '?')} — {f.get('error', '?')}"
                for f in d["failed"]] + [""]
    return "\n".join(out).rstrip() + "\n"
