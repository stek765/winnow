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
from winnow.budget import Halted, check_brake, record_spend
from winnow.i18n import DEFAULT, language_name
from winnow.render import extract_json

DAYS = 7

# Past this, the profile stops tinting the judgement and starts driving it:
# the model has more of your plan in front of it than of your week. Measured
# once at 128,000 characters — a quarter of the bundle, and the recap came
# back auditing saved posts against a plan instead of answering them.
PROFILE_BUDGET = 15_000

# How much of a backlog one recap may swallow. Not a token limit dressed up as
# a rule: the answer carries a sentence per *rejected* thing, so its length
# tracks the pile and not what got through — 178 things came back cut off, and
# 46 posts across five days is not what this tool is for anyway. A recap that
# covers a fortnight is a page nobody reads.
#
# Counted in things and cut on whole days, because the marker that remembers
# what has been judged moves a day at a time. A single day over the cap is
# still taken whole: half a day judged is a day that can never be finished.
THINGS_PER_RECAP = 250


def things_in(path: Path) -> int:
    """How many named things a day holds. A day that cannot be read counts as
    nothing — `load_days` reports it and drops it further down."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return sum(len(p.get("entities") or []) for p in data.get("posts") or [])


def slice_days(files: list[Path], cap: int = THINGS_PER_RECAP
               ) -> tuple[list[Path], int]:
    """The oldest days that fit, and how many things are left behind.

    Oldest first on purpose: judging the newest and leaving the old behind
    would bury them under a marker that only moves forward, and they would
    never be judged at all.
    """
    taken: list[Path] = []
    total = 0
    for f in files:
        n = things_in(f)
        if taken and total + n > cap:
            break
        taken.append(f)
        total += n
    left = sum(things_in(f) for f in files[len(taken):])
    return taken, left


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

# Things that must never be sent to a model provider. Deliberately narrow:
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

    The bundle goes straight to the model provider's API. A profile that
    points at a personal notes file can carry an API key along with it — and
    the person pointing at it will not remember it is in there.
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


def prompt_body(text: str, lang: str = DEFAULT) -> str:
    """The half of the prompt file meant for a model, in the chosen language.

    The file opens by explaining itself to a human reading it on GitHub. Handing
    that to a model wastes its attention on documentation about the instruction
    it is already being given.

    `{language}` is filled in here. It used to say "the language my profile is
    written in", which was right while the app had no language of its own: it
    pinned the output to *something* instead of letting the model guess, and a
    guess can come out differently next week. Now there is a language chosen
    explicitly in the window, and that is the better anchor — an English window
    that answers in Italian is winnow disagreeing with a setting the reader
    just changed.
    """
    _, _, after = text.partition(MARKER)
    return (after or text).strip().replace("{language}", language_name(lang))


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


def entered_package(files: list[Path]) -> list[Path]:
    """Of the candidate files, the ones that actually reached the model.

    `load_days` reports a corrupt day and skips it — but returns only the
    parsed dicts, with no way back to which path was dropped. Marking
    `files[-1]` blindly used to close a day the bundle never contained,
    which is worse than not marking it: every future recap would then skip
    a day it never judged. Same check `load_days` makes, kept separate so a
    caller that only needs "did this one make it" is not handed a parsed
    dict it has no use for.
    """
    good = []
    for f in files:
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        good.append(f)
    return good


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


def _next_answer_path(recap_dir: Path, stem: str) -> Path:
    """Where today's answer goes, without overwriting an earlier run's.

    Shared by the complete-answer path and the truncated one below: both are
    "the model's words, written before anything is done with them", and a
    second run on the same day must not silently clobber the first.
    """
    path = recap_dir / f"{stem}.answer.md"
    n = 2
    while path.exists():
        path = recap_dir / f"{stem}.answer-{n}.md"
        n += 1
    return path


def ask_confirm(prompt: str) -> bool:
    from winnow.setup import ask
    return ask(prompt).lower() in ("y", "yes", "s", "si")


def run_recap(now: datetime | None = None, open_file: bool = True,
              on_event=None, ask=None, confirm=None, should_stop=None) -> int:
    """Prepare, ask, write the page. One run instead of three.

    There used to be three — `winnow recap`, paste into a model, `winnow
    render` — and the step in between was the one place things could fail
    without anyone understanding why. On 2026-08-25 it ate a real response.

    `confirm` is injectable for the same reason `ask` is: the credential
    guard below must be testable without a terminal attached to stdin.
    """
    from winnow import judge, window
    from winnow.api import read_look
    from winnow.i18n import t
    from winnow.render import render_file

    now = now or datetime.now()
    lang = read_look()["lang"]

    def say(event: str, **data) -> None:
        if on_event:
            on_event(event, data)

    profile_path = paths.profile_file()
    if not profile_path.exists():
        say("failed", why=t("run.failed.profile", lang, path=profile_path))
        print(f"  ❌ no profile: {profile_path}")
        print("     run 'winnow init', it creates one to fill in.")
        return 1

    judged = paths.judged_file()
    all_files = window.pending_files(paths.findings_dir(),
                                     window.last_judged(judged))
    if not all_files:
        print("  Nothing new since the last recap.")
        return 0

    # A backlog is cut into recaps rather than sent as one. What is left over
    # is not lost: the marker only moves over the days actually judged, so the
    # next press picks up exactly where this one stopped.
    files, left = slice_days(all_files)
    if left:
        say("sliced", days=len(files), of=len(all_files), left=left)
        print(f"  {len(files)} of {len(all_files)} days this time; "
              f"{left} things left for the next recap.")

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
            say("failed", why=t("run.failed.credential", lang))
            return 1

    facts = digest.gather(days, now.date().isoformat())
    # build_bundle wants the PATHS, not the days already read into memory.
    bundle = build_bundle(prompt_body(package_file("recap-prompt.md"), lang),
                          profile, files, package_file("mentality.md"),
                          now.date().isoformat())
    say("bundling", days=len(files), posts=facts["posts"],
        things=len(facts["things"]), chars=len(bundle))

    # `config.py` exposes flat fields (`.provider`, `.model`, `.base_url`),
    # not a nested `.api` namespace — kept in step with the rest of the repo.
    try:
        cfg = config.load_config(paths.config_file())
    except FileNotFoundError:
        say("failed", why=t("run.failed.config", lang,
                            path=paths.config_file()))
        print(f"  ❌ no config: {paths.config_file()}")
        print("     run 'winnow init'.")
        return 1

    # `collect()` checks and records around every extraction (`run.py`); this
    # call was the one gap — the heaviest one winnow makes (a week in, up to
    # 16k tokens out), invisible to `weekly_spend` and able to run past an
    # already-tripped brake. Same guard, same place in the sequence: before
    # the money is spent, not after.
    state_dir = paths.state_dir()
    spend_path = state_dir / "spend.json"
    try:
        check_brake(state_dir, spend_path, cfg.limits, now)
    except Halted as e:
        say("failed", why=str(e))
        print(f"  ❌ {e}")
        return 1

    recap_dir = paths.recap_dir()
    recap_dir.mkdir(parents=True, exist_ok=True)
    stem = now.date().isoformat()

    try:
        text, tin, tout = (ask or judge.ask)(
            bundle, cfg.provider, cfg.model, cfg.base_url,
            on_event=on_event, should_stop=should_stop)
    except judge.Stopped as e:
        say("stopped", why=str(e))
        print(f"  {e}")
        return 0
    except providers.Truncated as e:
        # This is the one call the "written before it is read" guarantee
        # used to miss: `judge.ask` classifies it correctly (not retryable,
        # stop at once), but until now the cut-off text never reached disk —
        # a whole week's judgement, at max_tokens=16000, thrown away.
        partial = getattr(e, "partial", "") or ""
        src = _next_answer_path(recap_dir, stem)
        src.write_text(partial, encoding="utf-8")
        # The cut-off text already cost tokens — `providers.py` carries them
        # on the exception for exactly this. A network death or a revoked key
        # never reaches this branch at all (no reply came back to truncate),
        # so there is nothing dishonest about recording here and nowhere else.
        tin = getattr(e, "input_tokens", 0)
        tout = getattr(e, "output_tokens", 0)
        if tin or tout:
            record_spend(spend_path, providers.cost(
                cfg.provider, cfg.model, tin, tout), now)
        say("failed", why=t("run.failed.truncated", lang, file=src.name))
        print(f"  ❌ {e}")
        print(f"     partial answer saved: {src}")
        return 1
    except judge.Fatal as e:
        say("failed", why=str(e))
        print(f"  ❌ {e}")
        return 1

    # Written before it is read: a judgement costs real money, and a broken
    # answer on disk gets fixed by hand — a lost one does not.
    src = _next_answer_path(recap_dir, stem)
    src.write_text(text, encoding="utf-8")

    usd = providers.cost(cfg.provider, cfg.model, tin, tout)
    # Recorded now, not after `render_file`: the answer is on disk and paid
    # for at this point regardless of whether it turns out to parse.
    record_spend(spend_path, usd, now)
    try:
        # Parsed once, here, and handed to `render_file` — which otherwise
        # re-reads `src` and parses it again on its own. `data` is what the
        # "judged" event below needs too, so this is also the one place that
        # result has to be computed.
        data = extract_json(text)
        out = render_file(src, data=data, embed_shots=True, lang=lang)
    except json.JSONDecodeError as e:
        say("failed", why=t("run.failed.json", lang, why=e.msg,
                            file=src.name))
        print(f"  ❌ the answer is not valid JSON: {e.msg}")
        print(f"     saved anyway: {src}")
        return 1

    counts = data.get("counts") or {}
    discarded = data.get("discarded")
    say("judged", kept=counts.get("kept", 0), of=len(facts["things"]),
        binned=len(discarded) if isinstance(discarded, list) else None,
        sections=len(data.get("categories") or []), usd=usd)
    # `progress.line` already prints "  → {path}" for this event — printing
    # the path again here would just show the same line twice from the CLI.
    say("rendered", path=str(out))

    # The marker moves only now: marking as judged a day whose recap failed
    # would lose it forever. Two more conditions on top of that:
    #
    # - Never today's own file (`f.stem != stem`). `collect()` always writes
    #   into `findings/<today>.json`; a backlog run (`winnow collect --posts
    #   30`, which the CLI documents for exactly this) can still append to it
    #   later the same day. `window.pending_files` only ever returns a day
    #   once — `stem > after`, strictly — so closing today here would hide
    #   that later growth from every recap that follows, forever: entities
    #   paid for and collected, never judged. Today closes itself the first
    #   time a *later* day's recap runs and finds `stem < that day` true.
    # - Only a file that actually parsed (`entered_package`), not `files[-1]`
    #   blindly: a corrupt day is skipped by `load_days`, so `files[-1]`
    #   could be a day the bundle never contained.
    closed = [f for f in entered_package(files) if f.stem != stem]
    if closed:
        window.mark_judged(judged, closed[-1].stem)

    if open_file and sys.stdout.isatty():
        import webbrowser
        webbrowser.open(f"file://{out.resolve()}")
    return 0
