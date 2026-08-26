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


# --- changing the settings from the window ---------------------------------

def test_a_setting_can_be_changed_and_the_new_value_comes_straight_back(
        tmp_path, monkeypatch):
    """One round trip, not two: a window that has to re-ask after saving can
    show the old value for as long as the second request takes."""
    import winnow.api as A
    from tests.test_setup import CONFIG_SAMPLE
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG_SAMPLE, encoding="utf-8")
    monkeypatch.setattr(A.paths, "config_file", lambda: cfg)

    code, body = route("PATCH", "/api/config", {"posts_per_run": 30}, Jobs())
    assert code == 200
    assert body["posts_per_run"] == 30
    assert "posts_per_run = 30" in cfg.read_text(encoding="utf-8")


def test_a_refused_change_says_why_and_leaves_the_file_alone(
        tmp_path, monkeypatch):
    import winnow.api as A
    from tests.test_setup import CONFIG_SAMPLE
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG_SAMPLE, encoding="utf-8")
    monkeypatch.setattr(A.paths, "config_file", lambda: cfg)

    code, body = route("PATCH", "/api/config", {"posts_per_run": 0}, Jobs())
    assert code == 400 and "posts_per_run" in body["error"]
    assert cfg.read_text(encoding="utf-8") == CONFIG_SAMPLE


def test_the_key_cannot_be_written_from_the_window_either(tmp_path, monkeypatch):
    """It is refused on the way in for the same reason it is stripped on the
    way out: a route that could set it could be made to hand it back."""
    import winnow.api as A
    from tests.test_setup import CONFIG_SAMPLE
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG_SAMPLE, encoding="utf-8")
    monkeypatch.setattr(A.paths, "config_file", lambda: cfg)

    code, body = route("PATCH", "/api/config", {"api_key": "sk-ant-nope"}, Jobs())
    assert code == 400 and "api_key" in body["error"]
    assert "sk-ant-nope" not in cfg.read_text(encoding="utf-8")


def test_settings_cannot_be_rewritten_under_a_running_job(tmp_path, monkeypatch):
    """A collection reads the folder list and the post cap as it goes.
    Changing them underneath is a run that half obeyed two configurations."""
    import winnow.api as A
    from tests.test_setup import CONFIG_SAMPLE
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG_SAMPLE, encoding="utf-8")
    monkeypatch.setattr(A.paths, "config_file", lambda: cfg)

    jobs = Jobs()
    jobs.start("collect")
    code, body = route("PATCH", "/api/config", {"posts_per_run": 30}, jobs)
    assert code == 409 and cfg.read_text(encoding="utf-8") == CONFIG_SAMPLE


def test_the_window_is_told_which_models_it_may_offer():
    """Hard-coding the menu in the page would put the list in two places, and
    the copy in JavaScript is the one nobody updates."""
    code, body = route("GET", "/api/models", {}, Jobs())
    assert code == 200 and len(body["models"]) >= 3
    first = body["models"][0]
    assert {"label", "provider", "model", "hint"} <= set(first)


# --- asking Instagram which folders exist ----------------------------------

def test_scanning_for_folders_starts_a_job_like_any_other():
    """It opens a browser and waits on the network, so it cannot be a request
    that blocks until it is done — the window would look frozen."""
    jobs = Jobs()
    code, body = route("POST", "/api/folders/scan", {}, jobs,
                       spawn=lambda kind, jid, jobs: None)
    assert code == 202 and jobs.get(body["id"])["kind"] == "folders"


def test_a_scan_is_refused_while_something_else_runs():
    jobs = Jobs()
    route("POST", "/api/collect", {}, jobs, spawn=lambda *a: None)
    code, _ = route("POST", "/api/folders/scan", {}, jobs, spawn=lambda *a: None)
    assert code == 409


def test_a_job_can_carry_a_result_and_not_only_a_line_of_text():
    """The folders it found are data the window has to render as checkboxes.
    A progress line cannot be turned back into a list."""
    jobs = Jobs()
    jid = jobs.start("folders")
    jobs.finish(jid, 0, result={"folders": [
        {"name": "github", "url": "/x/saved/github/1/"}]})
    _, body = route("GET", f"/api/jobs/{jid}", {}, jobs)
    assert body["result"]["folders"][0]["name"] == "github"


def test_a_job_with_no_result_says_none_rather_than_missing_the_key():
    jobs = Jobs()
    jid = jobs.start("collect")
    jobs.finish(jid, 0)
    _, body = route("GET", f"/api/jobs/{jid}", {}, jobs)
    assert body["result"] is None


# --- the daily run ---------------------------------------------------------

