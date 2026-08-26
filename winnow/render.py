"""The judgement, as a page you scan instead of a file you read.

The model answers with JSON. This turns it into a page whose subject is not
the finds but **the cut**: a hundred and forty-four things went in and fifteen
came out, and the half that got stopped is half the product. A reader who
cannot see what was thrown away, and on what grounds, has no way to tell a
filter from a coin toss — and no way to correct it.

So the page has two parts:

  * what passed, with the slide it came from;
  * what stopped, grouped by the *verdict* that stopped it, with the count
    next to each.

Grouping the rejects by verdict is what makes the reasoning auditable. Reading
a hundred and twenty-nine prose lines tells you nothing about how the filter
thinks; seeing that thirty-one were dropped as out of scope and seven because
GitHub has nothing under that name tells you at a glance — and tells you which
group to go argue with.

The look comes from the material. These are slides from carousels, and slides
get reviewed on a light table with the keepers marked in red grease pencil.
Hence the glass, the mounts, and the one red.

The data shape it expects:

    {"week": "2026-08-24",
     "counts": {"posts": 30, "kept": 15, "failed": 1, "usd": 0.13},
     "comment": "one to three short paragraphs, **markdown** allowed",
     "categories": [
       {"name": "Reverse engineering", "items": [
         {"title": "Un LLM dentro Ghidra",
          "does": "what it does, in a plain sentence",
          "why":  "why it got through",
          "doubt": "the weak point, or leave it out",
          "kind": "tool", "state": "alive",
          "name": "weirdmachine64/GhidraGPT", "stars": 673,
          "last_commit": "2026-07", "url": "https://github.com/...",
          "post": "Dbnx278iPKV", "slide": 4}]}],
     "discarded": [{"name": "n8n-io/n8n", "verdict": "LO CONOSCI",
                    "why": "the reason", "post": "DcNOt8mkugc", "slide": 3}]}

`does` is the headline and `name` is the footnote, deliberately: a repo slug
tells you nothing you can scan, and scanning is the whole point. `verdict` is
optional — without it a reject lands under "Altro" rather than vanishing.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import date
from pathlib import Path

# What a chip says when there is no date to say it with. Words, not symbols:
# a tick and a quarter-circle need a legend, and a page with a legend is a page
# that failed to say it the first time.
STATES = {
    "alive":   "trovato alla fonte",
    "stale":   "fermo da anni",
    "unknown": "nessuna fonte da chiedere",
    "absent":  "la fonte non lo trova",
}

# The order verdicts appear in, when the judgement does not impose one. Source
# first (the feed is wrong), then reader (it is not for you) — because the
# first group says something about where these posts come from, and the second
# only says something about who is reading.
VERDICT_ORDER = [
    "NON ESISTE", "FERMO DA ANNI", "NOME FRAGILE", "CHI CI GUADAGNA",
    "SOLO ANNUNCIO", "NON VERIFICATO", "SCATOLA CHIUSA", "DOPPIONE",
    "GIA' TUO", "LO CONOSCI", "FUORI BERSAGLIO",
]


def _esc(value: object) -> str:
    # `value or ""` turned a zero into a blank cell: the week with no failed
    # posts showed an empty box where "0" belonged, which reads as a bug in
    # the page rather than as good news.
    return html.escape("" if value is None else str(value), quote=True)


_MD = ((re.compile(r"\*\*(.+?)\*\*", re.S), r"<strong>\1</strong>"),
       (re.compile(r"`(.+?)`", re.S), r"<code>\1</code>"),
       (re.compile(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])"), r"<em>\1</em>"))


def _md(text: object) -> str:
    """The little bit of markdown a model writes without being asked.

    Escaped first, marked up second — never the reverse, or a caption becomes
    a script tag. Before this existed the recap's own paragraph rendered as
    `**e' la lista stessa**`, asterisks and all, which reads as the page being
    broken rather than as the model having used bold.
    """
    out = _esc(text)
    for pattern, repl in _MD:
        out = pattern.sub(repl, out)
    return out


def _stars(n: object) -> str:
    """4200 -> 4.2k. A star count is a size, and sizes are read at a glance."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def post_of(item: dict) -> str:
    """The shortcode, however it was written down."""
    post = (item.get("post") or "").strip()
    if "/p/" in post:                       # a full URL was pasted instead
        post = post.split("/p/", 1)[1].strip("/").split("/")[0]
    return post


def _slide_of(item: dict) -> int:
    try:
        return int(item.get("slide") or 0)
    except (TypeError, ValueError):
        return 0


def shared_slides(items: list[dict]) -> set[tuple[str, int]]:
    """The (post, slide) pairs that more than one thing points at.

    Two things pointing at one slide means that slide is about neither of them
    on its own — it is a list. Kept as a fact about the picture, not as a
    reason to hide it: see `shot_for`.
    """
    seen: dict[tuple[str, int], int] = {}
    for it in items:
        key = (post_of(it), _slide_of(it))
        if key[0]:
            seen[key] = seen.get(key, 0) + 1
    return {k for k, n in seen.items() if n > 1}


