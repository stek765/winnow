"""`winnow update` — because the obvious command lies.

Measured 2026-08-25: `pipx upgrade winnow` and even `pipx upgrade --force`
print "already at latest version 1.0.0" and fetch nothing, because the version
string does not change between commits. The user believes they upgraded and
did not. Only `pipx install --force` actually refetches — and that one wipes
injected packages, which is how a dev install lost its pytest.
"""
from __future__ import annotations

import json

import pytest

from winnow.update import (
    describe_move, injected_packages, installed_commit, is_editable,
    remote_head, source_url,
)


def _dist_info(tmp_path, payload: dict):
    d = tmp_path / "winnow-1.0.0.dist-info"
    d.mkdir()
    (d / "direct_url.json").write_text(json.dumps(payload), encoding="utf-8")
    return d / "direct_url.json"


def test_the_installed_commit_is_read_from_the_package(tmp_path):
    """A version number that never moves cannot tell you whether you are
    behind. The commit can, and pip records it."""
    f = _dist_info(tmp_path, {"url": "https://github.com/stek765/winnow",
                              "vcs_info": {"commit_id": "447feb5f0db7a28",
                                           "vcs": "git"}})
    assert installed_commit(f) == "447feb5f0db7a28"
    assert source_url(f) == "git+https://github.com/stek765/winnow"


def test_an_editable_install_is_recognised_and_not_upgraded(tmp_path):
    """`pipx install --force` over an editable checkout would silently
    replace the code you are editing with whatever is on GitHub."""
    f = _dist_info(tmp_path, {"url": "file:///Users/x/winnow",
                              "dir_info": {"editable": True}})
    assert is_editable(f) is True
    assert installed_commit(f) is None


def test_a_missing_record_is_not_a_crash(tmp_path):
    assert installed_commit(tmp_path / "nope.json") is None
    assert source_url(tmp_path / "nope.json") is None
    assert is_editable(tmp_path / "nope.json") is False


def test_the_remote_head_comes_from_ls_remote(monkeypatch):
    """One network call, no clone."""
    import winnow.update as U
    monkeypatch.setattr(U, "_run", lambda *a, **k:
                        "9c1de2f0aa11\tHEAD\n")
    assert remote_head("git+https://github.com/x/y") == "9c1de2f0aa11"


def test_a_network_failure_is_a_shrug_and_not_a_wrong_answer(monkeypatch):
    """Saying "you are up to date" because the network was down is the same
    class of lie the whole tool exists to avoid."""
    import winnow.update as U
    monkeypatch.setattr(U, "_run", lambda *a, **k: None)
    assert remote_head("git+https://github.com/x/y") is None


@pytest.mark.parametrize("here,there,expect", [
    ("aaaaaaa1111", "aaaaaaa1111", "same"),
    ("aaaaaaa1111", "bbbbbbb2222", "behind"),
    (None, "bbbbbbb2222", "unknown"),
    ("aaaaaaa1111", None, "unknown"),
])
def test_what_the_two_commits_mean(here, there, expect):
    assert describe_move(here, there) == expect


def test_injected_packages_are_read_so_they_can_be_put_back(monkeypatch):
    """`pipx install --force` wipes them. Losing a dev's pytest without
    saying so is how the test suite stopped running on 2026-08-25."""
    import winnow.update as U
    monkeypatch.setattr(U, "_run", lambda *a, **k: json.dumps(
        {"venvs": {"winnow": {"metadata": {
            "injected_packages": {"pytest": {}, "ruff": {}}}}}}))
    assert injected_packages() == ["pytest", "ruff"]


def test_no_pipx_is_not_a_crash(monkeypatch):
    import winnow.update as U
    monkeypatch.setattr(U, "_run", lambda *a, **k: None)
    assert injected_packages() == []


# --- what the command actually does -------------------------------------------

def _patch(monkeypatch, **kw):
    import winnow.update as U
    for k, v in kw.items():
        monkeypatch.setattr(U, k, v)


