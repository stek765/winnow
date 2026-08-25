"""`winnow update` — because the obvious command lies.

`pipx upgrade winnow` prints *"already at latest version 1.0.0"* and fetches
nothing. So does `pipx upgrade --force`. Both compare version strings, and the
version does not move between commits of a tool installed from git — so the
reader believes they upgraded, and did not. Measured 2026-08-25, twice.

The only command that actually refetches is `pipx install --force`, and that
one **wipes injected packages** — which is how a development install lost its
pytest earlier the same day, silently, and the test suite stopped running.

So this module does what neither command does on its own:

  * reads the commit that is actually installed, from the record pip writes;
  * asks the remote what its HEAD is, with one call and no clone;
  * says *behind*, *same*, or *unknown* — and never guesses `same` because the
    network was down, which would be the same class of lie the rest of the
    tool exists to avoid;
  * reinstalls only when there is something to install, and puts the injected
    packages back afterwards.

Everything here is pure except `_run`, so the whole module is tested offline.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run(cmd: list[str], timeout: int = 30) -> str | None:
    """Stdout, or None. Never raises: every caller has a good answer for
    "I could not ask", and none of them has one for a traceback."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout


def record_path() -> Path | None:
    """Where pip wrote down how *this* copy was installed.

    `direct_url.json` is written for anything installed from a URL or a path,
    and for a git install it carries the exact commit — the one fact that can
    tell you whether you are behind, since the version string cannot.

    Found next to the package that is actually imported, and deliberately not
    through `importlib.metadata`: a checkout with a stale `winnow.egg-info`
    left over from an editable install shadows the real distribution, and the
    lookup then answers about a package nobody is running. Tying the record to
    the code in memory also gives the honest answer when winnow is being run
    straight from a clone — there is no dist-info beside it, so there is
    nothing to upgrade.
    """
    import winnow
    site = Path(winnow.__file__).resolve().parent.parent
    for d in sorted(site.glob("winnow-*.dist-info")):
        f = d / "direct_url.json"
        if f.is_file():
            return f
    return None


def _record(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def installed_commit(path: Path | None = None) -> str | None:
    """The commit this copy was built from, when it came from git."""
    return (_record(path or record_path()).get("vcs_info") or {}).get("commit_id")


def source_url(path: Path | None = None) -> str | None:
    """The pip spec that would reinstall this copy."""
    rec = _record(path or record_path())
    url = rec.get("url")
    if not url or not rec.get("vcs_info"):
        return None
    return f"git+{url}"


def is_editable(path: Path | None = None) -> bool:
    """An editable install points at a checkout somebody is working in.

    Reinstalling over it would replace the code being edited with whatever is
    on GitHub — so this is a refusal, not a branch.
    """
    return bool((_record(path or record_path()).get("dir_info") or {})
                .get("editable"))


def remote_head(spec: str) -> str | None:
    """What the remote calls HEAD. One call, no clone, and None if nobody
    could be asked."""
    url = spec[4:] if spec.startswith("git+") else spec
    out = _run(["git", "ls-remote", url, "HEAD"], timeout=20)
    if not out or "\t" not in out:
        return None
    return out.split("\t", 1)[0].strip() or None


def describe_move(here: str | None, there: str | None) -> str:
    """`same`, `behind`, or `unknown`. Never `same` by default: a network
    failure and an up-to-date install are different answers."""
    if not here or not there:
        return "unknown"
    return "same" if here == there else "behind"


def injected_packages() -> list[str]:
    """What `pipx install --force` is about to throw away."""
    out = _run(["pipx", "list", "--json"], timeout=30)
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    venv = (data.get("venvs") or {}).get("winnow") or {}
    return sorted((venv.get("metadata") or {}).get("injected_packages") or {})


def reinstall(spec: str) -> bool:
    """The only command that actually refetches a git install.

    `pipx upgrade` and `pipx upgrade --force` both compare version strings and
    stop there, so neither of them ever fetches a new commit of a package
    whose version does not move.
    """
    return _run(["pipx", "install", "--force", spec], timeout=600) is not None


def reinject(packages: list[str]) -> bool:
    if not packages:
        return True
    return _run(["pipx", "inject", "winnow", *packages],
                timeout=600) is not None


def _short(commit: str | None) -> str:
    return (commit or "?")[:7]


def run_update() -> int:
    """`winnow update` — check, then install only if there is something to."""
    if is_editable():
        print("  This is an editable install: the code lives in your checkout.")
        print("  Update it with  git pull  — reinstalling would overwrite it.")
        return 0

    spec, here = source_url(), installed_commit()
    if not spec:
        print("  This copy was not installed from git, so there is nothing to")
        print("  pull. Install it with:")
        print("    pipx install git+https://github.com/stek765/winnow")
        return 1

    print(f"  installed  {_short(here)}")
    there = remote_head(spec)
    if describe_move(here, there) == "unknown":
        # Never "you are up to date" because the network was down: that is the
        # same class of lie the rest of the tool exists to avoid.
        print("  Could not ask the remote what it has. Nothing was changed.")
        return 1

    print(f"  remote     {_short(there)}")
    if here == there:
        print("\n  Already the newest. Nothing to do.")
        return 0

    keep = injected_packages()
    print(f"\n  Updating {_short(here)} → {_short(there)} …")
    if not reinstall(spec):
        print("  pipx could not install it. Nothing was changed.")
        return 1
    # `pipx install --force` wipes these, silently. Losing a developer's
    # pytest without a word is how a test suite stopped running once.
    if keep and not reinject(keep):
        print(f"  ⚠ could not put back: {', '.join(keep)}")
        print(f"    pipx inject winnow {' '.join(keep)}")
    print(f"  ✅ now on {_short(there)}")
    return 0