def shot_for(item: dict, shots: Path | None,
             shapes: dict[str, str] | None = None,
             shared: set[tuple[str, int]] | None = None) -> str:
    """The slide the reader would have seen. Always, when one was captured.

    This is the whole reason the collector keeps screenshots: told in words, a
    judgement about a post cannot be checked without going back to Instagram,
    which is the thing nobody does.

    It used to refuse the picture whenever the slide named more than one
    project — the honest instinct that a wall of forty links is not a portrait
    of any one of them. But refusing left a coloured block in its place, and
    forty coloured blocks in a grid do not read as *"this came from a list"*.
    They read as **images that failed to load**, which is what a reader
    reported on 2026-08-24. So the slide is always shown and the wall of links
    is *labelled as one* (`slide_note`) — the picture then proves the very
    thing the label claims, instead of hiding it.

    `shapes` and `shared` are still taken so callers do not have to change;
    they now decide the caption rather than the picture.
    """
    post = post_of(item)
    if not post or shots is None:
        return ""
    names = sorted(p.name for p in shots.glob(f"{post}_*.png"))
    if not names:
        return ""
    exact = f"{post}_{_slide_of(item):02d}.png"
    return str(shots / (exact if exact in names else names[0]))


# What a sibling chip says about the one that got through.
KEPT = "TENUTA"


def siblings_map(kept: list[dict], stopped: list[dict]) -> dict:
    """(post, slide) -> every thing on that slide, with what happened to it.

    This is the answer to the one question the page could not answer. A list
    slide is a wall of fifty links; one of them got through and the reasons
    for the other forty-nine were a scroll away, in a list of a hundred and
    twenty-nine rows — which is the same as not being there at all. Measured
    2026-08-24: `perplexityai/bumblebee` shares its slide with ten others, and
    a reader looking at that wall asked, reasonably, *"why this one and not
    the other fifty?"*.

    Naming the neighbours right beside it, each with the verdict that stopped
    it, turns the confusing picture into the argument itself.
    """
    out: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for it in kept:
        key = (post_of(it), _slide_of(it))
        out.setdefault(key, []).append((it.get("name") or "?", KEPT))
    for it in stopped:
        key = (post_of(it), _slide_of(it))
        out.setdefault(key, []).append(
            (it.get("name") or it.get("what") or "?",
             (it.get("verdict") or "FERMATA").strip()))
    return out


def siblings_of(item: dict, siblings: dict | None) -> list[tuple[str, str]]:
    """The other things on this thing's slide. Never itself."""
    rows = (siblings or {}).get((post_of(item), _slide_of(item)), [])
    name = item.get("name")
    return [r for r in rows if r[0] != name]


def slide_note(item: dict, shapes: dict[str, str] | None = None,
               shared: set[tuple[str, int]] | None = None,
               siblings: dict | None = None) -> str:
    """What the picture is, when it is not a picture of this thing.

    A caption that says the slide names many projects turns a confusing image
    into evidence. Silence there is what made the same screenshot appear under
    four different labels and look like a bug.

    Decided per *slide*, by counting how many things point at it, and never
    from the post's `shape`: a list post still has slides that are about one
    thing. Measured 2026-08-24 — `GhidraGPT` sits alone on slide 4 of a list
    post, and the shape-based caption claimed the slide named many. The
    picture underneath said otherwise, which is the worst kind of wrong: the
    page contradicting its own evidence. `shapes` is still accepted so callers
    need not change, and is deliberately unused.
    """
    post, slide = post_of(item), _slide_of(item)
    if not post:
        return ""
    n = len((siblings or {}).get((post, slide), []))
    if n > 1:
        # A number where one is available: it is what tells you whether this
        # came off a list of three or of fifty.
        return f"una di {n} su questa slide"
    if (post, slide) in (shared or set()):
        return "questa slide ne nomina molti"
    return ""


def _rel(path: str, out_dir: Path | None) -> str:
    """A relative href, so the page keeps working if the folder is moved."""
    if not path:
        return ""
    if out_dir is None:
        return path
    try:
        return os.path.relpath(path, out_dir)
    except ValueError:
        return path


def _inline(path: str) -> str:
    """An image as a data URI, or "" if it cannot be read.

    Recap pages get moved, mailed and reopened months later. A reference to
    a shared folder — which on top of that has to be cleaned, or it grows
    into tens of GB — is a hole that opens on its own.
    """
    import base64
    try:
        data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/png;base64,{data}"


def plate(item: dict) -> str:
    """What stands in when no slide was ever captured.

    Not a placeholder: the name is the most useful thing that fits in a
    rectangle, and the tint comes from the name itself, so two things are
    never the same block.
    """
    name = (item.get("name") or "").strip()
    label = name.rsplit("/", 1)[-1] if name else (item.get("title") or "?")
    hue = sum(ord(c) * (i + 1) for i, c in enumerate(label)) % 360
    return (f'<span class="plate" style="--h:{hue}">'
            f'<span class="plate-n">{_esc(label)}</span></span>')


def state_chip(item: dict) -> str:
    """What was actually checked, in words that mean something on their own.

    This used to print the internal state — `vivo`, `fermo` — which is a word
    about winnow's bookkeeping and not about the project. A reader asked, quite
    fairly, what «VIVO» was supposed to tell them: nothing, is the answer. The
    chip is the most-read spot on the entry, so it carries the fact the state
    was *derived from* rather than the label winnow filed it under.
    """
    state = (item.get("state") or "unknown").strip().lower()
    when = (item.get("last_commit") or "").strip()
    if when and state == "alive":
        return f"ultimo commit {when}"
    if when and state == "stale":
        return f"fermo dal {when}"
    return STATES.get(state, STATES["unknown"])


def _facts(item: dict) -> str:
    """Name, size, age — the footnote line, in that order."""
    # No date here: the chip says it, and printing it twice reads as the page
    # repeating itself rather than as two facts.
    stars = _stars(item.get("stars"))
    return " · ".join(filter(None, [
        _esc(item.get("name")),
        f"{stars}★" if stars else "",
    ]))


