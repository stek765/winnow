"""`winnow schedule` — install the daily run on whatever this machine uses.

Writing a launchd plist by hand is the step where a first-time user gives up:
it is XML, it needs absolute paths, and getting it wrong fails silently at
1 a.m. So winnow looks at the operating system, writes the right thing itself,
and asks before touching anything.

The pure part — which backend, what the file says — is separated from the part
that writes and loads it, so all of it can be tested without a scheduler.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from winnow import paths

LABEL = "dev.winnow.collect"
DEFAULT_TIME = "13:00"


def parse_time(text: str) -> tuple[int, int]:
    """'13:00' -> (13, 0). Rejects anything that isn't a real clock time."""
    hh, _, mm = text.strip().partition(":")
    try:
        hour, minute = int(hh), int(mm or 0)
    except ValueError:
        raise ValueError(f"orario non valido: {text!r} (usa HH:MM)") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"orario non valido: {text!r} (usa HH:MM)")
    return hour, minute


def backend(platform: str | None = None, has_systemd: bool | None = None) -> str:
    """Which scheduler this machine actually uses."""
    platform = platform if platform is not None else sys.platform
    if platform == "darwin":
        return "launchd"
    if platform.startswith("win"):
        return "unsupported"
    if has_systemd is None:
        has_systemd = shutil.which("systemctl") is not None
    return "systemd" if has_systemd else "cron"


def winnow_exe() -> Path:
    """The absolute path of the installed command.

    A scheduler runs with a minimal PATH, so a bare `winnow` would not be
    found. `sys.argv[0]` is the command the user just typed — the right one
    even with several installs around.
    """
    argv0 = Path(sys.argv[0])
    if argv0.name == "winnow" and argv0.exists():
        return argv0.resolve()
    found = shutil.which("winnow")
    return Path(found).resolve() if found else argv0.resolve()


def log_file() -> Path:
    return paths.state_dir() / "collect.log"


