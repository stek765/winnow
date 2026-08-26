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

MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
          "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]

# Fields a thing can carry, and where the model puts them.
FACTS = ("does", "title", "url", "state", "kind")

# One real answer put an emoji in a category name. The rendered page bans
# them, and a heading is not where a reader should find that out.
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF←-⇿⌀-➿️‍]+")


def _clean(name: str) -> str:
    return EMOJI.sub("", str(name or "")).strip() or "Altro"


def merge(answers: list[dict]) -> dict:
    """Several weeks' answers into one arrangement.

    Weeks are ordered by date, not by the order they were chosen: a page that
    reshuffles depending on which row was ticked first is a page nobody can
    read twice the same way.
    """
    if not answers:
        # An empty page would still be a page, and it would look like a
        # merge that worked.
        raise ValueError("niente da unire")

    answers = sorted(answers, key=lambda a: str(a.get("week") or ""))
    things: dict[str, dict] = {}
    order: list[str] = []
    cats: list[str] = []
    posts = usd = 0.0

    for answer in answers:
        week = str(answer.get("week") or "")
        counts = answer.get("counts") or {}
        posts += counts.get("posts") or 0
        usd += counts.get("usd") or 0.0

        for cat in answer.get("categories") or []:
            name = _clean(cat.get("name"))
            if name not in cats:
                cats.append(name)
            for item in cat.get("items") or []:
                key = " ".join(str(item.get("name") or "").split())
                if not key:
                    continue
                thing = things.get(key)
                if thing is None:
                    thing = things[key] = {
                        "name": key, "category": name, "weeks": [],
                        "why": [], "stars": None, "last_commit": "",
                        **{f: "" for f in FACTS}}
                    order.append(key)
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

    grouped = [{"name": c,
                "items": [things[k] for k in order if things[k]["category"] == c]}
               for c in cats]
    return {
        "weeks": [str(a.get("week") or "") for a in answers],
        "things": [things[k] for k in order],
        "categories": [g for g in grouped if g["items"]],
        "counts": {
            "posts": int(posts),
            "usd": round(usd, 4),
            # Not the sum of each week's `kept`: that counts a thing kept in
            # two weeks twice. What is on the page is the truth about it.
            "things": len(order),
            "weeks": len(answers),
        },
    }


def say_day(iso: str) -> str:
    """`2026-08-24` is a serial number; `24 agosto` is a day."""
    try:
        y, m, d = (int(p) for p in str(iso).split("-"))
        return f"{d} {MONTHS[m - 1]}"
    except (ValueError, IndexError):
        return str(iso)


def label_for(weeks: list[str]) -> str:
    """What the merged page is called.

    Not a week — it is not one, and calling it one would put it in a list
    beside things that are. It is called by what it covers.
    """
    weeks = sorted(w for w in weeks if w)
    if not weeks:
        return "unione"
    if len(weeks) == 1:
        return say_day(weeks[0])
    first, last = say_day(weeks[0]), say_day(weeks[-1])
    if first.split()[-1] == last.split()[-1]:      # same month, said once
        return f"{first.split()[0]}–{last}"
    return f"{first} – {last}"


# --- the page ---------------------------------------------------------------

