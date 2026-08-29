"""The other half of the judgement: not what is worth reading, but what it
would do in one particular life.

Two things are being defended here — that the draw is random and that the
facts handed over are the ones that were checked. Everything else on this
page is speculation on purpose.
"""
from __future__ import annotations

import random

from winnow.ideas import (already_drawn, as_ideas, build_bundle, draw,
                          kept_things, render_ideas, render_things)

A = {"week": "2026-08-23", "counts": {"posts": 15, "kept": 9, "usd": 0.08},
     "categories": [{"name": "Modelli piccoli", "items": [
         {"name": "cactus/needle", "does": "Modello da 14 MB", "stars": 8575,
          "why": "l'unica cosa embedded", "last_commit": "2026-08-21"},
         {"name": "n8n-io/n8n", "does": "Automazioni", "why": "il tuo caso"}]}]}

B = {"week": "2026-08-24", "counts": {"posts": 30, "kept": 15, "usd": 0.13},
     "categories": [{"name": "Hardware", "items": [
         {"name": "needle", "why": "ricompare, e regge"}]}]}


def _archive(tmp_path, *answers):
    for a in answers:
        (tmp_path / f"{a['week']}.answer.md").write_text(
            "qualche parola\n```json\n" + __import__("json").dumps(a) + "\n```",
            encoding="utf-8")
    return tmp_path


def test_the_archive_is_read_as_one_wide_merge(tmp_path):
    """`needle` written two ways across two recaps is one thing here too —
    otherwise the same project gets drawn twice and the draw is a lie about
    how much there is."""
    things = kept_things(_archive(tmp_path, A, B))
    assert [t["name"] for t in things] == ["cactus/needle", "n8n-io/n8n"]
    needle = things[0]
    assert needle["stars"] == 8575 and len(needle["why"]) == 2


def test_a_broken_recap_does_not_take_the_draw_down_with_it(tmp_path):
    d = _archive(tmp_path, A)
    (d / "2026-08-25.answer.md").write_text("{ not json", encoding="utf-8")
    assert len(kept_things(d)) == 2


def test_a_merged_page_is_not_counted_as_a_judgement(tmp_path):
    """`unione-*.html` is derived from the answers. Reading it back would
    weight whatever happened to be merged, twice."""
    d = _archive(tmp_path, A)
    (d / "unione-abc.html").write_text("<html>", encoding="utf-8")
    (d / "idee-2026-08-26.answer.md").write_text("{}", encoding="utf-8")
    assert len(kept_things(d)) == 2


def test_an_empty_archive_draws_nothing_rather_than_raising(tmp_path):
    assert kept_things(tmp_path) == []


def test_the_draw_is_random_and_not_the_head_of_the_list():
    """A judge that always starts from the same three things answers with the
    ideas its reader already had."""
    things = [{"name": f"t{i}"} for i in range(40)]
    a = [t["name"] for t in draw(things, 12, random.Random(1))]
    b = [t["name"] for t in draw(things, 12, random.Random(2))]
    assert len(a) == 12 and len(set(a)) == 12
    assert a != b
    assert a != [t["name"] for t in things[:12]]


def test_a_short_archive_is_shuffled_rather_than_truncated():
    """Order is part of the draw: handed back alphabetically, the first three
    are read hardest and would be the same every single time."""
    things = [{"name": f"t{i}"} for i in range(5)]
    out = draw(things, 12, random.Random(3))
    assert sorted(t["name"] for t in out) == sorted(t["name"] for t in things)


def test_what_an_earlier_draw_already_showed_goes_last():
    """Pure chance over twenty things shows the model most of the same ones
    every run, and ideas about things already answered are noise."""
    things = [{"name": f"t{i}"} for i in range(20)]
    out = draw(things, 12, random.Random(4), used={f"t{i}" for i in range(10)})
    assert {t["name"] for t in out} >= {f"t{i}" for i in range(10, 20)}
    assert len(out) == 12


def test_the_draw_is_written_down_because_one_idea_cannot_report_it(tmp_path):
    """One idea names the pairing it used and says nothing about the other
    seven things the model read. Without the side file, every press would
    draw from the same eight names for ever."""
    (tmp_path / "idee-2026-08-27.answer.json").write_text(
        '{"drawn": ["a/b", "c/d", "e/f"], "usd": 0.01}', encoding="utf-8")
    assert already_drawn(tmp_path) == {"a/b", "c/d", "e/f"}


def test_a_side_file_that_counted_instead_of_naming_does_not_kill_the_run(tmp_path):
    """`drawn` held a count for one evening before it held the names. The
    first press after the change died with «TypeError: 'int' object is not
    iterable», before drawing anything."""
    (tmp_path / "idee-2026-08-27.answer.json").write_text(
        '{"drawn": 12, "usd": 0.06}', encoding="utf-8")
    assert already_drawn(tmp_path) == set()


def test_an_answer_from_before_the_side_file_is_still_read(tmp_path):
    """An archive written yesterday must not look like a draw that never
    happened."""
    (tmp_path / "idee-2026-08-26.answer.md").write_text(
        '```json\n{"ideas": [{"uses": ["a/b", "c/d"]}], '
        '"left": [{"name": "e/f", "why": "niente"}]}\n```', encoding="utf-8")
    assert already_drawn(tmp_path) == {"a/b", "c/d", "e/f"}