def _stamp(item: dict) -> str:
    """The name, over the picture.

    A wall of fifty links does not say which of the fifty this entry is about,
    and the reader should not have to hunt for it in a screenshot. The short
    name — `bumblebee`, not `perplexityai/bumblebee` — is what is legible at
    this size and what is written on the slide itself.
    """
    name = (item.get("name") or "").strip()
    if not name:
        return ""
    return f'<span class="stamp">{_esc(name.rsplit("/", 1)[-1])}</span>'


def _siblings_html(item: dict, siblings: dict | None) -> str:
    rows = siblings_of(item, siblings)
    if not rows:
        return ""
    chips = "".join(
        f'<span class="sib{" kept" if verdict == KEPT else ""}">'
        f'{_esc(name)}<b>{_esc(verdict)}</b></span>'
        for name, verdict in sorted(rows, key=lambda r: r[0].lower()))
    return (f'<div class="sibs"><span class="lab">Sulla stessa slide, '
            f'e cosa ne è stato</span>{chips}</div>')


def kept_html(item: dict, i: int, cat: str, shots: Path | None,
              out_dir: Path | None, shapes: dict[str, str] | None = None,
              shared: set | None = None, siblings: dict | None = None,
              embed_shots: bool = False) -> str:
    """One thing that got through: the slide, then why it got through."""
    found = shot_for(item, shots, shapes, shared)
    src = (_inline(found) if embed_shots and found
           else _rel(found, out_dir))
    pic = (f'<img loading="lazy" src="{_esc(src)}" alt="">' if src
           else plate(item))
    note = slide_note(item, shapes, shared, siblings)
    post = post_of(item)
    n = _slide_of(item)
    caption = f"slide {n}" if post and n > 0 else ""
    if note:
        caption = f"{caption} · {note}" if caption else note
    url = _esc(item.get("url"))
    links = []
    if item.get("url"):
        links.append(f'<a class="go" href="{url}" target="_blank" '
                     f'rel="noopener">apri</a>')
    if post:
        links.append(f'<a class="ghost" target="_blank" rel="noopener" '
                     f'href="https://www.instagram.com/p/{_esc(post)}/">'
                     f'il post</a>')
    state = _esc(item.get("state", "unknown"))
    doubt = _esc(item.get("doubt"))
    return f"""<article class="pass" data-cat="{_esc(cat)}">
  <figure class="mount">
    {pic}{_stamp(item)}
    {f'<figcaption>{_esc(caption)}</figcaption>' if caption else ''}
  </figure>
  <div class="body">
    <p class="tags"><span class="cat">{_esc(cat)}</span><span
       class="st s-{state}">{_esc(state_chip(item))}</span></p>
    <h3>{_esc(item.get("title") or item.get("does"))}</h3>
    <p class="does">{_md(item.get("does"))}</p>
    <p class="why"><span class="lab">Perché passa</span>{_md(item.get("why"))}</p>
    {f'<p class="doubt"><span class="lab">Dubbio</span>{doubt}</p>' if doubt else ''}
    {_siblings_html(item, siblings)}
    <p class="foot">{_facts(item)}</p>
    <p class="links">{" ".join(links)}</p>
  </div>
</article>"""


def stopped_html(rows: list[dict]) -> str:
    """What was thrown away, grouped by the verdict that threw it away.

    One line per thing — a bucket cannot be corrected, because the reader
    cannot see which of the eighteen to argue with. The counts next to each
    verdict are the part worth looking at: they are the shape of the
    reasoning, and they are the thing to disagree with first.
    """
    if not rows:
        return ""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault((r.get("verdict") or "ALTRO").strip(), []).append(r)
    order = [v for v in VERDICT_ORDER if v in groups]
    order += sorted(k for k in groups if k not in VERDICT_ORDER)

    chips = "".join(
        f'<button class="vf" data-v="{_esc(v)}">{_esc(v)}'
        f'<b>{len(groups[v])}</b></button>' for v in order)
    blocks = []
    for v in order:
        lis = "".join(
            f'<li><span class="n">{_esc(r.get("name") or r.get("what"))}</span>'
            f'<span class="r">{_md(r.get("why"))}</span></li>'
            for r in groups[v])
        blocks.append(
            f'<section class="vg" data-v="{_esc(v)}">'
            f'<h3>{_esc(v)}<b>{len(groups[v])}</b></h3>'
            f'<ol class="rows">{lis}</ol></section>')
    return f"""<section class="stopped">
  <p class="eyebrow">Fermate</p>
  <h2>{len(rows)} cose non sono passate</h2>
  <p class="intro">Ognuna col suo nome e il suo motivo, perché un mucchio non
    si può correggere. I numeri qui sotto sono la forma del ragionamento:
    se uno è sbagliato, è lì che si vede.</p>
  <div class="vfs"><button class="vf on" data-v="*">Tutte<b>{len(rows)}</b></button>{chips}</div>
  <div class="vgs">{"".join(blocks)}</div>
</section>"""


def counts_html(counts: dict) -> str:
    usd = counts.get("usd")
    cells = [(counts.get("posts"), "post letti"),
             (counts.get("kept"), "passate"),
             (counts.get("failed"), "illeggibili"),
             # The cost used to be a bare label with no number, which left it
             # with no first baseline to align on: it floated above the row.
             (f"${usd:.2f}" if usd is not None else None, "spesi")]
    out = []
    for v, label in cells:
        if v is None:
            continue
        out.append(f'<span class="stat"><b>{_esc(v)}</b>'
                   f'<span>{_esc(label)}</span></span>')
    return "".join(out)