def test_being_up_to_date_is_said_plainly_and_nothing_is_reinstalled(
        monkeypatch, capsys):
    """The whole reason this exists: `pipx upgrade` claims to be up to date
    without checking. This one checks, then says it."""
    from winnow.update import run_update
    calls = []
    _patch(monkeypatch, is_editable=lambda: False,
           installed_commit=lambda: "aaaaaaa1111",
           source_url=lambda: "git+https://x/y",
           remote_head=lambda s: "aaaaaaa1111",
           reinstall=lambda *a: calls.append(a) or True)
    assert run_update() == 0
    assert not calls
    assert "aaaaaaa" in capsys.readouterr().out


def test_an_editable_install_is_refused_with_the_command_to_use_instead(
        monkeypatch, capsys):
    from winnow.update import run_update
    calls = []
    _patch(monkeypatch, is_editable=lambda: True,
           reinstall=lambda *a: calls.append(a) or True)
    assert run_update() == 0
    assert not calls
    assert "git pull" in capsys.readouterr().out


def test_a_new_commit_is_installed_and_the_injections_go_back(
        monkeypatch, capsys):
    """`pipx install --force` is the only thing that refetches, and it wipes
    injected packages. Putting them back is the whole difference between this
    command and the one-liner it replaces."""
    from winnow.update import run_update
    done = {}
    _patch(monkeypatch, is_editable=lambda: False,
           installed_commit=lambda: "aaaaaaa1111",
           source_url=lambda: "git+https://x/y",
           remote_head=lambda s: "bbbbbbb2222",
           injected_packages=lambda: ["pytest"],
           reinstall=lambda spec: done.setdefault("spec", spec) or True,
           reinject=lambda pkgs: done.setdefault("re", pkgs) or True)
    assert run_update() == 0
    assert done["spec"] == "git+https://x/y" and done["re"] == ["pytest"]
    out = capsys.readouterr().out
    assert "aaaaaaa" in out and "bbbbbbb" in out


def test_a_source_checkout_says_so_instead_of_pretending(monkeypatch, capsys):
    """Run from a clone with no install behind it, there is nothing to
    upgrade and no record to read."""
    from winnow.update import run_update
    _patch(monkeypatch, is_editable=lambda: False, source_url=lambda: None,
           installed_commit=lambda: None)
    assert run_update() == 1
    assert "not installed from git" in capsys.readouterr().out


def test_an_unreachable_remote_never_claims_you_are_current(monkeypatch, capsys):
    from winnow.update import run_update
    calls = []
    _patch(monkeypatch, is_editable=lambda: False,
           installed_commit=lambda: "aaaaaaa1111",
           source_url=lambda: "git+https://x/y",
           remote_head=lambda s: None,
           reinstall=lambda *a: calls.append(a) or True)
    assert run_update() == 1
    assert not calls
    assert "could not ask" in capsys.readouterr().out.lower()


def test_a_stale_egg_info_in_a_checkout_does_not_answer_for_the_real_install(
        tmp_path, monkeypatch):
    """A checkout left over from `pipx install --editable .` keeps a
    `winnow.egg-info` around, and `importlib.metadata` finds *that* first when
    the working directory is the repo — so the lookup described a package
    nobody was running, and `winnow update` reported "not installed from git"
    on a machine where it was. The record is found beside the imported code
    instead."""
    import winnow.update as U
    pkg = tmp_path / "site-packages" / "winnow"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    info = tmp_path / "site-packages" / "winnow-1.0.0.dist-info"
    info.mkdir()
    (info / "direct_url.json").write_text(json.dumps(
        {"url": "https://github.com/stek765/winnow",
         "vcs_info": {"commit_id": "ccc3333", "vcs": "git"}}), encoding="utf-8")

    class FakePkg:
        __file__ = str(pkg / "__init__.py")
    monkeypatch.setitem(__import__("sys").modules, "winnow", FakePkg)
    assert U.record_path() == info / "direct_url.json"
    assert U.installed_commit() == "ccc3333"
