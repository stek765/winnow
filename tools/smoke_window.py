"""Drive the window through a whole run, without a model and without money.

Not a unit test, for the same reason `bench_extract.py` is not one: the test
suite is offline and stays that way. But the window is the one part of winnow
that no offline test can prove works — `pytest` reads `index.html` as text, so
a variable that was never declared parses perfectly and then throws the moment
somebody presses the button.

That is not hypothetical. `startJob` assigned `ticker` and called `phaseOf`,
and neither existed: every press threw before the polling began, the server did
the work, and the window sat still saying nothing until the four-second refresh
noticed the answer minutes later. `node --check` passed. The suite passed.

So: a real server, a real browser, fabricated jobs that emit exactly the events
`run.py` emits, and a failure if the page throws anything at all.

    python tools/smoke_window.py            # all three kinds
    python tools/smoke_window.py --shots /tmp/out   # and write screenshots

Needs playwright (`pip install playwright && playwright install chromium`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import winnow.api as A

# The events each kind of run emits, in order, with the fields the window
# reads. Kept beside nothing else on purpose: if `run.py` starts emitting a
# new one, this list is where it is noticed that the window has no wording
# for it.
SCRIPTS: dict[str, list[tuple[str, dict]]] = {
    "collect": [
        ("folder", {"name": "github", "found": 81, "new": 10}),
        ("folder", {"name": "ai", "found": 24, "new": 0}),
        ("post", {"i": 1, "n": 3, "account": "tizio", "slides": 5}),
        ("extracted", {"names": ["a/b", "c/d"], "shape": "list"}),
        ("verified", {"name": "a/b", "checked": True, "exists": True,
                      "stars": 900}),
        ("verified", {"name": "x/y", "checked": False, "note": "rate limit"}),
        ("verified", {"name": "n/o", "checked": True, "exists": False}),
        ("post", {"i": 2, "n": 3, "account": "caio", "slides": 1}),
        ("failed", {"shortcode": "ABC", "error": "unreadable"}),
        ("post", {"i": 3, "n": 3, "account": "sempronio", "slides": 9}),
        ("written", {"path": "/tmp/f.json", "entities": 40, "verified": 22,
                     "usd": 0.06}),
    ],
    "recap": [
        ("sliced", {"days": 1, "of": 2, "left": 20}),
        ("bundling", {"days": 1, "posts": 30, "things": 40, "chars": 90000}),
        ("asking", {"attempt": 1, "of": 3}),
        ("writing", {"chars": 1200}),
        ("writing", {"chars": 9100}),
        ("waiting", {"seconds": 8, "why": "overloaded"}),
        ("asking", {"attempt": 2, "of": 3}),
        ("judged", {"kept": 12, "of": 67, "binned": 55, "sections": 4,
                    "usd": 0.06}),
    ],
    "ideas": [
        ("drawing", {"drawn": 8, "of": 40}),
        ("asking", {"attempt": 1, "of": 3}),
        ("writing", {"chars": 800}),
        ("dreamt", {"ideas": 1, "of": 8, "usd": 0.02}),
    ],
}

STEP = 0.45          # seconds between two events, so a phase is observable


def serve_fake() -> tuple[ThreadingHTTPServer, int, A.Jobs]:
    """The real engine, with the three POSTs that start work replaced.

    Everything else — the archive, the config, the look — is the real route,
    because a window fed a fake of everything proves nothing.
    """
    jobs = A.Jobs()
    ui = Path(A.__file__).resolve().parent / "ui"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), A.make_handler(jobs, ui))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    real = A.route

    def fake(method, path, payload, j, spawn=None):
        kind = path.rsplit("/", 1)[1]
        if method == "POST" and kind in SCRIPTS:
            jid = jobs.start(kind)

            def work() -> None:
                for name, data in SCRIPTS[kind]:
                    time.sleep(STEP)
                    jobs.event(jid, name, data)
                time.sleep(STEP)
                jobs.finish(jid, 0)

            threading.Thread(target=work, daemon=True).start()
            return 202, {"id": jid}
        return real(method, path, payload, j, spawn)

    A.route = fake
    return httpd, httpd.server_address[1], jobs


async def run(shots: Path | None) -> int:
    from playwright.async_api import async_playwright

    httpd, port, _ = serve_fake()
    trouble: list[str] = []
    seen: dict[str, list] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 950})
        page.on("pageerror", lambda e: trouble.append(f"page error: {e}"))
        page.on("console", lambda m: trouble.append(f"console: {m.text}")
                if m.type == "error" else None)
        await page.goto(f"http://127.0.0.1:{port}/")
        await page.wait_for_timeout(1200)

        # Where each kind writes: the home screen's log, or the draw window's.
        LOGS = {"recap": "#log", "collect": "#log", "ideas": "#sow-log"}

        async def drive(name: str, selector: str) -> None:
            await page.click(selector)
            # Three quarters through: far enough in that every panel must be
            # saying something, before the end resets all of them. Half way is
            # too early for a draw — its first event prints no line on purpose,
            # because the die is the thing that says it is working.
            await page.wait_for_timeout(STEP * len(SCRIPTS[name]) * 750)
            seen[name] = await page.evaluate(
                "[$('phase').textContent, $('clock').textContent,"
                " $('fill').style.width, $('gauge').className,"
                " [].slice.call(document.querySelectorAll('" + LOGS[name] +
                " p')).map(p => p.textContent),"
                " $('sow-run-stamp').textContent]")
            if shots:
                await page.screenshot(path=str(shots / f"{name}.png"))
            # Let it finish, or the next press lands on a busy engine.
            await page.wait_for_timeout(STEP * len(SCRIPTS[name]) * 1000)

        # Which button starts which run depends on the state the machine is
        # actually in: `act` is whatever matters most right now, and `also` is
        # the quiet second action beside it — which is not on the screen when
        # there is nothing to offer as a second. Asked, never assumed.
        async def button_for(kind: str) -> str | None:
            if await page.evaluate(f"$('act').dataset.action === '{kind}'"):
                return "#act"
            if await page.evaluate(
                    f"!$('also').hidden && $('also').dataset.action === '{kind}'"):
                return "#also"
            return None

        for kind in ("recap", "collect"):
            where = await button_for(kind)
            if where is None:
                print(f"\n  {kind}\n    – no button for it in this state")
                continue
            await drive(kind, where)
            await page.wait_for_timeout(600)
        await page.click("[data-go='archive']")
        await page.wait_for_timeout(700)
        await drive("ideas", "#dream")

        # One run at a time, and the ones that cannot start have to say so.
        # A silent refusal is what this whole file exists to catch: the engine
        # answers 409 either way, so what is being checked here is the
        # window's half — the button dims, the press is answered in words
        # beside it, and both go away when the run is over.
        # The draw leaves its window open over everything else.
        if not await page.evaluate("$('sow').hidden"):
            await page.click("#sow-close")
            await page.wait_for_timeout(400)
        await page.click("[data-go='home']")
        await page.wait_for_timeout(400)
        await page.click("#act")
        await page.wait_for_timeout(900)
        await page.click("[data-go='archive']")
        await page.wait_for_timeout(500)
        dimmed = await page.evaluate("$('dream').classList.contains('busy')")
        await page.click("#dream")
        await page.wait_for_timeout(500)
        note = await page.evaluate(
            "[$('dream-note').hidden, $('dream-note').textContent]")
        print("\n  busy")
        print(f"    dimmed  {dimmed}")
        print(f"    said    {note[1]!r}")
        if not dimmed:
            print("    ✗ the button looks as pressable as ever")
            trouble.append("no dimming while busy")
        if note[0] or not note[1]:
            print("    ✗ a press that started nothing and said nothing")
            trouble.append("silent refusal")

        await browser.close()
    httpd.shutdown()

    bad = 0
    for name, (phase, clock, fill, gauge, log, stamp) in seen.items():
        print(f"\n  {name}")
        print(f"    phase   {phase!r}")
        print(f"    clock   {clock!r}    bar {fill!r} ({gauge})")
        for row in log:
            print(f"    log     {row}")
        if not log:
            print(f"    stamp   {stamp!r}")
        # A phase still on its opening line this far in means nothing was
        # read; an empty clock means the ticker never started.
        if not phase:
            print("    ✗ no phase")
            bad += 1
        if not clock:
            print("    ✗ the clock never started")
            bad += 1
        # A draw prints no log line while it draws — the die is what says it
        # is working — so the panel's own stamp counts as having spoken.
        if not log and not stamp:
            print("    ✗ nothing was said")
            bad += 1
    for t in trouble:
        print(f"  ✗ {t}")
    if trouble or bad:
        print(f"\n  {len(trouble) + bad} problems\n")
        return 1
    print("\n  the window follows all three kinds of run\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shots", type=Path, default=None,
                    help="write a screenshot of each run into this directory")
    args = ap.parse_args()
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    return asyncio.run(run(args.shots))


if __name__ == "__main__":
    sys.exit(main())
