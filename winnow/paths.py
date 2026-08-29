"""Where winnow keeps its things.

Installed globally, winnow has no directory of its own, so config and state
follow the XDG convention. Every location is overridable by environment
variable — which is also what makes them testable.
"""
from __future__ import annotations

import os
from pathlib import Path


def _dir(explicit: str, xdg: str, fallback: str) -> Path:
    if os.environ.get(explicit):
        return Path(os.environ[explicit])
    base = os.environ.get(xdg)
    if base:
        return Path(base) / "winnow"
    return Path(os.environ.get("HOME", "~")).expanduser() / fallback / "winnow"


def config_dir() -> Path:
    return _dir("WINNOW_CONFIG_DIR", "XDG_CONFIG_HOME", ".config")


def data_dir() -> Path:
    return _dir("WINNOW_DATA_DIR", "XDG_DATA_HOME", ".local/share")


def config_file() -> Path:
    return config_dir() / "config.toml"


def env_file() -> Path:
    """Where the API key lives. Sourced by the scheduled job, never committed."""
    return config_dir() / "env"


def profile_file() -> Path:
    """The profile the judge reads. Next to config.toml because it is the
    other half of the configuration — the half no code can write for you."""
    return config_dir() / "profile.md"


def look_file() -> Path:
    """How the window is coloured. Beside the config because it is a
    preference of this installation — but its own file, so nothing that reads
    `config.toml` (the collector, the scheduled job) ever has to parse it."""
    return config_dir() / "look.json"


def recap_dir() -> Path:
    return data_dir() / "recap"


def state_dir() -> Path:
    return data_dir() / "state"


def judged_file() -> Path:
    """How far the judgement has progressed. Like seen.json, but for recaps."""
    return state_dir() / "judged.json"


def drawn_file() -> Path:
    """Everything a draw has already put in front of the model.

    Not derivable from the pages: deleting an idea deletes its sidecar, and
    with it the only record of the eight things that draw had read — so the
    next press could offer them all over again. A page is an artifact and may
    be thrown away; what has already been asked is state, and state does not
    live inside the artifact. Same reason `judged.json` exists.
    """
    return state_dir() / "drawn.json"


def findings_dir() -> Path:
    return data_dir() / "findings"


def shots_dir() -> Path:
    return state_dir() / "shots"


def browser_profile() -> Path:
    return data_dir() / "browser-profile"


def ensure_dirs() -> None:
    """Create every directory winnow needs. Safe to call repeatedly."""
    config_dir().mkdir(parents=True, exist_ok=True)
    # Config holds the API key and the username: keep it to the owner.
    config_dir().chmod(0o700)
    for d in (data_dir(), state_dir(), findings_dir(), shots_dir(), recap_dir()):
        d.mkdir(parents=True, exist_ok=True)