PAINTING = Path(__file__).parent / "winnower.jpg"


def painting_data_uri() -> str:
    """Millet's winnower, as bytes inside the page.

    Embedded and never linked. This page gets moved, mailed and opened again
    in three years; a file reference is a hole waiting to open, and the whole
    point of the recap is that it survives being ignored for a while.

    The image is the tool's identity — it is the first thing in the README —
    and it earns the space: a man throwing grain into the air so the wind can
    take the husks is the argument the page is making, made once, by somebody
    better at it. Public domain, and credited under it anyway.
    """
    import base64
    try:
        data = base64.b64encode(PAINTING.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/jpeg;base64,{data}"


def logo_svg() -> str:
    """An ear of wheat, with three grains lifting off it.

    The small mark, for where the painting cannot go — a tab, a favicon, a
    printed page. Drawn, never fetched.

    Three earlier attempts drew the *vessel* and each failed the same way, on
    reading rather than on drawing: at this size a thin outlined bowl reads as
    a smile, round dots read as dust, a solid half-circle reads as a soup
    bowl, and a flat tray reads as a smudge. A vessel needs a scene to be
    recognised and a mark has none. An ear of wheat does not.
    """
    ear = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="3" ry="5.7" '
        f'transform="rotate({a} {x} {y})" fill="currentColor"/>'
        # Tapered: narrow at the tip, wider at the base. Even offsets made it
        # read as a pine cone.
        for x, y, a in ((22, 5.5, 0),
                        (17.9, 13, -28), (26.1, 13, 28),
                        (17.2, 21, -30), (26.8, 21, 30),
                        (16.6, 29, -32), (27.4, 29, 32)))
    off = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="2.5" ry="3.9" class="grain" '
        f'transform="rotate({a} {x} {y})" style="--i:{i}"/>'
        for i, (x, y, a) in enumerate(((38, 21, -46), (47, 13, -30),
                                       (56, 6, -16))))
    # The box ends where the drawing ends. Left over empty space under the
    # stem floated the ear above the word it sits beside.
    return (
        '<svg class="mark" viewBox="11 0 49 49" width="49" height="49" '
        'role="img" aria-label="winnow">'
        f'{ear}{off}'
        '<path d="M22 34 V47" stroke="currentColor" stroke-width="2.4" '
        'stroke-linecap="round" fill="none"/>'
        '</svg>')


FONTS = ("https://fonts.googleapis.com/css2?family=Familjen+Grotesk:wght@400"
         ";500;600;700&family=Instrument+Sans:wght@400;500;600&family="
         "JetBrains+Mono:wght@400;500;700&display=swap")

