"""Several weeks read as one page.

Merging is arranging, never weighing: what got through got through, and this
module must not re-decide it. Same rule as `digest.py`, one level up.
"""
from __future__ import annotations

import pytest

from winnow.harvest import label_for, merge

A = {"week": "2026-08-23", "counts": {"posts": 15, "kept": 9, "usd": 0.08},
     "comment": "Quindici post, ma una sola carosellata.",
     "categories": [
         {"name": "Modelli piccoli", "items": [
             {"name": "cactus/needle", "does": "Modello da 14 MB",
              "why": "l'unica cosa embedded", "stars": 8575,
              "last_commit": "2026-08-21", "url": "https://github.com/cactus/needle"},
             {"name": "n8n-io/n8n", "does": "Automazioni", "why": "il tuo caso"}]}]}

B = {"week": "2026-08-24", "counts": {"posts": 30, "kept": 15, "usd": 0.13},
     "comment": "Il grosso viene da liste.",
     "categories": [
         {"name": "Reverse engineering", "items": [
             {"name": "wm64/GhidraGPT", "title": "Un LLM dentro Ghidra",
              "why": "la linea che separa"}]},
         {"name": "Modelli piccoli", "items": [
             {"name": "cactus/needle", "why": "ricompare, e regge"}]}]}


def test_a_thing_kept_in_two_weeks_appears_once_and_says_both():
    """The whole point of one page instead of fifty-two: the same repo passing
    twice is one thing that passed twice, not two things."""
    out = merge([A, B])
    needle = [t for t in out["things"] if t["name"] == "cactus/needle"]
    assert len(needle) == 1
    assert needle[0]["weeks"] == ["2026-08-23", "2026-08-24"]


def test_the_facts_of_the_first_week_survive_a_thinner_second_one():
    """The model writes different fields week to week — measured on two real
    answers. A later mention with less in it must not blank what was known."""
    out = merge([A, B])
    needle = next(t for t in out["things"] if t["name"] == "cactus/needle")
    assert needle["stars"] == 8575 and needle["does"] == "Modello da 14 MB"
    assert needle["url"].endswith("/needle")


def test_both_reasons_are_kept_because_they_are_different_sentences():
    """`why` is the judgement, and two weeks gave two. Keeping only the first
    would throw away half of what the reader is here to re-read."""
    out = merge([A, B])
    needle = next(t for t in out["things"] if t["name"] == "cactus/needle")
    assert len(needle["why"]) == 2
    assert needle["why"][0]["week"] == "2026-08-23"
    assert "embedded" in needle["why"][0]["text"]


def test_every_category_a_thing_was_filed_under_travels_with_it():
    """The old rule — first week's category wins — deleted the second week's
    reading of the same thing, and *moved* it out of that week's section,
    which then rendered as a half-empty row. Choosing between two names is a
    judgement; this module makes none."""
    out = merge([A, B])
    needle = next(t for t in out["things"] if t["name"] == "cactus/needle")
    assert needle["categories"] == ["Modelli piccoli"]
    ghidra = next(t for t in out["things"] if t["name"] == "wm64/GhidraGPT")
    assert ghidra["categories"] == ["Reverse engineering"]
    assert "categories" not in out          # no taxonomy is invented here


def test_two_recaps_filing_one_thing_differently_keep_both_names():
    out = merge([A, {"week": "2026-08-25", "categories": [
        {"name": "Hardware", "items": [{"name": "cactus/needle"}]}]}])
    needle = next(t for t in out["things"] if t["name"] == "cactus/needle")
    assert needle["categories"] == ["Modelli piccoli", "Hardware"]


def test_the_same_repo_written_two_ways_is_one_thing():
    """`usestrix/strix` and `Strix` were printed as two on 2026-08-24, in two
    sections both called security. The owner is written when the slide shows
    it and dropped when it does not, so it cannot be part of the key — and
    the fuller name is the one a reader can look up."""
    out = merge([{"week": "2026-08-23", "categories": [
                    {"name": "S", "items": [{"name": "usestrix/strix",
                                             "stars": 57068}]}]},
                 {"week": "2026-08-24", "categories": [
                    {"name": "S", "items": [{"name": "Strix",
                                             "why": "ricompare"}]}]}])
    assert len(out["things"]) == 1
    assert out["things"][0]["name"] == "usestrix/strix"
    assert out["things"][0]["stars"] == 57068


def test_two_owners_of_the_same_short_name_stay_two_things():
    """Merging them would hang one project's stars on the other, which is the
    one failure worse than not checking at all."""
    out = merge([{"week": "2026-08-23", "categories": [
        {"name": "S", "items": [{"name": "foo/parser", "stars": 10},
                                {"name": "bar/parser", "stars": 90000}]}]}])
    assert len(out["things"]) == 2


def test_an_emoji_in_a_category_name_is_dropped():
    """One real answer put one there. The page bans them, and a heading is
    not the place to discover that."""
    out = merge([{"week": "2026-08-01", "categories": [
        {"name": "🔌 Modelli piccoli", "items": [{"name": "a/b"}]}]}])
    assert out["things"][0]["categories"] == ["Modelli piccoli"]


def test_the_counts_are_summed_and_the_weeks_listed_in_order():
    out = merge([B, A])                       # deliberately out of order
    assert out["weeks"] == ["2026-08-23", "2026-08-24"]
    assert out["counts"]["posts"] == 45 and out["counts"]["usd"] == 0.21
    # Not `kept`: 9 + 15 counts needle twice. What is on the page is the truth.
    assert out["counts"]["things"] == 3


