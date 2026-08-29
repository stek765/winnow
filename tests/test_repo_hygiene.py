"""No personal data may live outside config.toml.

These tests protect a public repository from the one mistake that cannot be
undone: publishing something personal and having it indexed.
"""
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ["winnow", "tests", "scripts"]


def _source_files():
    """Every source file except this one, which necessarily contains the
    forbidden strings in order to search for them."""
    here = Path(__file__).resolve()
    for d in SOURCE_DIRS:
        for py in (ROOT / d).rglob("*.py"):
            if py.resolve() != here:
                yield py


def test_personal_files_are_gitignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ["config.toml", "state/", "findings/", "browser-profile/"]:
        assert entry in ignored, f"{entry} deve stare in .gitignore"


def test_no_real_folder_ids_in_source():
    """Un id di cartella salvata reale ha 15+ cifre; le fixture ne usano 3.

    Non basta vietare la stringa '/saved/': i test hanno bisogno di URL finti.
    Cio' che non deve mai comparire e' un identificatore vero.
    """
    # Un id fatto di soli zeri e' un segnaposto, non un dato di qualcuno.
    real_id = re.compile(r"/saved/[^/]+/(?!0+/)\d{15,}")
    for py in _source_files():
        assert not real_id.search(py.read_text(encoding="utf-8")), \
            f"id di cartella reale trovato in {py}"


def test_the_real_username_never_appears_in_source():
    """Se esiste un config.toml locale, il suo username non deve stare nel codice."""
    cfg = ROOT / "config.toml"
    if not cfg.exists():
        pytest.skip("nessun config.toml locale: niente da confrontare")
    username = tomllib.loads(cfg.read_text(encoding="utf-8"))["instagram"]["username"]
    if username.startswith("YOUR_"):
        pytest.skip("config non ancora compilato")
    for py in _source_files():
        assert username not in py.read_text(encoding="utf-8"), \
            f"lo username di config.toml compare in {py}"


# Una chiave vera e' lunga; 'sk-ant-...' in un messaggio di aiuto non lo e'.
# Vietare il solo prefisso vieterebbe di spiegare all'utente cosa incollare.
REAL_KEY = re.compile(r"sk-ant-[A-Za-z0-9]{4,}-[A-Za-z0-9_\-]{40,}")
REAL_GH_TOKEN = re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")


def test_no_api_keys_in_source():
    for py in _source_files():
        text = py.read_text(encoding="utf-8")
        assert not REAL_KEY.search(text), f"chiave API in {py}"
        assert not REAL_GH_TOKEN.search(text), f"token GitHub in {py}"


def test_placeholder_ids_are_allowed():
    """Il template deve poter mostrare la forma di un URL senza far scattare
    il controllo: un id di soli zeri non e' il dato di nessuno."""
    real_id = re.compile(r"/saved/[^/]+/(?!0+/)\d{15,}")
    assert not real_id.search("/YOUR_USERNAME/saved/example/000000000000000/")
    assert real_id.search("/tizio/saved/github/123456789012345/")


# --- one stylesheet, no scoping ---------------------------------------------
#
# Twice in one day a new screen reused a class name that already meant
# something: `.dot` (the home screen's status light) put a grey pip inside
# every accent swatch, and `.bar` (the header) handed the whole title bar the
# progress bar's `border-radius:999px` and background. Both were found by a
# reader looking at the window, which is the expensive way.

# Split on purpose, each for a stated reason. Anything else that appears twice
# is one screen restyling another's element without knowing it.
SPLIT_ON_PURPOSE = {
    ".app": "the veil gives it a stacking context; the chrome gives it a layout",
    ".card": "the shared look, then the row form once it grew two controls",
    ".row": "the settings row, then `position` for the pencil that sits on it",
}


