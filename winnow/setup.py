"""Guided first-time setup: `winnow init`.

Written to be run by someone who just installed the tool and knows nothing
about it. It fixes what it can fix by itself and states plainly what only a
human can do — signing in, and pasting an API key. It is safe to run again:
each step reports where you stand rather than starting over.
"""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from winnow import paths

CONFIG_HEAD = """\
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
"""

# Fallback only: normally `winnow init` discovers the folders and writes them.
CONFIG_TEMPLATE = CONFIG_HEAD + """
# One section per saved folder you want read.
[[folders]]
name = "example"
url = "/YOUR_USERNAME/saved/example/000000000000000/"
active = true
kind = "repo"      # repo | news
"""


def ask(prompt: str, secret: bool = False) -> str:
    """input(), except that the end of the input is an answer and not a crash.

    Piped stdin, a closed terminal, Ctrl-D: all of them used to end `winnow
    init` in a traceback, which reads like the tool is broken when the user
    only meant "not now".
    """
    try:
        return (getpass.getpass(prompt) if secret else input(prompt)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def bold(text: str) -> str:
    """Escapes only where something can render them."""
    return f"\033[1m{text}\033[0m" if sys.stdout.isatty() else text


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
            "rilancia 'winnow init' dopo l'accesso: le cartelle salvate le "
            "trova da solo",
        )
    return Check("configurazione", True, str(config_file))


def check_api_key(env_file: Path) -> Check:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return Check("chiave API", True, "presente nell'ambiente")
    if env_file.exists() and "ANTHROPIC_API_KEY" in env_file.read_text(encoding="utf-8"):
        return Check("chiave API", True, str(env_file))
    return Check(
        "chiave API", False, "assente",
        "crea una chiave su console.anthropic.com (mettici anche un limite di "
        "spesa) e rilancia 'winnow init': te la chiede e la scrive lui",
    )


def check_profile(profile_file: Path) -> Check:
    """The profile is the half of the configuration no code can write for you.

    A file that still holds the template is worse than a missing one: `winnow
    recap` would happily hand a model somebody else's life.
    """
    if not profile_file.exists():
        return Check("profilo", False, "assente",
                     "rilancia 'winnow init': te lo crea da compilare")
    if "# Example profile" in profile_file.read_text(encoding="utf-8"):
        return Check("profilo", False, f"ancora l'esempio: {profile_file}",
                     "rilancia 'winnow init': quattro domande e lo scrive lui")
    return Check("profilo", True, str(profile_file))


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
        ask("  > ")
        return "/accounts/login" not in page.url



def render_config(username: str, folders: list[tuple[str, str, bool, str]]) -> str:
    """Build config.toml from what was discovered. Inactive folders are kept:
    turning one on later is editing a flag, not hunting for a URL again."""
    body = CONFIG_HEAD.replace("YOUR_USERNAME", username)
    for name, url, active, kind in folders:
        body += (f'\n[[folders]]\nname = "{name}"\nurl = "{url}"\n'
                 f'active = {str(active).lower()}\nkind = "{kind}"\n')
    return body


def parse_selection(text: str, count: int) -> set[int]:
    """'1,3-5' -> {1,3,4,5}. Out-of-range numbers are dropped, not fatal."""
    picked: set[int] = set()
    for chunk in text.replace(" ", ",").split(","):
        if not chunk:
            continue
        if "-" in chunk[1:]:
            a, _, b = chunk.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                continue
            picked.update(range(min(lo, hi), max(lo, hi) + 1))
        else:
            try:
                picked.add(int(chunk))
            except ValueError:
                continue
    return {i for i in picked if 1 <= i <= count}


def ask_api_key(env_file: Path) -> bool:
    """Ask for the key and write it, instead of printing a shell incantation.

    getpass keeps it out of the terminal scrollback and out of shell history —
    the two places a pasted secret usually survives.
    """
    print("  Serve una chiave API di Anthropic. Ti apro la pagina:")
    print(f"  {KEY_URL}")
    print("  Creane una, e mettici anche un limite di spesa mentre sei li'.\n")
    open_url(KEY_URL)
    key = ask("  Incolla la chiave qui (invio per saltare): ", secret=True)
    if not key:
        return False
    if not key.startswith("sk-"):
        print("  ⚠️  non sembra una chiave Anthropic. La scrivo lo stesso.")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(f"ANTHROPIC_API_KEY={key}\n", encoding="utf-8")
    env_file.chmod(0o600)
    print(f"  ✅ scritta in {env_file} (600)")
    return True


