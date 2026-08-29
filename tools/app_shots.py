"""Retake the six README screenshots, in whatever language the app is set to.

    python3 tools/app_shots.py assets/app

The six were taken by hand on macOS and cropped by `crop_shots.py`, which is
fine once and miserable the second time: the set has to be retaken *whole* —
mixing two languages, or two grounds, across it makes the app look like two
apps — and doing that by hand means six windows, six crops and six chances to
leave one behind.

So the window is driven instead. `?native=1` is the same switch the desktop
shell throws, so the padding and the rounded corners are the real ones; the
traffic lights are drawn in, because a browser has none and the set has always
had them.

The engine underneath is the real one — the real archive, the real pages, the
real settings — with only the three POSTs that start work faked, exactly as
`smoke_window.py` does it, so no model is called and nothing is spent.

⚠️ What is on screen is your own data. Read `assets/app/SHOTS.md` before
committing the result.

Needs playwright and pillow.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image
from smoke_window import STEP, SCRIPTS, serve_fake

WIDE = 1400          # what crop_shots.py writes, so the README does not move
SHOT = (1400, 998)   # the window the six were taken in

# macOS draws them at the same place at any size, and the crop has always
# started at the window's own edge — so these are the coordinates the existing
# six were measured at, not an invention.
LIGHTS = """
<div style="position:fixed;top:11px;left:12px;z-index:99;display:flex;gap:8px">
  <i style="width:17px;height:17px;border-radius:50%;background:#f2675f"></i>
  <i style="width:17px;height:17px;border-radius:50%;background:#f4bf4f"></i>
  <i style="width:17px;height:17px;border-radius:50%;background:#63c357"></i>
</div>"""


async def shoot(page, out: Path, name: str) -> None:
    """Full window, downscaled to the README's width, as JPEG.

    JPEG because each of these is mostly a photograph: the six were 2.9 MB as
    PNG and 600 KB this way.
    """
    raw = await page.screenshot()
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    if im.width != WIDE:
        im = im.resize((WIDE, round(im.height * WIDE / im.width)),
                       Image.LANCZOS)
    im.save(out / f"{name}.jpg", quality=88, optimize=True, progressive=True)
    print(f"  {name}.jpg   {im.size[0]}×{im.size[1]}")


async def run(out: Path, want: dict[str, str]) -> int:
    from playwright.async_api import async_playwright

    httpd, port, _ = serve_fake()
    trouble: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": SHOT[0],
                                                "height": SHOT[1]},
                                      device_scale_factor=2)
        page.on("pageerror", lambda e: trouble.append(f"page error: {e}"))
        await page.goto(f"http://127.0.0.1:{port}/?native=1")
        await page.wait_for_timeout(1500)
        await page.evaluate(
            "html => document.body.insertAdjacentHTML('beforeend', html)",
            LIGHTS)

        state = await page.evaluate("$('face').className")
        print(f"  home is in state: {state}")
        await shoot(page, out, "home")

        # A run in flight. The recap's is the one worth showing: it is the
        # phase that takes minutes, which is what the bar and the clock exist
        # for. Captured while the model is «writing», three quarters in.
        which = await page.evaluate(
            "$('act').dataset.action === 'recap' ? '#act'"
            " : (!$('also').hidden && $('also').dataset.action === 'recap')"
            " ? '#also' : null")
        if which:
            await page.click(which)
            await page.wait_for_timeout(STEP * len(SCRIPTS["recap"]) * 750)
            await shoot(page, out, "working")
            await page.wait_for_timeout(STEP * len(SCRIPTS["recap"]) * 1000)
        else:
            print("  working: no recap to start from this state — skipped")

        await page.click("[data-go='archive']")
        await page.wait_for_timeout(900)
        await page.click("[data-only='all']")
        await page.wait_for_timeout(500)
        await shoot(page, out, "archive")

        # The two pages, opened the way a reader opens them. The newest of
        # each kind: an older one was written in an older language.
        async def open_first(kind: str, name: str, only: str,
                             close: str) -> None:
            # Newest of its kind by default, or the one named on the command
            # line. Which page gets photographed is an editorial decision, not
            # an ordering: the newest recap of 29 August quoted a third
            # party's handle in its comment, and a README is a public place.
            kind = want.get(name) or kind
            # The filter is re-applied on the way back from a page, so the
            # list a click lands in is not necessarily the one left behind.
            # Asked for by name each time rather than assumed.
            await page.click(f"[data-only='{only}']")
            await page.wait_for_timeout(500)
            sel = f".card[data-file*='{kind}']:not([hidden])"
            if not await page.query_selector(sel):
                print(f"  {name}: no {kind} page in the archive — skipped")
                return
            await page.click(sel)
            await page.wait_for_timeout(1600)
            await shoot(page, out, name)
            # A recap opens the reader screen; a draw opens its own window
            # over everything. Two different ways out, and the wrong one hangs
            # on an element that is on the page and never visible.
            await page.click(close)
            await page.wait_for_timeout(700)

        await open_first("answer", "recap", "week", "#back")
        await open_first("idee-", "idea", "ideas", "#sow-close")

        await page.click("[data-go='settings']")
        await page.wait_for_timeout(900)
        await page.click("[data-edit='theme']")
        await page.wait_for_timeout(700)
        await shoot(page, out, "theme")

        await browser.close()
    httpd.shutdown()

    if trouble:
        print("\n  the page threw:")
        for t in trouble:
            print("   ", t)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="assets/app",
                    help="where the six jpgs go (default: assets/app)")
    ap.add_argument("--recap", metavar="PART",
                    help="part of the filename of the recap to photograph "
                         "(default: the newest)")
    ap.add_argument("--idea", metavar="PART",
                    help="same, for the idea (default: the newest)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    want = {k: v for k, v in (("recap", args.recap), ("idea", args.idea)) if v}
    return asyncio.run(run(out, want))


if __name__ == "__main__":
    raise SystemExit(main())