def test_the_window_can_read_what_the_scheduler_holds(monkeypatch):
    import winnow.api as A
    from winnow.schedule import Scheduled
    monkeypatch.setattr("winnow.schedule.current", lambda: Scheduled(True, "13:00", "launchd"))
    code, body = route("GET", "/api/schedule", {}, Jobs())
    assert code == 200
    assert body["active"] is True and body["when"] == "13:00"
    assert body["how"] == "launchd"


def test_setting_an_hour_installs_it(monkeypatch):
    called = {}
    monkeypatch.setattr("winnow.schedule.install",
                        lambda h, m, which=None: called.update(h=h, m=m) or 0)
    monkeypatch.setattr("winnow.schedule.current",
                        lambda: __import__("winnow.schedule", fromlist=["x"]).Scheduled(True, "07:30", "launchd"))
    code, body = route("PATCH", "/api/schedule", {"at": "07:30"}, Jobs())
    assert code == 200 and called == {"h": 7, "m": 30}
    assert body["when"] == "07:30"


def test_an_hour_that_is_not_an_hour_is_refused(monkeypatch):
    code, body = route("PATCH", "/api/schedule", {"at": "domani"}, Jobs())
    assert code == 400 and body["error"]


def test_turning_the_daily_run_off_removes_it(monkeypatch):
    called = {}
    monkeypatch.setattr("winnow.schedule.remove",
                        lambda which=None: called.setdefault("off", True) or 0)
    monkeypatch.setattr("winnow.schedule.current",
                        lambda: __import__("winnow.schedule", fromlist=["x"]).Scheduled(False))
    code, body = route("PATCH", "/api/schedule", {"off": True}, Jobs())
    assert code == 200 and called == {"off": True} and body["active"] is False


def test_the_schedule_cannot_be_moved_while_a_run_is_going():
    jobs = Jobs()
    jobs.start("collect")
    code, _ = route("PATCH", "/api/schedule", {"at": "07:30"}, jobs)
    assert code == 409


# --- the profile -----------------------------------------------------------

def test_the_window_can_see_whether_a_profile_exists(tmp_path, monkeypatch):
    """It is the one file the whole judgement leans on, and the one nobody
    remembers writing. A window that never mentions it lets that happen."""
    import winnow.api as A
    prof = tmp_path / "profile.md"
    monkeypatch.setattr(A.paths, "profile_file", lambda: prof)
    code, body = route("GET", "/api/profile", {}, Jobs())
    assert code == 200 and body["exists"] is False and body["chars"] == 0
    prof.write_text("chi sono, in breve", encoding="utf-8")
    _, body = route("GET", "/api/profile", {}, Jobs())
    assert body["exists"] is True and body["chars"] == 18
    assert str(prof) in body["path"]


def test_the_profile_never_travels_over_the_api(tmp_path, monkeypatch):
    """Its size and its path, never its text: it is the most personal file
    winnow touches and the window has no reason to hold a copy."""
    import winnow.api as A
    prof = tmp_path / "profile.md"
    prof.write_text("stipendio, salute, tutto quanto", encoding="utf-8")
    monkeypatch.setattr(A.paths, "profile_file", lambda: prof)
    _, body = route("GET", "/api/profile", {}, Jobs())
    assert "stipendio" not in json.dumps(body)


# --- the API keys ----------------------------------------------------------
#
# Switching the provider in the window wrote `provider = "openai"` and stopped
# there: no key existed, nothing asked for one, and the next run died. A
# setting that can be changed into a broken state without saying so is worse
# than one that cannot be changed at all.

def test_the_window_is_told_which_keys_exist_and_never_their_value(
        tmp_path, monkeypatch):
    import winnow.api as A
    env = tmp_path / "env"
    env.write_text("ANTHROPIC_API_KEY=sk-ant-secret\n", encoding="utf-8")
    monkeypatch.setattr(A.paths, "env_file", lambda: env)
    code, body = route("GET", "/api/keys", {}, Jobs())
    assert code == 200
    assert body["keys"]["anthropic"] is True
    assert body["keys"]["openai"] is False
    # Booleans, never values: the answer travels to a page and there is no
    # reason for the page to be able to read the key back.
    assert "sk-ant-secret" not in json.dumps(body)


def test_a_key_can_be_written_but_not_read_back(tmp_path, monkeypatch):
    import winnow.api as A
    env = tmp_path / "env"
    monkeypatch.setattr(A.paths, "env_file", lambda: env)
    code, body = route("POST", "/api/keys",
                       {"provider": "openai", "key": "sk-openai-new"}, Jobs())
    assert code == 200 and body["keys"]["openai"] is True
    assert "sk-openai-new" in env.read_text(encoding="utf-8")
    assert "sk-openai-new" not in json.dumps(body)
    # The file holds a credential: it must not be readable by anyone else.
    assert oct(env.stat().st_mode)[-3:] == "600"