def configure_folders(config_file: Path, profile: Path) -> bool:
    """Read the account's saved folders and write the config from them.

    Only ever called when there is no usable config: an existing one may hold
    edited limits and hand-tuned kinds, and regenerating it would silently
    throw them away.
    """
    from winnow.browser import list_saved_folders, open_session

    username = ask("\n  Username Instagram: ").lstrip("@")
    if not username:
        return False
    print("  cerco le tue cartelle salvate...")
    try:
        with open_session(profile) as page:
            found = list_saved_folders(page, username)
    except Exception as e:
        print(f"  ⚠️  non ci sono riuscito ({e.__class__.__name__}).")
        return False
    if not found:
        print("  nessuna cartella trovata. Creane una su Instagram e rilancia.")
        return False

    print("\n  Cartelle salvate trovate:\n")
    for i, (name, _) in enumerate(found, 1):
        print(f"    {i:2}. {name}")
    picked = parse_selection(
        ask("\n  Quali vuoi far leggere a winnow? (es. 1,3-4) "), len(found))
    if not picked:
        print("  nessuna scelta: le scrivo tutte spente, accendile quando vuoi.")
    repos = parse_selection(
        ask("  Di queste, quali contengono repo o tool? (invio = nessuna) "),
        len(found)) if picked else set()

    folders = [
        (name, url, i in picked, "repo" if i in repos else "news")
        for i, (name, url) in enumerate(found, 1)
    ]
    config_file.write_text(render_config(username, folders), encoding="utf-8")
    config_file.chmod(0o600)
    print(f"  ✅ {len(picked)} cartelle attive in {config_file}")
    return True


KEY_URL = "https://console.anthropic.com/settings/keys"

PROFILE_QUESTIONS = [
    ("Chi sei, in due righe?", "Who I am"),
    ("Cosa stai cercando di ottenere nei prossimi due o tre anni?",
     "What I'm actually after"),
    ("Che decisioni hai aperte adesso?", "Open questions"),
    ("Cosa hai gia' escluso, e perche'? (la riga piu' importante)",
     "Already decided — do NOT bring these back"),
]

PROFILE_TAIL = """\
## Interesting even if unrelated to work
Ways to earn, tools that change how I work day to day, where the market is
heading, things worth building.

## What I never want to see
Motivational content, courses, "get rich with X", and anything whose only
beneficiary is the person selling it.
"""


def render_profile(answers: list[tuple[str, str]]) -> str:
    """Turn the answers into the file the judge reads.

    The template used to be copied verbatim with "now rewrite it" — which is
    homework, and homework does not get done. The headings are the same, so a
    file written here and one edited by hand are the same kind of file.
    """
    out = ["# My profile", "",
           "Written by `winnow init`. Add to it whenever something changes —",
           "the more honest it is, the better the weekly recap.", ""]
    for heading, answer in answers:
        out += [f"## {heading}", answer.strip(), ""]
    return "\n".join(out) + "\n" + PROFILE_TAIL


def open_url(url: str) -> None:
    """Take them there instead of asking them to go there."""
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:      # noqa: BLE001 — a headless box has no browser
        pass


def open_in_editor(path: Path) -> None:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    try:
        if editor:
            subprocess.run([editor, str(path)])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-t", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
    except Exception:      # noqa: BLE001
        print(f"     aprilo a mano: {path}")


def ask_profile(profile_file: Path) -> bool:
    """Four questions, one line each. Empty answers mean "not now"."""
    template = Path(__file__).parent / "profile-template.md"
    if not profile_file.exists():
        profile_file.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        profile_file.chmod(0o600)

    print("  E' il file che decide cosa vale per TE. Quattro domande, una riga")
    print("  a testa. Invio vuoto per saltare e scriverlo dopo.\n")
    answers: list[tuple[str, str]] = []
    for question, heading in PROFILE_QUESTIONS:
        print(f"  {question}")
        answer = ask("  > ")
        print()
        if answer:
            answers.append((heading, answer))

    if not answers:
        print(f"  saltato. Il file da riscrivere e' {profile_file}")
        return False
    profile_file.write_text(render_profile(answers), encoding="utf-8")
    profile_file.chmod(0o600)
    print(f"  ✅ scritto {profile_file}")
    if ask("  Vuoi aprirlo per aggiungere altro? [s/N] ").lower() in (
            "s", "si", "y", "yes"):
        open_in_editor(profile_file)
        ask("  (premi INVIO quando hai finito) ")
    return True


STEPS = ("chiave API", "browser", "accesso Instagram", "cartelle salvate",
         "il tuo profilo", "raccolta giornaliera")


