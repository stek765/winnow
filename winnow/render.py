"""The judgement, as a page you scan instead of a file you read.

The model answers with JSON. This turns it into a page whose subject is not
the finds but **the cut**: a hundred and forty-four things went in and fifteen
came out, and the half that got stopped is half the product. A reader who
cannot see what was thrown away, and on what grounds, has no way to tell a
filter from a coin toss — and no way to correct it.

So the page has three parts, in this order:

  * the count, and one short paragraph that has to earn its place;
  * **the sieve** — every thing in the week as one mark, the kept ones lit.
    It is the only decoration on the page and it is not decoration: it is the
    ratio, at the size the ratio deserves;
  * what passed, with the slide it came from, and what stopped, grouped by
    the *verdict* that stopped it, with the count next to each.

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
from pathlib import Path

# Words, not symbols. A tick and a circle need a legend; these do not.
STATES = {
    "alive":   "vivo",
    "stale":   "fermo",
    "unknown": "non verificato",
    "absent":  "assente alla fonte",
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


def slide_note(item: dict, shapes: dict[str, str] | None = None,
               shared: set[tuple[str, int]] | None = None) -> str:
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


def _facts(item: dict) -> str:
    """Name, size, age — the footnote line, in that order."""
    stars = _stars(item.get("stars"))
    return " · ".join(filter(None, [
        _esc(item.get("name")),
        f"{stars}★" if stars else "",
        _esc(item.get("last_commit")),
    ]))


def sieve_html(kept: list[dict], stopped: list[dict]) -> str:
    """Every thing in the week as one mark. The kept ones lit.

    The signature element, and the only one: it is the ratio at the size the
    ratio deserves. Each mark carries its own name, so the block is not a
    graphic of the number — it is the number, made of the things.
    """
    total = len(kept) + len(stopped)
    if not total:
        return ""
    marks = []
    for i, it in enumerate(kept):
        marks.append(f'<i class="mk on" style="--n:{i}" '
                     f'title="{_esc(it.get("name") or it.get("title"))}"></i>')
    for j, it in enumerate(stopped):
        marks.append(f'<i class="mk" style="--n:{len(kept) + j}" '
                     f'title="{_esc(it.get("name"))} — '
                     f'{_esc(it.get("verdict") or "fermata")}"></i>')
    return f"""<section class="sieve">
  <p class="eyebrow">Il setaccio</p>
  <div class="marks">{"".join(marks)}</div>
  <p class="key"><span class="k-on">{len(kept)} passate</span>
     <span class="k-off">{len(stopped)} fermate</span>
     <span class="k-tot">{total} cose in tutto</span></p>
</section>"""


def kept_html(item: dict, i: int, cat: str, shots: Path | None,
              out_dir: Path | None, shapes: dict[str, str] | None = None,
              shared: set | None = None) -> str:
    """One thing that got through: the slide, then why it got through."""
    src = _rel(shot_for(item, shots, shapes, shared), out_dir)
    pic = (f'<img loading="lazy" src="{_esc(src)}" alt="">' if src
           else plate(item))
    note = slide_note(item, shapes, shared)
    post = post_of(item)
    n = _slide_of(item)
    stamp = f"slide {n}" if post and n > 0 else ""
    if note:
        stamp = f"{stamp} · {note}" if stamp else note
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
    {pic}
    {f'<figcaption>{_esc(stamp)}</figcaption>' if stamp else ''}
  </figure>
  <div class="body">
    <p class="tags"><span class="cat">{_esc(cat)}</span><span
       class="st s-{state}">{_esc(STATES.get(item.get("state", "unknown"),
                                             STATES["unknown"]))}</span></p>
    <h3>{_esc(item.get("title") or item.get("does"))}</h3>
    <p class="does">{_md(item.get("does"))}</p>
    <p class="why"><span class="lab">Perche' passa</span>{_md(item.get("why"))}</p>
    {f'<p class="doubt"><span class="lab">Dubbio</span>{doubt}</p>' if doubt else ''}
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
  <p class="intro">Ognuna col suo nome e il suo motivo, perche' un mucchio non
    si puo' correggere. I numeri qui sotto sono la forma del ragionamento:
    se uno e' sbagliato, e' li' che si vede.</p>
  <div class="vfs"><button class="vf on" data-v="*">Tutte<b>{len(rows)}</b></button>{chips}</div>
  <div class="vgs">{"".join(blocks)}</div>
</section>"""


def counts_html(counts: dict) -> str:
    cells = [(counts.get("posts"), "post letti"),
             (counts.get("kept"), "passate"),
             (counts.get("failed"), "illeggibili"),
             (None, f"${counts.get('usd', 0):.2f}"
              if counts.get("usd") is not None else None)]
    out = []
    for v, label in cells:
        if label is None:
            continue
        num = f"<b>{_esc(v)}</b>" if v is not None else ""
        out.append(f'<span class="stat">{num}<span>{_esc(label)}</span></span>')
    return "".join(out)


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
.eyebrow{
  font-family:var(--mono); font-size:.68rem; font-weight:500;
  letter-spacing:.22em; text-transform:uppercase; color:var(--faint);
  margin:0 0 1rem;
}