def test_a_week_with_nothing_in_it_does_not_break_the_merge():
    out = merge([A, {"week": "2026-08-30"}])
    assert out["weeks"] == ["2026-08-23", "2026-08-30"]
    assert len(out["things"]) == 2


def test_merging_nothing_is_refused_rather_than_producing_an_empty_page():
    with pytest.raises(ValueError):
        merge([])


def test_the_label_never_turns_scattered_weeks_into_a_period():
    """`1 giugno – 24 agosto` for ten weeks picked out of a summer is a
    sentence that is not true: it reads as everything in between.

    Putting the count in front of it was not enough. A merge of the 23rd, the
    24th and the 28th came out as `3 recap, da 23 agosto a 28 agosto`, and the
    person who had just made it read the 27th into it — two dates with a
    preposition between them are a period whatever precedes them. So a
    handful of days is listed, and a list cannot be misread.
    """
    assert label_for(["2026-08-23"]) == "August 23"
    assert label_for(["2026-08-23", "2026-08-24"]) == "August 23 and 24"
    assert label_for(["2026-07-30", "2026-08-24"]) == "July 30 and August 24"
    # Italian says the month once at the other end of the phrase.
    assert label_for(["2026-08-23", "2026-08-24"],
                     lang="it") == "23 e 24 agosto"
    # The case that was misread. Neither language may imply the 25th to 27th.
    three = ["2026-08-23", "2026-08-24", "2026-08-28"]
    assert label_for(three) == "August 23, 24 and 28"
    assert label_for(three, lang="it") == "23, 24 e 28 agosto"
    # Two recaps of one day are one day: «28 agosto e 28 agosto» is not a
    # label, and the number of pages is printed beside it anyway.
    assert label_for(["2026-08-23", "2026-08-28", "2026-08-28"],
                     lang="it") == "23 e 28 agosto"
    ten = ["2026-06-01", "2026-06-05", "2026-06-09", "2026-07-03",
           "2026-07-08", "2026-07-15", "2026-07-22", "2026-08-02",
           "2026-08-10", "2026-08-24"]
    # Thirty days written out one by one is a paragraph, not a name — so past
    # a handful the label says the two dates are the ends of a *choice*.
    # "settimane" was a lie about a page made of ten *days*: recaps are
    # dated by the day they judge.
    assert label_for(ten) == "10 recaps chosen between June 1 and August 24"
    assert label_for(ten, lang="it") == \
        "10 recap scelti tra 1 giugno e 24 agosto"


def test_a_name_the_reader_gave_it_wins_over_any_label():
    """Ten weeks chosen out of a year are a theme, and a theme has a name.
    That is the only thing that makes a shelf of merges findable."""
    assert label_for(["2026-08-23", "2026-08-24"], "Embedded") == "Embedded"
    assert label_for(["2026-08-23"], "   ") == "August 23"


def test_two_different_selections_cannot_land_on_the_same_file():
    """Named from the first and last week, `{23, 30}` and `{23, 26, 30}` came
    out identical — measured — and the second silently overwrote the first."""
    from winnow.harvest import merge_id
    a = merge_id(["2026-08-23", "2026-08-30"], "")
    b = merge_id(["2026-08-23", "2026-08-26", "2026-08-30"], "")
    assert a != b
    # Same weeks, same file: merging the same selection twice replaces it
    # rather than piling up copies nobody can tell apart.
    assert a == merge_id(["2026-08-30", "2026-08-23"], "")


def test_the_name_is_part_of_what_makes_a_merge_distinct():
    """Same weeks, two different readings of them, two pages."""
    from winnow.harvest import merge_id
    assert (merge_id(["2026-08-23", "2026-08-24"], "Embedded")
            != merge_id(["2026-08-23", "2026-08-24"], "Personal AI"))


def test_a_file_name_carries_no_surprises_from_a_typed_name():
    """It goes into a path and into a URL."""
    from winnow.harvest import merge_id
    stem = merge_id(["2026-08-23", "2026-08-24"], "Robe da /comprare/ ../ !!")
    assert "/" not in stem and ".." not in stem and " " not in stem
    assert stem.startswith("unione-")


# --- the page ---------------------------------------------------------------

def test_the_page_names_every_thing_and_says_which_weeks_it_covers():
    from winnow.harvest import render_harvest
    html = render_harvest(merge([A, B]))
    for name in ("cactus/needle", "n8n-io/n8n", "wm64/GhidraGPT"):
        assert name in html
    assert "August 23 and 24" in html
    assert "Reverse engineering" in html   # as a tag on the thing


def test_a_thing_from_two_weeks_shows_both_reasons_with_their_dates():
    from winnow.harvest import render_harvest
    html = render_harvest(merge([A, B]))
    # Without the apostrophe: `_esc` turns it into `&#x27;`, which is correct
    # and is the whole reason the next test exists.
    assert "unica cosa embedded" in html and "ricompare, e regge" in html
    assert "August 23" in html and "August 24" in html


def test_a_name_that_looks_like_markup_cannot_become_markup():
    from winnow.harvest import render_harvest
    html = render_harvest(merge([{"week": "2026-08-01", "categories": [
        {"name": "X", "items": [{"name": "<script>alert(1)</script>",
                                 "why": "b & c"}]}]}]))
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html and "b &amp; c" in html


def test_the_painting_travels_with_the_page():
    """The merged page gets moved and mailed like the recap does. A link to a
    checkout is a hole waiting to open."""
    from winnow.harvest import render_harvest
    html = render_harvest(merge([A]))
    assert "data:image/jpeg;base64," in html
    assert "winnower.jpg" not in html
