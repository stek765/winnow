"""The local API: the only thing the window is allowed to talk to.

The window never reads `findings/`, never writes `config.toml`, never decides
which face the home screen wears. It asks here and renders what comes back.

That rule is what makes the shell replaceable. A browser tab today and a Tauri
window tomorrow are the same client of the same server; if the window knew
where the files live, swapping it would mean rewriting that knowledge too.

Routing is a plain function over `(method, path, payload, jobs)` returning
`(status, body)`, so every rule below is provable without opening a socket —
the same reason `progress.line` was split out from the runs that emit events.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from winnow import appstate, paths
from winnow.i18n import t
from winnow.progress import line

# One run at a time. Two recaps in flight would pay twice and race on the same
# "how far have I judged" marker; two collections would race on seen.json.
# Looked up per request, so it answers in the window's language.
def busy_message() -> str:
    return t("err.busy", lang())


class Jobs:
    """What is running, and what it has said so far.

    In memory on purpose: a job that does not survive a restart is correct
    here, because the window dies with the server it started.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, kind: str) -> str:
        jid = secrets.token_hex(8)
        with self._lock:
            self._jobs[jid] = {"id": jid, "kind": kind, "events": [],
                               "done": False, "code": None, "error": None,
                               "stopping": False, "result": None,
                               "started": datetime.now().isoformat(timespec="seconds")}
        return jid

    def event(self, jid: str, kind: str, data: dict) -> None:
        job = self._jobs.get(jid)
        if job is None:
            return
        with self._lock:
            # The sentence travels with the event: the window renders it, and
            # never assembles one from the raw fields. One wording, one place.
            job["events"].append({"kind": kind, "data": data,
                                  "line": line(kind, data).strip()})

    def finish(self, jid: str, code: int, error: str | None = None,
               result: dict | None = None) -> None:
        """A run can end with data and not only with a line of text.

        The folder scan comes back with a list the window has to draw as
        checkboxes, and a progress sentence cannot be turned back into one.
        """
        job = self._jobs.get(jid)
        if job is None:
            return
        with self._lock:
            job.update(done=True, code=code, error=error, result=result)

    def get(self, jid: str) -> dict | None:
        return self._jobs.get(jid)

    def current(self) -> dict | None:
        for job in self._jobs.values():
            if not job["done"]:
                return job
        return None

    def stop(self, jid: str) -> bool:
        job = self._jobs.get(jid)
        if job is None or job["done"]:
            return False
        with self._lock:
            job["stopping"] = True
        return True


def lang() -> str:
    """The language the window is in. Read per request rather than cached: it
    changes while the app is open, and a cached copy would answer in the old
    one until a restart."""
    return read_look()["lang"]


def _facts(jobs: Jobs) -> dict:
    running = jobs.current()
    return appstate.read_facts(
        state_dir=paths.state_dir(), findings_dir=paths.findings_dir(),
        judged=paths.judged_file(), browser_profile=paths.browser_profile(),
        running={"kind": running["kind"],
                 "done": len(running["events"]), "of": 0} if running else None)


# Pages written before the slides were embedded carry `../state/shots/NAME.png`,
# which from `/recap/x.html` asks for this. New pages carry the image inside
# them and never come here.
SHOTS_PREFIX = "/state/shots/"


def shot_path(path: str) -> Path | None:
    """The slide a page is asking for, or None if it is asking for anything
    else. The name comes from a URL, so it is a name and not a path."""
    if not path.startswith(SHOTS_PREFIX):
        return None
    name = Path(path[len(SHOTS_PREFIX):]).name
    if not name or Path(name).suffix.lower() != ".png":
        return None
    f = paths.state_dir() / "shots" / name
    return f if f.is_file() else None


GROUNDS = ("chiaro", "penombra", "scuro")
ACCENTS = ("terracotta", "rosso", "arancione", "giallo", "verde", "blu",
           "viola", "rosa", "grafite")


