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
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from winnow import digest, paths

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
            print(f"  \u26a0\ufe0f  {f.name} could not be read ({exc}): "
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


def copy_to_clipboard(text: str) -> str | None:
    """Best effort. Returns the tool used, or None — never raises: a missing
    clipboard must not cost you the bundle that was already written."""
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text, text=True, check=True)
                return cmd[0]
            except subprocess.SubprocessError:
                return None
    return None


def ask_confirm(prompt: str) -> bool:
    from winnow.setup import ask
    return ask(prompt).lower() in ("y", "yes", "s", "si")


def run_recap(days: int = DAYS, now: datetime | None = None,
              open_file: bool = True) -> int:
    now = now or datetime.now()
    profile_path = paths.profile_file()
    if not profile_path.exists():
        print(f"  ❌ no profile: {profile_path}")
        print("     run 'winnow init', it creates one to fill in.")
        return 1

    files = week_files(paths.findings_dir(), now.date(), days)
    if not files:
        day = "day" if days == 1 else "days"
        print(f"  no findings in the last {days} {day}. Try 'winnow status'.")
        return 1

    profile, missing = resolve_includes(
        profile_path.read_text(encoding="utf-8"), profile_path.parent)
    for path in missing:
        print(f"  ⚠️  the profile points at {path}, which cannot be read: "
              "that context is not in the recap.")

    if len(profile) > PROFILE_BUDGET:
        print(f"\n  \u26a0\ufe0f  your profile is {len(profile):,} characters. The "
              "recap only needs\n      who you are and what you are after — "
              "a plan, a portfolio or a\n      year of notes will drown the "
              f"week's findings.\n      {profile_path}\n")

    leaks = find_secrets(profile)
    if leaks:
        print("\n  ⚠️  WARNING: the profile (or a file it includes) holds")
        print("      something that looks like a credential, and the recap")
        print("      goes to your clipboard and then into a chat:\n")
        for hint in leaks[:5]:
            print(f"        {hint}")
        print("\n      Remove it, or point at a file that does not hold it.")
        if ask_confirm("  Carry on anyway? [y/N] ") is False:
            return 1

    bundle = build_bundle(prompt_body(package_file("recap-prompt.md")),
                          profile, files, package_file("mentality.md"),
                          now.date().isoformat())
    out = paths.recap_dir() / f"{now.date().isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(bundle, encoding="utf-8")

    day = "day" if len(files) == 1 else "days"
    posts = sum(len(json.loads(f.read_text(encoding="utf-8")).get("posts", []))
                for f in files)
    print(f"  {len(files)} {day} · {posts} posts · ~{len(bundle) // 4000}k tokens")
    print(f"  {out}")

    # "Paste it into a model" told nobody anything. Say what to press, and say
    # that the instructions are already inside — otherwise the reader starts
    # writing a prompt that has been written for them.
    if copy_to_clipboard(bundle):
        print("\n  ✅ On your clipboard: the instructions, your profile and "
              "the week, in one piece.\n")
        print("  1.  Paste it into a model (Claude, ChatGPT, ...) and send.")
    else:
        print(f"\n  Copy the whole of {out} and paste it into a model.\n")
        print("  1.  Paste and send.")
    print("      You do not write a prompt — the file ends with the ask.")
    # The loop has to close here or the judgement dies in a chat window. Two
    # lines, and neither of them asks anybody to save a file: the bundle went
    # out through the clipboard and the answer comes back the same way.
    print("  2.  Copy its whole answer, ```json block included.")
    print("  3.  Run  winnow render  — the page opens by itself.")
    if len(bundle) > 300_000:
        print(f"         ⚠️  ~{len(bundle) // 4000}k tokens: it needs a large "
              "context window.")
        print("             `winnow recap --days 1` makes a smaller one.")

    # Opened, not just written: a path printed in a terminal is a path you look
    # at tomorrow. The clipboard already holds the text, so this is for reading
    # it — and for the case where the clipboard has been overwritten since.
    if open_file and sys.stdout.isatty():
        from winnow.setup import open_in_editor
        open_in_editor(out)
    return 0