def plist_text(exe: Path, log: Path, hour: int, minute: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{exe}</string>
    <string>collect</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>{hour}</integer>
    <key>Minute</key><integer>{minute}</integer>
  </dict>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def systemd_units(exe: Path, hour: int, minute: int) -> tuple[str, str]:
    service = f"""[Unit]
Description=winnow — raccolta giornaliera

[Service]
Type=oneshot
ExecStart={exe} collect
"""
    timer = f"""[Unit]
Description=winnow — raccolta giornaliera

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true

[Install]
WantedBy=timers.target
"""
    return service, timer


def cron_line(exe: Path, log: Path, hour: int, minute: int) -> str:
    return f"{minute} {hour} * * * {exe} collect >> {log} 2>&1  # {LABEL}"


def plist_path() -> Path:
    home = Path(os.environ.get("HOME", "~")).expanduser()
    return home / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def systemd_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    home = Path(os.environ.get("HOME", "~")).expanduser()
    return (Path(base) if base else home / ".config") / "systemd" / "user"


@dataclass(frozen=True)
class Scheduled:
    """What is installed right now, as far as we can see from disk."""
    active: bool
    when: str = ""
    how: str = ""

    def __str__(self) -> str:
        return f"ogni giorno alle {self.when} ({self.how})" if self.active else "no"


def _time_from_plist(text: str) -> str:
    def grab(key: str) -> int:
        # <key>Hour</key><integer>13</integer> — with any whitespace between.
        after = text.split(f"<key>{key}</key>", 1)[-1]
        return int(after.split("<integer>", 1)[1].split("</integer>", 1)[0])
    try:
        return f"{grab('Hour'):02d}:{grab('Minute'):02d}"
    except (IndexError, ValueError):
        return "?"


def current(which: str | None = None) -> Scheduled:
    """Read back what `winnow schedule` installed, if anything."""
    which = which or backend()
    if which == "launchd" and plist_path().exists():
        text = plist_path().read_text(encoding="utf-8")
        return Scheduled(True, _time_from_plist(text), "launchd")
    if which == "systemd":
        timer = systemd_dir() / "winnow.timer"
        if timer.exists():
            body = timer.read_text(encoding="utf-8")
            when = "?"
            for line in body.splitlines():
                if line.startswith("OnCalendar="):
                    when = line.split()[-1][:5]
            return Scheduled(True, when, "systemd")
    if which == "cron":
        for line in _crontab_lines():
            if LABEL in line:
                bits = line.split()
                return Scheduled(True, f"{int(bits[1]):02d}:{int(bits[0]):02d}", "cron")
    return Scheduled(False)


def _crontab_lines() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def _write_crontab(lines: list[str]) -> bool:
    body = "\n".join(lines).strip() + "\n"
    r = subprocess.run(["crontab", "-"], input=body, text=True)
    return r.returncode == 0


def _run(cmd: list[str]) -> bool:
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def install(hour: int, minute: int, which: str | None = None) -> int:
    which = which or backend()
    exe, log = winnow_exe(), log_file()
    paths.ensure_dirs()

    if which == "launchd":
        path = plist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(plist_text(exe, log, hour, minute), encoding="utf-8")
        target = f"gui/{os.getuid()}"
        _run(["launchctl", "bootout", target, str(path)])           # se c'era
        if not _run(["launchctl", "bootstrap", target, str(path)]):
            # launchctl bootstrap non esiste prima di macOS 10.11.
            _run(["launchctl", "load", str(path)])
        print(f"  ✅ programmato ogni giorno alle {hour:02d}:{minute:02d} (launchd)")
        print(f"     {path}")

    elif which == "systemd":
        d = systemd_dir()
        d.mkdir(parents=True, exist_ok=True)
        service, timer = systemd_units(exe, hour, minute)
        (d / "winnow.service").write_text(service, encoding="utf-8")
        (d / "winnow.timer").write_text(timer, encoding="utf-8")
        _run(["systemctl", "--user", "daemon-reload"])
        if not _run(["systemctl", "--user", "enable", "--now", "winnow.timer"]):
            print("  ⚠️  timer scritto ma non attivato: prova a mano con")
            print("     systemctl --user enable --now winnow.timer")
            return 1
        print(f"  ✅ programmato ogni giorno alle {hour:02d}:{minute:02d} (systemd)")
        print(f"     {d}/winnow.timer")

    elif which == "cron":
        lines = [l for l in _crontab_lines() if LABEL not in l]
        lines.append(cron_line(exe, log, hour, minute))
        if not _write_crontab(lines):
            print("  ❌ non sono riuscito a scrivere il crontab.")
            return 1
        print(f"  ✅ programmato ogni giorno alle {hour:02d}:{minute:02d} (cron)")
        print("  ⚠️  cron salta in silenzio le corse perse mentre la macchina "
              "dorme.")

    else:
        print("  ❌ programmazione automatica non disponibile su questo sistema.")
        print(f"     Esegui a mano, ogni giorno: {exe} collect")
        return 1

    print("\n  Scegli un orario in cui il computer e' acceso e sbloccato: la\n"
          "  raccolta apre una finestra del browser e serve una sessione grafica.")
    return 0


def remove(which: str | None = None) -> int:
    which = which or backend()
    if which == "launchd":
        path = plist_path()
        if not path.exists():
            print("  non era programmato.")
            return 0
        _run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)])
        _run(["launchctl", "unload", str(path)])
        path.unlink()
    elif which == "systemd":
        d = systemd_dir()
        if not (d / "winnow.timer").exists():
            print("  non era programmato.")
            return 0
        _run(["systemctl", "--user", "disable", "--now", "winnow.timer"])
        (d / "winnow.timer").unlink()
        (d / "winnow.service").unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"])
    elif which == "cron":
        lines = _crontab_lines()
        kept = [l for l in lines if LABEL not in l]
        if len(kept) == len(lines):
            print("  non era programmato.")
            return 0
        _write_crontab(kept)
    else:
        print("  niente da rimuovere.")
        return 0
    print("  rimosso. winnow non partira' piu' da solo.")
    return 0


def run_schedule(at: str | None, off: bool, assume_yes: bool = False) -> int:
    """`winnow schedule [--at HH:MM] [--off]`."""
    which = backend()
    if off:
        return remove(which)

    now = current(which)
    if now.active and at is None:
        print(f"  gia' programmato: {now}")
        print("  cambia orario con 'winnow schedule --at HH:MM', "
              "togli con 'winnow schedule --off'")
        return 0

    hour, minute = parse_time(at or DEFAULT_TIME)
    if not assume_yes and sys.stdin.isatty():
        where = {"launchd": plist_path(), "systemd": systemd_dir() / "winnow.timer",
                 "cron": Path("crontab")}.get(which, Path("-"))
        print(f"  winnow verra' eseguito ogni giorno alle {hour:02d}:{minute:02d}.")
        print(f"  Scrivo in {where} ({which}).")
        from winnow.setup import ask
        if ask("  Procedo? [S/n] ").lower() not in ("", "s", "si", "y", "yes"):
            print("  annullato.")
            return 1
    return install(hour, minute, which)
