#!/usr/bin/env python3
"""Build the winnow explainer GIF: drawn scenes, not screen recordings.

Every frame is an SVG rendered from the same design tokens as the README
diagrams. Frames are stacked into one HTML page, screenshotted by Playwright,
then assembled by ffmpeg.

Numbers shown are the real ones from the run of 2026-08-20.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

W, H = 960, 452
FPS = 12

PAPER = "#f5f5f5"
INK = "#2d3142"
MUTED = "#4f5d75"
SOFT = "#7a8399"
ACCENT = "#eb6c36"
RULE = "rgba(45,49,66,0.12)"
OK = "#4a7c59"
PINK = "#d64a86"
PINK_SOFT = "rgba(214,74,134,0.10)"
PINK_LINE = "rgba(214,74,134,0.35)"

MONO = "'Geist Mono', ui-monospace, monospace"
SANS = "'Geist', system-ui, sans-serif"
SERIF = "'Instrument Serif', serif"


# ----------------------------------------------------------------- easing

def ease(t: float) -> float:
    """Smooth in/out, clamped."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def seg(t: float, start: float, end: float) -> float:
    """Sub-progress of [start,end] within a 0..1 scene, eased."""
    if end <= start:
        return 1.0
    return ease((t - start) / (end - start))


def fade(op: float) -> str:
    return f'opacity="{max(0.0, min(1.0, op)):.3f}"'


# ------------------------------------------------------------- primitives

def text(x, y, s, size=13, fill=INK, family=SANS, anchor="start", weight=400,
         ls=0, op=1.0):
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
            f'font-family="{family}" text-anchor="{anchor}" font-weight="{weight}" '
            f'letter-spacing="{ls}em" {fade(op)}>{s}</text>')


def box(x, y, w, h, rx=8, fill="#ffffff", stroke=RULE, sw=1, op=1.0, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d} {fade(op)}/>')


def caption(s, op=1.0, sub=None):
    out = text(W / 2, 104, s, size=26, family=SERIF, anchor="middle", op=op)
    if sub:
        out += text(W / 2, 130, sub, size=11, fill=SOFT, family=MONO,
                    anchor="middle", ls=0.06, op=op)
    return out


def chrome(active: int) -> str:
    """Name plus the whole chain, always on screen.

    A GIF loops, so a reader arrives mid-story. Six pips at the bottom said
    "you are somewhere in a sequence"; the chain says which sequence and where.
    """
    out = [text(40, 34, "winnow", size=17, family=SERIF, op=0.9)]
    stages = ["SAVE", "FOLDER", "SLIDES", "NAMES", "CHECK", "RECAP"]
    x = W - 40
    for i in range(len(stages) - 1, -1, -1):
        on = i == active
        label = stages[i]
        w = len(label) * 6.4
        x -= w
        out.append(text(x, 33, label, size=9, family=MONO, ls=0.1,
                        fill=(ACCENT if on else "rgba(45,49,66,0.32)"),
                        weight=(600 if on else 400)))
        if on:
            out.append(f'<rect x="{x - 4:.1f}" y="{40}" width="{w + 8:.1f}" '
                       f'height="2" rx="1" fill="{ACCENT}"/>')
        x -= 16
        if i:
            out.append(text(x + 5, 33, "·", size=9, family=MONO,
                            fill="rgba(45,49,66,0.25)"))
    out.append(f'<line x1="40" y1="54" x2="{W - 40}" y2="54" stroke="{RULE}" '
               f'stroke-width="0.8"/>')
    return "".join(out)


def bookmark(cx, cy, s, filled: float, color=PINK):
    """Instagram's save icon. `filled` 0..1 fills it from the bottom."""
    w, h = 11 * s, 14 * s
    x, y = cx - w / 2, cy - h / 2
    outline = (f'<path d="M{x},{y} L{x + w},{y} L{x + w},{y + h} '
               f'L{cx},{y + h - 4.5 * s} L{x},{y + h} Z" fill="none" '
               f'stroke="{color}" stroke-width="{1.6 * s:.1f}" stroke-linejoin="round"/>')
    if filled <= 0.01:
        return outline
    clip_h = h * filled
    cid = f"bm{int(cx)}{int(cy)}{int(filled * 100)}"
    return (f'<defs><clipPath id="{cid}"><rect x="{x - 2}" y="{y + h - clip_h:.1f}" '
            f'width="{w + 4}" height="{clip_h + 2:.1f}"/></clipPath></defs>'
            f'<path d="M{x},{y} L{x + w},{y} L{x + w},{y + h} '
            f'L{cx},{y + h - 4.5 * s} L{x},{y + h} Z" fill="{color}" '
            f'clip-path="url(#{cid})"/>' + outline)


