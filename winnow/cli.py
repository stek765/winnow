"""winnow collect | status | reset-halt"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from winnow.budget import HALT_FILE, Halted, is_halted, weekly_spend
from winnow import paths
from winnow.config import load_config
from winnow.state import load_seen


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="winnow")
    p.add_argument("--state-dir", default=None, type=Path)
    p.add_argument("--findings-dir", default=None, type=Path)
    p.add_argument("--config", default=None, type=Path)
    p.add_argument(
        "command", nargs="?",
        choices=["init", "login", "collect", "status", "reset-halt", "where"],
    )
    return p


def _cmd_init(args) -> int:
    from winnow.setup import run_init
    return run_init()


def _cmd_status(args) -> int:
    """Everything you need to know in one screen: is it stopped, did it run,
    what has it found, what has it cost."""
    if is_halted(args.state_dir):
        print((args.state_dir / HALT_FILE).read_text(encoding="utf-8"))
        return 1

    spent = weekly_spend(args.state_dir / "spend.json", datetime.now())
    print(f"stato        attivo")
    print(f"spesa 7gg    USD {spent:.4f}")

    seen = load_seen(args.state_dir / "seen.json")
    print(f"post visti   {len(seen)}")

    files = sorted(args.findings_dir.glob("*.json")) if args.findings_dir.exists() else []
    if not files:
        print("ultimo giro  mai eseguito")
        return 0

    last = files[-1]
    data = json.loads(last.read_text(encoding="utf-8"))
    when = datetime.fromtimestamp(last.stat().st_mtime)
    posts = data.get("posts", [])
    entities = sum(len(p["entities"]) for p in posts)
    verified = sum(
        1 for p in posts for e in p["entities"]
        if e["verification"]["checked"] and e["verification"]["exists"]
    )
    ago = datetime.now() - when
    hours = int(ago.total_seconds() // 3600)
    when_txt = f"{when:%d/%m %H:%M} ({hours}h fa)" if hours < 48 else f"{when:%d/%m %H:%M}"

    print(f"ultimo giro  {when_txt} — {len(posts)} post, {entities} entita', "
          f"{verified} verificate")
    if data.get("failed"):
        print(f"             ⚠️  {len(data['failed'])} post falliti")
    if hours > 36:
        print("             ⚠️  piu' di 36h fa: il Mac era spento, o l'agent non parte")

    print(f"da leggere   {len(files)} file in {args.findings_dir}/")
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
                cfg, args.state_dir, args.findings_dir, paths.shots_dir(),
                anthropic.Anthropic(), http, page, datetime.now(),
            )
    except Halted as e:
        print(f"ARRESTO: {e}", file=sys.stderr)
        return 1
    except SessionExpired as e:
        print(f"SESSIONE: {e}", file=sys.stderr)
        return 3

    line = (f"{summary['posts']} post · {summary['entities']} entita' · "
            f"USD {summary['spend_usd']}")
    if summary["failed"]:
        line += f" · {summary['failed']} falliti (vedi findings)"
    print(line)
    if summary["status"] == "warn":
        print("ATTENZIONE: spesa settimanale oltre la soglia di avviso.",
              file=sys.stderr)
    return 0


def _cmd_login(args) -> int:
    """Sign in by hand, once. winnow never types your password."""
    from winnow.setup import run_login
    ok = run_login(paths.browser_profile())
    print("  sessione salvata." if ok else "  ATTENZIONE: sembri ancora fuori.")
    return 0 if ok else 1


def _cmd_where(args) -> int:
    print(f"config    {paths.config_file()}")
    print(f"chiave    {paths.env_file()}")
    print(f"stato     {paths.state_dir()}")
    print(f"findings  {paths.findings_dir()}")
    print(f"browser   {paths.browser_profile()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command is None:
        _parser().print_help()
        return 2
    # I default vengono dai percorsi standard, non dalla directory corrente:
    # winnow puo' essere lanciato da ovunque.
    if args.config is None:
        args.config = paths.config_file()
    if args.state_dir is None:
        args.state_dir = paths.state_dir()
    if args.findings_dir is None:
        args.findings_dir = paths.findings_dir()
    return {
        "status": _cmd_status,
        "reset-halt": _cmd_reset_halt,
        "collect": _cmd_collect,
        "init": _cmd_init,
        "where": _cmd_where,
        "login": _cmd_login,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