CSS = """
:root{
  --glass:#e9eced; --lit:#fbfcfc; --mount:#191d21; --ink:#10141a;
  --soft:#4d565f; --faint:#8b949c; --rule:#d7dcde;
  --grease:#ce3a24; --amber:#a8710f;
  --display:"Familjen Grotesk","Helvetica Neue",Arial,sans-serif;
  --body:"Instrument Sans",-apple-system,"Segoe UI",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --lift:0 1px 2px rgba(16,20,26,.16), 0 12px 28px -18px rgba(16,20,26,.5);
  --pad:clamp(1.25rem,5vw,5rem);
}
*{box-sizing:border-box;}
html{-webkit-text-size-adjust:100%;}
body{
  margin:0; color:var(--ink); font-family:var(--body); font-size:17px;
  line-height:1.55; -webkit-font-smoothing:antialiased;
  background:
    radial-gradient(120% 70% at 50% -10%, #ffffff 0%, rgba(255,255,255,0) 60%),
    var(--glass);
  background-attachment:fixed;
}
img{max-width:100%; display:block;}
.eyebrow, .comment .lab{
  font-family:var(--mono); font-size:.68rem; font-weight:500;
  letter-spacing:.22em; text-transform:uppercase; color:var(--faint);
  margin:0 0 1rem;
}

/* ---- head ------------------------------------------------------------- */
/* Two columns: the argument on the left, the painting on the right. Millet
   made this page's case in 1847 — a man throws grain in the air so the wind
   takes the husks — and it earns real estate rather than a corner. */
/* The first screen sits on the same light table as the rest of the page.
   It was a dark band for a while — the painting is dark, so giving it a night
   of its own made it bleed instead of sitting there as a rectangle — but the
   whole thing then read as *too much*: a second identity halfway down the
   page. The painting still bleeds; it just does it into the paper, at a third
   of its weight, where it is atmosphere rather than a photograph. */
.head{position:relative; isolation:isolate; overflow:hidden;
  padding:clamp(2.5rem,6vw,4.5rem) var(--pad) clamp(2.5rem,5vw,3.5rem);
  min-height:min(72vh,40rem); display:flex; flex-direction:column;
  justify-content:center;}
.head .say{position:relative; z-index:3; max-width:min(56ch,56%);}
/* Masked sideways and downwards, so no edge of it is ever a line. */
.art{position:absolute; z-index:0; inset:0 0 0 auto; height:100%; width:52%;
  object-fit:cover; object-position:62% 26%; opacity:.34; filter:saturate(.75);
  -webkit-mask-image:linear-gradient(100deg,transparent 6%,#000 58%),
    linear-gradient(#000 62%,transparent 100%);
  mask-image:linear-gradient(100deg,transparent 6%,#000 58%),
    linear-gradient(#000 62%,transparent 100%);
  -webkit-mask-composite:source-in; mask-composite:intersect;
  animation:sink 1.6s cubic-bezier(.2,.8,.3,1) both;}
@keyframes sink{from{opacity:0; transform:scale(1.05);}
  to{opacity:.34; transform:none;}}
/* A scrim in the page's own colour: type has to win over a picture, always. */
.head::after{content:""; position:absolute; inset:0; z-index:1;
  pointer-events:none;
  background:linear-gradient(100deg,var(--glass) 30%,
    rgba(233,236,237,.7) 50%,rgba(233,236,237,0) 74%);}
@keyframes up{from{opacity:0; transform:translateY(14px);}
  to{opacity:1; transform:none;}}

.wordmark{display:flex; align-items:center; gap:.55rem;
  margin:0 0 clamp(1.75rem,4vw,2.6rem);
  animation:up .7s cubic-bezier(.2,.8,.3,1) both;}
.wordmark span{font-family:var(--display); font-weight:700;
  font-size:clamp(1.5rem,3vw,2.1rem); letter-spacing:-.03em; color:var(--ink);}
.wordmark b{font-family:var(--mono); font-size:.7rem; font-weight:400;
  letter-spacing:.18em; color:var(--faint); margin-left:.3rem;
  padding-left:.9rem; border-left:1px solid var(--rule);}
/* «winnow» has neither an ascender nor a descender, so its visual mass sits
   below the centre of its own line box. Centring the mark on that line box is
   geometrically right and looks wrong; 3px down is the optical correction. */
.mark{color:var(--grease); flex:none; width:30px; height:30px;
  transform:translateY(3px);}
.mark .grain{fill:var(--grease); animation:drift 5s ease-in-out infinite;
  animation-delay:calc(var(--i) * .4s);}
@keyframes drift{
  0%,100%{transform:translate(0,0);}
  50%{transform:translate(2.5px,-2px);}
}

.head h1{
  font-family:var(--display); font-weight:700;
  font-size:clamp(1.9rem,4.4vw,3.4rem); line-height:1.05;
  letter-spacing:-.03em; margin:0 0 clamp(1.5rem,3vw,2.1rem); max-width:20ch;
  color:var(--ink);
  animation:up .8s cubic-bezier(.2,.8,.3,1) .1s both;}
.head h1 em{font-style:normal; color:var(--grease);}

/* The one piece of opinion on a page otherwise made of checked facts, so it
   is marked as one. Set as plain body copy it read as a subtitle; hung off a
   red bar it read as decoration stuck on the side. A hairline with the label
   sitting on it is how a magazine opens a column, and it is quiet. */
.comment{position:relative; max-width:50ch; padding-top:1.1rem;
  border-top:1px solid var(--rule);
  animation:up .8s cubic-bezier(.2,.8,.3,1) .2s both;}
.comment .lab{position:absolute; top:-.52rem; left:0; margin:0;
  padding-right:.8rem; background:var(--glass); color:var(--grease);}
.comment p{margin:0 0 .7rem; font-size:clamp(.86rem,.95vw,.94rem);
  line-height:1.68; color:var(--soft);}
.comment p:last-child{margin-bottom:0;}
.comment strong{color:var(--ink); font-weight:600;}
.comment em{font-style:italic;}
.comment code{font-family:var(--mono); font-size:.86em; color:var(--ink);}

.stats{display:flex; flex-wrap:wrap; align-items:baseline; gap:1.5rem;
  margin:clamp(1.6rem,3vw,2.2rem) 0 0;
  animation:up .8s cubic-bezier(.2,.8,.3,1) .3s both;}
.stat{display:flex; align-items:baseline; gap:.45rem; min-height:1.9rem;
  font-family:var(--mono); font-size:.72rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--faint);}
.stat b{font-family:var(--display); font-size:1.3rem; font-weight:600;
  letter-spacing:-.02em; color:var(--ink);}
/* A museum label. Public domain still has an author. */
.credit{position:absolute; z-index:3; right:var(--pad); bottom:1.4rem; margin:0;
  font-size:.72rem; color:var(--faint); text-align:right; max-width:26ch;}
.credit em{font-style:italic;}

/* ---- passed ----------------------------------------------------------- */
.passed{padding:clamp(2rem,5vw,3rem) var(--pad) clamp(3rem,7vw,5rem);
  border-top:1px solid var(--rule);}
.passed h2, .stopped h2{
  font-family:var(--display); font-weight:600;
  font-size:clamp(1.7rem,3.6vw,2.6rem); letter-spacing:-.025em;
  margin:0 0 .6rem;}
.cats{display:flex; flex-wrap:wrap; gap:.4rem; margin:1.6rem 0 2.6rem;}
.cf, .vf{
  font-family:var(--mono); font-size:.7rem; letter-spacing:.1em;
  text-transform:uppercase; cursor:pointer; color:var(--soft);
  background:transparent; border:1px solid var(--rule); border-radius:999px;
  padding:.5rem .95rem; transition:background .18s, color .18s, border-color .18s;
}
.cf:hover, .vf:hover{border-color:var(--ink); color:var(--ink);}
.cf.on, .vf.on{background:var(--ink); border-color:var(--ink); color:var(--lit);}
.vf b{font-weight:500; margin-left:.5rem; opacity:.6;}

.list{display:flex; flex-direction:column; gap:1px; background:var(--lit);
  border:1px solid var(--rule); max-width:78rem;}
.pass{
  display:grid; grid-template-columns:minmax(0,15rem) minmax(0,1fr);
  gap:clamp(1.25rem,3vw,2.75rem); align-items:start;
  background:var(--lit); padding:clamp(1.5rem,3vw,2.25rem);
  border-bottom:1px solid var(--rule);
  opacity:0; transform:translateY(14px);
  transition:opacity .5s ease, transform .5s cubic-bezier(.2,.8,.3,1);
}
.pass:last-child{border-bottom:0;}
.pass.seen{opacity:1; transform:none;}
.pass.hide{display:none;}
.mount{margin:0; background:var(--mount); border-radius:3px; overflow:hidden;
  position:relative; box-shadow:var(--lift);}
/* The name, over the picture: a wall of fifty links does not say which of
   the fifty this entry is, and hunting for it in a screenshot is work. */
.stamp{position:absolute; top:.55rem; left:.55rem; max-width:calc(100% - 1.1rem);
  font-family:var(--mono); font-size:.72rem; font-weight:500; color:#fff;
  background:var(--grease); padding:.3rem .55rem; border-radius:2px;
  box-shadow:0 2px 10px rgba(16,20,26,.35); overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap;}
.mount img{width:100%; aspect-ratio:4/5; object-fit:cover;
  transition:transform .7s cubic-bezier(.2,.8,.3,1);}
.pass:hover .mount img{transform:scale(1.035);}
.mount figcaption{
  font-family:var(--mono); font-size:.62rem; letter-spacing:.12em;
  text-transform:uppercase; color:#8d979e; padding:.55rem .7rem;
  border-top:1px solid rgba(255,255,255,.08);}
.plate{display:grid; place-items:center; aspect-ratio:4/5; padding:1rem;
  background:hsl(var(--h) 22% 16%);}
.plate-n{font-family:var(--mono); font-size:.9rem; color:hsl(var(--h) 30% 78%);
  text-align:center; word-break:break-word;}
.body{min-width:0;}
.tags{display:flex; flex-wrap:wrap; gap:.5rem; margin:0 0 .9rem;}
.tags span{font-family:var(--mono); font-size:.63rem; letter-spacing:.13em;
  text-transform:uppercase; padding:.28rem .6rem; border-radius:2px;}
.tags .cat{background:var(--ink); color:var(--lit);}
.tags .st{border:1px solid var(--rule); color:var(--soft);}
.tags .s-alive{border-color:#2f7d5b; color:#2f7d5b;}
.tags .s-stale{border-color:var(--amber); color:var(--amber);}
.tags .s-absent{border-color:var(--grease); color:var(--grease);}
.pass h3{font-family:var(--display); font-weight:600;
  font-size:clamp(1.35rem,2.5vw,1.85rem); line-height:1.14;
  letter-spacing:-.022em; margin:0 0 .7rem; max-width:26ch;}
.does{margin:0 0 1.1rem; color:var(--soft); max-width:62ch;}
.why, .doubt{margin:0 0 .8rem; max-width:62ch; font-size:.97rem;}
.why{color:var(--ink);}
.doubt{color:var(--amber);}
.lab{display:block; font-family:var(--mono); font-size:.62rem;
  letter-spacing:.15em; text-transform:uppercase; color:var(--faint);
  margin-bottom:.22rem;}
.doubt .lab{color:var(--amber); opacity:.75;}
.why strong, .does strong{font-weight:600;}
.why code, .does code, .r code{font-family:var(--mono); font-size:.86em;}
/* The neighbours on the same slide, and what happened to each. This is the
   answer to "why this one and not the other fifty" — and it has to sit next
   to the thing, not in a list of 129 rows further down the page. */
.sibs{margin:1.4rem 0 0; padding-top:1rem; border-top:1px dashed var(--rule);}
.sibs .lab{margin-bottom:.6rem;}
.sib{display:inline-flex; align-items:baseline; gap:.4rem; margin:0 .35rem .35rem 0;
  padding:.28rem .55rem; border:1px solid var(--rule); border-radius:2px;
  font-family:var(--mono); font-size:.72rem; color:var(--soft);
  background:var(--lit);}
.sib b{font-weight:500; font-size:.62rem; letter-spacing:.08em;
  color:var(--faint);}
.sib.kept{border-color:var(--grease); color:var(--grease);}
.sib.kept b{color:var(--grease);}
/* The name identifies the thing, so it is read, not squinted at. */
.foot{font-family:var(--mono); font-size:.82rem; font-weight:500;
  color:var(--ink); margin:1.2rem 0 .9rem; word-break:break-word;}
.links{display:flex; gap:.6rem; margin:0; flex-wrap:wrap;}
.links a{font-family:var(--mono); font-size:.68rem; letter-spacing:.12em;
  text-transform:uppercase; text-decoration:none; padding:.5rem .9rem;
  border-radius:999px; transition:background .18s, color .18s;}
.links .go{background:var(--grease); color:#fff;}
.links .go:hover{background:#a82c19;}
.links .ghost{border:1px solid var(--rule); color:var(--soft);}
.links .ghost:hover{border-color:var(--ink); color:var(--ink);}

/* ---- stopped ---------------------------------------------------------- */
.stopped{padding:clamp(2.5rem,6vw,4rem) var(--pad) clamp(4rem,9vw,7rem);
  border-top:1px solid var(--rule);}
.intro{max-width:52ch; color:var(--soft); margin:0;}
.vfs{display:flex; flex-wrap:wrap; gap:.4rem; margin:1.8rem 0 2.4rem;}
.vgs{max-width:78rem;}
.vg{margin:0 0 2.6rem;}
.vg.hide{display:none;}
.vg h3{font-family:var(--mono); font-size:.72rem; font-weight:700;
  letter-spacing:.16em; text-transform:uppercase; color:var(--ink);
  margin:0 0 .1rem; padding-bottom:.7rem; border-bottom:1px solid var(--ink);
  display:flex; justify-content:space-between; align-items:baseline;}
.vg h3 b{font-family:var(--display); font-size:1.15rem; font-weight:600;
  color:var(--faint);}
.rows{list-style:none; margin:0; padding:0;}
.rows li{display:grid; grid-template-columns:minmax(0,17rem) minmax(0,1fr);
  gap:.4rem clamp(1rem,3vw,2.5rem); padding:.85rem 0;
  border-bottom:1px solid var(--rule); align-items:baseline;}
.rows li:hover{background:rgba(255,255,255,.55);}
.rows .n{font-family:var(--mono); font-size:.82rem; color:var(--ink);
  word-break:break-word;}
.rows .r{color:var(--soft); font-size:.95rem;}
.rows .r strong{color:var(--ink); font-weight:600;}

/* ---- quality floor ---------------------------------------------------- */
a:focus-visible, button:focus-visible, .mk:focus-visible{
  outline:2px solid var(--grease); outline-offset:3px;}
@media (max-width:900px){
  .head{min-height:auto;}
  .head .say{max-width:100%;}
  .art{width:100%; opacity:.16;
    -webkit-mask-image:linear-gradient(#000 55%,transparent 100%);
    mask-image:linear-gradient(#000 55%,transparent 100%);}
  .head::after{background:linear-gradient(var(--glass) 20%,
    rgba(233,236,237,.55) 60%,rgba(233,236,237,0) 100%);}
  .credit{position:static; text-align:left; margin-top:2.5rem; max-width:100%;}
}
@media (max-width:720px){
  body{font-size:16px;}
  .pass{grid-template-columns:1fr;}
  .mount{max-width:20rem;}
  .rows li{grid-template-columns:1fr;}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none !important; transition:none !important;}
  .pass{opacity:1; transform:none;}
}
@media print{.cats,.vfs{display:none;} .pass{opacity:1; transform:none;}}
"""