def step(n: int, title: str) -> None:
    print("\n" + bold(f"[{n}/{len(STEPS)}] {title}"))


def run_init() -> int:
    """Six steps, in the only order they can happen in.

    Everything a first-time user has to do lives here, numbered, and each step
    is skipped when it is already done — so re-running after a stumble picks up
    where it stopped instead of starting over. The order is forced by the
    dependencies: reading the saved folders needs a session, and writing the
    config needs the folders.
    """
    print("winnow — sei passi, cinque minuti.")
    print("Puoi interrompere quando vuoi: rilanciando 'winnow init' riprende "
          "da dove eri.")
    paths.ensure_dirs()

    env_file, profile_file = paths.env_file(), paths.profile_file()
    browser = paths.browser_profile()
    config_file = paths.config_file()

    step(1, STEPS[0])
    if check_api_key(env_file).ok:
        print("  ✅ gia' a posto")
    else:
        ask_api_key(env_file)

    step(2, STEPS[1])
    if check_chromium().ok:
        print("  ✅ Chromium pronto")
    else:
        install_chromium()

    step(3, STEPS[2])
    if check_browser_profile(browser).ok:
        print("  ✅ sessione salvata")
    elif check_chromium().ok:
        print("  Apro una finestra: accedi a Instagram a mano, winnow non")
        print("  digita mai la tua password.")
        if ask("  Procedo? [S/n] ").lower() in ("", "s", "si", "y", "yes"):
            run_login(browser)

    step(4, STEPS[3])
    if check_config(config_file).ok:
        print(f"  ✅ {config_file}")
    elif check_browser_profile(browser).ok:
        configure_folders(config_file, browser)
    else:
        if not config_file.exists():
            config_file.write_text(CONFIG_TEMPLATE, encoding="utf-8")
            config_file.chmod(0o600)
        print("  serve prima l'accesso (passo 3): le cartelle le legge dal tuo "
              "account.")

    step(5, STEPS[4])
    if check_profile(profile_file).ok:
        print(f"  ✅ {profile_file}")
    else:
        ask_profile(profile_file)

    step(6, STEPS[5])
    offer_schedule()

    checks = [
        check_api_key(env_file),
        check_chromium(),
        check_browser_profile(browser),
        check_config(config_file),
        check_profile(profile_file),
    ]
    print("\n" + "-" * 58)
    for c in checks:
        print(f"  {'✅' if c.ok else '❌'} {c.name:20} {c.detail}")

    missing = [c for c in checks if not c.ok]
    if missing:
        print("\n  Manca ancora:\n")
        for c in missing:
            print(f"    • {c.name}: {c.todo or c.detail}")
        print("\n  Rilancia 'winnow init' e riprende da li'.\n")
        return 1

    print("\n  Tutto pronto. Il primo giro, con l'arretrato che hai salvato:\n")
    print("      winnow collect --posts 20\n")
    print("  Poi ogni notte da solo, e a fine settimana:  winnow recap\n")
    return 0


def offer_schedule() -> None:
    """Ask once whether winnow should run by itself.

    Writing a launchd plist by hand is where a first-time user gives up, so
    winnow offers to do it — and asks first, because installing something that
    wakes up daily is not a thing to do behind someone's back.
    """
    from winnow.schedule import DEFAULT_TIME, backend, current, install, parse_time

    which = backend()
    if which == "unsupported":
        return
    if current(which).active:
        print(f"\n  ✅ raccolta giornaliera: {current(which)}")
        return

    print(f"\n  winnow puo' raccogliere da solo una volta al giorno ({which}).")
    answer = ask(f"  Programmarla alle {DEFAULT_TIME}? [S/n, oppure HH:MM] ")
    if answer.lower() in ("n", "no"):
        print("  ok. Quando vuoi: winnow schedule --at HH:MM")
        return
    when = answer if ":" in answer else DEFAULT_TIME
    try:
        hour, minute = parse_time(when)
    except ValueError as e:
        print(f"  {e} — salto. Quando vuoi: winnow schedule --at HH:MM")
        return
    install(hour, minute, which)


def load_env_file(env_file: Path) -> dict[str, str]:
    """Parse KEY=value lines. Not a shell: no expansion, no execution.

    This is what lets a scheduled job be a bare `winnow collect` — no wrapper
    script sourcing a file, and no secret written into the schedule itself.
    """
    out: dict[str, str] = {}
    if not env_file.exists():
        return out
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def apply_env_file(env_file: Path) -> None:
    """Load the key file into the environment, without overriding what is set."""
    for key, value in load_env_file(env_file).items():
        os.environ.setdefault(key, value)
