"""winnow collect | status | recap | config | schedule | reset-halt"""
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


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("winnow")
    except PackageNotFoundError:      # eseguito dal sorgente, non installato
        return "dev"


USAGE = """\
winnow — reads the posts you save, checks what they name, and once a week hands
them to your profile to be filtered.

  winnow init          set everything up: model, browser, login, saved
                       folders, profile, daily run
  winnow collect       one pass now, instead of waiting for the next
  winnow status        is it alive? what did it find? what has it cost?
  winnow recap         the week + your profile on your clipboard, ready to
                       paste into a model
  winnow render FILE   turn the model's answer into a page you click
  winnow config        change folders, model, posts per run, hour, profile
  winnow reset-halt    restart after the spend brake stopped it

less used:
  winnow schedule      schedule the daily run   --at HH:MM   --off
  winnow login         sign in again when the Instagram session expires
  winnow where         print every path it uses
"""


def _parser() -> argparse.ArgumentParser:
    # RawDescription: the command list is aligned by hand, and argparse would
    # reflow it into a paragraph.
    p = argparse.ArgumentParser(
        prog="winnow", usage=argparse.SUPPRESS, description=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state-dir", default=None, type=Path,
                   help=argparse.SUPPRESS)
    p.add_argument("--findings-dir", default=None, type=Path,
                   help=argparse.SUPPRESS)
    p.add_argument("--config", default=None, type=Path, help=argparse.SUPPRESS)
    p.add_argument(
        "command", nargs="?",
        choices=["init", "login", "collect", "status", "recap", "render",
                 "config", "schedule", "reset-halt", "where"],
        metavar="COMMAND",
    )
    p.add_argument("--version", action="version",
                   version=f"winnow {_version()}")
    p.add_argument("--posts", type=int, default=None,
                   help="how many posts this run (default: config.toml); "
                        "for clearing a backlog")
    p.add_argument("file", nargs="?", default=None,
                   help="for 'render': the JSON the model answered with")
    p.add_argument("--no-open", action="store_true",
                   help="do not open the recap file at the end")
    p.add_argument("--days", type=int, default=7,
                   help="how many days of findings to put in the recap")
    p.add_argument("--at", default=None,
                   help="hour of the daily run, HH:MM")
    p.add_argument("--off", action="store_true",
                   help="remove the daily run")
    p.add_argument("-y", "--yes", action="store_true",
                   help="do not ask for confirmation")
    return p


def _cmd_init(args) -> int:
    from winnow.setup import run_init
    return run_init()


def _cmd_recap(args) -> int:
    from winnow.recap import run_recap
    return run_recap(args.days, open_file=not args.no_open)


def _cmd_render(args) -> int:
    """`winnow render answer.json` — the judgement, as a page."""
    import json as _json

    from winnow.render import render_file

    if not args.file:
        print("usage: winnow render <file.json>", file=sys.stderr)
        print("  save what the model answered, then render it.", file=sys.stderr)
        return 2
    src = Path(args.file)
    if not src.exists():
        print(f"{src} does not exist.", file=sys.stderr)
        return 2
    try:
        out = render_file(src)
    except _json.JSONDecodeError as e:
        print(f"{src} is not valid JSON: {e}", file=sys.stderr)
        print("  paste the model's answer without the surrounding text.",
              file=sys.stderr)
        return 2
    except (KeyError, TypeError, AttributeError) as e:
        print(f"{src} is JSON but not the shape winnow expects ({e}).",
              file=sys.stderr)
        print("  see the shape at the top of winnow/render.py", file=sys.stderr)
        return 2
    print(f"  → {out}")
    if sys.stdout.isatty():
        import webbrowser
        webbrowser.open(f"file://{out.resolve()}")
    return 0


def _cmd_config(args) -> int:
    from winnow.setup import run_config
    return run_config()


def _cmd_schedule(args) -> int:
    from winnow.schedule import run_schedule
    try:
        return run_schedule(args.at, args.off, args.yes)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2


