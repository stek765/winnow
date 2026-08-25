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
        return Check("config", False, "missing")
    text = config_file.read_text(encoding="utf-8")
    if "YOUR_USERNAME" in text:
        return Check(
            "config", False, f"to be filled in: {config_file}",
            "run 'winnow init' after signing in: it finds your saved folders "
            "by itself",
        )
    return Check("config", True, str(config_file))


def check_api_key(env_file: Path, name: str = "ANTHROPIC_API_KEY") -> Check:
    if os.environ.get(name):
        return Check("API key", True, "present in the environment")
    if env_file.exists() and name in env_file.read_text(encoding="utf-8"):
        return Check("API key", True, str(env_file))
    return Check(
        "API key", False, "missing",
        "create one at console.anthropic.com (set a spend limit while you are "
        "there) and run 'winnow init': it asks for it and writes it for you",
    )


def check_profile(profile_file: Path) -> Check:
    """The profile is the half of the configuration no code can write for you.

    A file that still holds the template is worse than a missing one: `winnow
    recap` would happily hand a model somebody else's life.
    """
    if not profile_file.exists():
        return Check("profile", False, "missing",
                     "run 'winnow init': it creates one to fill in")
    text = profile_file.read_text(encoding="utf-8")
    if "# Example profile" in text:
        return Check("profile", False, f"still the example: {profile_file}",
                     "run 'winnow init': four questions and it writes it")

    # A profile that points at a file which no longer exists is worse than a
    # missing one: it looks configured and carries nothing.
    from winnow.recap import resolve_includes
    _, missing = resolve_includes(text, profile_file.parent)
    if missing:
        return Check("profile", False,
                     f"points at {missing[0]}, which cannot be read",
                     "the file was moved or deleted: run 'winnow init' and "
                     "link it again")
    return Check("profile", True, str(profile_file))


