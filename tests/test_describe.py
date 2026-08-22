"""What a thing is, and what is shaky about it — derived, never judged."""
from __future__ import annotations

from winnow.describe import describe, doubts, what_it_is

VERIFIED = {"checked": True, "exists": True, "stars": 2113,
            "last_commit": "2026-08-18",
            "description": "News aggregation with AI ratings"}


def test_the_source_speaks_before_the_post_does():
    """Two descriptions exist for most things: what GitHub says and what the
    caption claims. One is checked and one is written to be saved."""
    got = what_it_is({"kind": "repo", "blurb": "THE BEST TOOL EVER 🔥"}, VERIFIED)
    assert got["text"] == "News aggregation with AI ratings"
    assert got["from"] == "GitHub" and got["trusted"] is True


def test_the_post_is_used_but_labelled_as_the_post():
    """When the source says nothing the caption is all there is — and the
    reader has to know that is what they are reading."""
    got = what_it_is({"kind": "repo", "blurb": "sends files between computers"},
                     {"checked": True, "exists": True, "description": ""})
    assert got["text"] == "sends files between computers"
    assert got["from"] == "the post" and got["trusted"] is False


def test_an_unchecked_thing_still_gets_its_sentence_from_the_post():
    got = what_it_is({"kind": "platform", "blurb": "a hosted CRM"},
                     {"checked": False})
    assert got["text"] == "a hosted CRM" and got["trusted"] is False


def test_nothing_anywhere_is_reported_as_nothing():
    got = what_it_is({"kind": "claim"}, {"checked": False})
    assert got["text"] == ""


# --- doubts ---------------------------------------------------------------

def test_same_name_rivals_become_an_explicit_doubt():
    """The failure of 2026-08-21: `Numbat` resolved to a units calculator with
    2656 stars while the post meant perplexityai/numbat. Three real projects
    share that name, and that is a fact to hand over, not a coin to flip."""
    d = doubts({"kind": "repo", "name": "Numbat"},
               {**VERIFIED, "candidates": ("perplexityai/numbat (948★, 2026-08)",
                                           "kharchenkolab/numbat (226★, 2025-11)")},
               today="2026-08-22")
    assert any("3 different things answer to this name" in x for x in d)
    assert any("perplexityai/numbat" in x for x in d)


def test_a_tiny_name_match_is_flagged_as_a_probable_homonym():
    """`NautilusTrader` matched a 3-star repo while the real one has 26,930."""
    d = doubts({"kind": "repo", "name": "NautilusTrader"},
               {"checked": True, "exists": True, "stars": 3,
                "last_commit": "2024-04-01", "description": "x"},
               today="2026-08-22")
    assert any("homonym" in x for x in d)


def test_a_full_slug_is_not_flagged_for_being_small():
    """`owner/name` came from the post itself: nobody guessed it, so a low star
    count is just a small project."""
    d = doubts({"kind": "repo", "name": "BatchDrake/suscan"},
               {"checked": True, "exists": True, "stars": 143,
                "last_commit": "2026-08-01", "description": "x"},
               today="2026-08-22")
    assert not any("homonym" in x for x in d)


def test_an_old_last_commit_is_said_out_loud():
    d = doubts({"kind": "repo", "name": "a/b"},
               {"checked": True, "exists": True, "stars": 22914,
                "last_commit": "2024-08-01", "description": "x"},
               today="2026-08-22")
    assert any("months ago" in x for x in d)


def test_a_fresh_repo_raises_no_doubt():
    assert doubts({"kind": "repo", "name": "a/b", "blurb": "x"},
                  VERIFIED, today="2026-08-22") == []


def test_archived_is_finished_not_maintained():
    d = doubts({"kind": "repo", "name": "a/b"},
               {**VERIFIED, "archived": True}, today="2026-08-22")
    assert any("archived" in x for x in d)


def test_unchecked_carries_the_reason_over():
    d = doubts({"kind": "model", "name": "Claude"},
               {"checked": False, "note": "proprietary, or a different name"})
    assert any("proprietary" in x for x in d)


def test_absent_names_the_registry_that_was_asked():
    d = doubts({"kind": "model", "name": "Miso One"},
               {"checked": True, "exists": False})
    assert any("HuggingFace" in x for x in d)


def test_a_broken_date_does_not_crash_the_run():
    d = doubts({"kind": "repo", "name": "a/b", "blurb": "x"},
               {"checked": True, "exists": True, "stars": 900,
                "last_commit": "not-a-date", "description": "x"}, today="2026-08-22")
    assert d == []


# --- describe -------------------------------------------------------------

def test_describe_adds_and_never_removes():
    entity = {"kind": "repo", "name": "a/b", "blurb": "x", "slide": 2}
    got = describe(entity, VERIFIED, today="2026-08-22")
    assert got["kind"] == "repo" and got["slide"] == 2
    assert "what_it_is" in got and "doubts" in got
    assert got["verification"] == VERIFIED
