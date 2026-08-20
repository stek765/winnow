"""Guided first-time setup: `winnow init`.

Written to be run by someone who just installed the tool and knows nothing
about it. It fixes what it can fix by itself and states plainly what only a
human can do — signing in, and pasting an API key. It is safe to run again:
each step reports where you stand rather than starting over.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from winnow import paths

CONFIG_TEMPLATE = """\
# winnow configuration. This file is private: it holds your username.

[instagram]
username = "YOUR_USERNAME"

[api]
model = "claude-haiku-4-5"

[limits]
warn_eur_week = 3.0     # warn
halt_eur_week = 10.0    # permanent halt
posts_per_run = 8       # per pass, to keep a human rhythm
max_slides = 15         # cap on slides per post
eur_per_usd = 0.92      # fixed rate: a brake must not depend on the network

# One section per saved folder you want read.
# Open the folder on instagram.com and copy the path from the address bar.
[[folders]]
name = "example"
url = "/YOUR_USERNAME/saved/example/000000000000000/"
active = true
kind = "repo"      # repo | news
"""


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    todo: str = ""


def check_config(config_file: Path) -> Check:
    if not config_file.exists():
        return Check("configurazione", False, "assente")
    text = config_file.read_text(encoding="utf-8")
    if "YOUR_USERNAME" in text:
        return Check(
            "configurazione", False, f"da compilare: {config_file}",
            f"apri {config_file} e metti username e URL delle cartelle salvate",
        )
    return Check("configurazione", True, str(config_file))


def check_api_key(env_file: Path) -> Check:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return Check("chiave API", True, "presente nell'ambiente")
    if env_file.exists() and "ANTHROPIC_API_KEY" in env_file.read_text(encoding="utf-8"):
        return Check("chiave API", True, str(env_file))
    return Check(
        "chiave API", False, "assente",
        f"crea una chiave su console.anthropic.com (mettici anche un limite di "
        f"spesa) e scrivila cosi', da un terminale:\n"
        f"       umask 177 && printf 'ANTHROPIC_API_KEY=%s\\n' 'sk-ant-...' "
        f"> {env_file}",
    )


def check_browser_profile(profile: Path) -> Check:
    """A logged-in Chromium profile has a Cookies database. An empty directory
    is not a session: better to say so than to fail at 1 a.m."""
    if (profile / "Default" / "Cookies").exists():
        return Check("accesso Instagram", True, str(profile))
    return Check(
        "accesso Instagram", False, "mai effettuato",
        "esegui 'winnow login' e accedi a mano nella finestra che si apre",
    )


def browsers_root() -> Path:
    """Where Playwright keeps downloaded browsers.

    Read from disk rather than by starting Playwright's driver: starting and
    stopping it just to read a path makes the interpreter print asyncio
    teardown warnings *at exit*, long after any stderr redirect has ended.
    To someone who just installed the tool those look like a crash.
    """
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        return Path(override)
    home = Path(os.environ.get("HOME", "~")).expanduser()
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    if sys.platform.startswith("win"):
        return home / "AppData" / "Local" / "ms-playwright"
    return home / ".cache" / "ms-playwright"


def chromium_installed(root: Path | None = None) -> bool:
    root = root or browsers_root()
    if not root.is_dir():
        return False
    return any(d.is_dir() for d in root.glob("chromium-*"))


def check_chromium() -> Check:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return Check("browser", False, "playwright non installato",
                     "reinstalla winnow")
    if not chromium_installed():
        return Check("browser", False, "Chromium non scaricato",
                     "esegui 'winnow init' (scarica ~150 MB)")
    return Check("browser", True, "Chromium pronto")


def install_chromium() -> bool:
    print("  scarico Chromium (~150 MB, una volta sola)...")
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    return r.returncode == 0


def run_login(profile: Path) -> bool:
    from winnow.browser import BASE, open_session

    print(f"  apro una finestra sul profilo dedicato: {profile}")
    with open_session(profile) as page:
        page.goto(BASE)
        print("\n  Nella finestra appena aperta:")
        print("    1. rifiuta i cookie facoltativi")
        print("    2. accedi a Instagram")
        print("    3. torna qui e premi INVIO\n")
        input("  > ")
        return "/accounts/login" not in page.url


def run_init() -> int:
    print("winnow — configurazione\n")
    paths.ensure_dirs()
    print(f"  cartelle pronte sotto {paths.data_dir()}")

    config_file = paths.config_file()
    if not config_file.exists():
        config_file.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        config_file.chmod(0o600)
        print(f"  creato {config_file} da compilare")

    if not check_chromium().ok:
        install_chromium()

    profile = paths.browser_profile()
    if not check_browser_profile(profile).ok and check_chromium().ok:
        answer = input("\n  Accedere a Instagram adesso? [S/n] ").strip().lower()
        if answer in ("", "s", "si", "y", "yes"):
            run_login(profile)

    checks = [
        check_config(config_file),
        check_api_key(paths.env_file()),
        check_chromium(),
        check_browser_profile(profile),
    ]

    print("\n" + "-" * 58)
    for c in checks:
        print(f"  {'✅' if c.ok else '❌'} {c.name:20} {c.detail}")
    missing = [c for c in checks if not c.ok]
    if not missing:
        print("\n  Tutto pronto. Prova con:  winnow collect\n")
        return 0

    print("\n  Manca ancora:\n")
    for c in missing:
        print(f"    • {c.name}: {c.todo or c.detail}")
    print("\n  Poi rilancia 'winnow init' per ricontrollare.\n")
    return 1