def check_browser_profile(profile: Path) -> Check:
    """A logged-in Chromium profile has a Cookies database. An empty directory
    is not a session: better to say so than to fail at 1 a.m."""
    if (profile / "Default" / "Cookies").exists():
        return Check("Instagram login", True, str(profile))
    return Check(
        "Instagram login", False, "never done",
        "run 'winnow login' and sign in by hand in the window that opens",
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


def api_ready(config_file: Path, env_file: Path) -> Check:
    """Is there a model, and can we reach it?

    Reads the provider out of config.toml rather than assuming Anthropic: with
    a local model there is no key to look for, and reporting a missing one
    would be a red cross next to a setup that works.
    """
    from winnow.providers import ANTHROPIC, KEY_ENV, needs_key

    provider, model = ANTHROPIC, None
    if config_file.exists():
        import tomllib
        try:
            api = tomllib.loads(config_file.read_text(encoding="utf-8")).get("api", {})
            provider, model = api.get("provider", ANTHROPIC), api.get("model")
        except tomllib.TOMLDecodeError:
            pass
    if not model:
        return Check("model", False, "not chosen",
                     "run 'winnow init': it offers a menu")
    if not needs_key(provider):
        return Check("model", True, f"{model} (local)")
    key = check_api_key(env_file, KEY_ENV[provider])
    if not key.ok:
        return Check("model", False, f"{model}: {KEY_ENV[provider]} is missing",
                     "run 'winnow init' and paste it when asked")
    return Check("model", True, f"{model} ({provider})")


def check_chromium() -> Check:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return Check("browser", False, "playwright not installed",
                     "reinstall winnow")
    if not chromium_installed():
        return Check("browser", False, "Chromium not downloaded",
                     "run 'winnow init' (downloads ~150 MB)")
    return Check("browser", True, "Chromium ready")


def install_chromium() -> bool:
    print("  downloading Chromium (~150 MB, once)...")
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    return r.returncode == 0


def run_login(profile: Path) -> bool:
    from winnow.browser import BASE, open_session

    print(f"  opening a window on the dedicated profile: {profile}")
    with open_session(profile) as page:
        page.goto(BASE)
        print("\n  In the window that just opened:")
        print("    1. reject the optional cookies")
        print("    2. sign in to Instagram")
        print("    3. come back here and press ENTER\n")
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


def render_folders_section(text: str, username: str,
                           folders: list[tuple[str, str, bool, str]]) -> str:
    """Replace the folder blocks, keep everything else byte for byte.

    `render_config` rebuilds the file from the template, which is right for a
    first setup and wrong as an editor: it would silently reset `posts_per_run`,
    the spend limits and the model choice back to their defaults.
    """
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "[[folders]]":
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("["):
                i += 1
            continue
        if stripped.startswith("username =") and username:
            out.append(f'username = "{username}"')
            i += 1
            continue
        out.append(lines[i])
        i += 1
    body = "\n".join(out).rstrip() + "\n"
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
    print("  You need an Anthropic API key. Opening the page:")
    print(f"  {KEY_URL}")
    print("  Create one, and set a spend limit while you are there.\n")
    open_url(KEY_URL)
    key = ask("  Paste the key here (enter to skip): ", secret=True)
    if not key:
        return False
    if not key.startswith("sk-"):
        print("  ⚠️  that does not look like an Anthropic key. Writing it anyway.")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(f"ANTHROPIC_API_KEY={key}\n", encoding="utf-8")
    env_file.chmod(0o600)
    print(f"  ✅ written to {env_file} (600)")
    return True


def configure_folders(config_file: Path, profile: Path) -> bool:
    """Read the account's saved folders and write the config from them.

    Safe to call on an existing config: only the folder blocks are replaced,
    so tuned limits and the model choice survive.
    """
    from winnow.browser import list_saved_folders, open_session

    username = ask("\n  Instagram username: ").lstrip("@")
    if not username:
        return False
    print("  looking for your saved folders...")
    try:
        with open_session(profile) as page:
            found = list_saved_folders(page, username)
    except Exception as e:
        print(f"  ⚠️  could not do it ({e.__class__.__name__}).")
        return False
    if not found:
        print("  no folders found. Make one on Instagram and run this again.")
        return False

    print("\n  Saved folders found:\n")
    for i, (name, _) in enumerate(found, 1):
        print(f"    {i:2}. {name}")
    picked = parse_selection(
        ask("\n  Which ones should winnow read? (e.g. 1,3-4) "), len(found))
    if not picked:
        print("  nothing picked: writing them all off, turn them on whenever.")
    repos = parse_selection(
        ask("  Of these, which hold repos or tools? (enter = none) "),
        len(found)) if picked else set()

    folders = [
        (name, url, i in picked, "repo" if i in repos else "news")
        for i, (name, url) in enumerate(found, 1)
    ]
    if config_file.exists() and "YOUR_USERNAME" not in config_file.read_text(
            encoding="utf-8"):
        text = render_folders_section(
            config_file.read_text(encoding="utf-8"), username, folders)
    else:
        text = render_config(username, folders)
    config_file.write_text(text, encoding="utf-8")
    config_file.chmod(0o600)
    print(f"  ✅ {len(picked)} folders active in {config_file}")
    return True


def choose_model() -> object:
    """Which model reads the slides. Asked, not assumed.

    A menu instead of a config field because the alternative is a first-time
    user editing a TOML key they have never seen, to a value they have to go
    and look up.
    """
    from winnow.providers import CHOICES

    print("  Who reads the slides. You can change it later in config.toml.\n")
    for i, c in enumerate(CHOICES, 1):
        print(f"    {i}. {c.label:22} {c.hint}")
    answer = ask("\n  Which one? [1] ") or "1"
    try:
        return CHOICES[int(answer) - 1]
    except (ValueError, IndexError):
        print("  did not understand that, keeping 1.")
        return CHOICES[0]


def setup_model(config_file: Path, env_file: Path) -> None:
    """The choice, its key, and the line in config.toml that records it."""
    from winnow.providers import CONSOLE, KEY_ENV, LOCAL_BASE_URL, needs_key

    choice = choose_model()
    model, base_url = choice.model, None

    if needs_key(choice.provider):
        env = KEY_ENV[choice.provider]
        if not check_api_key(env_file, env).ok:
            print(f"\n  You need a {choice.provider} key. Opening the page:")
            print(f"  {CONSOLE[choice.provider]}")
            print("  Create one, set a spend limit, and remember that a key")
            print("  with no credit loaded does not work.\n")
            open_url(CONSOLE[choice.provider])
            key = ask("  Paste the key here (enter to skip): ", secret=True)
            if key:
                write_key(env_file, env, key)
    else:
        print("\n  Your own model, on your own machine. It has to read")
        print("  images and speak the OpenAI API (Ollama, LM Studio, ...).")
        base_url = ask(f"  Address [{LOCAL_BASE_URL}] ") or LOCAL_BASE_URL
        model = ask("  Model name (e.g. qwen2.5vl) ") or "qwen2.5vl"

    write_api_choice(config_file, choice.provider, model, base_url)
    print(f"  ✅ model: {model} ({choice.provider})")


def write_api_choice(config_file: Path, provider: str, model: str,
                     base_url: str | None) -> None:
    """Record the choice without disturbing anything else in the file."""
    text = config_file.read_text(encoding="utf-8") if config_file.exists() else CONFIG_TEMPLATE
    text = render_api_section(text, provider, model, base_url)
    config_file.write_text(text, encoding="utf-8")
    config_file.chmod(0o600)


def render_api_section(text: str, provider: str, model: str,
                       base_url: str | None) -> str:
    """Replace the [api] block, keep the rest of the file byte for byte.

    Rewriting the whole config from a template would throw away the folders and
    the limits someone has tuned — the config is theirs, we only own one block.
    """
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip() == "[api]":
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("["):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    block = ["[api]", f'provider = "{provider}"', f'model = "{model}"']
    if base_url:
        block.append(f'base_url = "{base_url}"')
    # Subito dopo [instagram], dove stava prima: un file che cambia ordine a
    # ogni init e' un file che non riconosci piu'.
    for n, line in enumerate(out):
        if line.strip().startswith("[") and line.strip() != "[instagram]" and n:
            return "\n".join(out[:n] + block + [""] + out[n:]).rstrip() + "\n"
    return "\n".join(out + [""] + block).rstrip() + "\n"


def write_key(env_file: Path, name: str, key: str) -> None:
    lines = [l for l in (env_file.read_text(encoding="utf-8").splitlines()
                         if env_file.exists() else [])
             if not l.startswith(f"{name}=")]
    lines.append(f"{name}={key}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env_file.chmod(0o600)
    print(f"  ✅ key written to {env_file} (600)")


KEY_URL = "https://console.anthropic.com/settings/keys"

PROFILE_QUESTIONS = [
    ("Who are you, in two lines?", "Who I am"),
    ("What are you trying to get to in the next two or three years?",
     "What I'm actually after"),
    ("What decisions do you have open right now?", "Open questions"),
    ("What have you already ruled out, and why? (the line that matters most)",
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


# Files people are likely to already have written about themselves. Offered,
# never read unless asked: the people most likely to have one are the ones who
# already keep a CLAUDE.md, and re-answering four questions to say what that
# file already says is busywork.
PROFILE_CANDIDATES = (
    "~/.claude/CLAUDE.md",
    "~/.config/AGENTS.md",
    "~/AGENTS.md",
    "~/notes/about-me.md",
)


def find_candidates(profile_file: Path) -> list[Path]:
    return [p for raw in PROFILE_CANDIDATES
            if (p := Path(raw).expanduser()).is_file() and p != profile_file]


def link_profile(profile_file: Path, target: Path) -> bool:
    """Point the profile at a file the user already maintains.

    A reference and not a copy: a snapshot of a file that changes every week is
    a profile that is quietly out of date by the third week.
    """
    from winnow.recap import find_secrets

    try:
        body = target.read_text(encoding="utf-8")
    except OSError as e:
        print(f"  cannot read it ({e.__class__.__name__}): {target}")
        return False

    leaks = find_secrets(body)
    if leaks:
        print(f"\n  \u26a0\ufe0f  {target} holds something that looks like a credential:\n")
        for hint in leaks[:5]:
            print(f"        {hint}")
        print("\n      The recap goes straight to your model provider's API.")
        if ask("  Link it anyway? [y/N] ").lower() not in ("y", "yes", "s", "si"):
            return False

    profile_file.write_text(
        "# My profile\n\n"
        "Points at a file I maintain myself: winnow re-reads it at every\n"
        "recap, so it stays up to date on its own.\n\n"
        f"@{target}\n", encoding="utf-8")
    profile_file.chmod(0o600)
    print(f"  \u2705 linked {target}")
    print(f"     {profile_file} includes it, it does not copy it")
    return True


def answer_questions(profile_file: Path) -> bool:
    print("\n  Four questions, one line each. Empty line skips one.\n")
    answers: list[tuple[str, str]] = []
    for question, heading in PROFILE_QUESTIONS:
        print(f"  {question}")
        answer = ask("  > ")
        print()
        if answer:
            answers.append((heading, answer))

    if not answers:
        print(f"  skipped. The file to rewrite is {profile_file}")
        return False
    profile_file.write_text(render_profile(answers), encoding="utf-8")
    profile_file.chmod(0o600)
    print(f"  \u2705 scritto {profile_file}")
    if ask("  Open it to add more? [y/N] ").lower() in ("y", "yes", "s", "si"):
        open_in_editor(profile_file)
        ask("  (press ENTER when you are done) ")
    return True


def profile_menu(candidates: list[Path]) -> list[str]:
    """The options, in the order they are printed. Pure, so the numbering that
    decides what happens can be checked without a terminal."""
    return (["ask"] + [f"link:{c}" for c in candidates] + ["other", "skip"])


def ask_profile(profile_file: Path) -> bool:
    """Four questions — or a file you already keep."""
    template = Path(__file__).parent / "profile-template.md"
    if not profile_file.exists():
        profile_file.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        profile_file.chmod(0o600)

    candidates = find_candidates(profile_file)
    options = profile_menu(candidates)
    labels = {"ask": "answer four questions (2 minutes)",
              "other": "link a file you already have (path)",
              "skip": "skip, I will write it later"}

    print("  This is the file that decides what matters to YOU.\n")
    for i, opt in enumerate(options, 1):
        if opt.startswith("link:"):
            path = Path(opt[5:])
            kb = path.stat().st_size // 1024
            # A big file here is a trap worth naming at the moment of
            # choosing: the profile is meant to tint the week, and a file
            # this size ends up outweighing it.
            big = "  ⚠ large — it will outweigh the week" if kb > 15 else ""
            print(f"    {i}. link {path}  ({kb} KB){big}")
        else:
            print(f"    {i}. {labels[opt]}")

    raw = ask("\n  Which one? [1] ") or "1"
    try:
        chosen = options[int(raw) - 1]
    except (ValueError, IndexError):
        chosen = "ask"

    if chosen.startswith("link:"):
        return link_profile(profile_file, Path(chosen[5:]))
    if chosen == "other":
        raw = ask("  Path to the file: ")
        return link_profile(profile_file, Path(raw).expanduser()) if raw else False
    if chosen == "skip":
        print(f"  skipped. The file to rewrite is {profile_file}")
        return False
    return answer_questions(profile_file)


STEPS = ("the model", "browser", "Instagram login", "saved folders",
         "your profile", "daily run")


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
    print("winnow — six steps, five minutes.")
    print("Stop whenever you like: running 'winnow init' again picks up where "
          "you left off.")
    paths.ensure_dirs()

    env_file, profile_file = paths.env_file(), paths.profile_file()
    browser = paths.browser_profile()
    config_file = paths.config_file()

    step(1, STEPS[0])
    if api_ready(config_file, env_file).ok:
        print(f"  ✅ already set ({api_ready(config_file, env_file).detail})")
    else:
        setup_model(config_file, env_file)

    step(2, STEPS[1])
    if check_chromium().ok:
        print("  ✅ Chromium ready")
    else:
        install_chromium()

    step(3, STEPS[2])
    if check_browser_profile(browser).ok:
        print("  ✅ session saved")
    elif check_chromium().ok:
        print("  Opening a window: sign in to Instagram by hand, winnow")
        print("  never types your password.")
        if ask("  Go ahead? [Y/n] ").lower() in ("", "y", "yes", "s", "si"):
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
        print("  sign in first (step 3): it reads the folders off your "
              "account.")

    step(5, STEPS[4])
    if check_profile(profile_file).ok:
        print(f"  ✅ {profile_file}")
    else:
        ask_profile(profile_file)

    step(6, STEPS[5])
    offer_schedule()

    checks = [
        api_ready(config_file, env_file),
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
        print("\n  Still missing:\n")
        for c in missing:
            print(f"    • {c.name}: {c.todo or c.detail}")
        print("\n  Run 'winnow init' again and it picks up from there.\n")
        return 1

    print("\n  All set. Your first run, with the backlog you have saved:\n")
    print("      winnow collect --posts 20\n")
    print("  Then once a day on its own, and at the end of the week:  "
          "winnow recap\n")
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
        print(f"\n  ✅ daily run: {current(which)}")
        return

    print(f"\n  winnow can collect on its own once a day ({which}).")
    answer = ask(f"  Schedule it at {DEFAULT_TIME}? [Y/n, or HH:MM] ")
    if answer.lower() in ("n", "no"):
        print("  ok. Whenever you like: winnow schedule --at HH:MM")
        return
    when = answer if ":" in answer else DEFAULT_TIME
    try:
        hour, minute = parse_time(when)
    except ValueError as e:
        print(f"  {e} — skipping. Whenever you like: winnow schedule --at HH:MM")
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


# --- winnow config ---------------------------------------------------------

CONFIG_ACTIONS = ("folders", "model", "posts per run", "hour",
                  "profile", "open the file")


def set_posts_per_run(config_file: Path) -> None:
    """The one limit worth changing often: how many posts a run reads."""
    import tomllib

    current = 8
    try:
        current = tomllib.loads(
            config_file.read_text(encoding="utf-8"))["limits"]["posts_per_run"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        pass

    print(f"\n  It reads {current} per run. Higher clears a backlog faster,")
    print("  but each run takes longer.")
    raw = ask(f"  How many? [{current}] ")
    if not raw:
        return
    try:
        value = int(raw)
        if value < 1:
            raise ValueError
    except ValueError:
        print("  needs a number above zero. Leaving it as it was.")
        return

    text = config_file.read_text(encoding="utf-8")
    out = []
    for line in text.splitlines():
        if line.strip().startswith("posts_per_run"):
            out.append(f"posts_per_run = {value}       # per run")
        else:
            out.append(line)
    config_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"  ✅ {value} posts per run")


def run_config() -> int:
    """`winnow config` — change the handful of things worth changing.

    One command, not one per setting: each entry simply re-enters the step of
    `winnow init` that already knows how to ask. The last entry opens the file
    for anything this menu deliberately does not cover.
    """
    config_file, profile_file = paths.config_file(), paths.profile_file()
    if not config_file.exists():
        print("  nothing to change yet: run 'winnow init'.")
        return 1

    print("  What do you want to change?\n")
    for i, label in enumerate(CONFIG_ACTIONS, 1):
        print(f"    {i}. {label}")
    raw = ask("\n  Which one? [enter to quit] ")
    if not raw:
        return 0
    try:
        action = CONFIG_ACTIONS[int(raw) - 1]
    except (ValueError, IndexError):
        print("  did not understand that.")
        return 1

    if action == "folders":
        browser = paths.browser_profile()
        if not check_browser_profile(browser).ok:
            print("  sign in first: 'winnow login'.")
            return 1
        configure_folders(config_file, browser)
    elif action == "model":
        setup_model(config_file, paths.env_file())
    elif action == "posts per run":
        set_posts_per_run(config_file)
    elif action == "hour":
        from winnow.schedule import DEFAULT_TIME, install, backend, parse_time
        raw = ask(f"\n  What hour? [{DEFAULT_TIME}] ") or DEFAULT_TIME
        try:
            hour, minute = parse_time(raw)
        except ValueError as e:
            print(f"  {e}")
            return 1
        install(hour, minute, backend())
    elif action == "profile":
        ask_profile(profile_file)
    else:
        print(f"  opening {config_file}")
        open_in_editor(config_file)
    return 0