/* ---- head ------------------------------------------------------------- */
.head{padding:clamp(3rem,9vw,7rem) var(--pad) clamp(2rem,5vw,3.5rem); max-width:78rem;}
.head h1{
  font-family:var(--display); font-weight:700;
  font-size:clamp(2.6rem,8.5vw,6.4rem); line-height:.94;
  letter-spacing:-.035em; margin:0 0 1.6rem; max-width:16ch;
}
.head h1 em{font-style:normal; color:var(--grease);}
.lede{max-width:56ch; font-size:clamp(1.02rem,1.6vw,1.2rem); color:var(--soft);}
.lede p{margin:0 0 .85rem;}
.lede strong{color:var(--ink); font-weight:600;}
.lede code{font-family:var(--mono); font-size:.86em; color:var(--ink);}
.stats{display:flex; flex-wrap:wrap; gap:1.75rem; margin:2.4rem 0 0;}
.stat{display:flex; align-items:baseline; gap:.45rem; min-height:1.9rem;
  font-family:var(--mono); font-size:.74rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--faint);}
.stat b{font-family:var(--display); font-size:1.5rem; font-weight:600;
  letter-spacing:-.02em; color:var(--ink);}

/* ---- the sieve -------------------------------------------------------- */
.sieve{padding:clamp(2rem,5vw,3rem) var(--pad) clamp(2.5rem,6vw,4rem);
  border-top:1px solid var(--rule); max-width:78rem;}
.marks{display:flex; flex-wrap:wrap; gap:4px 3px; max-width:62rem;}
.mk{
  width:7px; height:30px; border-radius:1px; background:#c2c9cc;
  transform-origin:bottom center; animation:grow .5s cubic-bezier(.2,.8,.3,1) both;
  animation-delay:calc(var(--n)*7ms);
}
.mk.on{background:var(--grease); height:44px;}
.mk:hover{background:var(--ink);}
.mk.on:hover{background:#8e2214;}
@keyframes grow{from{transform:scaleY(0); opacity:0;} to{transform:scaleY(1); opacity:1;}}
.key{display:flex; flex-wrap:wrap; gap:1.5rem; margin:1.6rem 0 0;
  font-family:var(--mono); font-size:.72rem; letter-spacing:.1em;
  text-transform:uppercase; color:var(--faint);}
.key span{display:flex; align-items:center; gap:.5rem;}
.key span::before{content:""; width:9px; height:9px; border-radius:50%;
  background:#c2c9cc;}
.key .k-on::before{background:var(--grease);}
.key .k-tot::before{display:none;}

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
  box-shadow:0 1px 2px rgba(16,20,26,.16), 0 12px 28px -18px rgba(16,20,26,.5);}
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
.foot{font-family:var(--mono); font-size:.72rem; color:var(--faint);
  margin:1.2rem 0 .9rem; word-break:break-word;}
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
@media (max-width:720px){
  body{font-size:16px;}
  .pass{grid-template-columns:1fr;}
  .mount{max-width:20rem;}
  .rows li{grid-template-columns:1fr;}
  .mk{height:22px;} .mk.on{height:32px;}
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
    // Se per qualsiasi ragione l'osservatore non scatta, la pagina non puo'
    // restare vuota: una schermata di grigio si legge come un errore.
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
           shapes: dict[str, str] | None = None) -> str:
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
    passed = "".join(kept_html(it, i, cat, shots, out_dir, shapes, shared)
                     for i, (cat, it) in enumerate(flat))
    chips = "".join(f'<button class="cf" data-cat="{_esc(c.get("name"))}">'
                    f'{_esc(c.get("name"))}</button>' for c in cats)
    counts = data.get("counts") or {}
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
  <p class="eyebrow">winnow · {week}</p>
  <h1>{total} cose.<br><em>{len(kept)} passate.</em></h1>
  <div class="lede">{lede}</div>
  <div class="stats">{counts_html(counts)}</div>
</header>

{sieve_html(kept, stopped)}

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


def render_file(src: Path, out: Path | None = None,
                shots: Path | None = None,
                findings: Path | None = None) -> Path:
    data = extract_json(src.read_text(encoding="utf-8"))
    out = out or src.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    from winnow import paths
    if shots is None:
        shots = paths.shots_dir()
    shapes = shapes_from(findings if findings is not None else paths.findings_dir())
    out.write_text(
        render(data, shots if shots.is_dir() else None, out.parent, shapes),
        encoding="utf-8")
    return out
