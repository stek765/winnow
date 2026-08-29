"""Pages already on disk follow a language changed today."""
from __future__ import annotations

import json

from winnow.relabel import rebuild_all

ANSWER = {
    "week": "2026-08-28",
    "comment": "il commento della settimana",
    "counts": {"posts": 10, "things": 40, "kept": 1, "usd": 0.06},
    "categories": [{"name": "agents", "items": [{
        "name": "cline/cline",
        "does": "Autonomous coding agent",
        "why": "shows whether agent coding is real work",
        "doubt": "the silence on failure modes is loud",
        "state": "alive", "last_commit": "2026-08"}]}],
    "discarded": [{"name": "n8n-io/n8n", "verdict": "LO CONOSCI",
                   "why": "everyone already has it"}],
}


def _week(d, day="2026-08-28", answer=None):
    (d / f"{day}.answer.md").write_text(
        json.dumps(answer or ANSWER), encoding="utf-8")
    page = d / f"{day}.answer.html"
    page.write_text("<html>stale</html>", encoding="utf-8")
    return page


def test_a_page_written_yesterday_follows_the_language_chosen_today(tmp_path):
    """The first answer was «an artifact does not retranslate itself», which
    is right about the judgement and wrong about the chrome: switch the window
    to English, open yesterday's recap, and «Perché passa» is still on it with
    nothing the reader can do but make a new one."""
    page = _week(tmp_path)
    assert rebuild_all(tmp_path, "en") == (1, [])
    assert "Why it got through" in page.read_text(encoding="utf-8")
    assert "Perché passa" not in page.read_text(encoding="utf-8")

    assert rebuild_all(tmp_path, "it") == (1, [])
    assert "Perché passa" in page.read_text(encoding="utf-8")


def test_the_judgement_itself_is_never_touched(tmp_path):
    """Only what winnow writes *around* the model's words. Rebuilt, not
    re-judged: nothing is asked of a model and nothing costs anything."""
    page = _week(tmp_path)
    rebuild_all(tmp_path, "en")
    out = page.read_text(encoding="utf-8")
    assert "shows whether agent coding is real work" in out
    assert "il commento della settimana" in out
    # And the answer beside it is left exactly as it was.
    assert json.loads((tmp_path / "2026-08-28.answer.md")
                      .read_text(encoding="utf-8")) == ANSWER


def test_a_verdict_keeps_its_key_and_changes_only_its_name(tmp_path):
    """`LO CONOSCI` is what the prompt asks for, what the order sorts by and
    what a merge groups on. A key that moved with the language would make two
    recaps of the same week ungroupable."""
    page = _week(tmp_path)
    rebuild_all(tmp_path, "en")
    out = page.read_text(encoding="utf-8")
    assert 'data-v="LO CONOSCI"' in out          # the key, untouched
    assert "YOU KNOW IT" in out                  # what the reader reads


def test_a_page_whose_judgement_is_missing_is_left_alone_and_reported(tmp_path):
    """Half a page, or a page replaced by an error message, loses a judgement
    that was paid for — which is far worse than a caption in the wrong
    language. And a failure nobody is told about is the same as a lie."""
    page = tmp_path / "2026-08-27.answer.html"
    page.write_text("<html>the only copy</html>", encoding="utf-8")
    done, failed = rebuild_all(tmp_path, "en")
    assert done == 0 and len(failed) == 1
    assert "2026-08-27.answer.html" in failed[0]
    assert page.read_text(encoding="utf-8") == "<html>the only copy</html>"


def test_a_page_winnow_did_not_write_is_not_a_failure(tmp_path):
    """The folder holds things dropped in by hand — a demo, an export. Listing
    those as failures teaches the reader to ignore the list of failures."""
    (tmp_path / "demo.html").write_text("<html>mine</html>", encoding="utf-8")
    _week(tmp_path)
    assert rebuild_all(tmp_path, "en") == (1, [])
    assert (tmp_path / "demo.html").read_text(encoding="utf-8") == "<html>mine</html>"


def test_a_second_recap_of_a_day_is_rebuilt_from_its_own_answer(tmp_path):
    """`…answer-3.html` is answered by `…answer-3.md`. Rebuilding it from the
    date would print a different judgement under the same name."""
    first = _week(tmp_path)
    other = dict(ANSWER, comment="il secondo tentativo")
    (tmp_path / "2026-08-28.answer-3.md").write_text(
        json.dumps(other), encoding="utf-8")
    second = tmp_path / "2026-08-28.answer-3.html"
    second.write_text("<html>stale</html>", encoding="utf-8")

    assert rebuild_all(tmp_path, "en") == (2, [])
    assert "il commento della settimana" in first.read_text(encoding="utf-8")
    assert "il secondo tentativo" in second.read_text(encoding="utf-8")


def test_an_ideas_page_is_rebuilt_too(tmp_path):
    """A draw is a page winnow writes, with its own chrome around the model's
    words — the difficulty, the time, what it cost."""
    (tmp_path / "idee-2026-08-28.answer.md").write_text(json.dumps({
        "title": "Un ponte", "gist": "prendere lo STEP",
        "difficulty": "media", "time": "una sera", "uses": ["a/b"]}),
        encoding="utf-8")
    (tmp_path / "idee-2026-08-28.answer.json").write_text(json.dumps({
        "usd": 0.02, "of": 40, "drawn": ["a/b", "c/d"]}), encoding="utf-8")
    page = tmp_path / "idee-2026-08-28.answer.html"
    page.write_text("<html>stale</html>", encoding="utf-8")

    assert rebuild_all(tmp_path, "en") == (1, [])
    out = page.read_text(encoding="utf-8")
    assert "Un ponte" in out and "difficulty" in out
    # The count is the draw's own, read back from the sidecar.
    assert "2 things" in out


def test_a_missing_folder_is_not_an_error(tmp_path):
    assert rebuild_all(tmp_path / "nope", "en") == (0, [])
