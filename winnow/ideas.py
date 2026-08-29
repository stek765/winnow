"""`winnow ideas` — what the pile would do in one particular life.

The recap answers *is this worth my time*. Everything winnow does up to that
point is about the thing: what it is, whether it exists, whether it is alive.
This module asks the only question the README of a project can never answer —
**what would it change for me** — and it is the reason a saved post was saved
in the first place.

Two decisions hold it up, and both are refusals:

**The draw is random, and the code does the drawing.** A judge asked for "the
best ideas" walks straight back to whatever the profile shouts loudest about,
which is the thing already being worked on — and an idea you already had is
not an idea. Randomness is not a shortcut around ranking, it is the material:
the unlikely pairing is the only thing on this page that can surprise the
person reading it. It also belongs here rather than in the prompt, because a
model asked to "pick some at random" picks the first ones it read.

**The profile tints and does not brief.** Read against a plan, every drawn
thing turns into a compliance check on that plan — measured on a real recap,
where fifteen saved posts were dismissed by quoting the reader's own plan back
at them. The profile is here so an idea can be about a real desk with real
hardware on it, not so the ideas can be marked against a roadmap.
"""
from __future__ import annotations

import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

from winnow import config, harvest, paths, providers
from winnow.budget import Halted, check_brake, record_spend
from winnow.recap import (PROFILE_BUDGET, _next_answer_path, ask_confirm,
                          find_secrets, package_file, prompt_body,
                          resolve_includes)
from winnow.i18n import DEFAULT, t
from winnow.render import extract_json

# Enough that two of them can meet by accident. Smaller than it was, because
# the ask changed: twelve things and one idea meant eleven things drawn, read
# and silently dropped every press — paid for, and never seen again.
DRAW = 8

ANSWER = re.compile(r"^\d{4}-\d{2}-\d{2}\.answer\.md$")


def kept_things(recap_dir: Path) -> list[dict]:
    """Everything winnow ever kept, one entry per thing.

    The archive read as one very wide merge, `harvest.merge` and all: same
    identity rule, so a repo written two ways is one thing here too, and a
    thing kept in four recaps carries all four readings of it.

    Only `*.answer.md` — the model's own words. A merged page is derived from
    them, and counting it would weight whatever happened to be merged.
    """
    answers = []
    for f in sorted(recap_dir.glob("*.answer.md")):
        if not ANSWER.match(f.name):
            continue
        try:
            data = extract_json(f.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            # A recap whose JSON is broken is a page that still opens. It
            # must not take the ideas run down with it.
            continue
        if isinstance(data, dict):
            data.setdefault("week", f.name[:10])
            answers.append(data)
    return harvest.merge(answers)["things"] if answers else []


def remember_drawn(path: Path, names: list[str]) -> None:
    """Add these to the standing record of what has been drawn.

    Written the moment the model has answered and the call is paid for: from
    then on those things *have* been asked about, whatever happens to the page
    afterwards.
    """
    kept = _drawn_names(path)
    kept.update(str(n) for n in names if n)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"names": sorted(kept)}, ensure_ascii=False,
                               indent=2), encoding="utf-8")


def _drawn_names(path: Path | None) -> set[str]:
    """The standing record, or nothing if it has never been written."""
    if path is None:
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    names = data.get("names") if isinstance(data, dict) else None
    return {str(n) for n in names} if isinstance(names, list) else set()