def read_look() -> dict:
    """The chosen ground, accent and language, or the defaults.

    Validated on the way out, not only on the way in: a hand-edited file must
    not be able to put an arbitrary string into an HTML attribute.
    """
    from winnow.i18n import DEFAULT, LANGS

    out = {"ground": "chiaro", "accent": "terracotta", "lang": DEFAULT}
    f = paths.look_file()
    if f.is_file():
        try:
            saved = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return out
        if isinstance(saved, dict):
            if saved.get("ground") in GROUNDS:
                out["ground"] = saved["ground"]
            if saved.get("accent") in ACCENTS:
                out["accent"] = saved["accent"]
            if saved.get("lang") in LANGS:
                out["lang"] = saved["lang"]
    return out


def write_look(payload: dict) -> None:
    """Only these three names, only from their lists. Whatever else arrives is
    dropped rather than refused: a colour is not worth an error screen."""
    from winnow.i18n import LANGS

    look = read_look()
    if payload.get("ground") in GROUNDS:
        look["ground"] = payload["ground"]
    if payload.get("accent") in ACCENTS:
        look["accent"] = payload["accent"]
    if payload.get("lang") in LANGS:
        look["lang"] = payload["lang"]
    f = paths.look_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(look), encoding="utf-8")


def _keys_present() -> dict:
    """Which providers have a key on disk. Booleans, never values."""
    from winnow.providers import KEY_ENV
    from winnow.setup import load_env_file

    try:
        env = load_env_file(paths.env_file())
    except OSError:
        env = {}
    return {provider: bool((env.get(name) or "").strip())
            for provider, name in KEY_ENV.items()}


def _config_dict() -> dict:
    from winnow.config import load_config
    cfg = load_config(paths.config_file())
    from winnow.providers import needs_key

    return {"model": cfg.model, "provider": cfg.provider,
            "base_url": cfg.base_url,
            # Said beside the model that needs it, which is the one place a
            # missing key is actionable rather than a puzzle.
            "key_ready": (not needs_key(cfg.provider)
                          or _keys_present().get(cfg.provider, False)),
            "posts_per_run": cfg.limits.posts_per_run,
            "warn_eur_week": cfg.limits.warn_eur_week,
            "halt_eur_week": cfg.limits.halt_eur_week,
            "folders": [{"name": f.name, "active": f.active}
                        for f in cfg.folders]}


def _write_config(patch: dict) -> dict:
    """Validate, write, and answer with the config as it now is.

    One round trip, not two: a window that has to ask again after saving
    shows the old values for as long as the second request takes, which reads
    as a change that did not take.
    """
    from winnow.setup import apply_config_patch

    path = paths.config_file()
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    # Nothing is written until the whole patch has been accepted, so a refusal
    # can never leave half a change on disk.
    new = apply_config_patch(text, patch)
    if new != text:
        path.write_text(new, encoding="utf-8")
        path.chmod(0o600)
    raw = _config_dict()
    return {k: raw[k] for k in CONFIG_PUBLIC if k in raw}


# Never handed to the window, however the config grows. An allow-list and not
# a deny-list: a key added later must not leak because nobody updated a filter.
CONFIG_PUBLIC = ("model", "provider", "base_url", "posts_per_run",
                 "warn_eur_week", "halt_eur_week", "key_ready", "folders")


# The archive is the weeks winnow judged. A page dropped into that folder by
# hand — a demo, an export — is not one of them, and listing it beside them
# says it is.
# `-2`, `-3`… because `_next_answer_path` never overwrites an earlier answer:
# a second recap on the same day — and a day whose first attempt failed leaves
# a file behind — writes beside it. Without the suffix here the page opened
# fine and simply was not in the archive, which is the same as lost. The ideas
# pattern below has always allowed it.
WEEK_PAGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.answer(?:-\d+)?\.html$")
WEEK_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# The names a person gave to pages, keyed by the file they belong to. One
# small file rather than a field inside each answer: the answers are the
# model's own words, written once and never edited afterwards.
def read_titles() -> dict:
    f = paths.recap_dir() / "titles.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v)[:60] for k, v in data.items()
            } if isinstance(data, dict) else {}


def write_titles(titles: dict) -> None:
    f = paths.recap_dir() / "titles.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(titles, ensure_ascii=False), encoding="utf-8")


