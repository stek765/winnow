"""Playwright session against Instagram, using a dedicated browser profile."""
from __future__ import annotations

import random
import re
import time
from contextlib import contextmanager
from pathlib import Path

BASE = "https://www.instagram.com"
SHORTCODE_RE = re.compile(r"/p/([A-Za-z0-9_-]+)/?")

# Frasi che compaiono solo sulla pagina di accesso.
LOGGED_OUT_MARKERS = (
    "Accedi a Instagram",
    "Log in to Instagram",
    "Password dimenticata",
)


class SessionExpired(RuntimeError):
    """The Instagram session is gone. Stop; never retry in a loop."""


def parse_shortcodes(hrefs: list[str]) -> list[str]:
    out: list[str] = []
    for href in hrefs:
        m = SHORTCODE_RE.search(href)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def looks_logged_out(page_url: str, page_text: str) -> bool:
    if "/accounts/login" in page_url:
        return True
    return any(marker in page_text for marker in LOGGED_OUT_MARKERS)


def human_pause(low: float = 1.5, high: float = 4.0) -> None:
    """Irregular waits. 30 posts in four minutes, every day, gets noticed."""
    time.sleep(random.uniform(low, high))


@contextmanager
def open_session(profile_dir: Path):
    from playwright.sync_api import sync_playwright

    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,  # Instagram tratta male l'headless
            viewport={"width": 1440, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            yield page
        finally:
            context.close()


def _guard_session(page) -> None:
    if looks_logged_out(page.url, page.inner_text("body")):
        raise SessionExpired(
            "Instagram session expired. Run 'winnow login', sign in by hand, "
            "then try again. I do not retry on my own."
        )


POST_LINK_SELECTOR = "a[href*='/p/']"
GRID_TIMEOUT_MS = 20_000


# Instagram paints one screenful and loads the rest as you scroll. Reading the
# DOM straight after load therefore sees ~12-24 posts and *nothing else* — a
# folder of two hundred looks like a folder of twenty, with no error anywhere.
# Once those are marked seen, the run reports "0 new" forever while the backlog
# sits below the fold.
SCROLL_STALLS = 3          # letture consecutive senza crescita = fine griglia
SCROLL_WAIT_S = 4.0        # attesa che il batch successivo compaia
MAX_POSTS_PER_FOLDER = 400  # tetto: una cartella enorme non deve girare a vuoto


def keep_scrolling(before: int, after: int, stalls: int,
                   cap: int = MAX_POSTS_PER_FOLDER) -> tuple[bool, int]:
    """Decide whether to scroll again, and carry the stall count.

    Split out of the browser loop on purpose: "when do I stop scrolling" is the
    logic that decides whether a folder is read whole or in part, and it must be
    testable without a browser.
    """
    if after >= cap:
        return False, stalls
    if after > before:
        return True, 0
    stalls += 1
    return stalls < SCROLL_STALLS, stalls


def _merge(into: list[str], page) -> None:
    """Add the shortcodes currently in the DOM, keeping order, skipping dupes.

    Read at every step, never once at the end: Instagram recycles the grid and
    drops the rows that scrolled out of view, so a single read after scrolling
    returns the *tail* of the folder and loses everything above it. Measured on
    a real account — 39 posts came back and not one of them was among the 24
    read before scrolling.
    """
    hrefs = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))")
    known = set(into)
    for code in parse_shortcodes([h for h in hrefs if h]):
        if code not in known:
            known.add(code)
            into.append(code)


class Stopped(RuntimeError):
    """The person pressed «Ferma». Not a failure, and not something to retry."""


def list_shortcodes(page, folder_url: str, enough=None,
                    should_stop=None) -> list[str]:
    """List the posts in a saved folder — the whole folder, not the first screen.

    The grid is lazy-loaded, so we wait for the links themselves rather than for
    a fixed number of seconds: a clock-based wait is a coin flip that silently
    reports an empty folder when the network is slow. Same reason we stop
    scrolling on "nothing new came in" and never on "N scrolls done".
    """
    page.goto(BASE + folder_url, wait_until="domcontentloaded")
    _guard_session(page)
    try:
        page.wait_for_selector(POST_LINK_SELECTOR, timeout=GRID_TIMEOUT_MS)
    except Exception:
        # Genuinely empty folder, or a layout change. Either way: report zero
        # rather than guess, and let the caller notice.
        _guard_session(page)
        return []
    human_pause(1.0, 2.0)

    codes: list[str] = []
    stalls = 0

    def stop_asked() -> bool:
        return bool(should_stop and should_stop())

    while True:
        # A folder of 300 saved posts is a minute of scrolling before a single
        # post is opened, and «Ferma» pressed in that minute used to do
        # nothing at all: the only checkpoint was between two posts, which had
        # not started yet.
        if stop_asked():
            raise Stopped("fermata mentre leggeva la cartella")
        _merge(codes, page)
        before = len(codes)
        if before >= MAX_POSTS_PER_FOLDER:
            break
        if enough is not None and enough(codes):
            break
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        deadline = time.time() + SCROLL_WAIT_S
        while time.time() < deadline:
            time.sleep(0.4)
            if stop_asked():
                raise Stopped("fermata mentre leggeva la cartella")
            _merge(codes, page)
            if len(codes) > before:
                break
        again, stalls = keep_scrolling(before, len(codes), stalls)
        if not again:
            break
        human_pause(0.6, 1.4)
    return codes


