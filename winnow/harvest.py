"""Several weeks read as one page.

Merging is arranging, never weighing — the same rule `digest.py` follows one
level down. What got through got through; nothing here re-decides it, and
nothing here drops a thing for being repeated or thin.

The one judgement call is what to do when two weeks describe the same thing
differently, and the answer is: keep both reasons and the richer facts. The
model does not write the same fields every week — measured on two real
answers, one carried `stars`, `state` and `url`, the next carried none of
them for the same repo — so a later, thinner mention must never blank what an
earlier one knew.
"""
from __future__ import annotations

import re

from winnow.i18n import DEFAULT
from winnow.i18n import t as tr

MONTHS = {
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}

# Fields a thing can carry, and where the model puts them.
FACTS = ("does", "title", "url", "state", "kind")

# One real answer put an emoji in a category name. The rendered page bans
# them, and a heading is not where a reader should find that out.
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF←-⇿⌀-➿️‍]+")


def _clean(name: str) -> str:
    return EMOJI.sub("", str(name or "")).strip() or "Altro"


def short_name(name: str) -> tuple[str, str]:
    """What identifies a thing, and who owns it.

    `usestrix/strix` and `Strix` are the same repository, and on 2026-08-23
    and 2026-08-24 they were printed as two, in two sections both called
    security — because identity was the name string, character for character.
    A model writes the owner when the slide shows it and drops it when it
    does not, so the owner cannot be part of the key.

    It still cannot be thrown away: `foo/parser` and `bar/parser` are two
    projects, and merging them would attach one's stars to the other — the
    exact failure this repo keeps paying for. So the key is the short name,
    and an owner is a veto, not a key.
    """
    n = " ".join(str(name or "").split()).lower().strip("/")
    owner, _, short = n.rpartition("/")
    return re.sub(r"[^a-z0-9]+", "", short), owner


def _fuller(a: str, b: str) -> str:
    """Of two names for one thing, the one that says more. `cactus/needle`
    over `needle`: the reader can look the first one up."""
    return b if ("/" in b and "/" not in a) or len(b) > len(a) else a


def merge(answers: list[dict]) -> dict:
    """Several weeks' answers into one arrangement.

    Weeks are ordered by date, not by the order they were chosen: a page that
    reshuffles depending on which row was ticked first is a page nobody can
    read twice the same way.

    Nothing is grouped by category any more, and that is the correction of a
    real mistake. Two recaps are two taxonomies: on 23 and 24 August they
    produced eleven headings for twenty-one things, with «Modelli che stanno
    in un microcontrollore» and «Hardware» naming the same subject. Worse, the
    old rule — first week's category wins — *moved* a thing out of the second
    week's section, which then rendered as a half-empty row that reads as a
    page that failed to load. Choosing which of two names survives is a
    judgement, and this module does not make judgements. Every category a
    thing was filed under travels with the thing.
    """
    if not answers:
        # An empty page would still be a page, and it would look like a
        # merge that worked.
        raise ValueError("niente da unire")

    answers = sorted(answers, key=lambda a: str(a.get("week") or ""))
    things: list[dict] = []
    index: dict[str, list[dict]] = {}
    posts = usd = 0.0

    for answer in answers:
        week = str(answer.get("week") or "")
        counts = answer.get("counts") or {}
        posts += counts.get("posts") or 0
        usd += counts.get("usd") or 0.0

        for cat in answer.get("categories") or []:
            name = _clean(cat.get("name"))
            for item in cat.get("items") or []:
                label = " ".join(str(item.get("name") or "").split())
                short, owner = short_name(label)
                if not short:
                    continue
                thing = None
                for cand in index.get(short, []):
                    if not owner or not cand["owner"] or owner == cand["owner"]:
                        thing = cand
                        break
                if thing is None:
                    thing = {"name": label, "owner": owner, "categories": [],
                             "weeks": [], "why": [], "stars": None,
                             "last_commit": "", **{f: "" for f in FACTS}}
                    index.setdefault(short, []).append(thing)
                    things.append(thing)
                else:
                    thing["name"] = _fuller(thing["name"], label)
                    thing["owner"] = thing["owner"] or owner
                if name not in thing["categories"]:
                    thing["categories"].append(name)
                if week and week not in thing["weeks"]:
                    thing["weeks"].append(week)
                # Both reasons are kept: `why` is the judgement, and two weeks
                # gave two different sentences. Keeping only the first throws
                # away half of what the reader came back to re-read.
                why = str(item.get("why") or "").strip()
                if why and why not in [w["text"] for w in thing["why"]]:
                    thing["why"].append({"week": week, "text": why})
                for f in FACTS:
                    if not thing[f] and item.get(f):
                        thing[f] = str(item[f])
                if not thing["last_commit"] and item.get("last_commit"):
                    thing["last_commit"] = str(item["last_commit"])
                if thing["stars"] is None and item.get("stars") is not None:
                    thing["stars"] = item["stars"]

    # Alphabetical, so position carries no information — the same reason
    # `render.py` refuses to order by stars. What passed twice says so on its
    # own line; it does not need to be pushed to the top as well.
    things.sort(key=lambda t: t["name"].lower())
    return {
        "weeks": [str(a.get("week") or "") for a in answers],
        "things": things,
        "counts": {
            "posts": int(posts),
            "usd": round(usd, 4),
            # Not the sum of each week's `kept`: that counts a thing kept in
            # two weeks twice. What is on the page is the truth about it.
            "things": len(things),
            "weeks": len(answers),
        },
    }


