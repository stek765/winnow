"""The weekly recap as a page you click, not a wall you read.

The judge decides what matters; this file decides nothing. It takes the
judgement as data and lays it out — which is why the layout lives in code and
not in the prompt: an interface a model rewrites every week is a different
interface every week, and sometimes a broken one.

The shape it expects:

    {
      "week": "2026-08-21",
      "counts": {"posts": 136, "kept": 19, "failed": 7, "usd": 0.333},
      "comment": "one paragraph about the pile, or several",
      "categories": [
        {
          "name": "Hardware e radio",
          "icon": "📡",
          "items": [
            {
              "does": "Guarda cosa trasmettono le radio intorno a te",
              "name": "BatchDrake/SigDigger",
              "stars": 2871,
              "state": "alive",            # alive | stale | unknown | absent
              "last_commit": "2026-02",
              "why": "RED è metà della tua tesi, e questo è lo strumento
                      con cui si guarda ciò che la norma regola",
              "url": "https://github.com/BatchDrake/SigDigger"
            }
          ]
        }
      ]
    }

`does` is the headline and `name` is the footnote, deliberately: a repo slug
tells you nothing you can scan, and scanning is the whole point.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

STATES = {
    "alive":   ("✓", "alive"),
    "stale":   ("◔", "stale"),
    "unknown": ("?", "unchecked"),
    "absent":  ("✗", "absent at the source"),
}


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _stars(n: object) -> str:
    """4200 -> 4.2k. A star count is a size, and sizes are read at a glance."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def item_html(item: dict) -> str:
    mark, label = STATES.get(item.get("state", "unknown"), STATES["unknown"])
    state = item.get("state", "unknown")
    name = _esc(item.get("name"))
    if item.get("url"):
        name = f'<a href="{_esc(item["url"])}" target="_blank" rel="noopener">{name}</a>'
    meta = " · ".join(filter(None, [
        name,
        _stars(item.get("stars")) + "★" if _stars(item.get("stars")) else "",
        _esc(item.get("last_commit")),
    ]))
    why = _esc(item.get("why"))
    return f"""<li class="item">
  <p class="does">{_esc(item.get("does"))}</p>
  <p class="meta"><span class="st st-{state}" title="{label}">{mark}</span> {meta}</p>
  {f'<p class="why">{why}</p>' if why else ""}
</li>"""


def category_html(cat: dict, index: int) -> str:
    items = cat.get("items") or []
    # <details> and not JS tabs: it prints, it works with the page saved to
    # disk, it survives a browser with scripting off, and the keyboard opens it.
    return f"""<details class="cat"{' open' if index == 0 else ''}>
  <summary>
    <span class="ico">{_esc(cat.get("icon") or "•")}</span>
    <span class="cname">{_esc(cat.get("name"))}</span>
    <span class="count">{len(items)}</span>
  </summary>
  <ul class="items">
{chr(10).join(item_html(i) for i in items)}
  </ul>
</details>"""


def counts_html(counts: dict) -> str:
    cells = [
        ("posts read", counts.get("posts")),
        ("kept", counts.get("kept")),
        ("failed", counts.get("failed")),
        ("cost", f"${counts.get('usd', 0):.2f}" if counts.get("usd") is not None else None),
    ]
    return "".join(
        f'<div class="cell"><b>{_esc(v)}</b><span>{label}</span></div>'
        for label, v in cells if v is not None)


