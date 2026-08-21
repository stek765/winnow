"""`winnow recap` — put the week in one place, ready to hand to a model.

This module is the one place where the two halves meet, and it is careful not
to become the judge: it gathers, it does not weigh. No entity is dropped, no
score is computed, nothing is ranked. What comes out is the prompt, your
profile and the week's findings, concatenated in that order.

The reason it exists at all: without it the weekly step means remembering
three paths, knowing that "the week" is the last seven daily files, and that
the profile lives somewhere the tool never mentioned. That friction is exactly
what stops people going back to their saved posts in the first place.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from winnow import paths

DAYS = 7


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


def build_bundle(prompt: str, profile: str, files: list[Path]) -> str:
    """Prompt, profile, findings — in the order a model should read them."""
    parts = [
        "# winnow — weekly recap",
        "",
        "Everything below is one week of collected facts plus the profile they",
        "must be weighed against. Follow the instructions in the first section.",
        "",
        "---",
        "",
        "## 1. What to do",
        "",
        prompt.strip(),
        "",
        "---",
        "",
        "## 2. My profile",
        "",
        profile.strip(),
        "",
        "---",
        "",
        f"## 3. The findings ({len(files)} day{'s' if len(files) != 1 else ''})",
        "",
    ]
    for f in files:
        parts += [f"### {f.stem}", "", "```json", f.read_text(encoding="utf-8").strip(),
                  "```", ""]
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


def run_recap(days: int = DAYS, now: datetime | None = None) -> int:
    now = now or datetime.now()
    profile_path = paths.profile_file()
    if not profile_path.exists():
        print(f"  ❌ manca il profilo: {profile_path}")
        print("     esegui 'winnow init', te lo crea da compilare.")
        return 1

    files = week_files(paths.findings_dir(), now.date(), days)
    if not files:
        giorni = "giorno" if days == 1 else "giorni"
        print(f"  nessun findings negli ultimi {days} {giorni}. "
              "Prova 'winnow status'.")
        return 1

    bundle = build_bundle(prompt_body(package_file("recap-prompt.md")),
                          profile_path.read_text(encoding="utf-8"), files)
    out = paths.recap_dir() / f"{now.date().isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(bundle, encoding="utf-8")

    giorni = "giorno" if len(files) == 1 else "giorni"
    print(f"  {len(files)} {giorni} di findings + il tuo profilo → {out}")
    if copy_to_clipboard(bundle):
        print("  ✅ copiato negli appunti: incollalo a un modello e chiedi il recap.")
    else:
        print("  incollalo a un modello e chiedi il recap.")
    return 0