def say_day(iso: str, lang: str = DEFAULT) -> str:
    """`2026-08-24` is a serial number; `24 agosto` is a day.

    And `24 August` is not one in English — the order goes the other way
    round. A date written by a rule that only knows one language reads as a
    translation of a date rather than as a date.
    """
    try:
        y, m, d = (int(p) for p in str(iso).split("-"))
        month = MONTHS.get(lang, MONTHS[DEFAULT])[m - 1]
        return f"{month} {d}" if lang == "en" else f"{d} {month}"
    except (ValueError, IndexError, KeyError):
        return str(iso)


def _and_join(parts: list[str], lang: str = DEFAULT) -> str:
    """`a, b e c` — the last one joined by a word, not by a comma."""
    if len(parts) == 1:
        return parts[0]
    word = "e" if lang == "it" else "and"
    return f"{', '.join(parts[:-1])} {word} {parts[-1]}"


def say_days(days: list[str], lang: str = DEFAULT) -> str:
    """A handful of days as one phrase, with the month said once.

    `23 agosto e 24 agosto` makes a reader check whether the two really are
    the same month; English puts the month first, so the repeated word is at
    the other end — `August 23 and 24`, not `August 23 and August 24`.
    """
    said = [say_day(d, lang) for d in days]
    months = {s.split()[-1] if lang == "it" else s.split()[0] for s in said}
    if len(months) > 1:
        return _and_join(said, lang)
    if lang == "it":
        # The month rides on the last one: «23, 24 e 28 agosto».
        return _and_join([s.split()[0] for s in said[:-1]] + [said[-1]], lang)
    # English keeps it on the first: «August 23, 24 and 28».
    return _and_join([said[0]] + [s.split()[-1] for s in said[1:]], lang)


# Past this many days the label lists nothing and says it is a selection: a
# merge of thirty recaps written out day by day is a paragraph, not a name.
NAME_DAYS = 5


def label_for(weeks: list[str], name: str = "", lang: str = DEFAULT) -> str:
    """What the merged page is called.

    A name the reader typed wins over everything: ten weeks picked out of a
    year are a theme, not a period, and a theme is the only thing that makes
    a shelf of merges findable a month later.

    Without one, the label must not turn a selection into a span. `3 recap,
    da 23 agosto a 28 agosto` was a merge of the 23rd, the 24th and the 28th,
    and it was read — by the person who made it — as containing the 27th too.
    Putting the count first was not enough: a reader sees two dates with a
    preposition between them and reads a period, whatever precedes it.

    So a few days are *listed*, which cannot be misread, and many days say
    they were chosen out of a window rather than filling it.
    """
    name = " ".join(str(name or "").split())
    if name:
        return name
    weeks = sorted(w for w in weeks if w)
    if not weeks:
        return "unione"
    # Distinct days: one day can hold two recaps — a first attempt that ran
    # out of tokens and the real one beside it — and «28 agosto e 28 agosto»
    # is not a label. The count of *pages* still leads the long form.
    days = sorted(set(weeks))
    if len(days) <= NAME_DAYS:
        return say_days(days, lang)
    # Days, not pages, so the label can be rebuilt from what the merge wrote
    # down — the archive keeps the distinct days, and a count that only the
    # moment of creation could produce is a label that goes stale. How many
    # pages went in is printed beside the label anyway.
    return tr("merge.label_many", lang, n=len(days),
              a=say_day(days[0], lang), b=say_day(days[-1], lang))


