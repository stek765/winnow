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
