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
    """Irregular waits. 30 posts in four minutes every night gets noticed."""
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
            "Sessione Instagram scaduta. Apri il profilo browser dedicato, "
            "accedi a mano, poi rilancia. Non ritento da solo."
        )


POST_LINK_SELECTOR = "a[href*='/p/']"
GRID_TIMEOUT_MS = 20_000


def list_shortcodes(page, folder_url: str) -> list[str]:
    """List the posts in a saved folder.

    The grid is lazy-loaded, so we wait for the links themselves rather than
    for a fixed number of seconds: a clock-based wait is a coin flip that
    silently reports an empty folder when the network is slow.
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
    hrefs = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    return parse_shortcodes([h for h in hrefs if h])


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

# La slide visibile e' l'immagine di AREA MASSIMA con x >= 0.
# Filtrare per sola larghezza non basta: i post suggeriti in fondo alla pagina
# sono larghi 311px e passerebbero. Le slide adiacenti hanno la stessa area
# della visibile ma stanno a x negativo (precedente) o piu' a destra
# (successiva), quindi fra quelle di area massima si prende la piu' a sinistra.
VISIBLE_SLIDE_JS = """() => {
  const imgs = [...document.querySelectorAll('main img')].map(i => {
    const r = i.getBoundingClientRect();
    return {x: r.x, y: r.y, width: r.width, height: r.height,
            area: r.width * r.height, src: i.currentSrc || i.src};
  });
  if (!imgs.length) return null;
  const maxArea = Math.max(...imgs.map(o => o.area));
  if (maxArea < 40000) return null;              // niente di abbastanza grande
  const slides = imgs
    .filter(o => o.area >= maxArea * 0.95 && o.x >= 0)
    .sort((a, b) => a.x - b.x);
  return slides.length ? slides[0] : null;
}"""

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
        raise ValueError(f"l'indice della slide parte da 1, ricevuto {index}")
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
    """Pull the account handle out of og:description."""
    i = content.find(" - ")
    if i == -1:
        return ""
    rest = content[i + 3:]
    end = rest.find(" su ")
    if end == -1:
        end = rest.find(": ")
    return rest[:end].strip() if end != -1 else ""


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


def _wait_for_new_slide(page, previous_src: str) -> dict | None:
    """Wait until the visible slide actually changed. Returns its box, or None."""
    deadline = time.time() + ADVANCE_TIMEOUT_S
    while time.time() < deadline:
        box = page.evaluate(VISIBLE_SLIDE_JS)
        if box and box["src"] != previous_src:
            time.sleep(0.4)  # lascia finire il rendering
            return page.evaluate(VISIBLE_SLIDE_JS)
        time.sleep(0.3)
    return None


def capture_post(
    page, shortcode: str, out_dir: Path, max_slides: int
) -> tuple[str, str, list[Path]]:
    """Return (caption, account, screenshot paths) for one post."""
    out_dir.mkdir(parents=True, exist_ok=True)

    page.goto(slide_url(shortcode, 1), wait_until="domcontentloaded")
    time.sleep(SLIDE_WAIT_S)
    _guard_session(page)

    caption, account = read_meta(page)
    total = min(count_slides(page), max_slides)

    shots: list[Path] = []
    box = page.evaluate(VISIBLE_SLIDE_JS)
    for i in range(1, total + 1):
        if box is None:
            break
        path = out_dir / f"{shortcode}_{i:02d}.png"
        # Screenshot della REGIONE, non dell'elemento: cattura cio' che si vede
        # davvero li', non un nodo eventualmente coperto o ritagliato.
        page.screenshot(
            path=str(path),
            clip={k: box[k] for k in ("x", "y", "width", "height")},
        )
        shots.append(path)
        if i == total:
            break
        human_pause(0.8, 2.0)
        if not _click_next(page):
            break
        box = _wait_for_new_slide(page, box["src"])

    return caption, account, shots