# Without JavaScript nothing may be hidden: the filters are a convenience, and
# a page that needs them to show its content is a page that can lose it.
NOSCRIPT = """<noscript><style>
.pass{opacity:1 !important; transform:none !important;}
.cats,.vfs{display:none;}
</style></noscript>"""

JS = """
(function(){
  var pass = [].slice.call(document.querySelectorAll('.pass'));

  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function(es){
      es.forEach(function(e){
        if (e.isIntersecting) { e.target.classList.add('seen'); io.unobserve(e.target); }
      });
    }, {rootMargin:'400px 0px 400px 0px'});
    pass.forEach(function(el){ io.observe(el); });
    // If the observer never fires, for any reason, the page must not stay
    // blank: a screenful of grey reads as an error, not as a page.
    setTimeout(function(){
      pass.forEach(function(el){ el.classList.add('seen'); });
    }, 2500);
  } else {
    pass.forEach(function(el){ el.classList.add('seen'); });
  }

  function group(buttons, targets, attr){
    buttons.forEach(function(b){
      b.addEventListener('click', function(){
        var want = b.dataset[attr];
        buttons.forEach(function(o){ o.classList.toggle('on', o === b); });
        targets.forEach(function(t){
          var show = (want === '*' || t.dataset[attr] === want);
          t.classList.toggle('hide', !show);
          if (show) { t.classList.add('seen'); }
        });
      });
    });
  }
  group([].slice.call(document.querySelectorAll('.cf')), pass, 'cat');
  group([].slice.call(document.querySelectorAll('.vf')),
        [].slice.call(document.querySelectorAll('.vg')), 'v');
})();
"""