def _verdict(answer: Path) -> dict:
    """What that week decided, read back from the reply that produced it.

    A file size is a fact about a disk, not about a week: it gives a reader no
    way to tell one entry from another. The ratio does — it is the product.
    """
    blank = {"kept": None, "things": None, "posts": None, "usd": None,
             "comment": ""}
    if not answer.is_file():
        # The page is the product; this JSON is bookkeeping. Losing it must
        # not hide a recap that opens perfectly well.
        return blank
    try:
        from winnow.render import extract_json
        data = extract_json(answer.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return blank
    if not isinstance(data, dict):
        return blank
    counts = data.get("counts") or {}
    discarded = data.get("discarded")
    if isinstance(discarded, list):
        discarded = len(discarded)
    kept = counts.get("kept")
    return {
        "kept": kept,
        "things": (kept + discarded)
        if isinstance(kept, int) and isinstance(discarded, int) else None,
        "posts": counts.get("posts"), "usd": counts.get("usd"),
        "comment": data.get("comment") or "",
    }


# `_` too: merges made before the id became a hash are named after the days
# they join — `unione-2026-08-23_2026-08-24.html` — and a pattern that only
# knew the new shape left them on disk and out of the archive, which is the
# same failure the `.answer-3` pages had.
MERGE_PAGE = re.compile(r"^unione-[a-z0-9_-]+\.html$")
# `idee-2026-08-27.answer.html`, and `-2` for a second draw the same day.
IDEAS_PAGE = re.compile(r"^idee-(\d{4}-\d{2}-\d{2})\.answer(-\d+)?\.html$")


def extract_json_file(answer: Path) -> dict:
    """The JSON a model answered with, from the file it was written to."""
    from winnow.render import extract_json
    data = extract_json(answer.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def _drawn(answer: Path) -> dict:
    """How many ideas came out, read back from the reply that produced them.

    Same reason `_verdict` exists: a file size tells a reader nothing, and the
    row has to say what makes this draw different from the last one.
    """
    # What the row needs is beside the answer, not inside it: the model does
    # not know what it was charged, and a title read out of the JSON would
    # mean parsing a 40 KB reply to draw one line of a list.
    meta = {}
    side = answer.with_suffix(".json")
    if side.is_file():
        try:
            meta = json.loads(side.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            meta = {}
    card = {"usd": meta.get("usd"), "title": meta.get("title") or "",
            "gist": meta.get("gist") or "",
            "difficulty": meta.get("difficulty") or "",
            "time": meta.get("time") or ""}
    if not answer.is_file():
        return {"ideas": None, "note": "", **card}
    try:
        from winnow.render import extract_json
        data = extract_json(answer.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {"ideas": None, "note": "", **card}
    if not isinstance(data, dict):
        return {"ideas": None, "note": "", **card}
    from winnow.ideas import as_ideas
    found = as_ideas(data)
    first = found[0] if found else {}
    # An answer written before the side file existed still has to draw a row.
    return {"ideas": len(found), "note": data.get("note") or "",
            **{**card,
               "title": card["title"] or first.get("title") or "",
               "gist": card["gist"] or first.get("gist") or "",
               "difficulty": card["difficulty"] or first.get("difficulty") or "",
               "time": card["time"] or first.get("time") or ""}}


def _archive() -> list[dict]:
    """Everything ever produced, newest first — weeks and merges in one list.

    Kept in two lists, a merge made today sat below a week judged in January,
    and the question a reader actually has — *what did I do last?* — had no
    answer on the screen. They are different kinds of thing, so each row says
    which it is and the window can filter; but the order is the order things
    happened, because that is what a history is.

    A week is placed by when its **page was written**, not by the week it
    covers: a recap of an old backlog produced today is something done today.
    """
    from winnow.harvest import NAME_DAYS, label_for

    out = []
    d = paths.recap_dir()
    if not d.is_dir():
        return out
    titles = read_titles()

    # The glob has to be as wide as the pattern, or the pattern is decorative:
    # `*.answer.html` cannot see `…answer-3.html`, which is where a second
    # recap of the same day lands.
    for f in d.glob("*.html"):
        m = WEEK_PAGE.match(f.name)
        if not m:
            continue
        week = m.group(1)
        # From the page's own stem, not rebuilt from the date: `-3.html` is
        # answered by `-3.md`, and guessing would read the wrong judgement.
        out.append({"kind": "week", "week": week, "file": f.name,
                    "made": f.stat().st_mtime, "named": titles.get(f.name, ""),
                    **_verdict(d / (f.stem + ".md"))})

    for f in d.glob("idee-*.html"):
        m = IDEAS_PAGE.match(f.name)
        if not m:
            continue
        out.append({"kind": "ideas", "week": "", "file": f.name,
                    "label": "Idee", "day": m.group(1),
                    # `title` on a draw is the model's own name for the idea.
                    # A name given by hand is a different thing and cannot
                    # overwrite it — it is what the reader called this page.
                    "named": titles.get(f.name, ""),
                    "made": f.stat().st_mtime,
                    **_drawn(d / (f.stem + ".md"))})

    for f in d.glob("unione-*.html"):
        if not MERGE_PAGE.match(f.name):
            continue
        side = d / (f.stem + ".json")
        info = {}
        if side.is_file():
            try:
                info = json.loads(side.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                info = {}
        # Rebuilt, not read back: a label written once is stuck in the
        # language the window was in that day, and it is stuck in whatever
        # wording shipped that day — the merge of 23, 24 and 28 August kept
        # calling itself «from August 23 to August 28» long after that phrase
        # was found to read as a period. The days are the fact; the sentence
        # about them is not.
        weeks = info.get("weeks") or []
        name = info.get("name") or ""
        label = (label_for(weeks, name, lang())
                 if weeks else (info.get("label") or f.stem))
        # Whether the label already *is* the list of days. Without it the row
        # printed «August 23, 24 and 28» and, directly underneath, «23 agosto
        # · 24 agosto · 28 agosto» — the same fact twice. Decided here because
        # the rule that decides it (NAME_DAYS) lives here.
        lists_days = bool(weeks) and not name and len(set(weeks)) <= NAME_DAYS
        out.append({"kind": "merge", "file": f.name, "week": "",
                    "named": titles.get(f.name, ""),
                    "label": label,
                    "weeks": weeks, "lists_days": lists_days,
                    "things": info.get("things"),
                    "made": f.stat().st_mtime})

    out.sort(key=lambda i: i["made"], reverse=True)
    return out


def route(method: str, path: str, payload: dict, jobs: Jobs,
          spawn=None) -> tuple[int, dict]:
    """One request in, one `(status, body)` out. No sockets, no globals."""
    if path == "/api/state":
        if method != "GET":
            return 405, {"error": "GET only"}
        # The running job's id travels with the state, so the window can stop
        # a run it did not start. The daily one comes from the scheduler and
        # this window has never heard of it — «Ferma» used to post to
        # `/api/stop`, which is not a route, and did nothing at all.
        now = jobs.current()
        return 200, {**appstate.home(_facts(jobs), lang=lang()),
                     "running_id": now["id"] if now else None}

    if path == "/api/recaps":
        if method != "GET":
            return 405, {"error": "GET only"}
        return 200, {"items": _archive()}

    if path == "/api/models":
        if method != "GET":
            return 405, {"error": "GET only"}
        # The menu comes from the same list `winnow init` reads. Written out
        # again in the page it would be in two places, and the copy in
        # JavaScript is the one nobody updates.
        from winnow.providers import CHOICES
        return 200, {"models": [{"label": c.label, "provider": c.provider,
                                 "model": c.model, "hint": c.hint,
                                 "hint_it": c.hint_it}
                                for c in CHOICES]}

    if path == "/api/keys":
        # A key is write-only over this API. The window has to know *whether*
        # one exists — a provider without its key is a run that dies at the
        # first post — but it has no reason to be able to read it back, and a
        # value that never travels cannot be caught travelling.
        from winnow.providers import KEY_ENV
        from winnow.setup import load_env_file, write_key

        if method == "POST":
            provider = payload.get("provider")
            if provider not in KEY_ENV:
                # A model on your own machine has no account and no bill.
                return 400, {"error": t("err.no_key_needed", lang(), provider=provider)}
            key = (payload.get("key") or "").strip()
            if not key:
                # Written through, it looks set and fails at the next run —
                # which is the exact failure this endpoint exists to stop.
                return 400, {"error": t("err.empty_key", lang())}
            write_key(paths.env_file(), KEY_ENV[provider], key)
        elif method != "GET":
            return 405, {"error": "GET or POST"}
        return 200, {"keys": _keys_present()}

    if path == "/api/look":
        # The window's colours have to survive a restart, and `localStorage`
        # cannot carry them: the engine binds port 0, so every launch is a
        # different origin and the browser hands back an empty store. Kept on
        # disk, and only ever read by the window.
        if method == "PATCH":
            was = read_look()["lang"]
            write_look(payload)
            now = read_look()["lang"]
            if now != was:
                # Every page already on disk, relabelled. The judgement inside
                # them is the model's words and is not touched — only what
                # winnow writes around it, which is not part of what was
                # decided. Without this, a reader who switches to English
                # opens yesterday's recap and finds «Perché passa» on it with
                # no way to do anything about it but make a new one.
                from winnow.relabel import rebuild_all
                done, failed = rebuild_all(paths.recap_dir(), now)
                return 200, {**read_look(), "relabelled": done,
                             "not_relabelled": failed}
        elif method != "GET":
            return 405, {"error": "GET or PATCH"}
        return 200, read_look()

    if path == "/api/profile":
        if method != "GET":
            return 405, {"error": "GET only"}
        prof = paths.profile_file()
        try:
            chars = len(prof.read_text(encoding="utf-8")) if prof.is_file() else 0
        except OSError:
            chars = 0
        # Size and path, never the text. It is the most personal file winnow
        # touches, and the window has no reason to hold a copy of it.
        # `short` is the same path with the home folder written the way a
        # person writes it: the settings row shows where the file *is*, and
        # `/Users/<name>/.config/...` is mostly a repetition of who is logged
        # in — the part that identifies the file is the tail.
        home = str(Path.home())
        short = str(prof)
        if short.startswith(home + "/"):
            short = "~" + short[len(home):]
        return 200, {"exists": prof.is_file(), "chars": chars,
                     "path": str(prof), "short": short}

    if path.startswith("/api/console"):
        # Opening the provider's key page in a real browser. The window cannot
        # do it itself: a webview navigating away would replace the app.
        if method != "POST":
            return 405, {"error": "POST only"}
        from winnow.providers import CONSOLE
        from winnow.setup import open_url
        which = path.partition("?p=")[2]
        if which not in CONSOLE:
            return 400, {"error": t("err.no_console", lang(), provider=which)}
        open_url(CONSOLE[which])
        return 200, {"opened": True}

    if path == "/api/open":
        # A link inside a recap. In a real browser tab `target="_blank"` is
        # enough; inside the app's webview nothing happens at all — no popup,
        # no error, a link that simply does not work. The window intercepts
        # the click and asks the engine, which owns the real browser.
        if method != "POST":
            return 405, {"error": "POST only"}
        url = str(payload.get("url") or "")
        # Only the two schemes a recap ever carries. `file:` and `javascript:`
        # are how "open a link" turns into "run whatever the page says".
        if not url.startswith(("http://", "https://")):
            return 400, {"error": t("err.bad_url", lang())}
        from winnow.setup import open_url
        open_url(url)
        return 200, {"opened": True}

    if path == "/api/profile/open":
        if method != "POST":
            return 405, {"error": "POST only"}
        from winnow.setup import open_in_editor
        open_in_editor(paths.profile_file())
        return 200, {"opened": True}

    if path == "/api/schedule":
        from winnow import schedule

        if method == "PATCH":
            busy = jobs.current()
            if busy:
                # Moving the hour reinstalls the job. Doing that under a run
                # started by the old one is asking for two of them.
                return 409, {"error": busy_message(), "running": busy["id"],
                             "kind": busy["kind"]}
            try:
                if payload.get("off"):
                    schedule.remove()
                else:
                    hour, minute = schedule.parse_time(payload.get("at") or "")
                    schedule.install(hour, minute)
            except ValueError as exc:
                return 400, {"error": str(exc)}
        elif method != "GET":
            return 405, {"error": "GET or PATCH"}
        # Read back from disk either way: what got installed is the answer,
        # not what was asked for.
        now = schedule.current()
        return 200, {"active": now.active, "when": now.when, "how": now.how}

    if path == "/api/config":
        if method == "PATCH":
            busy = jobs.current()
            if busy:
                # A collection reads the folder list and the post cap as it
                # goes: changing them underneath produces a run that half
                # obeyed two configurations, and no way to tell afterwards.
                return 409, {"error": busy_message(), "running": busy["id"],
                             "kind": busy["kind"]}
            try:
                return 200, _write_config(payload)
            except FileNotFoundError:
                return 404, {"error": "no config yet — run the setup"}
            except ValueError as exc:
                # The sentence `apply_config_patch` raised, verbatim: it was
                # written to be read by whoever pressed the button.
                return 400, {"error": str(exc)}
        if method != "GET":
            return 405, {"error": "GET or PATCH"}
        try:
            raw = _config_dict()
        except FileNotFoundError:
            return 404, {"error": "no config yet — run the setup"}
        return 200, {k: raw[k] for k in CONFIG_PUBLIC if k in raw}

    if path == "/api/merge":
        if method != "POST":
            return 405, {"error": "POST only"}
        from winnow.harvest import label_for, merge, merge_id, render_harvest
        from winnow.render import extract_json

        # Pages, not dates. A day can hold two recaps — the first attempt of
        # 28 August ran out of tokens and the second is the real one — so
        # asking for «2026-08-28» is ambiguous, and the ambiguity was silent:
        # it read whichever file happened to be called `{day}.answer.md`,
        # which is the failed one. Dates are still accepted so a merge can be
        # asked for from a script, where one recap a day is the normal case.
        d = paths.recap_dir()
        files = [f for f in (payload.get("files") or [])
                 if isinstance(f, str) and WEEK_PAGE.match(Path(f).name)]
        if not files:
            files = [f"{w}.answer.html" for w in (payload.get("weeks") or [])
                     if isinstance(w, str) and WEEK_RE.match(w)]
        files = sorted({Path(f).name for f in files})
        if len(files) < 2:
            return 400, {"error": t("err.two_recaps", lang())}
        # Optional, and the only thing that makes ten scattered weeks
        # findable a month later.
        name = " ".join(str(payload.get("name") or "").split())[:60]

        answers, weeks, missing = [], [], []
        for page in files:
            week = WEEK_PAGE.match(page).group(1)
            side = d / (page[:-len(".html")] + ".md")
            try:
                answers.append(extract_json(side.read_text(encoding="utf-8")))
                weeks.append(week)
            except Exception:                              # noqa: BLE001
                # The page can be reopened without its answer, but it cannot
                # be merged: the answer *is* the content. Producing a page
                # quietly missing half of what was asked for is the failure
                # this repo keeps paying for.
                missing.append(week)
        if missing:
            return 400, {"error": t("err.missing_judgement", lang(),
                                    days=", ".join(missing))}

        merged = merge(answers)
        label = label_for(weeks, name, lang())
        # Seeded from the pages: two different recaps of one day are two
        # different merges, and a seed made of dates would give them one file.
        stem = merge_id(files, name)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{stem}.html").write_text(
            render_harvest(merged, label, lang()), encoding="utf-8")
        (d / f"{stem}.json").write_text(json.dumps(
            {"weeks": sorted(set(weeks)), "files": files, "label": label,
             "name": name, "things": merged["counts"]["things"],
             "made": datetime.now().isoformat(timespec="seconds")},
            ensure_ascii=False), encoding="utf-8")
        return 200, {"file": f"{stem}.html", "label": label,
                     "things": merged["counts"]["things"]}

    if path.startswith("/api/draw/"):
        # The ideas as data, so the window can lay them out itself. The page
        # on disk stays the artifact — it gets mailed and moved — but a
        # judgement worth reading twice should not be read through an iframe.
        if method != "GET":
            return 405, {"error": "GET only"}
        name = Path(path[len("/api/draw/"):]).name
        if not IDEAS_PAGE.match(name):
            return 404, {"error": t("err.no_such_page", lang())}
        d = paths.recap_dir()
        answer = d / (name[:-len(".html")] + ".md")
        try:
            data = extract_json_file(answer)
        except Exception:                                  # noqa: BLE001
            # The page opens perfectly well on its own; only this view of it
            # is missing. Saying "non esiste" would be a lie about the file.
            return 409, {"error": t("err.not_readable", lang())}
        from winnow.ideas import as_ideas
        return 200, {**_drawn(answer), "note": data.get("note") or "",
                     "ideas_list": as_ideas(data),
                     "left": data.get("left") or []}

    if path.startswith("/api/name/"):
        # A title, not a filename. Renaming the file would break every link
        # already written into a page, and the date in the name is what makes
        # the folder readable from a terminal — so the name is stored beside
        # it and the date never stops being shown.
        if method != "PATCH":
            return 405, {"error": "PATCH only"}
        page = Path(path[len("/api/name/"):]).name
        d = paths.recap_dir()
        if not page or not (d / page).is_file() or not page.endswith(".html"):
            return 404, {"error": t("err.no_such_page", lang())}
        titles = read_titles()
        title = " ".join(str(payload.get("title") or "").split())[:60]
        if title:
            titles[page] = title
        else:
            titles.pop(page, None)          # emptied: back to its date
        write_titles(titles)
        return 200, {"file": page, "title": title}

    if path.startswith("/api/recaps/"):
        if method != "DELETE":
            return 405, {"error": "DELETE only"}
        # The name arrives in a URL: `..` in it must not become a path.
        name = Path(path[len("/api/recaps/"):]).name
        d = paths.recap_dir()
        target = d / name
        if not name or not target.is_file() or target.suffix != ".html":
            return 404, {"error": t("err.no_such_page", lang())}
        # The page and the judgement that produced it go together. Leaving the
        # answer behind is half a delete, and the half that stays is the one
        # holding the reading.
        titles = read_titles()
        if titles.pop(name, None) is not None:
            write_titles(titles)
        # Exactly this page and the files that belong to it, named one by one.
        # A glob built by stripping «.answer» from the stem was two bugs in
        # one line: `2026-08-28.answer-3` became `2026-08-28-3`, which matches
        # nothing — so deleting a second recap of a day silently did nothing —
        # while `2026-08-28.answer` became `2026-08-28`, which matches every
        # *other* recap of that day and would have taken their judgements with
        # it. A delete has to be exact or it must not be a delete.
        removed = []
        for f in (target, d / (target.stem + ".md"),
                  d / (target.stem + ".json")):
            if f.is_file():
                f.unlink()
                removed.append(f.name)
        return 200, {"removed": removed}

    if path in ("/api/collect", "/api/recap", "/api/ideas",
                "/api/folders/scan"):
        if method != "POST":
            return 405, {"error": "POST only"}
        busy = jobs.current()
        if busy:
            return 409, {"error": busy_message(), "running": busy["id"],
                         "kind": busy["kind"]}
        # A scan drives the same browser session a collection does; two of
        # them at once is one Playwright profile with two drivers.
        kind = "folders" if path.endswith("/scan") else path.rsplit("/", 1)[1]
        jid = jobs.start(kind)
        if spawn:
            spawn(kind, jid, jobs)
        return 202, {"id": jid, "kind": kind}

    if path.startswith("/api/jobs/"):
        rest = path[len("/api/jobs/"):]
        if rest.endswith("/stop"):
            if method != "POST":
                return 405, {"error": "POST only"}
            return (202, {"stopping": True}) if jobs.stop(rest[:-5]) \
                else (404, {"error": "no such job"})
        if method != "GET":
            return 405, {"error": "GET only"}
        job = jobs.get(rest)
        return (200, job) if job else (404, {"error": "no such job"})

    return 404, {"error": f"no such path: {path}"}


# --- the server ------------------------------------------------------------

def _run_job(kind: str, jid: str, jobs: Jobs) -> None:
    """A run, in a thread, reporting as it goes.

    Long work in the background is what lets the window stay drawable: a
    collection waits minutes on GitHub's rate limit, and a page that freezes
    for that long is indistinguishable from one that crashed.
    """
    def say(event: str, data: dict) -> None:
        jobs.event(jid, event, data)

    def stop_asked() -> bool:
        """Whether «Ferma» was pressed. Read at the run's own checkpoints —
        between two posts, before a model call — never mid-request: a reply
        already on its way is a reply already paid for."""
        job = jobs.get(jid)
        return bool(job and job["stopping"])

    try:
        if kind == "recap":
            from winnow.recap import run_recap
            code = run_recap(open_file=False, on_event=say,
                             should_stop=stop_asked)
        elif kind == "ideas":
            from winnow.ideas import run_ideas
            code = run_ideas(open_file=False, on_event=say,
                             should_stop=stop_asked)
        elif kind == "folders":
            jobs.finish(jid, 0, result={"folders": scan_folders()})
            return
        else:
            # Through the CLI on purpose — the session, the http client and
            # the error wording live there — but with the window's two hooks,
            # which is why `main` takes them. Without `on_event` a collection
            # ran for minutes and the window showed nothing at all.
            from winnow.cli import main as cli_main
            code = cli_main(["collect"], on_event=say,
                            should_stop=stop_asked)
    except Exception as exc:                       # noqa: BLE001
        # A crashed thread with nobody watching is a spinner that never stops.
        # Whatever went wrong, the window has to hear about it.
        jobs.finish(jid, 1, error=f"{type(exc).__name__}: {exc}")
        return
    jobs.finish(jid, code or 0)


def scan_folders() -> list[dict]:
    """Ask the account which saved folders it has.

    The window offers what Instagram actually holds instead of a name typed
    from memory: a folder whose URL is one character wrong reads nothing and
    says nothing, which is the quietest way for this tool to be useless.
    """
    from winnow.browser import list_saved_folders, open_session
    from winnow.config import load_config

    cfg = load_config(paths.config_file())
    with open_session(cfg.browser_profile) as page:
        found = list_saved_folders(page, cfg.username)
    return [{"name": name, "url": url} for name, url in found]


def spawn(kind: str, jid: str, jobs: Jobs) -> None:
    t = threading.Thread(target=_run_job, args=(kind, jid, jobs), daemon=True)
    t.start()


def make_handler(jobs: Jobs, ui_dir: Path):
    from http.server import SimpleHTTPRequestHandler

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ui_dir), **kw)

        def log_message(self, *a) -> None:      # quiet: this is an app, not a site
            pass

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _api(self, method: str) -> bool:
            if not self.path.startswith("/api/"):
                return False
            payload = {}
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                try:
                    payload = json.loads(self.rfile.read(length))
                except json.JSONDecodeError:
                    payload = {}
            code, body = route(method, self.path, payload, jobs, spawn=spawn)
            self._send(code, body)
            return True

        def do_GET(self) -> None:
            if self._api("GET"):
                return
            # The recap pages live in the data directory, not next to the UI:
            # they are the user's, they outlive any installed copy of winnow,
            # and copying them under the app would make two of each.
            # The painting the tool is named after, from the package. The
            # recap page embeds it as base64 because it gets mailed and moved;
            # the window is served over a socket, so a URL is right here — the
            # home screen polls every four seconds and would otherwise carry
            # 93 KB of inline picture each time.
            if self.path == "/winnower.jpg":
                from winnow.render import PAINTING
                data = PAINTING.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
                return
            shot = shot_path(self.path)
            if shot is not None:
                data = shot.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            # The page arrives already coloured. Fetching the look after
            # load would paint the default first and repaint a frame later —
            # a white flash on a dark ground, on every single launch.
            if self.path in ("/", "/index.html") or self.path.startswith("/?"):
                page = (ui_dir / "index.html").read_text(encoding="utf-8")
                look = read_look()
                # The `lang` attribute is the real one — a screen reader
                # reads it — and the page's own strings key off it too.
                page = page.replace(
                    '<html lang="it">',
                    f'<html lang="{look["lang"]}" '
                    f'data-ground="{look["ground"]}" '
                    f'data-accent="{look["accent"]}">', 1)
                data = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if self.path.startswith("/recap/"):
                name = Path(self.path[len("/recap/"):]).name
                page = paths.recap_dir() / name
                if page.is_file() and page.suffix == ".html":
                    data = page.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self._send(404, {"error": "no such page"})
                return
            super().do_GET()

        def do_DELETE(self) -> None:
            if not self._api("DELETE"):
                self._send(404, {"error": "no such path"})

        def do_POST(self) -> None:
            if not self._api("POST"):
                self._send(404, {"error": "no such path"})

        def do_PATCH(self) -> None:
            if not self._api("PATCH"):
                self._send(404, {"error": "no such path"})

    return Handler


def serve(port: int = 0, ui_dir: Path | None = None) -> tuple[object, int]:
    """Start the server and say which port it took.

    Port 0 means "any free one": a fixed port is a crash waiting for the day
    something else already holds it, and the window must never open on a blank
    page because of that.
    """
    from http.server import ThreadingHTTPServer

    ui = ui_dir or (Path(__file__).parent / "ui")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Jobs(), ui))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]