def test_no_two_screens_claim_the_same_class_name():
    """Twice in one day a new screen reused a name that already meant
    something: `.dot` (the home screen's status light) put a grey pip inside
    every accent swatch, and `.bar` (the header) took the progress bar's
    `border-radius:999px` and turned the whole title bar into a pill. Both
    were found by a reader looking at the window, which is the expensive way.
    """
    import collections
    import re
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "winnow" / "ui"
            / "index.html").read_text(encoding="utf-8")
    css = "\n".join(re.findall(r"<style>(.*?)</style>", page, re.S))
    counts = collections.Counter(
        # Column zero only: a rule indented inside `@media` is an override of
        # itself, which is the whole point of a media query.
        re.findall(r"(?m)^(\.[A-Za-z][\w-]*)\s*\{", css))
    clashes = {n: c for n, c in counts.items()
               if c > 1 and n not in SPLIT_ON_PURPOSE}
    assert not clashes, (
        "declared as a bare rule more than once, so the later one silently "
        f"restyles the earlier element: {clashes}. If it is deliberate, say "
        "so in SPLIT_ON_PURPOSE.")


def test_every_phrase_the_window_asks_for_exists():
    """`_("sheet.hour.never")` had no row in `T`, and `_` falls back to the
    key: the «Never» option on the collection sheet was labelled
    `sheet.hour.never` on screen, in both languages. A key that is not there
    is not an error anywhere — it just renders as itself, which is exactly
    the kind of defect nobody reports because it looks deliberate."""
    import re
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "winnow" / "ui"
            / "index.html").read_text(encoding="utf-8")
    # The table's own lines, and the calls that read from it. Both are found
    # by shape rather than by parsing JS: the file is one script, and a
    # missing quote in either pattern shows up as a failure, never as a pass.
    declared = set(re.findall(r'(?m)^\s{2}"([\w.]+)":\s*\[', page))
    # A whole literal, closed on the spot: `_("ground." + g.id)` builds its
    # key from an id and there is nothing here to check it against.
    used = set(re.findall(r'_\(\s*"([\w.]+)"\s*[),]', page))
    # Keys written into the markup for `applyLang` to fill in later.
    used |= set(re.findall(r'data-t(?:-aria|-title)?="([\w.]+)"', page))
    # The two families whose keys are built from an id, checked against the
    # ids themselves — otherwise adding a tenth accent is a row that renders
    # as `accent.ocra` and nothing fails.
    for family, block in (("ground", "GROUNDS"), ("accent", "ACCENTS")):
        body = page.split(f"const {block} = [", 1)[1].split("];", 1)[0]
        for ident in re.findall(r'id:\s*"([\w-]+)"', body):
            used.add(f"{family}.{ident}")
            if family == "ground":
                used.add(f"{family}.{ident}.why")
    # The three difficulties the prompt allows, which `sayHard` builds a key
    # from. Read off `HARD`, so adding a fourth fails here rather than
    # printing `difficulty.impossibile` on a card.
    hard = page.split("const HARD = {", 1)[1].split("}", 1)[0]
    for ident in re.findall(r"(\w+)\s*:", hard):
        used.add(f"difficulty.{ident}")
    missing = sorted(used - declared)
    assert not missing, (
        "asked for by the window and absent from the phrase table, so they "
        f"render as their own key: {missing}")


def test_every_archive_row_is_the_same_height():
    """A merge with no comment, a week with a one-line one and a week with a
    two-line one were 67, 87 and 107 pixels tall in the same list — measured
    in the window, and reported by a reader before anyone looked.

    The fix is three declarations that only work together: one number, a
    floor on the row, and a comment block that *reserves* two lines instead of
    only being clamped to two. Clamping alone stops a row growing and does
    nothing about the short ones, which is how it was written the first time.
    """
    import re
    from pathlib import Path

    css = "\n".join(re.findall(
        r"<style>(.*?)</style>",
        (Path(__file__).resolve().parents[1] / "winnow" / "ui"
         / "index.html").read_text(encoding="utf-8"), re.S))
    assert re.search(r"--row:\s*[\d.]+rem", css), "the row height has no token"
    assert re.search(r"\.card\{[^}]*min-height:\s*var\(--row\)", css), \
        "`.card` does not take its height from `--row`"
    said = re.search(r"\.card \.said\{([^}]*)\}", css)
    assert said and "min-height" in said.group(1), \
        "the comment is clamped but not reserved, so short rows stay short"