def merge_id(parts: list[str], name: str = "") -> str:
    """The file this merge lives in.

    Named from the first and last week — the first attempt — `{23, 30}` and
    `{23, 26, 30}` produced the same file, and the second quietly overwrote
    the first. Measured, not imagined. The name is derived from *everything*
    that makes a merge what it is: the exact set of weeks and the name given
    to it. Same choice twice replaces itself; anything else is a new page.

    The typed name is slugged, never used raw: it ends up in a path and in a
    URL.
    """
    import hashlib

    # Whatever identifies the pieces — dates once, page names now that a day
    # can hold two recaps. Same set twice replaces itself; anything else is a
    # new page.
    parts = sorted(p for p in parts if p)
    seed = "|".join(parts) + "\u0000" + " ".join(str(name or "").split())
    short = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")[:32]
    return f"unione-{slug}-{short}" if slug else f"unione-{short}"


# --- the page ---------------------------------------------------------------

def render_harvest(merged: dict, label: str = "",
                   lang: str = DEFAULT) -> str:
    """The merge as a page.

    Its own renderer rather than a bend in `render.py`: a recap page is built
    around one week's argument — what got through, what did not, and the
    slide each came from. This is a different artifact with a different job,
    and sharing a renderer between them would leave both worse.
    """
    from winnow.render import _esc, painting_data_uri

    m = merged["counts"]
    label = label or label_for(merged["weeks"], lang=lang)
    rows = []
    for th in merged["things"]:
        facts = []
        if th["stars"] is not None:
            sep = "." if lang == "it" else ","
            facts.append(f"{th['stars']:,}".replace(",", sep) + " "
                         + tr("page.stars", lang))
        if th["last_commit"]:
            facts.append(tr("page.last_commit", lang, when=th["last_commit"]))
        what = th["title"] or th["does"]
        # Folded, not dropped. A merge exists to be *scanned* — what came back
        # across several recaps, and what the pile was about — and the reasons
        # are what the reader has already read, once per recap, on the page
        # that produced them. Printed in full they turned twenty things into a
        # wall four screens deep, which is the one thing this page must not be.
        whys = "".join(
            f'<p class="why"><span>{_esc(say_day(w["week"], lang))}</span>'
            f'{_esc(w["text"])}</p>' for w in th["why"])
        fold = (f'<details class="more">'
                f'<summary>{tr("merge.why", lang)}</summary>{whys}'
                "</details>" if whys else "")
        # Where each recap filed it, all of them. Two names for one subject
        # are worth seeing side by side; one of them deleted is not.
        cats = "".join(f'<span class="tag">{_esc(c)}</span>'
                       for c in th["categories"])
        # The one thing a merge can say that no single recap can.
        again = (f'<span class="again">'
                 f'{tr("merge.n_recaps", lang, n=len(th["weeks"]))}</span>'
                 if len(th["weeks"]) > 1 else "")
        rows.append(
            '<article class="thing">'
            f'<div class="hd"><b>{_esc(th["name"])}</b>{again}'
            f'<span class="wk">{_esc(say_day(th["weeks"][0], lang))}</span>'
            "</div>"
            + (f'<p class="what">{_esc(what)}</p>' if what else "")
            + '<p class="facts">'
            + (_esc(" · ".join(facts)) if facts
               # Said once per thing, because a repo with no numbers beside
               # it otherwise reads as a repo with none to find.
               else f'<i>{tr("page.no_answer", lang)}</i>')
            + (f'<span class="tags">{cats}</span>' if cats else "")
            + "</p>" + fold + "</article>")
    body = f'<div class="list">{"".join(rows)}</div>'

    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(tr("merge.title", lang, label=label))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Familjen+Grotesk:wght@400;600;700&family=Instrument+Sans:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{{--glass:#e9eced;--lit:#fbfcfc;--ink:#10141a;--soft:#4d565f;--faint:#8b949c;
--rule:#d7dcde;--grease:#ce3a24;--display:"Familjen Grotesk","Helvetica Neue",Arial,sans-serif;
--body:"Instrument Sans",-apple-system,sans-serif;--mono:"JetBrains Mono",ui-monospace,monospace;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--glass);color:var(--ink);font-family:var(--body);
-webkit-font-smoothing:antialiased}}
.veil{{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}}
.art{{position:absolute;inset:-6%;
background:url("{painting_data_uri()}") no-repeat 88% 46%/auto 112%;
/* Quieter than on a recap: that page has one argument and room around it,
   this one is twenty rows of small type and the picture was reading through
   every line of them. */
opacity:.10;filter:saturate(.7) contrast(1.04);
-webkit-mask-image:radial-gradient(50% 78% at 82% 50%,#000 0%,rgba(0,0,0,.6) 46%,transparent 78%);
mask-image:radial-gradient(50% 78% at 82% 50%,#000 0%,rgba(0,0,0,.6) 46%,transparent 78%)}}
/* A measure, not the width of the window. At 74rem the names sat far left,
   the dates far right, and the middle was empty page with the painting
   showing through it. */
.wrap{{position:relative;z-index:1;max-width:54rem;margin:0 auto;
padding:clamp(2rem,5vw,3.5rem) clamp(1.2rem,4vw,3rem) 6rem}}
h1{{font-family:var(--display);font-weight:700;letter-spacing:-.03em;
font-size:clamp(2rem,5vw,2.9rem);margin:0 0 .4rem;line-height:1.05}}
/* Which weeks, written out. A page called "Embedded" must still say what it
   was made from, or in a month it is a title with nothing behind it. */
.from{{font-size:.92rem;color:var(--soft);margin:0 0 .5rem;line-height:1.4}}
.sub{{font-family:var(--mono);font-size:.74rem;letter-spacing:.1em;
color:var(--faint);margin:0 0 2.4rem}}
/* One column, one row per thing. Two columns of cards was the wrong shape
   for a list whose rows are all different heights: it left holes wherever a
   short card met a tall one, and it made the page twice as long as the thing
   it describes. */
.list{{border-top:1px solid var(--rule)}}
.thing{{padding:1.1rem 0; border-bottom:1px solid var(--rule)}}
.hd{{display:flex; align-items:baseline; gap:.7rem}}
.hd b{{font-family:var(--display); font-size:1.05rem; letter-spacing:-.01em;
word-break:break-word}}
.wk{{margin-left:auto; font-family:var(--mono); font-size:.66rem;
color:var(--faint); white-space:nowrap}}
/* The one thing a merge can say that no single recap can: this came back. */
.again{{font-family:var(--mono); font-size:.6rem; letter-spacing:.08em;
text-transform:uppercase; color:var(--grease);
border:1px solid var(--grease); border-radius:999px; padding:.1rem .45rem}}
.what{{margin:.3rem 0 0; font-size:.92rem; color:var(--soft); line-height:1.45}}
/* Numbers and filings on one line: they are the same kind of thing — where
   this came from — and stacked they doubled the height of every row. */
.facts{{margin:.35rem 0 0; font-family:var(--mono); font-size:.68rem;
color:var(--faint); display:flex; flex-wrap:wrap; align-items:center;
gap:.5rem}}
.facts i{{font-style:italic}}
.tags{{display:flex; flex-wrap:wrap; gap:.35rem}}
.tag{{font-size:.6rem; letter-spacing:.06em; text-transform:uppercase;
background:#e3e6e8; border-radius:3px; padding:.12rem .4rem}}
/* The judgements, folded. Native `details`, so the page still works after it
   has been mailed to somebody and opened with no server behind it. */
.more{{margin:.5rem 0 0}}
.more summary{{display:inline-block; cursor:pointer; list-style:none;
font-family:var(--mono); font-size:.62rem; letter-spacing:.12em;
text-transform:uppercase; color:var(--faint); padding:.15rem 0;
border-bottom:1px solid var(--rule)}}
.more summary::-webkit-details-marker{{display:none}}
.more summary:hover{{color:var(--grease); border-color:var(--grease)}}
.more[open] summary{{margin-bottom:.55rem}}
.why{{margin:0 0 .55rem; font-size:.88rem; line-height:1.5; max-width:74ch;
padding-left:.75rem; border-left:2px solid var(--rule)}}
.why span{{display:block;font-family:var(--mono); font-size:.6rem;
letter-spacing:.12em; text-transform:uppercase; color:var(--faint);
margin-bottom:.15rem}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style></head><body>
<div class="veil" aria-hidden="true"><div class="art"></div></div>
<div class="wrap">
<h1>{_esc(label)}</h1>
<p class="from">{_esc(tr("merge.harvest_of", lang,
  days=say_days(sorted(set(w for w in merged["weeks"] if w)), lang)))}</p>
<p class="sub">{tr("merge.counts", lang, things=m["things"], weeks=m["weeks"],
  posts=m["posts"], usd=f'{m["usd"]:.2f}')}</p>
{body}
</div></body></html>
"""