def shapes_from(findings_dir: Path | None) -> dict[str, str]:
    """shortcode -> the shape the *collector* recorded for that post.

    Read from the findings and never from the judgement: whether a post is a
    list is an observation made while reading it, and asking the judge to
    repeat it is asking it to remember something it has no reason to know.
    """
    out: dict[str, str] = {}
    if findings_dir is None or not findings_dir.is_dir():
        return out
    for f in sorted(findings_dir.glob("*.json")):
        try:
            day = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for post in day.get("posts", []):
            if post.get("shortcode"):
                out[post["shortcode"]] = post.get("shape", "")
    return out


def render(data: dict, shots: Path | None = None,
           out_dir: Path | None = None,
           shapes: dict[str, str] | None = None,
           embed_shots: bool = False) -> str:
    """Judgement (as data) -> the week, cut in half and both halves shown."""
    week = _esc(data.get("week"))
    lede = "".join(f"<p>{_md(p.strip())}</p>"
                   for p in (data.get("comment") or "").split("\n\n")
                   if p.strip())
    cats = data.get("categories") or []
    stopped = data.get("discarded") or []

    flat: list[tuple[str, dict]] = [(c.get("name") or "", it)
                                    for c in cats
                                    for it in (c.get("items") or [])]
    kept = [it for _, it in flat]
    # Counted over the whole week, not over the fifteen that got through: a
    # slide holding one keeper and eleven rejects is still a wall of links,
    # and asking only the keepers would call it a portrait.
    shared = shared_slides(kept + list(stopped))
    siblings = siblings_map(kept, list(stopped))
    passed = "".join(kept_html(it, i, cat, shots, out_dir, shapes, shared,
                               siblings, embed_shots)
                     for i, (cat, it) in enumerate(flat))
    chips = "".join(f'<button class="cf" data-cat="{_esc(c.get("name"))}">'
                    f'{_esc(c.get("name"))}</button>' for c in cats)
    counts = data.get("counts") or {}
    art = painting_data_uri()
    total = len(kept) + len(stopped)
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>winnow · {week}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style>{NOSCRIPT}</head>
<body>