SAVED_RE = re.compile(r"^/[^/]+/saved/([^/]+)/(\d+)/?$")


def parse_saved_folders(hrefs: list[str]) -> list[tuple[str, str]]:
    """Saved-folder links -> [(name, url)], in page order, deduplicated.

    Instagram's own "All posts" pseudo-folder has no id and no name of its
    own; it never matches, which is what we want — winnow reads folders you
    made on purpose.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href in hrefs:
        href = (href or "").split("?")[0]
        m = SAVED_RE.match(href)
        if not m or href in seen:
            continue
        seen.add(href)
        url = href if href.endswith("/") else href + "/"
        out.append((m.group(1), url))
    return out


def list_saved_folders(page, username: str) -> list[tuple[str, str]]:
    """Read the account's saved folders, so nobody has to copy URLs by hand."""
    page.goto(f"{BASE}/{username}/saved/", wait_until="domcontentloaded")
    _guard_session(page)
    try:
        page.wait_for_selector("a[href*='/saved/']", timeout=GRID_TIMEOUT_MS)
    except Exception:
        _guard_session(page)
        return []
    human_pause(1.0, 2.0)
    hrefs = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    return parse_saved_folders([h for h in hrefs if h])


# --- Selettori verificati contro il DOM reale il 2026-08-20 ---
# Instagram non usa <article> ne' <h1> sulla pagina di un post: entrambe le
# ipotesi iniziali erano sbagliate. Cio' che regge:
#   - la caption e l'account stanno nel meta og:description (server-rendered)
#   - la slide visibile e' l'immagine larga piu' a sinistra con x >= 0:
#     le adiacenti sono precaricate a x negativo (precedente) o oltre (successiva)
#   - i pallini del carosello sono un div di figli-foglia, basso e largo

SLIDE_WAIT_S = 6.0        # attesa dopo il caricamento del post
ADVANCE_TIMEOUT_S = 8.0   # attesa che la slide successiva sia davvero comparsa

# La freccia "avanti" e' localizzata: aria-label segue la lingua dell'account.
NEXT_LABELS = ("Avanti", "Next", "Suivant", "Siguiente", "Weiter", "Volgende")

# Il JS raccoglie i candidati, la scelta la fa pick_slide() in Python: cosi' la
# regola e' testabile senza browser, ed e' la regola che sbagliava.
PAGE_IMAGES_JS = """() => {
  const imgs = [...document.querySelectorAll('main img')].map(i => {
    const r = i.getBoundingClientRect();
    return {x: r.x, y: r.y, width: r.width, height: r.height,
            area: r.width * r.height, src: i.currentSrc || i.src};
  });
  return {imgs: imgs, hasVideo: !!document.querySelector('main video')};
}"""

# Nel viewport 1440x900 una slide vera sta sopra i 200.000 px². La soglia
# precedente era 40.000 e il 20/08/2026 ha fatto passare, sul post DcN9kKpqfDR,
# una striscia 310x130 con lo screenshot di una chat presa altrove nella pagina:
# 40.300 px², dentro per 300 pixel. Pagare per guardare l'immagine sbagliata e'
# peggio che ammettere di non avere immagini.
MIN_SLIDE_AREA = 90_000
# Instagram accetta da 4:5 verticale (0.8) a 1.91:1 orizzontale. Fuori da questa
# forma non e' il contenuto di un post: e' un banner, una barra, una copertina.
MIN_SLIDE_RATIO = 0.5
MAX_SLIDE_RATIO = 2.2


def pick_slide(imgs: list[dict]) -> dict | None:
    """The visible slide among every image on the page, or None.

    Largest area wins, then leftmost: the adjacent slides of a carousel are
    preloaded at the same size, the previous one at a negative x and the next
    one further right. Anything too small or the wrong shape is not a slide.
    """
    plausible = [
        o for o in imgs
        if o["area"] >= MIN_SLIDE_AREA
        and o["x"] >= 0
        and o["height"] > 0
        and MIN_SLIDE_RATIO <= o["width"] / o["height"] <= MAX_SLIDE_RATIO
    ]
    if not plausible:
        return None
    top = max(o["area"] for o in plausible)
    return min((o for o in plausible if o["area"] >= top * 0.95),
               key=lambda o: o["x"])


DOTS_JS = """() => {
  let best = 1;
  document.querySelectorAll('div').forEach(d => {
    const kids = [...d.children];
    if (kids.length >= 2 && kids.length <= 30 &&
        kids.every(k => k.tagName === 'DIV' && k.children.length === 0)) {
      const r = d.getBoundingClientRect();
      if (r.height > 0 && r.height < 40 && r.width > 40) {
        best = Math.max(best, kids.length);
      }
    }
  });
  return best;
}"""


