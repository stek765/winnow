import os
from pathlib import Path

from winnow import paths


def test_defaults_follow_xdg(monkeypatch):
    monkeypatch.delenv("WINNOW_CONFIG_DIR", raising=False)
    monkeypatch.delenv("WINNOW_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/cfg")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/data")
    assert paths.config_dir() == Path("/tmp/cfg/winnow")
    assert paths.data_dir() == Path("/tmp/data/winnow")


def test_falls_back_to_home_when_xdg_is_unset(monkeypatch):
    for v in ("WINNOW_CONFIG_DIR", "WINNOW_DATA_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", "/tmp/casa")
    assert paths.config_dir() == Path("/tmp/casa/.config/winnow")
    assert paths.data_dir() == Path("/tmp/casa/.local/share/winnow")


def test_winnow_env_vars_win_over_xdg(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/cfg")
    monkeypatch.setenv("WINNOW_CONFIG_DIR", "/altrove/conf")
    monkeypatch.setenv("WINNOW_DATA_DIR", "/altrove/dati")
    assert paths.config_dir() == Path("/altrove/conf")
    assert paths.data_dir() == Path("/altrove/dati")


def test_the_derived_paths_sit_under_the_right_roots(monkeypatch):
    monkeypatch.setenv("WINNOW_CONFIG_DIR", "/c")
    monkeypatch.setenv("WINNOW_DATA_DIR", "/d")
    assert paths.config_file() == Path("/c/config.toml")
    assert paths.env_file() == Path("/c/env")
    assert paths.state_dir() == Path("/d/state")
    assert paths.findings_dir() == Path("/d/findings")
    assert paths.browser_profile() == Path("/d/browser-profile")
    assert paths.shots_dir() == Path("/d/state/shots")


def test_ensure_dirs_creates_everything_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("WINNOW_CONFIG_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("WINNOW_DATA_DIR", str(tmp_path / "d"))
    paths.ensure_dirs()
    paths.ensure_dirs()
    for p in (paths.config_dir(), paths.state_dir(), paths.findings_dir()):
        assert p.is_dir()


def test_config_dir_is_private(tmp_path, monkeypatch):
    """Ci finiscono chiave API e nome utente: non deve essere leggibile da altri."""
    monkeypatch.setenv("WINNOW_CONFIG_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("WINNOW_DATA_DIR", str(tmp_path / "d"))
    paths.ensure_dirs()
    assert oct(paths.config_dir().stat().st_mode)[-3:] == "700"
