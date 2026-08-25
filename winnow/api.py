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
                               "stopping": False,
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

    def finish(self, jid: str, code: int, error: str | None = None) -> None:
        job = self._jobs.get(jid)
        if job is None:
            return
        with self._lock:
            job.update(done=True, code=code, error=error)

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


def _config_dict() -> dict:
    from winnow.config import load_config
    cfg = load_config(paths.config_file())
    return {"model": cfg.model, "provider": cfg.provider,
            "base_url": cfg.base_url,
            "folders": [{"name": f.name, "active": f.active, "kind": f.kind}
                        for f in cfg.folders]}


# Never handed to the window, however the config grows. An allow-list and not
# a deny-list: a key added later must not leak because nobody updated a filter.
CONFIG_PUBLIC = ("model", "provider", "base_url", "folders")


def _archive() -> list[dict]:
    """The pages already produced, newest first."""
    out = []
    d = paths.recap_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.html"), reverse=True):
        week = f.stem.replace(".answer", "")
        out.append({"week": week, "file": f.name,
                    "size_kb": f.stat().st_size // 1024})
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
        return 200, {"recaps": _archive()}

    if path == "/api/config":
        if method != "GET":
            return 405, {"error": "GET only"}
        try:
            raw = _config_dict()
        except FileNotFoundError:
            return 404, {"error": "no config yet — run the setup"}
        return 200, {k: raw[k] for k in CONFIG_PUBLIC if k in raw}

    if path in ("/api/collect", "/api/recap"):
        if method != "POST":
            return 405, {"error": "POST only"}
        busy = jobs.current()
        if busy:
            return 409, {"error": BUSY_MESSAGE, "running": busy["id"],
                         "kind": busy["kind"]}
        kind = path.rsplit("/", 1)[1]
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
        else:
            from winnow.cli import main as cli_main
            code = cli_main(["collect"])
    except Exception as exc:                       # noqa: BLE001
        # A crashed thread with nobody watching is a spinner that never stops.
        # Whatever went wrong, the window has to hear about it.
        jobs.finish(jid, 1, error=f"{type(exc).__name__}: {exc}")
        return
    jobs.finish(jid, code or 0)


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

        def do_POST(self) -> None:
            if not self._api("POST"):
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