def render_harvest(merged: dict) -> str:
    """The merge as a page.

    Its own renderer rather than a bend in `render.py`: a recap page is built
    around one week's argument — what got through, what did not, and the
    slide each came from. This is a different artifact with a different job,
    and sharing a renderer between them would leave both worse.
    """
    from winnow.render import _esc, painting_data_uri

    m = merged["counts"]
    label = label_for(merged["weeks"])
    blocks = []
    for cat in merged["categories"]:
        rows = []
        for t in cat["items"]:
            facts = []
            if t["stars"] is not None:
                facts.append(f"{t['stars']:,}".replace(",", ".") + " stelle")
            if t["last_commit"]:
                facts.append("ultimo commit " + t["last_commit"])
            what = t["title"] or t["does"]
            whys = "".join(
                f'<p class="why"><span>{_esc(say_day(w["week"]))}</span>'
                f'{_esc(w["text"])}</p>' for w in t["why"])
            again = (f'<p class="again">tenuta in {len(t["weeks"])} settimane</p>'
                     if len(t["weeks"]) > 1 else "")
            rows.append(
                '<article class="thing"><div class="hd">'
                f'<b>{_esc(t["name"])}</b>'
                f'<span class="wk">{_esc(say_day(t["weeks"][0]))}</span></div>'
                + (f'<p class="what">{_esc(what)}</p>' if what else "")
                + (f'<p class="facts">{_esc(" · ".join(facts))}</p>' if facts
                   # Said once per thing, because a repo with no numbers beside
                   # it otherwise reads as a repo with none to find.
                   else '<p class="facts thin">la fonte non ha risposto'
                        " quella settimana</p>")
                + whys + again + "</article>")
        blocks.append(f'<h2>{_esc(cat["name"])}</h2>'
                      f'<div class="grid">{"".join(rows)}</div>')

    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Il raccolto, {_esc(label)} — winnow</title>
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
opacity:.16;filter:saturate(.7) contrast(1.04);
-webkit-mask-image:radial-gradient(50% 78% at 82% 50%,#000 0%,rgba(0,0,0,.6) 46%,transparent 78%);
mask-image:radial-gradient(50% 78% at 82% 50%,#000 0%,rgba(0,0,0,.6) 46%,transparent 78%)}}
.wrap{{position:relative;z-index:1;max-width:74rem;margin:0 auto;
padding:clamp(2rem,5vw,3.5rem) clamp(1.2rem,4vw,3rem) 6rem}}
h1{{font-family:var(--display);font-weight:700;letter-spacing:-.03em;
font-size:clamp(2rem,5vw,2.9rem);margin:0 0 .4rem;line-height:1.05}}
.sub{{font-family:var(--mono);font-size:.74rem;letter-spacing:.1em;
color:var(--faint);margin:0 0 2.4rem}}
h2{{font-family:var(--mono);font-size:.68rem;letter-spacing:.18em;
text-transform:uppercase;color:var(--faint);margin:2.6rem 0 1rem;
padding-bottom:.6rem;border-bottom:1px solid var(--rule)}}
/* The hairlines belong to the cards, not to the gaps between them. Drawn as
   a 1px background showing through a grid gap — the usual trick — a category
   holding one thing leaves the rest of the row grey, and it reads as a block
   that failed to load rather than as a row with nothing else in it. */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(21rem,1fr));
gap:0;background:var(--lit);border:1px solid var(--rule);border-radius:4px;
overflow:hidden}}
.thing{{background:var(--lit);padding:1.15rem 1.25rem;
box-shadow:1px 0 0 var(--rule),0 1px 0 var(--rule)}}
.hd{{display:flex;align-items:baseline;gap:.8rem}}
.hd b{{font-family:var(--display);font-size:1.02rem;letter-spacing:-.01em;
word-break:break-word}}
.wk{{margin-left:auto;font-family:var(--mono);font-size:.66rem;
color:var(--faint);white-space:nowrap}}
.what{{margin:.45rem 0 0;font-size:.88rem;color:var(--soft);line-height:1.4}}
.facts{{margin:.5rem 0 0;font-family:var(--mono);font-size:.68rem;color:var(--faint)}}
.facts.thin{{font-style:italic}}
.why{{margin:.7rem 0 0;font-size:.85rem;line-height:1.45;padding-left:.75rem;
border-left:2px solid var(--rule)}}
.why span{{display:block;font-family:var(--mono);font-size:.62rem;
letter-spacing:.12em;text-transform:uppercase;color:var(--faint);
margin-bottom:.2rem}}
.again{{display:inline-block;margin:.7rem 0 0;font-family:var(--mono);
font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;
color:var(--grease);border:1px solid var(--grease);border-radius:999px;
padding:.18rem .55rem}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style></head><body>
<div class="veil" aria-hidden="true"><div class="art"></div></div>
<div class="wrap">
<h1>Il raccolto, {_esc(label)}</h1>
<p class="sub">{m["things"]} cose &middot; {m["weeks"]} settimane &middot;
{m["posts"]} post letti &middot; ${m["usd"]:.2f} spesi</p>
{"".join(blocks)}
</div></body></html>
"""
