"""The local API: the only thing the window is allowed to talk to.

Tested without a socket wherever possible — routing and job bookkeeping are
plain functions, so the shell can be swapped for Tauri later without any of
this moving.
"""
from __future__ import annotations

import json

import pytest

from winnow.api import Jobs, route


def test_the_home_state_arrives_in_one_request(monkeypatch):
    """Spec §7.2: one call gives the home screen everything. Five calls to
    paint one screen is five chances to show a half-drawn one."""
    import winnow.api as A
    monkeypatch.setattr(A, "_facts", lambda jobs: {
        "halted": False, "logged_in": True, "running": None,
        "pending_posts": 30, "pending_days": 3, "last_collect": None,
        "spend_usd": 0.13})
    code, body = route("GET", "/api/state", {}, Jobs())
    assert code == 200
    assert body["state"] == "ready" and body["pending_posts"] == 30
    assert body["button"] and body["action"]


def test_an_unknown_path_is_a_404_and_not_a_crash():
    code, body = route("GET", "/api/nonsense", {}, Jobs())
    assert code == 404 and "error" in body


def test_a_command_on_the_wrong_verb_is_refused():
    """`GET /api/recap` from a stray link must not start a paid run."""
    code, _ = route("GET", "/api/recap", {}, Jobs())
    assert code == 405


def test_starting_a_job_returns_an_id_to_follow():
    jobs = Jobs()
    code, body = route("POST", "/api/recap", {}, jobs,
                       spawn=lambda kind, jid, jobs: None)
    assert code == 202 and body["id"]
    assert jobs.get(body["id"])["kind"] == "recap"


def test_two_runs_at_once_are_refused(monkeypatch):
    """Two recaps in flight would pay twice and race on the same marker."""
    jobs = Jobs()
    _, first = route("POST", "/api/recap", {}, jobs,
                     spawn=lambda *a: None)
    code, body = route("POST", "/api/collect", {}, jobs,
                       spawn=lambda *a: None)
    assert code == 409 and first["id"] in json.dumps(body)


def test_a_finished_job_lets_the_next_one_start():
    jobs = Jobs()
    _, first = route("POST", "/api/recap", {}, jobs, spawn=lambda *a: None)
    jobs.finish(first["id"], 0)
    code, _ = route("POST", "/api/collect", {}, jobs, spawn=lambda *a: None)
    assert code == 202


def test_the_events_of_a_job_can_be_read_as_they_arrive():
    jobs = Jobs()
    jid = jobs.start("recap")
    jobs.event(jid, "bundling", {"days": 3, "posts": 30, "things": 144})
    jobs.event(jid, "judged", {"kept": 15, "of": 144, "usd": 0.42})
    code, body = route("GET", f"/api/jobs/{jid}", {}, jobs)
    assert code == 200
    kinds = [e["kind"] for e in body["events"]]
    assert kinds == ["bundling", "judged"]
    assert body["done"] is False


def test_each_event_carries_the_line_a_human_would_read():
    """`progress.line` already knows how to say these. The window renders the
    sentence; it never assembles one from the raw fields."""
    jobs = Jobs()
    jid = jobs.start("recap")
    jobs.event(jid, "judged", {"kept": 15, "of": 144, "usd": 0.42})
    _, body = route("GET", f"/api/jobs/{jid}", {}, jobs)
    assert "15" in body["events"][0]["line"] and "144" in body["events"][0]["line"]


def test_asking_for_a_job_that_never_existed_is_a_404():
    code, _ = route("GET", "/api/jobs/nope", {}, Jobs())
    assert code == 404


def test_a_finished_job_says_so_and_carries_its_exit_code():
    jobs = Jobs()
    jid = jobs.start("collect")
    jobs.finish(jid, 1, error="no config")
    _, body = route("GET", f"/api/jobs/{jid}", {}, jobs)
    assert body["done"] is True and body["code"] == 1
    assert body["error"] == "no config"


def test_stopping_a_job_marks_it_and_does_not_lie_about_it():
    jobs = Jobs()
    jid = jobs.start("collect")
    code, _ = route("POST", f"/api/jobs/{jid}/stop", {}, jobs)
    assert code == 202 and jobs.get(jid)["stopping"] is True


def test_the_archive_lists_the_pages_newest_first(tmp_path, monkeypatch):
    import winnow.api as A
    for day in ("2026-08-20", "2026-08-25"):
        (tmp_path / f"{day}.answer.html").write_text("<html>", encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    code, body = route("GET", "/api/recaps", {}, Jobs())
    assert code == 200
    assert [r["week"] for r in body["recaps"]] == ["2026-08-25", "2026-08-20"]


def test_an_empty_archive_is_a_list_and_not_an_error(tmp_path, monkeypatch):
    import winnow.api as A
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    code, body = route("GET", "/api/recaps", {}, Jobs())
    assert code == 200 and body["recaps"] == []


def test_the_config_is_readable_and_never_leaks_the_key(tmp_path, monkeypatch):
    """The window shows which model is set. It must never be handed the
    credential that goes with it."""
    import winnow.api as A
    monkeypatch.setattr(A, "_config_dict", lambda: {
        "model": "claude-haiku-4-5", "provider": "anthropic",
        "api_key": "sk-ant-secret", "folders": []})
    code, body = route("GET", "/api/config", {}, Jobs())
    assert code == 200 and body["model"] == "claude-haiku-4-5"
    assert "sk-ant-secret" not in json.dumps(body)
    assert "api_key" not in body


@pytest.mark.parametrize("path", ["/api/state", "/api/recaps", "/api/config"])
def test_reading_never_starts_anything(path):
    """A GET must be free of side effects: the window polls these."""
    jobs = Jobs()
    route("GET", path, {}, jobs)
    assert jobs.current() is None


def test_the_painting_is_served_to_the_window():
    """The window's background is the Millet the tool is named after — the
    same picture the recap page opens with, so the app and the page it
    produces read as one product. It lives in the package, not next to the
    UI, so there is exactly one copy of it."""
    from winnow.api import Jobs, make_handler
    from winnow.render import PAINTING
    assert PAINTING.is_file()
    # Served under its own path, so the page can reference it by URL instead
    # of carrying 93 KB of base64 inline on every poll of the home screen.
    assert make_handler(Jobs(), PAINTING.parent / "ui")