def ig_post(x, y, w, h, saved=0.0, op=1.0, dim=1.0, label=None):
    """A generic Instagram post card: header, pink photo, action bar."""
    g = [f'<g {fade(op)}>']
    g.append(box(x, y, w, h, rx=10, fill="#ffffff", stroke=PINK_LINE, sw=1.2))
    # header
    g.append(f'<circle cx="{x + 20}" cy="{y + 20}" r="9" fill="{PINK_SOFT}" '
             f'stroke="{PINK_LINE}" stroke-width="1"/>')
    g.append(box(x + 36, y + 15, 62, 5, rx=2.5, fill="rgba(45,49,66,0.16)", stroke="none"))
    g.append(box(x + 36, y + 24, 38, 4, rx=2, fill="rgba(45,49,66,0.09)", stroke="none"))
    # photo
    ph_y, ph_h = y + 38, h - 76
    g.append(f'<rect x="{x + 1}" y="{ph_y}" width="{w - 2}" height="{ph_h}" '
             f'fill="url(#igGrad)" opacity="{dim:.2f}"/>')
    # a suggestion of content inside the photo
    g.append(box(x + 16, ph_y + ph_h - 30, w * 0.55, 6, rx=3,
                 fill="rgba(255,255,255,0.75)", stroke="none"))
    g.append(box(x + 16, ph_y + ph_h - 19, w * 0.34, 5, rx=2.5,
                 fill="rgba(255,255,255,0.5)", stroke="none"))
    # action bar
    ay = y + h - 20
    for i, cx in enumerate((x + 20, x + 42, x + 64)):
        g.append(f'<circle cx="{cx}" cy="{ay}" r="5.5" fill="none" '
                 f'stroke="rgba(45,49,66,0.28)" stroke-width="1.3"/>')
    g.append(bookmark(x + w - 22, ay, 1.0, saved))
    if label:
        g.append(text(x + w / 2, y + h + 20, label, size=10, fill=SOFT,
                      family=MONO, anchor="middle", ls=0.08))
    g.append("</g>")
    return "".join(g)