CSS = """
:root {
  --ground:#f3f5f4; --panel:#fbfcfb; --ink:#171c1b; --soft:#4a5654;
  --faint:#75817f; --rule:#d6dcda; --signal:#1b6d66; --warn:#8a6412;
  --bad:#a03726;
  --serif:"Source Serif 4",Georgia,serif;
  --sans:system-ui,-apple-system,"Helvetica Neue",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,monospace;
}
:root:not([data-theme=light]) { }
@media (prefers-color-scheme: dark) { :root:not([data-theme=light]) {
  --ground:#101514; --panel:#161c1b; --ink:#e4eae8; --soft:#a9b5b2;
  --faint:#7c8886; --rule:#2a3332; --signal:#57b3aa; --warn:#d6ac58;
  --bad:#e08a76;
}}
:root[data-theme=dark] {
  --ground:#101514; --panel:#161c1b; --ink:#e4eae8; --soft:#a9b5b2;
  --faint:#7c8886; --rule:#2a3332; --signal:#57b3aa; --warn:#d6ac58;
  --bad:#e08a76;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); line-height:1.5;
  padding:3rem 1.25rem 5rem; }
.wrap { max-width:44rem; margin:0 auto; }
.eyebrow { font-family:var(--mono); font-size:.7rem; letter-spacing:.16em;
  text-transform:uppercase; color:var(--signal); margin:0 0 .4rem; }
h1 { font-family:var(--sans); font-size:2.4rem; font-weight:700;
  letter-spacing:-.02em; margin:0 0 .1rem; }
h1 span { display:block; font-weight:400; color:var(--soft); }
.counts { display:flex; flex-wrap:wrap; border:1px solid var(--rule);
  border-radius:6px; overflow:hidden; margin:1.6rem 0 2.4rem;
  background:var(--panel); }
.cell { flex:1 1 5.5rem; padding:.7rem .9rem; border-right:1px solid var(--rule); }
.cell:last-child { border-right:0; }
.cell b { display:block; font-family:var(--mono); font-size:1.15rem; }
.cell span { font-family:var(--mono); font-size:.62rem; letter-spacing:.1em;
  text-transform:uppercase; color:var(--faint); }
.comment { font-family:var(--serif); font-size:1.06rem; border-left:3px solid var(--signal);
  padding:.1rem 0 .1rem 1.1rem; margin:0 0 2.6rem; }
.comment p { margin:.7rem 0; }
.cat { border:1px solid var(--rule); border-radius:6px; background:var(--panel);
  margin-bottom:.6rem; }
.cat summary { cursor:pointer; padding:.85rem 1rem; display:flex; gap:.6rem;
  align-items:center; font-weight:600; list-style:none; }
.cat summary::-webkit-details-marker { display:none; }
.cat summary::after { content:"+"; margin-left:auto; font-family:var(--mono);
  color:var(--faint); font-weight:400; }
.cat[open] summary::after { content:"−"; }
.cat[open] summary { border-bottom:1px solid var(--rule); }
.count { font-family:var(--mono); font-size:.75rem; color:var(--faint);
  font-weight:400; }
.items { list-style:none; margin:0; padding:.4rem 0; }
.item { padding:.85rem 1rem; border-bottom:1px solid var(--rule); }
.item:last-child { border-bottom:0; }
.does { font-weight:600; font-size:1rem; margin:0 0 .25rem; }
.meta { font-family:var(--mono); font-size:.76rem; color:var(--faint);
  margin:0 0 .3rem; }
.meta a { color:var(--faint); }
.why { font-family:var(--serif); font-size:.95rem; color:var(--soft); margin:0; }
.st { font-weight:700; }
.st-alive { color:var(--signal); } .st-stale, .st-unknown { color:var(--warn); }
.st-absent { color:var(--bad); }
footer { font-family:var(--mono); font-size:.7rem; color:var(--faint);
  margin-top:2.5rem; border-top:1px solid var(--rule); padding-top:1rem; }
"""


def render(data: dict) -> str:
    """Judgement (as data) -> one self-contained page."""
    week = _esc(data.get("week"))
    comment = data.get("comment") or ""
    paras = "".join(f"<p>{_esc(p.strip())}</p>"
                    for p in comment.split("\n\n") if p.strip())
    cats = data.get("categories") or []
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>winnow · {week}</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<p class="eyebrow">winnow · weekly recap</p>
<h1>Setaccio<span>{week}</span></h1>
<div class="counts">{counts_html(data.get("counts") or {})}</div>
<div class="comment">{paras}</div>
{chr(10).join(category_html(c, i) for i, c in enumerate(cats))}
<footer>{sum(len(c.get("items") or []) for c in cats)} items in
{len(cats)} categories · click a category to open it</footer>
</div></body></html>
"""


def render_file(src: Path, out: Path | None = None) -> Path:
    data = json.loads(src.read_text(encoding="utf-8"))
    out = out or src.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    return out
