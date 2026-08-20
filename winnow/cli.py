"""winnow collect | status | reset-halt"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from winnow.budget import HALT_FILE, Halted, is_halted, weekly_spend
from winnow.config import load_config


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="winnow")
    p.add_argument("--state-dir", default="state", type=Path)
    p.add_argument("--findings-dir", default="findings", type=Path)
    p.add_argument("--config", default="config.toml", type=Path)
    p.add_argument("command", nargs="?", choices=["collect", "status", "reset-halt"])
    return p


def _cmd_status(args) -> int:
    if is_halted(args.state_dir):
        print((args.state_dir / HALT_FILE).read_text(encoding="utf-8"))
        return 1
    spent = weekly_spend(args.state_dir / "spend.json", datetime.now())
    print(f"attivo · spesa ultimi 7 giorni: USD {spent:.4f}")
    return 0


def _cmd_reset_halt(args) -> int:
    f = args.state_dir / HALT_FILE
    if f.exists():
        f.unlink()
        print(f"{HALT_FILE} rimosso. winnow puo' ripartire.")
    else:
        print("non era fermo.")
    return 0


def _cmd_collect(args) -> int:
    import anthropic

    from winnow.browser import SessionExpired, open_session
    from winnow.run import collect, make_http

    cfg = load_config(args.config)
    try:
        with open_session(cfg.browser_profile) as page, make_http() as http:
            summary = collect(
                cfg, args.state_dir, args.findings_dir, args.state_dir / "shots",
                anthropic.Anthropic(), http, page, datetime.now(),
            )
    except Halted as e:
        print(f"ARRESTO: {e}", file=sys.stderr)
        return 1
    except SessionExpired as e:
        print(f"SESSIONE: {e}", file=sys.stderr)
        return 3

    print(
        f"{summary['posts']} post · {summary['entities']} entita' · "
        f"USD {summary['spend_usd']}"
    )
    if summary["status"] == "warn":
        print("ATTENZIONE: spesa settimanale oltre la soglia di avviso.",
              file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command is None:
        _parser().print_help()
        return 2
    return {
        "status": _cmd_status,
        "reset-halt": _cmd_reset_halt,
        "collect": _cmd_collect,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
