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

import re
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
            return (f"> ⚠️ il profilo puntava a `{path}`, che non si riesce a "
                    f"leggere: quel pezzo di contesto MANCA.")
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


def ask_confirm(prompt: str) -> bool:
    from winnow.setup import ask
    return ask(prompt).lower() in ("s", "si", "y", "yes")


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

    profile, missing = resolve_includes(
        profile_path.read_text(encoding="utf-8"), profile_path.parent)
    for path in missing:
        print(f"  ⚠️  il profilo punta a {path}, che non si legge: "
              "quel contesto non c'e' nel recap.")

    leaks = find_secrets(profile)
    if leaks:
        print("\n  ⚠️  ATTENZIONE: nel profilo (o in un file che include) c'e'")
        print("      qualcosa che sembra una credenziale, e il recap finisce")
        print("      negli appunti e poi in una chat:\n")
        for hint in leaks[:5]:
            print(f"        {hint}")
        print("\n      Togliela dal file, o punta a un file che non la contiene.")
        if ask_confirm("  Continuo comunque? [s/N] ") is False:
            return 1

    bundle = build_bundle(prompt_body(package_file("recap-prompt.md")),
                          profile, files)
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