def slide_url(shortcode: str, index: int) -> str:
    if index < 1:
        raise ValueError(f"slide index starts at 1, got {index}")
    if index == 1:
        return f"{BASE}/p/{shortcode}/"
    return f"{BASE}/p/{shortcode}/?img_index={index}"


def parse_meta_caption(content: str) -> str:
    """Pull the caption out of og:description.

    Shape: '4,922 likes, 194 comments - account su August 15, 2026: "text"'
    """
    marker = ': "'
    i = content.find(marker)
    if i == -1:
        return ""
    body = content[i + len(marker):]
    return body[:-1] if body.endswith('"') else body


def parse_meta_account(content: str) -> str:
    """Pull the account handle out of og:description.

    Instagram serves at least two shapes, and only one of them was handled:

        '4,922 likes, 194 comments - getintoai su August 15, 2026: "..."'
        'codingknowledge on Instagram: "50 GitHub Repos ..."'

    The second one returned nothing at all — measured on post DcNOt8mkugc,
    a 97-entity list post that arrived with no account against it. Without
    the handle the judge cannot tell one account posting five times from
    five accounts agreeing, which is the difference between a watermark and
    a signal.
    """
    head, marker, _ = content.partition(': "')
    if not marker and " - " not in content:
        return ""
    # 'N likes, M comments - handle ...' — drop the counters when present.
    if " - " in head:
        head = head.split(" - ", 1)[1]
    # '... su August 15, 2026' / '... on Instagram' — both are what follows
    # the handle, in whichever language the account is served in.
    for sep in (" su ", " on "):
        if sep in head:
            head = head.split(sep, 1)[0]
    return head.strip()


def read_meta(page) -> tuple[str, str]:
    """Return (caption, account) from the page's og:description meta tag."""
    node = page.query_selector('meta[property="og:description"]')
    content = (node.get_attribute("content") or "") if node else ""
    return parse_meta_caption(content), parse_meta_account(content)


def count_slides(page) -> int:
    """The carousel dots tell how many slides there are. One dot per slide."""
    try:
        return int(page.evaluate(DOTS_JS))
    except Exception:
        return 1


def _click_next(page) -> bool:
    """Advance the carousel. URL navigation does not work on a cold load:
    ?img_index=N is handled client-side only, so a fresh goto lands on slide 1.
    """
    for label in NEXT_LABELS:
        btn = page.query_selector(f'[aria-label="{label}"]')
        if btn is not None:
            btn.click()
            return True
    return False


def visible_slide(page) -> dict | None:
    """The post's visible slide right now, or None if the page has no slide."""
    return pick_slide(page.evaluate(PAGE_IMAGES_JS)["imgs"])


def _wait_for_new_slide(page, previous_src: str) -> dict | None:
    """Wait until the visible slide actually changed. Returns its box, or None."""
    deadline = time.time() + ADVANCE_TIMEOUT_S
    while time.time() < deadline:
        box = visible_slide(page)
        if box and box["src"] != previous_src:
            time.sleep(0.4)  # let the rendering finish
            return visible_slide(page)
        time.sleep(0.3)
    return None


def capture_post(
    page, shortcode: str, out_dir: Path, max_slides: int
) -> tuple[str, str, list[Path], bool]:
    """Return (caption, account, screenshot paths, is_video).

    `is_video` matters: a reel has no slide to read, so everything the post says
    is in its caption. Saying so beats silently sending zero images and letting
    the extractor assume the post was empty.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    page.goto(slide_url(shortcode, 1), wait_until="domcontentloaded")
    time.sleep(SLIDE_WAIT_S)
    _guard_session(page)

    caption, account = read_meta(page)
    total = min(count_slides(page), max_slides)

    page_state = page.evaluate(PAGE_IMAGES_JS)
    shots: list[Path] = []
    box = pick_slide(page_state["imgs"])
    is_video = bool(page_state["hasVideo"]) and box is None
    for i in range(1, total + 1):
        if box is None:
            break
        path = out_dir / f"{shortcode}_{i:02d}.png"
        # Screenshot della REGIONE, non dell'elemento: cattura cio' che si vede
        # davvero li', non un nodo eventualmente coperto o ritagliato.
        try:
            page.screenshot(
                path=str(path),
                clip={k: box[k] for k in ("x", "y", "width", "height")},
            )
        except Exception:  # noqa: BLE001
            # "Clipped area is either empty or outside the resulting image":
            # the slide scrolled out of the viewport, or Instagram reported a
            # box it then moved. Four of seven failures on 2026-08-21 were
            # this, and each one threw away a whole post — including the slides
            # already captured. One unreadable slide is not an unreadable post.
            continue
        shots.append(path)
        if i == total:
            break
        human_pause(0.8, 2.0)
        if not _click_next(page):
            break
        box = _wait_for_new_slide(page, box["src"])

    return caption, account, shots, is_video