def already_drawn(recap_dir: Path, drawn_path: Path | None = None) -> set[str]:
    """Everything a previous draw already put in front of the model.

    Written down beside the answer, because the answer stopped being able to
    say it: when the model produced a page of ideas plus a list of leftovers,
    the two together *were* the draw. One idea reports one pairing and says
    nothing about the other seven things it read — which would make every
    press draw from the same eight names forever.

    And written down a second time, in `drawn_path`, because the sidecar dies
    with its page: deleting an idea from the archive handed those eight things
    back to the pool as if they had never been asked about. Deleting a page
    means "I do not want to read this again", not "this never happened". The
    pages are still read, so an archive written before the record existed is
    not forgotten.

    Older answers are still read the way they used to be, or an archive
    written before today would look like a draw that never happened.
    """
    out: set[str] = _drawn_names(drawn_path)
    for f in sorted(recap_dir.glob("idee-*.json")):
        try:
            side = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # `drawn` held a *count* for one evening, before it held the names.
        # Iterating that is `TypeError: 'int' object is not iterable`, and it
        # killed the run before it drew anything — a field that changed shape
        # must be read as "whatever is on disk", never as what is written now.
        if isinstance(side, dict) and isinstance(side.get("drawn"), list):
            out.update(str(n) for n in side["drawn"])
    for f in sorted(recap_dir.glob("idee-*.md")):
        try:
            data = extract_json(f.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if not isinstance(data, dict):
            continue
        for idea in as_ideas(data):
            out.update(str(u) for u in (idea.get("uses") or []))
        for gone in data.get("left") or []:
            if isinstance(gone, dict) and gone.get("name"):
                out.add(str(gone["name"]))
    return out


def as_ideas(data: dict) -> list[dict]:
    """The ideas in an answer, however that answer was shaped.

    One object today; a page of them until 2026-08-27. A reader who opens an
    old draw must still see what it said — the file on disk is the artifact,
    and an artifact that stops opening because the ask changed is a promise
    broken after the money was spent.
    """
    if isinstance(data.get("ideas"), list):
        return [i for i in data["ideas"] if isinstance(i, dict)]
    return [data] if data.get("title") or data.get("idea") else []


def draw(things: list[dict], n: int = DRAW, rng=None,
         used: set[str] | None = None) -> list[dict]:
    """The random handful, in random order, freshest first.

    Order matters as much as the choice: handed back alphabetically, the model
    reads the first three hardest, and the first three would be the same every
    single time.

    `used` is what earlier draws already showed. Pure chance over twenty
    things puts most of the same ones in front of the model every run — the
    second draw shares seven of twelve with the first, on average — and a page
    of ideas about things already answered is the one way this feature becomes
    noise. So the never-drawn ones go in first, shuffled among themselves, and
    the rest of the room is filled at random. Not a ranking: nothing here is
    better than anything else, it is only newer to this question.
    """
    rng = rng or random.Random()
    used = used or set()
    fresh = [t for t in things if t["name"] not in used]
    seen = [t for t in things if t["name"] in used]
    rng.shuffle(fresh)
    rng.shuffle(seen)
    return (fresh + seen)[:n]


def render_things(picked: list[dict]) -> str:
    """The drawn things as facts — never as a pitch.

    Same rule as `digest.py`: what was checked, what it said, and who said it.
    The `why` lines are the recap's judgement, kept because they carry what
    the thing looked like from inside this person's week; they are quoted as
    a past reading, not as a conclusion to defend.
    """
    out = []
    for t in picked:
        out.append(f"### {t['name']}")
        what = t.get("title") or t.get("does")
        if what:
            out.append(str(what))
        facts = []
        if t.get("stars") is not None:
            facts.append(f"{t['stars']} stelle")
        if t.get("last_commit"):
            facts.append(f"ultimo commit {t['last_commit']}")
        if t.get("state"):
            facts.append(str(t["state"]))
        if t.get("url"):
            facts.append(str(t["url"]))
        if facts:
            out.append(" · ".join(facts))
        for w in t.get("why") or []:
            out.append(f"tenuta il {w['week']}: {w['text']}")
        out.append("")
    return "\n".join(out)


def build_bundle(prompt: str, profile: str, picked: list[dict],
                 total: int) -> str:
    """Three blocks: the draw, who is reading, the ask.

    No mentality block. `mentality.md` teaches how to weigh a pile, and
    nothing here is being weighed — these things already got through. Handing
    it over anyway would put a filter's instructions in front of a model asked
    to imagine, which is how ideas come back sounding like verdicts.
    """
    return "\n".join([
        "# winnow — ideas",
        "",
        f"Below: {len(picked)} things drawn at random out of the {total} "
        "winnow has kept so far,",
        "who is reading them, and what to produce. In that order.",
        "",
        "---", "",
        f"## 1. The draw ({len(picked)} of {total})", "",
        render_things(picked),
        "---", "",
        "## 2. Who is reading — this tints it, it does not brief it", "",
        profile.strip().replace("\n## ", "\n### ").replace("\n# ", "\n### "),
        "",
        "---", "",
        "## 3. What to produce", "",
        prompt.strip(), ""])


def run_ideas(now: datetime | None = None, n: int = DRAW, open_file: bool = True,
              on_event=None, ask=None, confirm=None, rng=None,
              should_stop=None) -> int:
    """Draw, ask, write the page.

    Deliberately the same sequence as `run_recap`, down to the order of the
    guards: profile first, credentials before the bundle leaves the machine,
    the brake before the money is spent, and the model's words on disk before
    anything tries to parse them. A judgement that costs real money and dies
    in a parser is the one failure this repo has already paid for twice.
    """
    from winnow import judge
    from winnow.api import read_look

    now = now or datetime.now()
    # Read once at the start: a run that changed language half way through
    # would say two things in two tongues about the same job.
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

    recap_dir = paths.recap_dir()
    things = kept_things(recap_dir)
    if len(things) < 4:
        # Four is not a pile. Drawing from it produces a page about whatever
        # happens to be there, and says nothing about the habit.
        say("failed", why=t("run.failed.thin", lang))
        print("  Too little kept so far to draw from: run a recap first.")
        return 0

    profile, missing = resolve_includes(
        profile_path.read_text(encoding="utf-8"), profile_path.parent)
    for m in missing:
        print(f"  ⚠️  the profile points at {m}, which cannot be read.")
    if len(profile) > PROFILE_BUDGET:
        print(f"\n  ⚠️  your profile is {len(profile):,} characters — long "
              "enough to brief\n      the ideas instead of tinting them.\n"
              f"      {profile_path}\n")

    leaks = find_secrets(profile)
    if leaks:
        print(f"\n  ⚠️  {profile_path} holds something that looks like a "
              "credential:\n")
        for hint in leaks[:5]:
            print(f"        {hint}")
        print("\n      The bundle goes straight to the model provider.")
        if not (confirm or ask_confirm)("  Send it anyway? [y/N] "):
            return 1

    drawn_path = paths.drawn_file()
    seen_before = already_drawn(recap_dir, drawn_path)
    picked = draw(things, n, rng, seen_before)
    bundle = build_bundle(prompt_body(package_file("ideas-prompt.md"), lang),
                          profile, picked, len(things))
    say("drawing", drawn=len(picked), of=len(things))

    try:
        cfg = config.load_config(paths.config_file())
    except FileNotFoundError:
        say("failed", why=t("run.failed.config", lang,
                            path=paths.config_file()))
        print(f"  ❌ no config: {paths.config_file()}")
        return 1

    state_dir = paths.state_dir()
    spend_path = state_dir / "spend.json"
    try:
        check_brake(state_dir, spend_path, cfg.limits, now)
    except Halted as e:
        say("failed", why=str(e))
        print(f"  ❌ {e}")
        return 1

    recap_dir.mkdir(parents=True, exist_ok=True)
    stem = f"idee-{now.date().isoformat()}"
    try:
        text, tin, tout = (ask or judge.ask)(
            bundle, cfg.provider, cfg.model, cfg.base_url, on_event=on_event,
            should_stop=should_stop)
    except judge.Stopped as e:
        # Not a failure: nobody broke anything, they changed their mind. It
        # must not print like an error, and it must not cost anything —
        # `judge.ask` only raises this before a call or between two.
        say("stopped", why=str(e))
        print(f"  {e}")
        return 0
    except providers.Truncated as e:
        src = _next_answer_path(recap_dir, stem)
        src.write_text(getattr(e, "partial", "") or "", encoding="utf-8")
        tin, tout = getattr(e, "input_tokens", 0), getattr(e, "output_tokens", 0)
        if tin or tout:
            record_spend(spend_path, providers.cost(
                cfg.provider, cfg.model, tin, tout), now)
        say("failed", why=t("run.failed.truncated", lang, file=src.name))
        print(f"  ❌ {e}\n     partial answer saved: {src}")
        return 1
    except judge.Fatal as e:
        say("failed", why=str(e))
        print(f"  ❌ {e}")
        return 1

    src = _next_answer_path(recap_dir, stem)
    src.write_text(text, encoding="utf-8")
    usd = providers.cost(cfg.provider, cfg.model, tin, tout)
    record_spend(spend_path, usd, now)
    # Here and not beside the sidecar: the model has read these and the call
    # is paid for, so the draw happened even if the answer turns out to be
    # unparseable below.
    # The union, not just this handful: the record catches up with whatever
    # the pages already knew, so an idea deleted after today takes nothing
    # with it — including the draws made before this record existed.
    remember_drawn(drawn_path,
                   sorted(seen_before | {t["name"] for t in picked}))

    try:
        data = extract_json(text)
    except json.JSONDecodeError as e:
        say("failed", why=t("run.failed.json", lang, why=e.msg,
                            file=src.name))
        print(f"  ❌ the answer is not valid JSON: {e.msg}")
        print(f"     saved anyway: {src}")
        return 1

    out = src.with_suffix(".html")
    out.write_text(render_ideas(data, picked, len(things), usd, lang),
                   encoding="utf-8")
    # What it cost, beside it. The model cannot report this — it does not know
    # what it was charged — so unlike a recap's `counts.usd` it has to be
    # written down here, or the archive row is the only one in the stack with
    # no price on it.
    first = (as_ideas(data) or [{}])[0]
    src.with_suffix(".json").write_text(json.dumps(
        {"usd": round(usd, 4), "of": len(things),
         # The names, not the count. One of the two places the next draw
         # reads — the other, `state/drawn.json`, is the one that survives
         # this page being deleted.
         "drawn": [t["name"] for t in picked],
         "title": first.get("title") or "", "gist": first.get("gist") or "",
         "difficulty": first.get("difficulty") or "",
         "time": first.get("time") or ""}, ensure_ascii=False),
        encoding="utf-8")
    say("dreamt", ideas=len(as_ideas(data)), of=len(picked), usd=usd)
    say("rendered", path=str(out))

    if open_file and sys.stdout.isatty():
        import webbrowser
        webbrowser.open(f"file://{out.resolve()}")
    return 0


# --- the page ---------------------------------------------------------------

def say_difficulty(value: str, lang: str = DEFAULT) -> str:
    """`facile` as the reader reads it.

    The three the prompt allows are keys — they are what colours the chip, so
    they stay put whatever language the answer is in, exactly like a verdict.
    Anything else the model wrote is printed as it came.
    """
    v = (value or "").strip()
    if not v:
        return ""
    key = f"difficulty.{v}"
    said = t(key, lang)
    return v if said == key else said


def render_ideas(data: dict, picked: list[dict], total: int,
                 usd: float = 0.0, lang: str = DEFAULT) -> str:
    """The ideas as a page.

    Its own look, on purpose. A recap page is an argument about what got
    through and it is printed like a ledger; this is speculation, and it has
    to *read* as speculation or every line on it will be taken for advice.
    Hence one idea per row, wide, with the doubt printed under it in the same
    type as the idea — never smaller, which is how a caveat becomes a
    disclaimer nobody reads.
    """
    from winnow.render import _esc, painting_data_uri

    ideas = as_ideas(data)
    rows = []
    for i, idea in enumerate(ideas, 1):
        uses = "".join(f'<span class="tag">{_esc(u)}</span>'
                       for u in (idea.get("uses") or []))
        # Difficulty and time sit beside the gist, not at the bottom: they are
        # what decides whether the rest gets read at all.
        meta = "".join(
            f'<span class="m"><i>{_esc(k)}</i>{_esc(v)}</span>'
            for k, v in ((t("idea.difficulty", lang),
                          say_difficulty(idea.get("difficulty"), lang)),
                         (t("idea.time", lang),
                          idea.get("time") or "")) if v)
        step = idea.get("first_step") or ""
        shaky = idea.get("shaky") or ""
        gist = idea.get("gist") or ""
        rows.append(
            f'<article class="idea"><div class="n">{i:02d}</div>'
            f'<div class="body"><h2>{_esc(idea.get("title") or "")}</h2>'
            + (f'<div class="tags">{uses}</div>' if uses else "")
            + (f'<p class="gist">{_esc(gist)}</p>' if gist else "")
            + (f'<div class="meta">{meta}</div>' if meta else "")
            + f'<p class="txt">{_esc(idea.get("idea") or "")}</p>'
            + (f'<p class="step"><span>{t("idea.one_evening", lang)}</span>'
               f'{_esc(step)}</p>' if step else "")
            + (f'<p class="shaky"><span>{t("idea.but", lang)}</span>'
               f'{_esc(shaky)}</p>' if shaky else "")
            + "</div></article>")

    left = [l for l in (data.get("left") or []) if isinstance(l, dict)]
    tail = ""
    if left:
        tail = (f'<h3>{t("idea.nothing_came", lang)}</h3><ul class="left">'
                + "".join(
            f'<li><b>{_esc(l.get("name") or "")}</b> {_esc(l.get("why") or "")}'
            "</li>" for l in left) + "</ul>")

    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(t("idea.title", lang))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Familjen+Grotesk:wght@400;600;700&family=Instrument+Sans:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{{--glass:#e9eced;--lit:#fbfcfc;--ink:#10141a;--soft:#4d565f;--faint:#8b949c;
--rule:#d7dcde;--grease:#ce3a24;--display:"Familjen Grotesk","Helvetica Neue",Arial,sans-serif;
--body:"Instrument Sans",-apple-system,sans-serif;--mono:"JetBrains Mono",ui-monospace,monospace;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--glass);color:var(--ink);font-family:var(--body);
-webkit-font-smoothing:antialiased}}
.veil{{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}}
.art{{position:absolute;inset:-6%;
background:url("{painting_data_uri()}") no-repeat 88% 46%/auto 112%;
opacity:.14;filter:saturate(.7) contrast(1.04);
-webkit-mask-image:radial-gradient(50% 78% at 82% 50%,#000 0%,rgba(0,0,0,.6) 46%,transparent 78%);
mask-image:radial-gradient(50% 78% at 82% 50%,#000 0%,rgba(0,0,0,.6) 46%,transparent 78%)}}
.wrap{{position:relative;z-index:1;max-width:52rem;margin:0 auto;
padding:clamp(2rem,5vw,3.5rem) clamp(1.2rem,4vw,3rem) 6rem}}
h1{{font-family:var(--display);font-weight:700;letter-spacing:-.03em;
font-size:clamp(2rem,5vw,2.9rem);margin:0 0 .5rem;line-height:1.05}}
.lede{{font-size:1.02rem;color:var(--soft);line-height:1.5;margin:0 0 .8rem;
max-width:38rem}}
.sub{{font-family:var(--mono);font-size:.74rem;letter-spacing:.1em;
color:var(--faint);margin:0 0 3rem}}
.idea{{display:flex;gap:1.1rem;background:var(--lit);border:1px solid var(--rule);
border-radius:4px;padding:1.3rem 1.4rem;margin:0 0 .9rem}}
.n{{font-family:var(--mono);font-size:.72rem;color:var(--grease);padding-top:.35rem}}
.body{{flex:1;min-width:0}}
h2{{font-family:var(--display);font-size:1.24rem;letter-spacing:-.02em;
margin:0 0 .55rem;line-height:1.2}}
.tags{{display:flex;flex-wrap:wrap;gap:.35rem;margin:0 0 .7rem}}
.tag{{font-family:var(--mono);font-size:.62rem;letter-spacing:.06em;
color:var(--soft);background:var(--glass);border-radius:3px;padding:.2rem .45rem}}
.txt{{margin:0;font-size:.95rem;line-height:1.55}}
.step,.shaky{{margin:.85rem 0 0;font-size:.95rem;line-height:1.5;
padding-left:.85rem;border-left:2px solid var(--rule)}}
.step{{border-color:var(--grease)}}
.step span,.shaky span{{display:block;font-family:var(--mono);font-size:.6rem;
letter-spacing:.14em;text-transform:uppercase;color:var(--faint);
margin-bottom:.15rem}}
.shaky{{color:var(--soft)}}
h3{{font-family:var(--mono);font-size:.68rem;letter-spacing:.18em;
text-transform:uppercase;color:var(--faint);margin:3rem 0 .9rem;
padding-bottom:.6rem;border-bottom:1px solid var(--rule)}}
.left{{list-style:none;margin:0;padding:0;font-size:.9rem;color:var(--soft)}}
.left li{{padding:.42rem 0;line-height:1.45}}
.left b{{font-family:var(--display);color:var(--ink);margin-right:.4rem}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style></head><body>
<div class="veil" aria-hidden="true"><div class="art"></div></div>
<div class="wrap">
<h1>{_esc(ideas[0].get("title")) if len(ideas) == 1
     else _esc(t("idea.heading", lang))}</h1>
<p class="lede">{_esc(data.get("note") or (ideas[0].get("gist") if len(ideas) == 1 else ""))}</p>
<p class="sub">{t("idea.counts_one" if len(ideas) == 1 else "idea.counts",
   lang, drawn=len(picked), total=total, n=len(ideas), usd=f"{usd:.2f}")}</p>
{"".join(rows)}
{tail}
</div></body></html>
"""