def test_an_empty_key_is_refused_rather_than_written(tmp_path, monkeypatch):
    """Written through, it looks set and fails at the next run — which is the
    exact failure this endpoint exists to stop."""
    import winnow.api as A
    env = tmp_path / "env"
    monkeypatch.setattr(A.paths, "env_file", lambda: env)
    for bad in ("", "   ", None):
        code, _ = route("POST", "/api/keys",
                        {"provider": "openai", "key": bad}, Jobs())
        assert code == 400
    assert not env.exists()


def test_a_provider_with_no_console_takes_no_key(tmp_path, monkeypatch):
    """A model on your own machine has no account and no bill."""
    import winnow.api as A
    monkeypatch.setattr(A.paths, "env_file", lambda: tmp_path / "env")
    code, _ = route("POST", "/api/keys",
                    {"provider": "local", "key": "whatever"}, Jobs())
    assert code == 400


def test_the_config_says_whether_the_chosen_provider_has_its_key(
        tmp_path, monkeypatch):
    """The one place it matters is beside the model that needs it."""
    import winnow.api as A
    from tests.test_setup import CONFIG_SAMPLE
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG_SAMPLE, encoding="utf-8")
    env = tmp_path / "env"
    monkeypatch.setattr(A.paths, "config_file", lambda: cfg)
    monkeypatch.setattr(A.paths, "env_file", lambda: env)
    _, body = route("GET", "/api/config", {}, Jobs())
    assert body["provider"] == "anthropic" and body["key_ready"] is False
    env.write_text("ANTHROPIC_API_KEY=sk-ant-x\n", encoding="utf-8")
    _, body = route("GET", "/api/config", {}, Jobs())
    assert body["key_ready"] is True


# --- the archive -----------------------------------------------------------
#
# It listed a file size. "186 KB" is a fact about a disk, not about a week,
# and it gave a reader no way to tell one entry from another — so the whole
# section read as a folder listing that happened to be in the app.

def _answer(week, kept, discarded, posts, usd, comment):
    return json.dumps({"week": week, "comment": comment,
                       "counts": {"posts": posts, "kept": kept, "usd": usd},
                       "discarded": discarded})


