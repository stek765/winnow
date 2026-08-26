"""What the app's home screen shows, decided here and not in the browser.

The window never decides anything (spec §7.3): it renders a state and sends
commands. So "which of the five faces is the home screen wearing" is a pure
function over facts read from disk — which is what makes it testable without
a browser, a key, or a cent of spend.
"""
from __future__ import annotations

import json
from datetime import datetime

from winnow.appstate import BRAKE, BUSY, LOGGED_OUT, NOTHING_NEW, READY, home


def _facts(**kw):
    base = dict(halted=False, logged_in=True, running=None, pending_posts=0,
                pending_days=0, last_collect=None, spend_usd=0.0)
    base.update(kw)
    return base


def test_posts_waiting_to_be_judged_is_the_normal_face():
    s = home(_facts(pending_posts=30, pending_days=3))
    assert s["state"] == READY
    assert s["action"] == "recap"
    assert "30" in s["headline"]


def test_no_new_posts_offers_a_collection_instead_of_a_recap():
    """Judging nothing costs money and produces an empty page. The button has
    to offer the thing that would actually help."""
    s = home(_facts(pending_posts=0))
    assert s["state"] == NOTHING_NEW
    assert s["action"] == "collect"


def test_a_run_in_flight_beats_everything_else():
    """While something is running, the only honest thing to offer is stopping
    it — even if the spend brake also happens to be tripped."""
    s = home(_facts(running={"kind": "collect", "done": 36, "of": 41},
                    halted=True, pending_posts=30))
    assert s["state"] == BUSY
    assert s["action"] == "stop"
    assert "36" in s["headline"] and "41" in s["headline"]


def test_a_dead_session_outranks_having_posts_to_judge():
    """With Instagram logged out nothing new will ever arrive, so offering a
    recap would send the reader down a path that ends nowhere."""
    s = home(_facts(logged_in=False, pending_posts=30))
    assert s["state"] == LOGGED_OUT
    assert s["action"] == "login"


def test_the_brake_outranks_work_but_not_a_run_in_flight():
    s = home(_facts(halted=True, pending_posts=30))
    assert s["state"] == BRAKE
    assert s["action"] == "reset-halt"


def test_every_face_names_exactly_one_thing_to_press():
    """Spec §5: there is never a screen where you cannot tell what to do."""
    for facts in (_facts(pending_posts=30), _facts(), _facts(halted=True),
                  _facts(logged_in=False),
                  _facts(running={"kind": "recap", "done": 1, "of": 3})):
        s = home(facts)
        assert s["action"] and s["button"] and s["headline"]


def test_the_spend_is_always_reported_whatever_the_face():
    for facts in (_facts(pending_posts=30, spend_usd=0.58), _facts(spend_usd=0.58)):
        assert home(facts)["spend_usd"] == 0.58


def test_a_stale_collection_is_said_and_not_hidden(tmp_path):
    """A run older than 36h means the daily job stopped and nobody noticed —
    which is exactly the failure winnow itself exists to prevent."""
    s = home(_facts(pending_posts=5, last_collect="2026-08-20T13:00:00"),
             now=datetime(2026, 8, 26, 10, 0))
    assert s["stale"] is True
    s2 = home(_facts(pending_posts=5, last_collect="2026-08-26T09:00:00"),
              now=datetime(2026, 8, 26, 10, 0))
    assert s2["stale"] is False


def test_a_missing_last_collect_is_not_called_stale():
    """Never collected and collected long ago are different sentences."""
    assert home(_facts())["stale"] is False


def test_facts_are_read_from_disk_without_a_browser(tmp_path):
    """`read_facts` is the only part that touches the filesystem, so the rest
    of this module stays pure."""
    from winnow.appstate import read_facts
    state = tmp_path / "state"
    state.mkdir()
    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "2026-08-25.json").write_text(json.dumps(
        {"posts": [{"shortcode": "A"}, {"shortcode": "B"}]}), encoding="utf-8")
    (state / "spend.json").write_text(json.dumps(
        [{"ts": "2026-08-25T10:00:00", "usd": 0.25}]), encoding="utf-8")

    facts = read_facts(state_dir=state, findings_dir=findings,
                       judged=tmp_path / "judged.json",
                       browser_profile=tmp_path / "nope",
                       now=datetime(2026, 8, 26, 10, 0))
    assert facts["pending_posts"] == 2 and facts["pending_days"] == 1
    assert facts["spend_usd"] == 0.25
    assert facts["logged_in"] is False      # no browser profile on disk


