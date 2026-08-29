"""Crop app screenshots down to the window, and shrink them for the README.

    python3 tools/crop_shots.py shot1.png shot2.png ...

Writes `<name>.jpg` beside each input at 1400px wide.

Finding the window is the whole job, and two obvious methods do not work:

- **Sampling the wallpaper from the corners.** The wallpaper is textured, so
  no two corners agree and nearly every pixel counts as "not background".
- **Walking down the left margin from the top.** It matches the wallpaper by
  accident and stops a few hundred pixels in.

What does work is the traffic lights: three coloured dots every macOS window
has, in the same place at the same size. From the red one, the title bar is a
band of near-uniform colour, and left, right and top are the ends of that band.
The bottom is found by walking *up* from the foot of the image along the
window's own left margin — going up cannot match wallpaper by accident,
because the wallpaper is never that colour.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

RED = (255, 95, 87)
WIDE = 1400


def near(a, b, tol):
    return sum(abs(x - y) for x, y in zip(a, b)) <= tol


def window_box(im: Image.Image) -> tuple[int, int, int, int]:
    w, h = im.size
    px = im.load()
    lit = None
    for y in range(0, min(h, 400), 2):
        for x in range(0, min(w, 700), 2):
            if near(px[x, y], RED, 130):
                lit = (x, y)
                break
        if lit:
            break
    if not lit:
        return 0, 0, w, h
    lx, ly = lit
    bar = px[min(w - 1, lx + 320), ly]
    left = lx
    while left > 0 and near(px[left - 1, ly], bar, 90):
        left -= 1
    right = lx + 320
    while right < w - 1 and near(px[right + 1, ly], bar, 90):
        right += 1
    top = ly
    while top > 0 and near(px[left + 8, top - 1], bar, 90):
        top -= 1
    probe, ground, bottom = left + 40, px[left + 40, top + 300], h - 1
    for y in range(h - 1, top + 300, -1):
        if near(px[probe, y], ground, 40):
            bottom = y
            break
    return left, top, right + 1, bottom + 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for name in argv:
        src = Path(name)
        im = Image.open(src).convert("RGB")
        im = im.crop(window_box(im))
        w, h = im.size
        if w > WIDE:
            im = im.resize((WIDE, round(h * WIDE / w)), Image.LANCZOS)
        # JPEG, not PNG: each of these is mostly the painting, and PNG stored
        # the set at five times the size for no visible gain.
        out = src.with_suffix(".jpg")
        im.save(out, "JPEG", quality=90, optimize=True, progressive=True)
        print(f"{src.name} {w}x{h} -> {out.name} {out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