<header class="head">
  {f'<img class="art" src="{art}" alt="Un contadino lancia il grano in aria: il vento porta via la pula.">' if art else ""}
  <div class="say">
    <p class="wordmark">{logo_svg()}<span>winnow</span><b>{week}</b></p>
    <h1>{total} cose salvate.<br><em>{len(kept)} valgono il tuo tempo.</em></h1>
    {f'<div class="comment"><p class="lab">Il commento della settimana</p>{lede}</div>' if lede else ""}
    <div class="stats">{counts_html(counts)}</div>
  </div>
  <p class="credit">Jean-François Millet, <em>Il vagliatore</em>, 1847–48. Pubblico dominio.</p>
</header>

<section class="passed">
  <p class="eyebrow">Passate</p>
  <h2>Cosa vale il tuo tempo</h2>
  <div class="cats"><button class="cf on" data-cat="*">Tutte</button>{chips}</div>
  <div class="list">{passed}</div>
</section>

{stopped_html(stopped)}

<script>{JS}</script></body></html>
"""


FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.S)


def extract_json(text: str) -> dict:
    """The model answers with prose and a fenced block, not with a file.

    Asking someone to delete the sentences around the JSON before saving it
    is the step where this stops being used. Parse the fence, or the
    outermost object, and only then give up.
    """
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    for block in FENCE_RE.findall(text):
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise json.JSONDecodeError("no JSON object in this file", text, 0)


def paste_from_clipboard() -> str:
    """Whatever is on the clipboard. Best effort, never raises."""
    import shutil
    import subprocess
    for cmd in (["pbpaste"], ["wl-paste"],
                ["xclip", "-selection", "clipboard", "-o"]):
        if shutil.which(cmd[0]):
            try:
                return subprocess.run(cmd, capture_output=True, text=True,
                                      check=True).stdout
            except subprocess.SubprocessError:
                return ""
    return ""


def render_clipboard(recap_dir: Path, shots: Path | None = None,
                     findings: Path | None = None,
                     now: date | None = None) -> Path:
    """The model's answer, straight from the clipboard to a page.

    `winnow recap` never puts anything on the clipboard any more — it writes
    the answer to disk itself. This is the escape hatch for someone who ran
    the judgement outside that command (pasted the bundle into a chat by
    hand, copied the reply back): "save the model's whole answer to a file,
    then render it" was one instruction too many, and the step where it
    stopped being done at all.

    The answer is written down before it is rendered, and never over an
    earlier one: re-asking the model after correcting it is the normal way to
    use this, and a judgement that cost real money must survive both the next
    thing copied and the next attempt.
    """
    text = paste_from_clipboard()
    if not text.strip():
        raise ValueError("the clipboard is empty — copy the model's answer "
                         "first, all of it, including the ```json block")
    # Written down *before* it is parsed. Validating first meant a JSON error
    # destroyed the answer instead of the page: the reply leaves the clipboard
    # the moment anything else is copied — including the error message you
    # copy in order to ask for help, which is how one was lost on 2026-08-25.
    # A broken answer on disk can be repaired by hand; a lost one cannot.
    recap_dir.mkdir(parents=True, exist_ok=True)
    stem = (now or date.today()).isoformat()
    src = recap_dir / f"{stem}.answer.md"
    n = 2
    while src.exists():
        src = recap_dir / f"{stem}.answer-{n}.md"
        n += 1
    src.write_text(text, encoding="utf-8")
    # Slides embedded, always. This is the archive copy — the same reasoning
    # the other call site already carried, and the one place that did not do
    # it. A page with `../state/shots/...` in it is broken the moment it is
    # read from anywhere but its own folder (the app's reader serves it over
    # HTTP, where that path resolves to nothing) and broken for good once
    # `state/shots/` is cleaned, which it has to be or it grows to tens of GB.
    return render_file(src, shots=shots, findings=findings, embed_shots=True)


def blame_json(text: str, err: json.JSONDecodeError) -> str:
    """The line that broke, not the grammar rule that noticed.

    «Expecting property name enclosed in double quotes: line 2 column 3» names
    a rule and hides the text. Showing the line is what makes it fixable —
    and the usual cause is visible the moment you see it: an answer copied out
    of a terminal pane, where long lines were wrapped and truncated on screen.
    """
    lines = text.splitlines()
    n = getattr(err, "lineno", 0) or 0
    if not (1 <= n <= len(lines)):
        return ""
    line = lines[n - 1]
    caret = " " * max(0, (getattr(err, "colno", 1) or 1) - 1) + "^"
    return f"riga {n}:  {line[:160]}\n         {caret[:160]}"


def render_file(src: Path, out: Path | None = None,
                shots: Path | None = None,
                findings: Path | None = None,
                data: dict | None = None,
                embed_shots: bool = False) -> Path:
    if data is None:
        data = extract_json(src.read_text(encoding="utf-8"))
    out = out or src.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    from winnow import paths
    if shots is None:
        shots = paths.shots_dir()
    shapes = shapes_from(findings if findings is not None else paths.findings_dir())
    out.write_text(
        render(data, shots if shots.is_dir() else None, out.parent, shapes,
               embed_shots),
        encoding="utf-8")
    return out