def test_reading_a_corrupt_findings_file_does_not_crash(tmp_path):
    from winnow.appstate import read_facts
    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "2026-08-25.json").write_text("{{{", encoding="utf-8")
    facts = read_facts(state_dir=tmp_path, findings_dir=findings,
                       judged=tmp_path / "j.json",
                       browser_profile=tmp_path / "nope",
                       now=datetime(2026, 8, 26, 10, 0))
    assert facts["pending_posts"] == 0


# --- what the screen has to be able to say ---------------------------------
#
# A home screen that reads "30 post da giudicare" over a button says how much
# work is waiting and nothing about what the work is. The numbers below are
# what the chain is made of — collected, checked at the source, judged — and
# the middle one is the whole reason winnow is not a bookmark folder.

def test_the_facts_carry_how_many_names_were_checked(tmp_path):
    """Posts are the container; the things named inside them are the product.
    Counting only posts hides the step nobody else performs."""
    from winnow.appstate import read_facts
    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "2026-08-25.json").write_text(json.dumps({"posts": [
        {"shortcode": "A", "entities": [
            {"name": "one", "verification": {"checked": True, "exists": True}},
            {"name": "two", "verification": {"checked": False}}]},
        {"shortcode": "B", "entities": [
            {"name": "three", "verification": {"checked": True, "exists": True}}]},
    ]}), encoding="utf-8")
    facts = read_facts(state_dir=tmp_path, findings_dir=findings,
                       judged=tmp_path / "j.json",
                       browser_profile=tmp_path / "nope",
                       now=datetime(2026, 8, 26, 10, 0))
    assert facts["pending_things"] == 3
    assert facts["pending_checked"] == 2


def test_a_post_with_no_entities_counts_zero_things_and_does_not_crash(tmp_path):
    from winnow.appstate import read_facts
    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "2026-08-25.json").write_text(
        json.dumps({"posts": [{"shortcode": "A"}]}), encoding="utf-8")
    facts = read_facts(state_dir=tmp_path, findings_dir=findings,
                       judged=tmp_path / "j.json",
                       browser_profile=tmp_path / "nope",
                       now=datetime(2026, 8, 26, 10, 0))
    assert facts["pending_things"] == 0 and facts["pending_checked"] == 0


def test_the_last_recap_is_named_by_its_week_and_not_by_its_mtime(tmp_path):
    """The file name is the week that was judged. The modification time is
    when the file happened to be written, which is a different fact and the
    wrong one to show beside 'ultimo giudizio'."""
    from winnow.appstate import read_facts
    recaps = tmp_path / "recap"
    recaps.mkdir()
    for day in ("2026-08-16", "2026-08-24"):
        (recaps / f"{day}.answer.html").write_text("<html>", encoding="utf-8")
    facts = read_facts(state_dir=tmp_path, findings_dir=tmp_path / "f",
                       judged=tmp_path / "j.json",
                       browser_profile=tmp_path / "nope", recaps=recaps,
                       now=datetime(2026, 8, 26, 10, 0))
    assert facts["last_recap"] == "2026-08-24"


def test_never_having_judged_is_a_state_and_not_a_missing_field(tmp_path):
    from winnow.appstate import read_facts
    facts = read_facts(state_dir=tmp_path, findings_dir=tmp_path / "f",
                       judged=tmp_path / "j.json",
                       browser_profile=tmp_path / "nope",
                       recaps=tmp_path / "nothing-here",
                       now=datetime(2026, 8, 26, 10, 0))
    assert facts["last_recap"] is None


def test_the_home_hands_the_chain_to_the_window(tmp_path):
    from winnow.appstate import home
    s = home({"pending_posts": 30, "pending_days": 3, "pending_things": 144,
              "pending_checked": 128, "last_recap": "2026-08-24",
              "logged_in": True})
    assert s["pending_things"] == 144 and s["pending_checked"] == 128
    assert s["last_recap"] == "2026-08-24"


def test_every_face_says_what_pressing_the_button_will_do():
    """The button names an action; it does not say what comes out of it. A
    reader who has not built this tool cannot guess that a recap is a page."""
    from winnow.appstate import home
    faces = [
        {"logged_in": True, "pending_posts": 30, "pending_days": 3},
        {"logged_in": True, "pending_posts": 0},
        {"logged_in": False},
        {"logged_in": True, "halted": True},
        {"logged_in": True, "running": {"done": 4, "of": 30}},
    ]
    for facts in faces:
        s = home(facts)
        assert s["consequence"], f"no consequence for {s['state']}"
        assert s["consequence"][-1] == ".", "it is a sentence, not a label"
