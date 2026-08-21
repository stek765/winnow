"""The scheduler chosen and the file written, without touching a scheduler."""
from __future__ import annotations

from pathlib import Path

import pytest

from winnow import schedule


def test_backend_per_system():
    assert schedule.backend("darwin") == "launchd"
    assert schedule.backend("linux", has_systemd=True) == "systemd"
    assert schedule.backend("linux", has_systemd=False) == "cron"
    assert schedule.backend("win32") == "unsupported"


@pytest.mark.parametrize("text,expected", [
    ("13:00", (13, 0)), ("7:5", (7, 5)), ("00:00", (0, 0)), (" 23:59 ", (23, 59)),
])
def test_parse_time(text, expected):
    assert schedule.parse_time(text) == expected


@pytest.mark.parametrize("bad", ["24:00", "13:60", "-1:00", "mezzogiorno", "13:aa"])
def test_parse_time_rejects_nonsense(bad):
    """An hour silently clamped is a run that never fires and never says why."""
    with pytest.raises(ValueError):
        schedule.parse_time(bad)


def test_plist_holds_absolute_paths_and_the_time():
    text = schedule.plist_text(Path("/usr/local/bin/winnow"), Path("/tmp/c.log"), 13, 5)
    assert "<string>/usr/local/bin/winnow</string>" in text
    assert "<string>collect</string>" in text
    assert "<key>Hour</key><integer>13</integer>" in text
    assert "<key>Minute</key><integer>5</integer>" in text
    assert "/tmp/c.log" in text


def test_plist_round_trips_through_current(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = schedule.plist_path()
    p.parent.mkdir(parents=True)
    p.write_text(schedule.plist_text(Path("/bin/winnow"), Path("/tmp/l"), 9, 30))
    assert schedule.current("launchd") == schedule.Scheduled(True, "09:30", "launchd")


def test_current_is_false_when_nothing_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert not schedule.current("launchd").active
    assert str(schedule.current("launchd")) == "no"


def test_systemd_timer_fires_daily_and_catches_up():
    service, timer = schedule.systemd_units(Path("/bin/winnow"), 13, 0)
    assert "ExecStart=/bin/winnow collect" in service
    assert "OnCalendar=*-*-* 13:00:00" in timer
    # Persistent=true is the whole reason systemd is preferred over cron.
    assert "Persistent=true" in timer


def test_cron_line_is_taggable_so_it_can_be_removed():
    line = schedule.cron_line(Path("/bin/winnow"), Path("/tmp/l.log"), 13, 5)
    assert line.startswith("5 13 * * * /bin/winnow collect")
    assert schedule.LABEL in line
