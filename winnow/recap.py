"""`winnow recap` — put the week in one place, ready to hand to a model.

This module is the one place where the two halves meet, and it is careful not
to become the judge: it gathers, it does not weigh. No entity is dropped, no
score is computed, nothing is ranked. What comes out is four blocks — the
week's facts, how to read them, who is reading, and the ask — with the facts
arranged by `digest.py` rather than dumped as the JSON they are stored in.

The reason it exists at all: without it the weekly step means remembering
three paths, knowing that "the week" is the last seven daily files, and that
the profile lives somewhere the tool never mentioned. That friction is exactly
what stops people going back to their saved posts in the first place.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from winnow import config, digest, paths, providers
from winnow.render import extract_json

DAYS = 7

# Past this, the profile stops tinting the judgement and starts driving it:
# the model has more of your plan in front of it than of your week. Measured
# once at 128,000 characters — a quarter of the bundle, and the recap came
# back auditing saved posts against a plan instead of answering them.
PROFILE_BUDGET = 15_000


def week_files(findings_dir: Path, today: date, days: int = DAYS) -> list[Path]:
    """The findings files of the last `days` days, oldest first.

    Selected by the date in the filename, not by mtime: a file rewritten by a
    later run of the same day must not look like a different day.
    """
    if not findings_dir.is_dir():
        return []
    window = {(today - timedelta(days=i)).isoformat() for i in range(days)}
    return sorted(p for p in findings_dir.glob("*.json") if p.stem in window)


MARKER = "<!-- PROMPT -->"

# A line that is just a path, `@`-prefixed — the same syntax CLAUDE.md uses for
# its own imports, because the people most likely to already have a file worth
# pointing at are the ones who wrote one of those.
INCLUDE_RE = re.compile(r"^@(\S.*)$", re.MULTILINE)

# Things that must never be pasted into a chat window. Deliberately narrow:
# crying wolf on every line containing "token" would train people to ignore it.
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[abposr]-[A-Za-z0-9\-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{12}:[A-Za-z0-9]{20,})"
)


def find_secrets(text: str) -> list[str]:
    """Lines that look like they hold a credential.

    The bundle ends up in a clipboard and then in somebody's chat window. A
    profile that points at a personal notes file can carry an API key along
    with it — and the person pointing at it will not remember it is in there.
    """
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if SECRET_RE.search(line):
            out.append(f"riga {n}: {line.strip()[:60]}")
    return out


def resolve_includes(text: str, base: Path | None = None
                     ) -> tuple[str, list[str]]:
    """Replace `@path` lines with the file's contents.

    Returns the text and the paths that could not be read. A missing include is
    reported, never quietly dropped: the whole point of the profile is what it
    says, and half a profile that looks whole is worse than an error.
    """
    missing: list[str] = []

    def swap(m: re.Match) -> str:
        raw = m.group(1).strip()
        path = Path(raw).expanduser()
        if not path.is_absolute() and base is not None:
            path = base / path
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            missing.append(str(path))
            return (f"> ⚠️ the profile pointed at `{path}`, which cannot be "
                    f"read: that piece of context is MISSING.")
        return f"<!-- da {path} -->\n{body.strip()}"

    return INCLUDE_RE.sub(swap, text), missing


def package_file(name: str) -> str:
    return (Path(__file__).parent / name).read_text(encoding="utf-8")


def prompt_body(text: str) -> str:
    """The half of the prompt file meant for a model.

    The file opens by explaining itself to a human reading it on GitHub. Handing
    that to a model wastes its attention on documentation about the instruction
    it is already being given.
    """
    _, _, after = text.partition(MARKER)
    return (after or text).strip()


def load_days(files: list[Path]) -> list[dict]:
    """The findings files, parsed. A corrupt day is reported, not fatal."""
    days = []
    for f in files:
        try:
            days.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ⚠️  {f.name} could not be read ({exc}): "
                  "that day is not in the recap.")
    return days


def build_bundle(prompt: str, profile: str, files: list[Path],
                 mentality: str = "", today: str = "") -> str:
    """The four blocks, in the order the reader needs them.

    Contents first, then how to read them, then who is reading — because the
    profile must tint the judgement, not drive it. The week that a profile
    drove the judgement, fifteen saved posts were dismissed by quoting the
    reader's own plan back at them, which answered a question nobody asked.

    The ask comes last on purpose: it is what gets acted on, and in a long
    context the last thing read is the thing that gets done.
    """
    parts = [
        "# winnow — weekly recap",
        "",
        "Below: a week of collected facts, how to read them, who is reading,",
        "and what to produce. Work through it in that order.",
        "",
        "---",
        "",
        f"## 1. The week ({len(files)} day{'s' if len(files) != 1 else ''})",
        "",
        digest.render(digest.gather(load_days(files), today), len(files)),
        "",
    ]

    parts += ["---", "", "## 2. How to read a pile like this", "",
              # Demoted one level: its `##` headings would otherwise sit at
              # the same rank as the four blocks and flatten the structure.
              (mentality or "").strip().replace("\n## ", "\n### ")
                                       .replace("\n# ", "\n### "), "",
              "---", "", "## 3. Who is reading — this tints it, it does not "
              "drive it", "",
              profile.strip().replace("\n## ", "\n### ")
                             .replace("\n# ", "\n### "), "",
              "---", "", "## 4. What to produce", "", prompt.strip(), ""]
    return "\n".join(parts)


def ask_confirm(prompt: str) -> bool:
    from winnow.setup import ask
    return ask(prompt).lower() in ("y", "yes", "s", "si")


def run_recap(now: datetime | None = None, open_file: bool = True,
              on_event=None, ask=None, confirm=None) -> int:
    """Prepare, ask, write the page. One run instead of three.

    There used to be three — `winnow recap`, paste into a model, `winnow
    render` — and the step in between was the one place things could fail
    without anyone understanding why. On 2026-08-25 it ate a real response.

    `confirm` is injectable for the same reason `ask` is: the credential
    guard below must be testable without a terminal attached to stdin.
    """
    from winnow import judge, window
    from winnow.render import render_file

    now = now or datetime.now()

    def say(event: str, **data) -> None:
        if on_event:
            on_event(event, data)

    profile_path = paths.profile_file()
    if not profile_path.exists():
        print(f"  ❌ no profile: {profile_path}")
        print("     run 'winnow init', it creates one to fill in.")
        return 1

    judged = paths.judged_file()
    files = window.pending_files(paths.findings_dir(),
                                 window.last_judged(judged))
    if not files:
        print("  Nothing new since the last recap.")
        return 0

    # `load_days`, not a raw read: a corrupt day here must be reported and
    # skipped, the same as everywhere else this window is read.
    days = load_days(files)
    profile = profile_path.read_text(encoding="utf-8")
    profile, missing = resolve_includes(profile, profile_path.parent)
    for m in missing:
        print(f"  ⚠️  the profile points at {m}, which cannot be read.")

    if len(profile) > PROFILE_BUDGET:
        print(f"\n  ⚠️  your profile is {len(profile):,} characters. The "
              "recap only needs\n      who you are and what you are after — "
              "a plan, a portfolio or a\n      year of notes will drown the "
              f"week's findings.\n      {profile_path}\n")

    # The bundle now goes straight to a third-party API instead of sitting on
    # a clipboard where a person could notice it — the guard matters more
    # than it used to, not less.
    leaks = find_secrets(profile)
    if leaks:
        print(f"\n  ⚠️  {profile_path} holds something that looks like a "
              "credential:\n")
        for hint in leaks[:5]:
            print(f"        {hint}")
        print("\n      The bundle goes straight to the model provider.")
        if not (confirm or ask_confirm)("  Send it anyway? [y/N] "):
            return 1

    facts = digest.gather(days, now.date().isoformat())
    # build_bundle wants the PATHS, not the days already read into memory.
    bundle = build_bundle(prompt_body(package_file("recap-prompt.md")),
                          profile, files, package_file("mentality.md"),
                          now.date().isoformat())
    say("bundling", days=len(files), posts=facts["posts"],
        things=len(facts["things"]))

    # `config.py` exposes flat fields (`.provider`, `.model`, `.base_url`),
    # not a nested `.api` namespace — kept in step with the rest of the repo.
    try:
        cfg = config.load_config(paths.config_file())
    except FileNotFoundError:
        print(f"  ❌ no config: {paths.config_file()}")
        print("     run 'winnow init'.")
        return 1
    try:
        text, tin, tout = (ask or judge.ask)(
            bundle, cfg.provider, cfg.model, cfg.base_url,
            on_event=on_event)
    except judge.Fatal as e:
        print(f"  ❌ {e}")
        return 1

    # Written before it is read: a judgement costs real money, and a broken
    # answer on disk gets fixed by hand — a lost one does not.
    recap_dir = paths.recap_dir()
    recap_dir.mkdir(parents=True, exist_ok=True)
    stem = now.date().isoformat()
    src = recap_dir / f"{stem}.answer.md"
    n = 2
    while src.exists():
        src = recap_dir / f"{stem}.answer-{n}.md"
        n += 1
    src.write_text(text, encoding="utf-8")

    usd = providers.cost(cfg.provider, cfg.model, tin, tout)
    try:
        out = render_file(src, embed_shots=True)
    except json.JSONDecodeError as e:
        print(f"  ❌ the answer is not valid JSON: {e.msg}")
        print(f"     saved anyway: {src}")
        return 1

    data = extract_json(text)
    say("judged", kept=(data.get("counts") or {}).get("kept", 0),
        of=len(facts["things"]), usd=usd)
    # `progress.line` already prints "  → {path}" for this event — printing
    # the path again here would just show the same line twice from the CLI.
    say("rendered", path=str(out))

    # The marker moves only now: marking as judged a day whose recap failed
    # would lose it forever.
    window.mark_judged(judged, files[-1].stem)

    if open_file and sys.stdout.isatty():
        import webbrowser
        webbrowser.open(f"file://{out.resolve()}")
    return 0
