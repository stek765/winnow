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
from winnow.progress import line

# One run at a time. Two recaps in flight would pay twice and race on the same
# "how far have I judged" marker; two collections would race on seen.json.
BUSY_MESSAGE = "something is already running"


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


def _facts(jobs: Jobs) -> dict:
    running = jobs.current()
    return appstate.read_facts(
        state_dir=paths.state_dir(), findings_dir=paths.findings_dir(),
        judged=paths.judged_file(), browser_profile=paths.browser_profile(),
        running={"kind": running["kind"],
                 "done": len(running["events"]), "of": 0} if running else None)


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
WEEK_PAGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.answer\.html$")
WEEK_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


MERGE_PAGE = re.compile(r"^unione-[\d_-]+\.html$")


def _merges() -> list[dict]:
    """The pages made by putting weeks together, newest first.

    Kept apart from the weeks: a merge is not one, and listing it among them
    would claim it is.
    """
    out = []
    d = paths.recap_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("unione-*.html"), reverse=True):
        if not MERGE_PAGE.match(f.name):
            continue
        side = d / (f.stem + ".json")
        info = {}
        if side.is_file():
            try:
                info = json.loads(side.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                info = {}
        out.append({"file": f.name, "label": info.get("label") or f.stem,
                    "weeks": info.get("weeks") or [],
                    "things": info.get("things")})
    return out


def _archive() -> list[dict]:
    """The weeks already judged, newest first."""
    out = []
    d = paths.recap_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.answer.html"), reverse=True):
        m = WEEK_PAGE.match(f.name)
        if not m:
            continue
        week = m.group(1)
        out.append({"week": week, "file": f.name,
                    **_verdict(d / f"{week}.answer.md")})
    return out


def route(method: str, path: str, payload: dict, jobs: Jobs,
          spawn=None) -> tuple[int, dict]:
    """One request in, one `(status, body)` out. No sockets, no globals."""
    if path == "/api/state":
        if method != "GET":
            return 405, {"error": "GET only"}
        return 200, appstate.home(_facts(jobs))

    if path == "/api/recaps":
        if method != "GET":
            return 405, {"error": "GET only"}
        return 200, {"recaps": _archive(), "merges": _merges()}

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
                return 400, {"error": f"{provider!r} non usa una chiave"}
            key = (payload.get("key") or "").strip()
            if not key:
                # Written through, it looks set and fails at the next run —
                # which is the exact failure this endpoint exists to stop.
                return 400, {"error": "la chiave è vuota"}
            write_key(paths.env_file(), KEY_ENV[provider], key)
        elif method != "GET":
            return 405, {"error": "GET or POST"}
        return 200, {"keys": _keys_present()}

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
        return 200, {"exists": prof.is_file(), "chars": chars,
                     "path": str(prof)}

    if path.startswith("/api/console"):
        # Opening the provider's key page in a real browser. The window cannot
        # do it itself: a webview navigating away would replace the app.
        if method != "POST":
            return 405, {"error": "POST only"}
        from winnow.providers import CONSOLE
        from winnow.setup import open_url
        which = path.partition("?p=")[2]
        if which not in CONSOLE:
            return 400, {"error": f"nessuna pagina per {which!r}"}
        open_url(CONSOLE[which])
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
                return 409, {"error": BUSY_MESSAGE, "running": busy["id"],
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
                return 409, {"error": BUSY_MESSAGE, "running": busy["id"],
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
        from winnow.harvest import label_for, merge, render_harvest
        from winnow.render import extract_json

        weeks = sorted({w for w in (payload.get("weeks") or [])
                        if isinstance(w, str) and WEEK_RE.match(w)})
        if len(weeks) < 2:
            return 400, {"error": "servono almeno due settimane"}

        d = paths.recap_dir()
        answers, missing = [], []
        for week in weeks:
            side = d / f"{week}.answer.md"
            try:
                answers.append(extract_json(side.read_text(encoding="utf-8")))
            except Exception:                              # noqa: BLE001
                # The page can be reopened without its answer, but it cannot
                # be merged: the answer *is* the content. Producing a page
                # quietly missing half of what was asked for is the failure
                # this repo keeps paying for.
                missing.append(week)
        if missing:
            return 400, {"error": "manca il giudizio di " + ", ".join(missing)}

        merged = merge(answers)
        label = label_for(weeks)
        stem = f"unione-{weeks[0]}_{weeks[-1]}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{stem}.html").write_text(render_harvest(merged), encoding="utf-8")
        (d / f"{stem}.json").write_text(json.dumps(
            {"weeks": weeks, "label": label,
             "things": merged["counts"]["things"]},
            ensure_ascii=False), encoding="utf-8")
        return 200, {"file": f"{stem}.html", "label": label,
                     "things": merged["counts"]["things"]}

    if path.startswith("/api/recaps/"):
        if method != "DELETE":
            return 405, {"error": "DELETE only"}
        # The name arrives in a URL: `..` in it must not become a path.
        name = Path(path[len("/api/recaps/"):]).name
        d = paths.recap_dir()
        target = d / name
        if not name or not target.is_file() or target.suffix != ".html":
            return 404, {"error": "non esiste"}
        # The page and the judgement that produced it go together. Leaving the
        # answer behind is half a delete, and the half that stays is the one
        # holding the reading.
        removed = []
        for f in sorted(d.glob(target.stem.replace(".answer", "") + "*")):
            if f.is_file():
                f.unlink()
                removed.append(f.name)
        return 200, {"removed": removed}

    if path in ("/api/collect", "/api/recap", "/api/folders/scan"):
        if method != "POST":
            return 405, {"error": "POST only"}
        busy = jobs.current()
        if busy:
            return 409, {"error": BUSY_MESSAGE, "running": busy["id"],
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

    try:
        if kind == "recap":
            from winnow.recap import run_recap
            code = run_recap(open_file=False, on_event=say)
        elif kind == "folders":
            jobs.finish(jid, 0, result={"folders": scan_folders()})
            return
        else:
            from winnow.cli import main as cli_main
            code = cli_main(["collect"])
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