def arrow(x1, y1, x2, y2, op=1.0, color=MUTED, accent=False, width=1.4):
    mk = "arrA" if accent else "arrM"
    c = ACCENT if accent else color
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{c}" stroke-width="{width}" marker-end="url(#{mk})" {fade(op)}/>')


def chip(x, y, label, kind="plain", op=1.0, w=None):
    """A name pulled out of a slide."""
    w = w or 9 + len(label) * 6.6
    fill, stroke, col = {
        "plain": ("#ffffff", "rgba(45,49,66,0.30)", INK),
        "ok":    ("rgba(74,124,89,0.10)", OK, OK),
        "none":  ("rgba(45,49,66,0.03)", "rgba(45,49,66,0.22)", SOFT),
    }[kind]
    return (box(x, y, w, 22, rx=5, fill=fill, stroke=stroke, sw=1, op=op)
            + text(x + w / 2, y + 15, label, size=11, fill=col, family=MONO,
                   anchor="middle", op=op)), w


# ---------------------------------------------------------------- scenes

def scene_save(t: float) -> str:
    """1 — You save a post. The bookmark fills."""
    o = seg(t, 0.0, 0.15)
    saved = seg(t, 0.34, 0.56)
    out = [caption("You save a post.", o,
                   "AND NEVER GO BACK TO IT" if t > 0.62 else None)]
    x, y, w, h = W / 2 - 118, 156, 224, 244
    lift = (1 - seg(t, 0.05, 0.3)) * 14
    out.append(ig_post(x, y - lift, w, h, saved=saved, op=o))
    if saved > 0.2:
        out.append(text(x + w - 22, y + h + 4, "saved", size=9, fill=PINK,
                        family=MONO, anchor="middle", ls=0.1, op=saved))
        r = 12 + 26 * seg(t, 0.34, 0.62)
        ring = (1 - seg(t, 0.34, 0.62)) * 0.5
        out.append(f'<circle cx="{x + w - 22}" cy="{y + h - 20}" r="{r:.1f}" '
                   f'fill="none" stroke="{PINK}" stroke-width="1.2" {fade(ring)}/>')
    return "".join(out) + chrome(0)


def scene_folder(t: float) -> str:
    """2 — The folder fills up. winnow looks at what is new."""
    o = seg(t, 0.0, 0.12)
    out = [caption("The folder fills up.", o,
                   "24 SAVED · 8 NEVER OPENED" if t > 0.5 else None)]
    cols, rows, cw, ch, gap = 4, 2, 132, 96, 18
    gx = W / 2 - (cols * cw + (cols - 1) * gap) / 2
    gy = 176
    new = {1, 2, 5, 6}
    for i in range(cols * rows):
        cx = gx + (i % cols) * (cw + gap)
        cy = gy + (i // cols) * (ch + gap)
        pop = seg(t, 0.08 + i * 0.035, 0.28 + i * 0.035)
        is_new = i in new and t > 0.55
        hl = seg(t, 0.55, 0.72) if is_new else 0.0
        out.append(f'<g {fade(pop * o)}>')
        out.append(box(cx, cy, cw, ch, rx=8,
                       fill="#ffffff",
                       stroke=(ACCENT if hl > 0.5 else PINK_LINE), sw=1 + hl))
        out.append(f'<rect x="{cx + 1}" y="{cy + 1}" width="{cw - 2}" height="{ch - 34}" '
                   f'rx="7" fill="url(#igGrad)" opacity="{0.85 if not is_new else 1.0}"/>')
        out.append(box(cx + 12, cy + ch - 24, cw * 0.5, 5, rx=2.5,
                       fill="rgba(45,49,66,0.14)", stroke="none"))
        out.append(bookmark(cx + cw - 18, cy + ch - 18, 0.8, 1.0))
        if hl > 0.3:
            out.append(text(cx + 12, cy + ch - 10, "NEW", size=8, fill=ACCENT,
                            family=MONO, ls=0.12, op=hl))
        out.append("</g>")
    return "".join(out) + chrome(1)


def scene_slides(t: float) -> str:
    """3 — It opens the carousel, slide by slide. This is where the names are."""
    o = seg(t, 0.0, 0.12)
    total = 7
    idx = min(total - 1, int(t * 8.4))
    out = [caption("It opens every slide.", o,
                   "THE CAPTION NAMES NONE OF THEM")]
    cw, ch = 200, 250
    cx0, cy = W / 2 - cw / 2, 168
    # the deck behind
    for d in (2, 1):
        out.append(box(cx0 + d * 7, cy + d * 5, cw, ch, rx=10, fill="#ffffff",
                       stroke="rgba(45,49,66,0.10)", op=o * 0.8))
    slide_in = seg((t * 8.4) % 1.0, 0.0, 0.45)
    out.append(f'<g {fade(o)}>')
    out.append(box(cx0, cy, cw, ch, rx=10, fill="#ffffff", stroke=PINK_LINE, sw=1.2))
    out.append(f'<rect x="{cx0 + 1}" y="{cy + 1}" width="{cw - 2}" height="{ch - 56}" '
               f'rx="9" fill="url(#igGrad)" opacity="0.9"/>')
    # the slide's content: a heading and two named lines
    out.append(text(cx0 + 20, cy + 44, "9 REPOS", size=16, fill="#8a2b52",
                    family=SANS, weight=600))
    out.append(text(cx0 + 20, cy + 60, "WORTH BOOKMARKING", size=8, fill="#a8446b",
                    family=MONO, ls=0.1))
    names = ["cline/cline", "firecrawl", "crewAI", "pipecat-ai",
             "anything-llm", "postiz-app", "browser-use"]
    out.append(box(cx0 + 18, cy + 74, cw - 36, 26, rx=5,
                   fill="rgba(255,255,255,0.86)", stroke="none", op=slide_in))
    out.append(text(cx0 + cw / 2, cy + 91, names[idx], size=12, fill=INK,
                    family=MONO, anchor="middle", op=slide_in))
    out.append(box(cx0 + 18, cy + 110, (cw - 36) * 0.6, 6, rx=3,
                   fill="rgba(255,255,255,0.5)", stroke="none"))
    # pagination
    for i in range(total):
        on = i == idx
        out.append(f'<circle cx="{cx0 + cw / 2 - (total - 1) * 7 + i * 14:.1f}" '
                   f'cy="{cy + ch - 22}" r="{3.5 if on else 2.5}" '
                   f'fill="{PINK if on else "rgba(45,49,66,0.20)"}"/>')
    out.append(text(cx0 + cw / 2, cy + ch + 26, f"slide {idx + 1}/{total}", size=10,
                    fill=SOFT, family=MONO, anchor="middle", ls=0.08))
    out.append("</g>")
    return "".join(out) + chrome(2)


def scene_extract(t: float) -> str:
    """4 — Names come out of the slides."""
    o = seg(t, 0.0, 0.1)
    out = [caption("It pulls out the names.", o, "REPOS · MODELS · PRODUCTS")]
    cw, ch = 150, 190
    cx0, cy = 96, 196
    out.append(box(cx0, cy, cw, ch, rx=10, fill="#ffffff", stroke=PINK_LINE,
                   sw=1.2, op=o))
    out.append(f'<rect x="{cx0 + 1}" y="{cy + 1}" width="{cw - 2}" height="{ch - 40}" '
               f'rx="9" fill="url(#igGrad)" opacity="0.5"/>')
    out.append(text(cx0 + cw / 2, cy + ch - 14, "7 slides", size=10, fill=SOFT,
                    family=MONO, anchor="middle", ls=0.08, op=o))
    items = [("cline/cline", "plain"), ("firecrawl", "plain"), ("crewAI", "plain"),
             ("browser-use", "plain"), ("some tool", "none")]
    for i, (name, kind) in enumerate(items):
        p = seg(t, 0.16 + i * 0.11, 0.42 + i * 0.11)
        if p <= 0.01:
            continue
        y = 190 + i * 36
        x_from, x_to = cx0 + cw - 10, 420
        x = x_from + (x_to - x_from) * p
        c, w = chip(x, y, name, kind, op=p)
        out.append(c)
        out.append(arrow(cx0 + cw + 6, cy + ch / 2, x - 8, y + 11, op=p * 0.5))
    return "".join(out) + chrome(3)


def scene_verify(t: float) -> str:
    """5 — Each name is checked at the source. Three outcomes, never merged."""
    o = seg(t, 0.0, 0.1)
    out = [caption("It checks each one at the source.", o,
                   "GITHUB · HUGGING FACE")]
    # All three outcomes, because collapsing them is the one thing the tool
    # must never do. Every value here is from the real run of 2026-08-20.
    rows = [("cline/cline", "66.542 ★", "today", "ok"),
            ("firecrawl", "169.996 ★", "today", "ok"),
            ("Claude Code", "no model by that name", "", "gone"),
            ("some product", "no source to ask", "", "none")]
    x, y0 = 200, 206
    out.append(box(x - 24, y0 - 24, 584, 196, rx=10, fill="rgba(45,49,66,0.02)",
                   stroke=RULE, op=o))
    out.append(text(x, y0 - 6, "NAME", size=8, fill=SOFT, family=MONO, ls=0.14, op=o))
    out.append(text(x + 300, y0 - 6, "AT THE SOURCE", size=8, fill=SOFT,
                    family=MONO, ls=0.14, op=o))
    for i, (name, val, when, kind) in enumerate(rows):
        p = seg(t, 0.12 + i * 0.15, 0.34 + i * 0.15)
        if p <= 0.01:
            continue
        y = y0 + 22 + i * 38
        good = kind == "ok"
        mark = {"ok": "✓", "gone": "✗", "none": "?"}[kind]
        col = {"ok": OK, "gone": ACCENT, "none": SOFT}[kind]
        out.append(text(x, y + 4, name, size=13, fill=INK, family=MONO, op=p))
        # the check "travels" before it resolves
        travel = seg(t, 0.12 + i * 0.15, 0.28 + i * 0.15)
        out.append(f'<line x1="{x + 150}" y1="{y}" x2="{x + 150 + 130 * travel:.1f}" '
                   f'y2="{y}" stroke="{RULE}" stroke-width="1" {fade(p)}/>')
        if travel > 0.98:
            r = seg(t, 0.28 + i * 0.15, 0.4 + i * 0.15)
            out.append(text(x + 300, y + 4, val, size=(13 if good else 11),
                            fill=col, family=MONO, op=r))
            if when:
                out.append(text(x + 400, y + 4, when, size=10, fill=SOFT,
                                family=MONO, op=r))
            out.append(text(x + 520, y + 5, mark, size=15, fill=col, family=SANS,
                            weight=600, op=r))
    return "".join(out) + chrome(4)


def scene_recap(t: float) -> str:
    """6 — Findings meet your profile. Only then does anything get judged."""
    o = seg(t, 0.0, 0.1)
    out = [caption("Your profile decides what survives.", o,
                   "FACTS + WHO YOU ARE = THE RECAP")]
    # findings — bottom left
    fx, fy = 88, 268
    out.append(box(fx, fy, 196, 112, rx=8, fill="rgba(45,49,66,0.05)",
                   stroke=MUTED, op=o))
    out.append(text(fx + 14, fy + 26, "findings", size=13, fill=INK, family=SANS,
                    weight=600, op=o))
    out.append(text(fx + 14, fy + 44, "42 names, 17 checked", size=10, fill=MUTED,
                    family=MONO, op=o))
    for i in range(3):
        out.append(box(fx + 14, fy + 60 + i * 13, 150 - i * 34, 5, rx=2.5,
                       fill="rgba(45,49,66,0.16)", stroke="none", op=o))
    # your profile — top left, clear of the caption
    px, py = 88, 166
    pop = seg(t, 0.14, 0.34)
    out.append(box(px, py, 196, 76, rx=8, fill="rgba(235,108,54,0.08)",
                   stroke=ACCENT, op=pop))
    out.append(text(px + 14, py + 28, "your profile", size=13, fill=INK,
                    family=SANS, weight=600, op=pop))
    out.append(text(px + 14, py + 48, "what you ruled out", size=10, fill=ACCENT,
                    family=MONO, op=pop))
    # into the judgement
    jx, jy, jw, jh = 480, 176, 384, 216
    a1 = seg(t, 0.3, 0.46)
    out.append(arrow(px + 196, py + 38, jx - 10, jy + 54, op=a1, accent=True))
    out.append(arrow(fx + 196, fy + 56, jx - 10, jy + jh - 66, op=a1))
    rp = seg(t, 0.42, 0.6)
    out.append(box(jx, jy, jw, jh, rx=10, fill="#ffffff", stroke=INK, op=rp))
    out.append(text(jx + 24, jy + 34, "the weekly recap", size=15, fill=INK,
                    family=SANS, weight=600, op=rp))
    out.append(f'<line x1="{jx + 24}" y1="{jy + 50}" x2="{jx + jw - 24}" '
               f'y2="{jy + 50}" stroke="{RULE}" stroke-width="1" {fade(rp)}/>')
    kept = seg(t, 0.52, 0.66)
    out.append(text(jx + 24, jy + 78, "✓  kept", size=11, fill=OK, family=MONO,
                    ls=0.06, op=kept))
    out.append(text(jx + 24, jy + 100, "cline/cline · firecrawl", size=12, fill=INK,
                    family=MONO, op=kept))
    out.append(text(jx + 24, jy + 118, "alive today, and new to you", size=10,
                    fill=MUTED, family=MONO, op=kept))
    drop = seg(t, 0.64, 0.78)
    out.append(text(jx + 24, jy + 154, "✗  thrown out", size=11, fill=MUTED,
                    family=MONO, ls=0.06, op=drop))
    out.append(text(jx + 24, jy + 176, "another freelance marketplace", size=12,
                    fill=MUTED, family=MONO, op=drop))
    out.append(text(jx + 24, jy + 194, "the 4th this month — you ruled", size=10,
                    fill=SOFT, family=MONO, op=drop))
    out.append(text(jx + 24, jy + 208, "that category out in August", size=10,
                    fill=SOFT, family=MONO, op=drop))
    return "".join(out) + chrome(5)


def scene_end(t: float) -> str:
    o = seg(t, 0.0, 0.22)
    out = [text(W / 2, H / 2 - 10, "winnow", size=44, family=SERIF,
                anchor="middle", op=o)]
    out.append(text(W / 2, H / 2 + 18, "a filter for the posts you save",
                    size=13, fill=MUTED, family=SANS, anchor="middle", op=o))
    out.append(text(W / 2, H / 2 + 52, "github.com/stek765/winnow", size=11,
                    fill=SOFT, family=MONO, anchor="middle", ls=0.08,
                    op=seg(t, 0.2, 0.45)))
    return "".join(out)


SCENES = [
    (scene_save, 2.3),
    (scene_folder, 2.5),
    (scene_slides, 2.7),
    (scene_extract, 2.7),
    (scene_verify, 3.4),
    (scene_recap, 3.9),
    (scene_end, 1.7),
]


def svg_frame(body: str) -> str:
    return f'''<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">
<defs>
  <linearGradient id="igGrad" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#fbd6c4"/><stop offset="45%" stop-color="#f3a8b8"/>
    <stop offset="100%" stop-color="#e08ab4"/>
  </linearGradient>
  <marker id="arrM" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
    <polygon points="0 0, 7 3, 0 6" fill="{MUTED}"/></marker>
  <marker id="arrA" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
    <polygon points="0 0, 7 3, 0 6" fill="{ACCENT}"/></marker>
</defs>
<rect width="{W}" height="{H}" fill="{PAPER}"/>
{body}
</svg>'''


def namespace_ids(svg: str, i: int) -> str:
    """Every frame lives in the same HTML document, so `id="igGrad"` would be
    defined 250 times and every `url(#igGrad)` would resolve to the first one —
    which sits in a hidden subtree and paints nothing."""
    svg = re.sub(r'id="([^"]+)"', lambda m: f'id="{m.group(1)}-f{i}"', svg)
    return re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{m.group(1)}-f{i})", svg)


def build_frames() -> list[str]:
    frames = []
    for fn, dur in SCENES:
        n = max(1, round(dur * FPS))
        for i in range(n):
            frames.append(svg_frame(fn(i / (n - 1) if n > 1 else 1.0)))
    return [namespace_ids(f, i) for i, f in enumerate(frames)]


HTML = """<!doctype html><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>html,body{margin:0;padding:0;background:%s}
.f{display:none}.f.on{display:block}svg{display:block}</style>
<div id="stage">%s</div>
<script>
const fs=[...document.querySelectorAll('.f')];
window.setFrame=i=>{fs.forEach(f=>f.classList.remove('on'));fs[i].classList.add('on');};
window.frameCount=fs.length;setFrame(0);
</script>"""


def render_gif(frames: list[str], out: Path, work: Path) -> None:
    """Frames -> PNGs -> GIF. Shared by every explainer built from this file."""
    shots = work / "frames"
    shots.mkdir(exist_ok=True)
    for old in shots.glob("*.png"):
        old.unlink()

    page_html = HTML % (PAPER, "".join(f'<div class="f">{s}</div>' for s in frames))
    page = work / "frames.html"
    page.write_text(page_html, encoding="utf-8")
    print(f"{len(frames)} frames -> {page}")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto(f"file://{page.resolve()}")
        pg.wait_for_load_state("networkidle")
        pg.evaluate("document.fonts.ready")
        n = pg.evaluate("window.frameCount")
        for i in range(n):
            pg.evaluate(f"setFrame({i})")
            pg.screenshot(path=str(shots / f"{i:04d}.png"))
        b.close()
    print(f"rendered {n} png")

    pal = work / "palette.png"
    vf = f"fps={FPS},scale={W}:-1:flags=lanczos"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", str(shots / "%04d.png"), "-vf",
                    f"{vf},palettegen=max_colors=128:stats_mode=diff", str(pal)],
                   check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", str(shots / "%04d.png"), "-i", str(pal), "-lavfi",
                    f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
                    "-loop", "0", str(out)], check=True)
    pal.unlink(missing_ok=True)
    print(f"{out}  {out.stat().st_size / 1e6:.2f} MB")


def main() -> int:
    here = Path(__file__).parent
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "winnow-demo.gif"
    render_gif(build_frames(), out, here)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
