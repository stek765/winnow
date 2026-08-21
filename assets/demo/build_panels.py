#!/usr/bin/env python3
"""The two "Once a week" panels: the tool's half, and yours.

Static PNGs, not a GIF — the point is a side-by-side you can stare at, and an
animation makes the reader wait for the half they want. Drawn with the same
primitives, palette and Instagram-pink card as the explainer GIF.

    python3 assets/demo/build_panels.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build import (  # noqa: E402
    ACCENT, INK, MONO, MUTED, OK, PAPER, SANS, SERIF, SOFT,
    arrow, box, ig_post, text,
)

W, H = 480, 452


def frame(body: str) -> str:
    return f'''<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">
<defs>
  <linearGradient id="igGrad" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#fbd6c4"/><stop offset="45%" stop-color="#f3a8b8"/>
    <stop offset="100%" stop-color="#e08ab4"/>
  </linearGradient>
  <marker id="arrM" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
    <polygon points="0 0, 7 3, 0 6" fill="{MUTED}"/></marker>
  <marker id="arrA" markerWidth="7" markerHeight="6" refX="7" refY="3" orient="auto">
    <polygon points="0 0, 7 3, 0 6" fill="{ACCENT}"/></marker>
</defs>
<rect width="{W}" height="{H}" fill="{PAPER}"/>
{body}
</svg>'''


def panel_tool():
    """Start: a saved post. Result: the recap. Nothing in between —
    findings.json is true, but it is plumbing, and plumbing in the picture is
    what made this section take five minutes to read."""
    out = [ig_post(174, 32, 132, 148, saved=1.0)]
    out.append(arrow(240, 180, 240, 210))
    out.append(text(252, 202, "EVERY NIGHT", size=9, family=MONO, ls=0.1,
                    fill=SOFT))

    out.append(box(40, 220, 400, 196, rx=10, fill="#ffffff",
                   stroke="rgba(45,49,66,0.28)"))
    out.append(text(240, 296, "The weekly recap", size=28, family=SERIF,
                    anchor="middle"))
    out.append(text(240, 332, "kept  \u00b7  thrown out  \u00b7  why", size=14,
                    family=MONO, anchor="middle", fill=MUTED))
    out.append(text(240, 376, "ONE MINUTE, ONCE A WEEK", size=10, family=MONO,
                    ls=0.12, anchor="middle", fill=SOFT))
    return frame("".join(out))


def panel_you():
    """Start: the file you write. Result: a sentence nobody else would get."""
    out = [box(120, 32, 240, 148, rx=10, fill="#ffffff", stroke=ACCENT, sw=1.2),
           f'<line x1="120" y1="72" x2="360" y2="72" stroke="rgba(235,108,54,0.35)" '
           f'stroke-width="1"/>',
           text(240, 58, "profile.md", size=14, family=MONO, anchor="middle",
                fill=ACCENT, weight=600)]
    for i, line in enumerate(["what you want",
                              "what you already decided",
                              "what you ruled out"]):
        out.append(f'<circle cx="146" cy="{100 + i * 28:.0f}" r="3" fill="{ACCENT}"/>')
        out.append(text(162, 104 + i * 28, line, size=13, family=SANS, fill=INK))

    out.append(arrow(240, 180, 240, 210, accent=True))
    out.append(text(252, 202, "WINNOW RECAP", size=9, family=MONO, ls=0.1,
                    fill=ACCENT))

    out.append(box(40, 220, 400, 196, rx=10, fill="rgba(235,108,54,0.06)",
                   stroke=ACCENT))
    out.append(text(64, 250, "YOUR WEEK, FILTERED", size=10, family=MONO,
                    ls=0.12, fill=ACCENT))

    # Both rows carry real numbers from the run of 2026-08-20, and both are
    # alive and popular *on purpose*: if the kept one were the bigger of the
    # two, the picture would say "it keeps what is popular", which is what
    # every other feed already does. Equal facts, opposite verdicts — so the
    # only thing left that could have decided is the file above.
    # Named repos meant nothing to a reader who does not follow the scene —
    # `cline/cline` is not an argument, it is trivia. What the two rows have to
    # show is the *kind* of thing and which line of the file decided it. Both
    # kinds are lifted from the shipped profile template, so the mapping is
    # something the reader can go and check.
    for i, (mark, mark_col, name, name_col, stars, reason) in enumerate((
        ("\u2713", OK, "a self-hosted notes app", INK, "48k \u2605 \u00b7 alive",
         "\u21b3 what you want"),
        ("\u2717", SOFT, "another crypto bot", SOFT, "31k \u2605 \u00b7 alive",
         "\u21b3 what you ruled out"),
    )):
        y = 288 + i * 64
        out.append(text(64, y, mark, size=14, family=MONO, fill=mark_col))
        out.append(text(88, y, name, size=15, family=SANS, weight=600,
                        fill=name_col))
        out.append(text(416, y, stars, size=12, family=MONO, fill=OK,
                        anchor="end"))
        out.append(text(88, y + 20, reason, size=12, family=MONO, fill=ACCENT))
        if i == 0:
            out.append(f'<line x1="64" y1="{y + 40}" x2="416" y2="{y + 40}" '
                       f'stroke="rgba(45,49,66,0.12)" stroke-width="0.8"/>')

    out.append(text(240, 400, "BOTH REAL \u00b7 BOTH ALIVE \u00b7 YOUR FILE DECIDED", size=11,
                    family=MONO, ls=0.1, anchor="middle"))
    return frame("".join(out))


PANELS = {"winnow-half-tool": panel_tool(), "winnow-half-you": panel_you()}


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "diagrams"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        for name, svg in PANELS.items():
            html = (
                '<!doctype html><meta charset="utf-8">'
                '<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif'
                '&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600'
                '&display=swap" rel="stylesheet">'
                f'<style>html,body{{margin:0;background:{PAPER}}}</style>{svg}')
            src = out_dir / f"{name}.html"
            src.write_text(html, encoding="utf-8")
            pg.goto(f"file://{src.resolve()}")
            pg.wait_for_load_state("networkidle")
            pg.evaluate("document.fonts.ready")
            pg.locator("svg").first.screenshot(path=str(out_dir / f"{name}.png"))
            print("\u2192", out_dir / f"{name}.png")
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