def _cmd_status(args) -> int:
    """Everything you need to know in one screen: is it stopped, did it run,
    what has it found, what has it cost."""
    if is_halted(args.state_dir):
        print((args.state_dir / HALT_FILE).read_text(encoding="utf-8"))
        return 1

    spent = weekly_spend(args.state_dir / "spend.json", datetime.now())
    print("state        active")
    print(f"spend 7d     USD {spent:.4f}")

    from winnow.schedule import current
    print(f"scheduled    {current()}")

    seen = load_seen(args.state_dir / "seen.json")
    print(f"posts seen   {len(seen)}")

    files = sorted(args.findings_dir.glob("*.json")) if args.findings_dir.exists() else []
    if not files:
        print("last run     never")
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
    when_txt = f"{when:%d/%m %H:%M} ({hours}h ago)" if hours < 48 else f"{when:%d/%m %H:%M}"

    print(f"last run     {when_txt} — {len(posts)} posts, {entities} entities, "
          f"{verified} verified")
    if data.get("failed"):
        print(f"             ⚠️  {len(data['failed'])} posts failed")
    if hours > 36:
        print("             ⚠️  over 36h ago: the machine was off, or the "
              "schedule is broken")

    print(f"to read      {len(files)} file(s) in {args.findings_dir}/"
          "  →  winnow recap")
    return 0


def _cmd_reset_halt(args) -> int:
    f = args.state_dir / HALT_FILE
    if f.exists():
        f.unlink()
        print(f"{HALT_FILE} removed. winnow can run again.")
    else:
        print("it was not halted.")
    return 0


def _cmd_collect(args) -> int:
    from winnow.setup import apply_env_file

    # La chiave sta in un file con permessi 600, non nella definizione dello
    # scheduler: cosi' il job programmato e' un semplice `winnow collect`.
    apply_env_file(paths.env_file())

    from winnow.browser import SessionExpired, open_session
    from winnow.run import Unusable, collect, make_http

    from winnow.progress import line

    def show(event: str, data: dict) -> None:
        # flush: a run is mostly waiting, and a buffered line is a line you
        # read after the thing it was announcing already finished.
        text = line(event, data)
        if text:
            print(text, flush=True)

    cfg = load_config(args.config)
    if args.posts is not None:
        from winnow.config import override_posts
        try:
            cfg = override_posts(cfg, args.posts)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2

    from winnow.run import has_github_token, search_delay
    token = has_github_token()
    delay = search_delay(token)
    if args.posts is not None:
        print(f"  {args.posts} posts this run · est. ~"
              f"${args.posts * 0.005:.2f} · GITHUB_TOKEN "
              f"{'present' if token else 'absent'} ({delay:.0f}s between "
              f"checks)", flush=True)

    try:
        with open_session(cfg.browser_profile) as page, make_http() as http:
            summary = collect(
                cfg, args.state_dir, args.findings_dir, paths.shots_dir(),
                http, page, datetime.now(),
                search_delay=delay, on_event=show,
            )
    except Unusable as e:
        print(f"\nMODEL UNREACHABLE: {e}", file=sys.stderr)
        print("The run stopped and the posts were NOT marked as seen: try "
              "again once it is fixed.\n"
              "If it is the key: check the account has credit "
              "(console.anthropic.com).", file=sys.stderr)
        return 4
    except Halted as e:
        print(f"HALTED: {e}", file=sys.stderr)
        return 1
    except SessionExpired as e:
        print(f"SESSION: {e}", file=sys.stderr)
        return 3

    line = (f"{summary['posts']} posts · {summary['entities']} entities · "
            f"USD {summary['spend_usd']}")
    if summary["failed"]:
        line += f" · {summary['failed']} failed (see findings)"
    print(line)
    if summary["status"] == "warn":
        print("WARNING: weekly spend above the warning threshold.",
              file=sys.stderr)
    return 0


def _cmd_login(args) -> int:
    """Sign in by hand, once. winnow never types your password."""
    from winnow.setup import run_login
    ok = run_login(paths.browser_profile())
    print("  session saved." if ok else "  WARNING: you still look logged out.")
    return 0 if ok else 1


def _cmd_where(args) -> int:
    print(f"config    {paths.config_file()}")
    print(f"profile   {paths.profile_file()}")
    print(f"key       {paths.env_file()}")
    print(f"state     {paths.state_dir()}")
    print(f"findings  {paths.findings_dir()}")
    print(f"recap     {paths.recap_dir()}")
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
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print("\ninterrupted.", file=sys.stderr)
        return 130


def _dispatch(args) -> int:
    return {
        "status": _cmd_status,
        "reset-halt": _cmd_reset_halt,
        "collect": _cmd_collect,
        "recap": _cmd_recap,
        "render": _cmd_render,
        "config": _cmd_config,
        "schedule": _cmd_schedule,
        "init": _cmd_init,
        "where": _cmd_where,
        "login": _cmd_login,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
