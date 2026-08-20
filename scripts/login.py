"""One-time sign-in into the dedicated browser profile.

Run this yourself, interactively. winnow never types your password.
The session is stored in the profile directory and reused by every later run.
"""
from __future__ import annotations

import sys
from pathlib import Path

from winnow.browser import BASE, open_session
from winnow.config import load_config


def main() -> int:
    cfg = load_config(Path(sys.argv[1] if len(sys.argv) > 1 else "config.toml"))
    print(f"Apro il profilo dedicato: {cfg.browser_profile}")
    with open_session(cfg.browser_profile) as page:
        page.goto(BASE)
        print(
            "\nNella finestra appena aperta:\n"
            "  1. rifiuta i cookie facoltativi\n"
            "  2. accedi a Instagram\n"
            "  3. torna qui e premi INVIO\n"
        )
        input("> ")
        logged_out = "/accounts/login" in page.url
        print("ATTENZIONE: sembri ancora fuori." if logged_out else "Sessione salvata.")
    return 1 if logged_out else 0


if __name__ == "__main__":
    raise SystemExit(main())