def test_a_week_is_listed_by_what_it_decided(tmp_path, monkeypatch):
    import winnow.api as A
    (tmp_path / "2026-08-24.answer.html").write_text("<html>", encoding="utf-8")
    (tmp_path / "2026-08-24.answer.md").write_text(
        _answer("2026-08-24", 15, 129, 30, 0.13, "Il grosso viene da liste."),
        encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    _, body = route("GET", "/api/recaps", {}, Jobs())
    row = body["recaps"][0]
    assert row["kept"] == 15 and row["things"] == 144      # kept + discarded
    assert row["posts"] == 30 and row["usd"] == 0.13
    assert row["comment"].startswith("Il grosso")


def test_a_page_whose_answer_was_lost_is_still_listed(tmp_path, monkeypatch):
    """The page is the product; the JSON beside it is bookkeeping. Dropping
    the row would hide a recap that opens perfectly well."""
    import winnow.api as A
    (tmp_path / "2026-08-20.answer.html").write_text("<html>", encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    _, body = route("GET", "/api/recaps", {}, Jobs())
    assert body["recaps"][0]["week"] == "2026-08-20"
    assert body["recaps"][0]["kept"] is None


def test_a_broken_answer_does_not_take_the_archive_down(tmp_path, monkeypatch):
    import winnow.api as A
    (tmp_path / "2026-08-20.answer.html").write_text("<html>", encoding="utf-8")
    (tmp_path / "2026-08-20.answer.md").write_text("{{{", encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    code, body = route("GET", "/api/recaps", {}, Jobs())
    assert code == 200 and body["recaps"][0]["kept"] is None


def test_only_pages_named_after_a_week_are_listed(tmp_path, monkeypatch):
    """The archive is the weeks winnow judged. A page dropped in that folder
    by hand — a demo, an export — is not one of them, and listing it beside
    them says it is."""
    import winnow.api as A
    for name in ("2026-08-24.answer.html", "demo-motore.html", "notes.html"):
        (tmp_path / name).write_text("<html>", encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    _, body = route("GET", "/api/recaps", {}, Jobs())
    assert [r["week"] for r in body["recaps"]] == ["2026-08-24"]


# --- merging, and deleting --------------------------------------------------

def test_merging_two_weeks_writes_a_page_and_says_where(tmp_path, monkeypatch):
    import winnow.api as A
    for week, kept in (("2026-08-23", 9), ("2026-08-24", 15)):
        (tmp_path / f"{week}.answer.html").write_text("<html>", encoding="utf-8")
        (tmp_path / f"{week}.answer.md").write_text(json.dumps({
            "week": week, "counts": {"posts": 10, "kept": kept, "usd": 0.05},
            "categories": [{"name": "X", "items": [
                {"name": f"a/{week}", "why": "perché sì"}]}]}), encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)

    code, body = route("POST", "/api/merge",
                       {"weeks": ["2026-08-23", "2026-08-24"]}, Jobs())
    assert code == 200
    page = tmp_path / body["file"]
    assert page.is_file() and "23 e 24 agosto" in page.read_text(encoding="utf-8")
    assert body["label"] == "23 e 24 agosto"


def test_a_merge_can_be_given_a_name_and_keeps_it(tmp_path, monkeypatch):
    """Ten weeks out of a year are a theme. Without a name there is nothing
    to find them by."""
    import winnow.api as A
    for week in ("2026-08-23", "2026-08-24"):
        (tmp_path / f"{week}.answer.md").write_text(json.dumps({
            "week": week, "counts": {}, "categories": [
                {"name": "X", "items": [{"name": f"a/{week}"}]}]}),
            encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    _, body = route("POST", "/api/merge", {
        "weeks": ["2026-08-23", "2026-08-24"], "name": "Embedded"}, Jobs())
    assert body["label"] == "Embedded"
    page = (tmp_path / body["file"]).read_text(encoding="utf-8")
    assert "Embedded" in page
    # And it still says what it was made from, or the title has nothing
    # behind it a month later.
    assert "23 agosto" in page and "24 agosto" in page
    _, listing = route("GET", "/api/recaps", {}, Jobs())
    assert listing["merges"][0]["label"] == "Embedded"


def test_a_merge_is_listed_apart_from_the_weeks_it_covers(tmp_path, monkeypatch):
    """It is not a week. Listed among them it would claim to be one."""
    import winnow.api as A
    (tmp_path / "2026-08-24.answer.html").write_text("<html>", encoding="utf-8")
    (tmp_path / "unione-embedded-1a2b3c4d.html").write_text(
        "<html>", encoding="utf-8")
    (tmp_path / "unione-embedded-1a2b3c4d.json").write_text(json.dumps(
        {"weeks": ["2026-08-23", "2026-08-24"], "label": "23–24 agosto",
         "things": 21}), encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    _, body = route("GET", "/api/recaps", {}, Jobs())
    assert [r["week"] for r in body["recaps"]] == ["2026-08-24"]
    assert body["merges"][0]["label"] == "23–24 agosto"
    assert body["merges"][0]["things"] == 21


def test_merging_fewer_than_two_weeks_is_refused(tmp_path, monkeypatch):
    import winnow.api as A
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    code, _ = route("POST", "/api/merge", {"weeks": ["2026-08-24"]}, Jobs())
    assert code == 400


def test_a_week_whose_judgement_is_gone_cannot_be_merged_silently(
        tmp_path, monkeypatch):
    """The page can be reopened without its answer, but it cannot be merged:
    the answer *is* the content. Producing a page missing half of what was
    asked for, without saying so, is the failure this repo keeps paying for."""
    import winnow.api as A
    (tmp_path / "2026-08-24.answer.html").write_text("<html>", encoding="utf-8")
    (tmp_path / "2026-08-23.answer.md").write_text(json.dumps(
        {"week": "2026-08-23", "categories": []}), encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    code, body = route("POST", "/api/merge",
                       {"weeks": ["2026-08-23", "2026-08-24"]}, Jobs())
    assert code == 400 and "2026-08-24" in body["error"]


def test_deleting_a_week_takes_its_page_and_its_judgement(tmp_path, monkeypatch):
    import winnow.api as A
    for name in ("2026-08-24.answer.html", "2026-08-24.answer.md",
                 "2026-08-24.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "2026-08-23.answer.html").write_text("x", encoding="utf-8")
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)

    code, body = route("DELETE", "/api/recaps/2026-08-24.answer.html", {}, Jobs())
    assert code == 200 and sorted(body["removed"]) == [
        "2026-08-24.answer.html", "2026-08-24.answer.md", "2026-08-24.md"]
    assert not (tmp_path / "2026-08-24.answer.html").exists()
    assert (tmp_path / "2026-08-23.answer.html").exists()   # nothing else moved


def test_a_delete_cannot_reach_outside_the_recap_folder(tmp_path, monkeypatch):
    """The name arrives in a URL. `../` in it must not become a path."""
    import winnow.api as A
    monkeypatch.setattr(A.paths, "recap_dir", lambda: tmp_path)
    secret = tmp_path.parent / "keep-me.html"
    secret.write_text("x", encoding="utf-8")
    code, _ = route("DELETE", "/api/recaps/../keep-me.html", {}, Jobs())
    assert code == 404 and secret.exists()