def test_an_answer_is_one_idea_now_and_was_a_page_of_them_before():
    """The file on disk is the artifact. One that stops opening because the
    ask changed is a promise broken after the money was spent."""
    assert len(as_ideas({"title": "Un ponte", "idea": "..."})) == 1
    assert len(as_ideas({"ideas": [{"title": "a"}, {"title": "b"}]})) == 2
    assert as_ideas({"note": "niente"}) == []


def test_deleting_an_idea_does_not_hand_its_things_back_to_the_pool(tmp_path):
    """A page is an artifact and may be thrown away; what has already been
    asked about is state. Reading the sidecars alone, deleting an idea from
    the archive put its eight things back among the never-drawn — so the very
    next press could offer the same handful again, which is the one way this
    feature turns into noise."""
    from winnow.ideas import remember_drawn

    pages, record = tmp_path / "recap", tmp_path / "drawn.json"
    pages.mkdir()
    side = pages / "idee-2026-08-27.answer.json"
    side.write_text('{"drawn": ["a/b", "c/d"], "usd": 0.01}', encoding="utf-8")
    remember_drawn(record, ["a/b", "c/d"])
    assert already_drawn(pages, record) == {"a/b", "c/d"}

    side.unlink()                      # the reader deletes the idea
    assert already_drawn(pages, record) == {"a/b", "c/d"}
    # And the pages are still read, so an archive older than the record is
    # not suddenly a draw that never happened.
    assert already_drawn(pages) == set()


def test_the_record_of_what_was_drawn_accumulates(tmp_path):
    """Each press adds to it. Overwriting would make the memory one draw
    deep, which is the same as no memory from the third press on."""
    from winnow.ideas import remember_drawn

    record = tmp_path / "drawn.json"
    remember_drawn(record, ["a/b"])
    remember_drawn(record, ["c/d", "a/b"])
    assert already_drawn(tmp_path, record) == {"a/b", "c/d"}


def test_a_record_that_cannot_be_read_is_not_a_dead_run(tmp_path):
    """Truncated or hand-edited, it must cost a repeated draw, never a
    traceback: nothing here is worth failing a run over."""
    record = tmp_path / "drawn.json"
    record.write_text("{oops", encoding="utf-8")
    assert already_drawn(tmp_path, record) == set()


def test_no_earlier_draw_is_not_an_error(tmp_path):
    assert already_drawn(tmp_path) == set()


def test_the_facts_handed_over_are_the_ones_that_were_checked():
    text = render_things([{"name": "cactus/needle", "title": "LLM da 14 MB",
                           "stars": 8575, "last_commit": "2026-08-21",
                           "url": "https://github.com/cactus/needle",
                           "why": [{"week": "2026-08-23", "text": "embedded"}],
                           "categories": ["Modelli"]}])
    assert "8575 stelle" in text and "ultimo commit 2026-08-21" in text
    assert "tenuta il 2026-08-23: embedded" in text


def test_the_profile_comes_after_the_things_and_before_the_ask():
    """Read first, a plan turns every drawn thing into a compliance check
    against it — measured on a real recap."""
    out = build_bundle("ASK", "IO SONO", [{"name": "x"}], 40)
    assert out.index("1. The draw") < out.index("IO SONO") < out.index("ASK")
    assert "1 of 40" in out


def test_no_mentality_block_reaches_the_ideas():
    """`mentality.md` teaches how to weigh a pile. Nothing here is being
    weighed, and a filter's instructions in front of a model asked to imagine
    is how ideas come back sounding like verdicts."""
    out = build_bundle("ASK", "IO", [{"name": "x"}], 4)
    assert "How to read a pile" not in out


def test_the_page_says_the_gist_the_cost_and_the_doubt():
    html = render_ideas({"title": "Un ponte", "uses": ["n8n"],
                         "gist": "Due righe che si capiscono da sole.",
                         "difficulty": "media", "time": "un weekend",
                         "idea": "Lo metti fra due cose.",
                         "first_step": "Una sera.",
                         "shaky": "Non è detto regga."},
                        [{"name": "a"}], 40, 0.06)
    assert "Un ponte" in html and "Non è detto regga." in html
    assert "Due righe che si capiscono da sole." in html
    assert "media" in html and "un weekend" in html
    assert "1 things drawn at random out of 40" in html


def test_a_page_of_ideas_from_before_still_renders_all_of_them():
    html = render_ideas({"note": "Pescata sparsa.",
                         "ideas": [{"title": "Uno"}, {"title": "Due"}],
                         "left": [{"name": "x/y", "why": "non tocca niente"}]},
                        [{"name": "a"}], 40, 0.06)
    assert "Uno" in html and "Due" in html
    assert "x/y" in html and "non tocca niente" in html


def test_a_name_that_looks_like_markup_cannot_become_markup():
    html = render_ideas({"title": "<script>alert(1)</script>",
                         "idea": "b & c"}, [], 1)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html and "b &amp; c" in html
