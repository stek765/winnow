"""winnow collect | status | recap | ideas | config | schedule | reset-halt"""
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
  winnow recap         judge the days not judged yet, and open the page
  winnow ideas         draw at random from everything kept, and ask what it
                       would change in your life
  winnow render        an answer you saved by hand, as a page you click
  winnow config        change folders, model, posts per run, hour, profile
  winnow app           open winnow as a window
  winnow update        pull the newest winnow, if there is one
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
    p.add_argument("--port", default=0, type=int, help=argparse.SUPPRESS)
    p.add_argument("--state-dir", default=None, type=Path,
                   help=argparse.SUPPRESS)
    p.add_argument("--findings-dir", default=None, type=Path,
                   help=argparse.SUPPRESS)
    p.add_argument("--config", default=None, type=Path, help=argparse.SUPPRESS)
    p.add_argument(
        "command", nargs="?",
        choices=["init", "login", "collect", "status", "recap", "ideas", "render",
                 "config", "schedule", "update", "reset-halt", "where",
                 "app", "serve"],
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


def _cmd_ideas(args) -> int:
    """The other half of the judgement: not what is worth reading, but what it
    would do here. Same shape as `_cmd_recap` — the events do the talking."""
    from winnow.ideas import run_ideas

    def show(event: str, data: dict) -> None:
        text = line(event, data)
        if text:
            print(text)

    return run_ideas(open_file=not args.no_open, on_event=show)


def _cmd_recap(args) -> int:
    from winnow.progress import line
    from winnow.recap import run_recap

    def show(event: str, data: dict) -> None:
        text = line(event, data)
        if text:
            print(text, flush=True)

    return run_recap(open_file=not args.no_open, on_event=show)


def _cmd_serve(args) -> int:
    """`winnow serve` — the engine alone, for a shell to drive.

    Prints the port it took on the first line and then stays up. The native
    window reads that line instead of guessing: a hard-coded port is a crash
    waiting for the day something else already holds it.
    """
    import time

    from winnow.api import serve

    httpd, port = serve(port=args.port or 0)
    # First line, flushed: the shell blocks on it before opening the window.
    print(f"WINNOW_PORT={port}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


def _cmd_app(args) -> int:
    """`winnow app` — the window, and the engine behind it.

    The port is picked by the OS: a fixed one is a crash waiting for the day
    something else already holds it, and an app must never open on a blank
    page because of that.
    """
    import webbrowser

    from winnow.api import serve

    httpd, port = serve()
    url = f"http://127.0.0.1:{port}/"
    print(f"  winnow is running at {url}")
    print("  close this window — or press ctrl-C — to stop it.")
    webbrowser.open(url)
    try:
        while True:
            import time
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n  stopped.")
        httpd.shutdown()
    return 0


def _cmd_update(args) -> int:
    """`winnow update` — `pipx upgrade` lies about git installs, so this
    checks the commit itself before touching anything."""
    from winnow.update import run_update
    return run_update()


def _cmd_render(args) -> int:
    """`winnow render answer.json` — the judgement, as a page."""
    import json as _json

    from winnow.render import render_file

    from winnow import paths
    from winnow.render import render_clipboard

    # No argument means "the answer I just copied" — the escape hatch for
    # anyone who ran the judgement by hand (pasted the bundle into a chat,
    # copied the reply back) rather than through `winnow recap`, which never
    # touches the clipboard: it writes the answer straight to disk itself.
    src = Path(args.file) if args.file else None
    if src is not None and not src.exists():
        print(f"{src} does not exist.", file=sys.stderr)
        return 2
    try:
        # embed_shots=True: this is the page made by hand after repairing a
        # judgement, which means it is the one that outlives `state/shots/` —
        # the archive copy, not a disposable one made from the day's slides.
        out = (render_file(src, embed_shots=True) if src is not None
               else render_clipboard(paths.recap_dir()))
    # JSONDecodeError first: it *inherits from ValueError*, so an
    # `except ValueError` above it would swallow every parse error and leave
    # this branch as dead code — which is exactly what happened once.
    except _json.JSONDecodeError as e:
        from winnow.render import blame_json
        # The answer is on disk either way — render_clipboard writes before it
        # parses — so say where, or the reader thinks it is gone.
        saved = sorted(paths.recap_dir().glob("*.answer*.md"))
        raw = saved[-1].read_text(encoding="utf-8") if saved else ""
        spot = blame_json(raw, e) if raw else ""
        print(f"  The answer is not valid JSON: {e.msg}.", file=sys.stderr)
        if spot:
            print("\n" + spot + "\n", file=sys.stderr)
        if saved:
            print(f"  Saved anyway: {saved[-1]}", file=sys.stderr)
            print("  Fix that file and run:  winnow render "
                  f"{saved[-1].name}", file=sys.stderr)
        print("\n  Most often: the answer was copied out of a terminal, which\n"
              "  wraps and truncates long lines. Copy it from the chat window,\n"
              "  or have the model write the JSON straight to a file.",
              file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"  {e}", file=sys.stderr)
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
    # La chiave sta in un file con permessi 600, non nella definizione dello
    # scheduler: cosi' il job programmato e' un semplice `winnow collect`.
    # Caricarla non e' piu' compito di questo comando: `providers.load_key`
    # lo fa subito prima della chiamata, per chiunque la faccia.
    from winnow.browser import SessionExpired, Stopped as BrowserStopped
    from winnow.browser import open_session
    from winnow.run import Unusable, collect, make_http

    from winnow.progress import line

    def show(event: str, data: dict) -> None:
        # flush: a run is mostly waiting, and a buffered line is a line you
        # read after the thing it was announcing already finished.
        text = line(event, data)
        if text:
            print(text, flush=True)

    watcher = getattr(args, "on_event", None) or show
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

    stop = getattr(args, "should_stop", None)
    try:
        with open_session(cfg.browser_profile) as page, make_http() as http:
            # Opening the browser is ten seconds of its own, and «Ferma»
            # pressed during them used to be swallowed: the first checkpoint
            # was inside `collect`, which had not been reached yet.
            if stop and stop():
                watcher("stopped", {"done": 0, "of": 0})
                return 0
            summary = collect(
                cfg, args.state_dir, args.findings_dir, paths.shots_dir(),
                http, page, datetime.now(),
                search_delay=delay, on_event=watcher, should_stop=stop,
            )
    except BrowserStopped as e:
        # Not a failure: nobody broke anything, they changed their mind. The
        # posts read before it are already written by `collect`.
        watcher("stopped", {"done": 0, "of": 0})
        print(f"  {e}")
        return 0
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


def main(argv: list[str] | None = None, on_event=None, should_stop=None) -> int:
    """The command line, and the same commands called from the window.

    `on_event` and `should_stop` ride on `args` rather than through every
    handler's signature: the window needs them for a collection, and the
    alternative was a second copy of `_cmd_collect` — session, http client,
    error wording and all — living in `api.py` and drifting from this one.
    """
    args = _parser().parse_args(argv)
    args.on_event = on_event
    args.should_stop = should_stop
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
        "ideas": _cmd_ideas,
        "render": _cmd_render,
        "update": _cmd_update,
        "app": _cmd_app,
        "serve": _cmd_serve,
        "config": _cmd_config,
        "schedule": _cmd_schedule,
        "init": _cmd_init,
        "where": _cmd_where,
        "login": _cmd_login,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
