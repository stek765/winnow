"""The recap as a page. Layout is code; judgement is not in here."""
from __future__ import annotations

import json

import pytest

from winnow.render import (
    _md, _stars, extract_json, kept_html, render, render_file, shared_slides,
    shot_for, sieve_html, slide_note, stopped_html,
)


def _item(**kw):
    base = {"title": "Rete cifrata su radio", "does": "Guarda cosa trasmettono",
            "name": "markqvist/Reticulum", "stars": 6965, "state": "alive"}
    base.update(kw)
    return base


# --- what you read first ------------------------------------------------------

def test_the_title_leads_and_the_repo_slug_is_the_footnote():
    """A repo slug is not scannable and scanning is the whole point — so the
    plain sentence is the heading and the name goes under it, not the other
    way round. Both are on the page: an entry with no URL used to lose its
    identity altogether."""
    out = kept_html(_item(), 0, "cat", None, None)
    assert out.index("Rete cifrata su radio") < out.index("markqvist/Reticulum")
    assert "7k★" in out


def test_the_state_is_never_invented():
    """An item with no state is unchecked, not alive: the page must not put a
    mark next to something nobody asked a source about."""
    out = kept_html({"title": "x"}, 0, "c", None, None)
    assert "s-unknown" in out and "s-alive" not in out


@pytest.mark.parametrize("state,cls", [
    ("alive", "s-alive"), ("stale", "s-stale"),
    ("absent", "s-absent"), ("unknown", "s-unknown"),
    ("nonsense", "s-nonsense"),
])
def test_every_state_gets_its_own_mark(state, cls):
    assert cls in kept_html({"title": "x", "state": state}, 0, "c", None, None)


def test_the_state_is_a_word_and_not_a_symbol():
    """A tick and a quarter-circle need a legend, and a page with a legend is
    a page that did not say it the first time."""
    out = kept_html({"title": "x", "state": "stale"}, 0, "c", None, None)
    assert "fermo" in out


@pytest.mark.parametrize("n,text", [
    (6965, "7k"), (999, "999"), (1000, "1k"), (26930, "26.9k"),
    (None, ""), ("", ""), ("abc", ""),
])
def test_stars_are_read_at_a_glance(n, text):
    assert _stars(n) == text


def test_a_zero_is_a_number_and_not_a_blank():
    """No failed posts is good news, and an empty box reads as a broken page."""
    assert "<b>0</b>" in render({"counts": {"posts": 15, "failed": 0}})


# --- the paragraph the judge writes -------------------------------------------

def test_the_comment_is_read_as_markdown_and_not_printed_as_asterisks():
    """Measured 2026-08-24: the recap's own paragraph rendered as
    `**e' la lista stessa**`, asterisks and all. A model writes bold without
    being asked, and raw asterisks read as the page being broken."""
    page = render({"comment": "sette nomi **non esistono** su `GitHub`"})
    assert "<strong>non esistono</strong>" in page
    assert "<code>GitHub</code>" in page
    assert "**" not in page


def test_markup_is_escaped_before_it_is_marked_up():
    """Escaped first, marked up second — never the reverse, or a caption
    becomes a script tag."""
    assert _md("<script>**x**</script>") == "&lt;script&gt;<strong>x</strong>&lt;/script&gt;"


# --- the picture --------------------------------------------------------------

def test_the_slide_the_reader_would_have_seen_is_the_one_shown(tmp_path):
    """Told in words, a judgement about a post cannot be checked without going
    back to Instagram — which is the thing nobody does."""
    for n in ("01", "02", "03"):
        (tmp_path / f"ABC123_{n}.png").write_bytes(b"x")
    got = shot_for({"post": "ABC123", "slide": 3}, tmp_path)
    assert got.endswith("ABC123_03.png")


def test_a_slide_that_was_never_captured_falls_back_to_the_first(tmp_path):
    """max_slides caps the capture, and a slide can fail on its own: showing
    the cover beats showing an empty square."""
    (tmp_path / "ABC123_01.png").write_bytes(b"x")
    assert shot_for({"post": "ABC123", "slide": 9}, tmp_path).endswith("_01.png")


def test_a_post_url_works_as_well_as_a_shortcode(tmp_path):
    (tmp_path / "ABC123_01.png").write_bytes(b"x")
    got = shot_for({"post": "https://www.instagram.com/p/ABC123/"}, tmp_path)
    assert got.endswith("ABC123_01.png")


def test_no_shot_is_not_a_broken_image(tmp_path):
    assert shot_for({"post": "NOPE"}, tmp_path) == ""
    assert "<img" not in kept_html({"title": "x", "post": "NOPE"},
                                   0, "c", tmp_path, tmp_path)


def test_the_picture_is_linked_relatively_so_the_folder_can_move(tmp_path):
    shots = tmp_path / "shots"; shots.mkdir()
    (shots / "ABC_01.png").write_bytes(b"x")
    out = kept_html({"title": "x", "post": "ABC"}, 0, "c", shots, tmp_path)
    assert 'src="shots/ABC_01.png"' in out


def test_a_list_slide_is_shown_and_labelled_rather_than_withheld(tmp_path):
    """⚠ This REVERSES the rule of 2026-08-24, deliberately, and the reason
    the old rule existed still stands: a wall of forty links is not a portrait
    of any one of them, and four tiles carrying that identical screenshot
    under four different labels is a lie.

    But withholding it put a coloured block there instead — and forty coloured
    blocks in a grid do not read as *"this came from a list"*. They read as
    **images that failed to load**, which is exactly what a reader reported.
    Showing the wall of links and *saying* it is one keeps the honesty and
    loses the bug: the picture then proves the caption.
    """
    (tmp_path / "LIST_03.png").write_bytes(b"x")
    item = {"post": "LIST", "slide": 3, "name": "o/x"}
    twin = {"post": "LIST", "slide": 3, "name": "o/y"}
    shared = shared_slides([item, twin])
    assert shot_for(item, tmp_path, None, shared).endswith("_03.png")
    assert slide_note(item, None, shared) == "questa slide ne nomina molti"
    out = kept_html(item | {"title": "x"}, 0, "c", tmp_path, tmp_path,
                    None, shared)
    assert "<img" in out and "ne nomina molti" in out


def test_the_caption_follows_the_slide_and_not_the_shape_of_the_post(tmp_path):
    """A list post still has slides that are about one thing. Measured
    2026-08-24: `GhidraGPT` sits alone on slide 4 of a post the collector
    called a list, and the shape-based caption announced that the slide named
    many — with the picture underneath showing one. A page contradicting its
    own evidence is worse than a page with no caption."""
    (tmp_path / "LIST_04.png").write_bytes(b"x")
    alone = {"post": "LIST", "slide": 4, "name": "o/only"}
    assert slide_note(alone, {"LIST": "list"}, shared_slides([alone])) == ""


def test_one_slide_shared_by_two_things_says_so(tmp_path):
    """Two things pointing at one slide means that slide is about neither of
    them on its own — true even when the collector did not call the post a
    list. The caption is what carries that, now that the picture stays."""
    a = {"post": "P", "slide": 2, "name": "o/a"}
    b = {"post": "P", "slide": 2, "name": "o/b"}
    c = {"post": "P", "slide": 5, "name": "o/c"}
    shared = shared_slides([a, b, c])
    assert shared == {("P", 2)}
    assert slide_note(a, {}, shared) == "questa slide ne nomina molti"
    assert slide_note(c, {}, shared) == ""


def test_two_different_things_never_get_the_same_block():
    from winnow.render import plate
    assert plate({"name": "o/alpha"}) != plate({"name": "o/beta"})


# --- the critical point -------------------------------------------------------

def test_the_doubt_is_on_the_page_next_to_the_thing():
    """Knowing where the weak points are is the reason to trust the rest — so
    it is read, not revealed by a click."""
    out = kept_html({"title": "x", "doubt": "quattro omonimi"}, 0, "c", None, None)
    assert "quattro omonimi" in out and "Dubbio" in out


def test_no_doubt_means_no_label():
    assert "Dubbio" not in kept_html({"title": "x"}, 0, "c", None, None)


def test_why_it_got_through_is_labelled_as_such():
    """The whole complaint was not being able to see why one thing was
    valued over another. The reason is a labelled field, not a paragraph the
    reader has to guess the purpose of."""
    out = kept_html({"title": "x", "why": "tocca la tesi"}, 0, "c", None, None)
    assert "Perche' passa" in out and "tocca la tesi" in out


# --- the sieve ----------------------------------------------------------------

def test_the_sieve_has_one_mark_per_thing_and_lights_the_kept_ones():
    """The signature element, and the only decoration: it is the ratio at the
    size the ratio deserves, made of the things themselves."""
    out = sieve_html([{"name": "a"}, {"name": "b"}],
                     [{"name": "c", "verdict": "LO CONOSCI"}])
    assert out.count('class="mk') == 3
    assert out.count('class="mk on"') == 2
    assert "2 passate" in out and "1 fermate" in out


def test_an_empty_week_has_no_sieve():
    assert sieve_html([], []) == ""


def test_every_mark_carries_its_own_name():
    """A graphic of the number would be decoration. Naming each mark makes it
    the number, made of the things."""
    out = sieve_html([], [{"name": "n8n-io/n8n", "verdict": "LO CONOSCI"}])
    assert "n8n-io/n8n" in out and "LO CONOSCI" in out


# --- what was stopped ---------------------------------------------------------

def test_a_stopped_thing_is_named_on_its_own_line():
    """The bin is per thing, never per bucket: a bucket cannot be corrected,
    because the reader cannot see which of the eighteen to argue with. Old
    recaps wrote `what` instead of `name`; they still render."""
    out = stopped_html([{"name": "n8n-io/n8n", "why": "lo conosci gia'"},
                        {"what": "un gruppo vecchio", "why": "motivo"}])
    assert "n8n-io/n8n" in out and "un gruppo vecchio" in out


def test_the_verdicts_are_counted_so_the_reasoning_can_be_argued_with():
    """Reading 129 prose lines says nothing about how the filter thinks.
    Seeing that 31 went as out-of-scope and 7 because GitHub has nothing under
    that name says it at a glance — and says which group to go argue with."""
    out = stopped_html([{"name": "a", "verdict": "NON ESISTE", "why": "x"},
                        {"name": "b", "verdict": "LO CONOSCI", "why": "y"},
                        {"name": "c", "verdict": "LO CONOSCI", "why": "z"}])
    assert 'data-v="NON ESISTE"' in out and 'data-v="LO CONOSCI"' in out
    assert "<b>2</b>" in out and "<b>1</b>" in out


def test_a_verdict_the_judge_invents_still_gets_printed():
    """A fixed list of verdicts would silently swallow whatever the judge
    reaches for next week."""
    out = stopped_html([{"name": "a", "verdict": "QUALCOSA DI NUOVO", "why": "x"}])
    assert "QUALCOSA DI NUOVO" in out and "a" in out


def test_a_reject_with_no_verdict_is_not_lost():
    out = stopped_html([{"name": "orfana", "why": "x"}])
    assert "orfana" in out and "ALTRO" in out


def test_nothing_stopped_means_no_section():
    assert stopped_html([]) == ""


# --- safety, shape, fallbacks -------------------------------------------------

def test_html_from_a_post_cannot_inject_markup():
    """Captions come from Instagram and the judgement from a model: neither is
    trusted input, and this page gets opened in a browser."""
    out = kept_html({"title": "<script>alert(1)</script>",
                     "name": '"><img src=x onerror=alert(1)>'},
                    0, "c", None, None)
    # What matters is that no tag survives as a tag: the word "onerror" as
    # escaped text is inert, an onerror= attribute is not.
    assert "<script>" not in out and "<img src=x" not in out
    assert "&lt;script&gt;" in out and "&lt;img" in out


def test_the_filters_name_every_category():
    page = render({"categories": [{"name": "Hardware", "items": []},
                                  {"name": "Trading", "items": []}]})
    assert 'data-cat="*"' in page
    assert "Hardware" in page and "Trading" in page


def test_nothing_is_hidden_from_a_browser_with_no_javascript():
    """A page that shows nothing without a script is a page that lost the
    recap. The filters are a convenience; the content is not behind them."""
    page = render({"categories": [{"name": "x", "items": [
        {"title": "primo", "why": "il motivo"}]}]})
    assert "primo" in page and "il motivo" in page and "<noscript>" in page


def test_the_page_paints_its_own_ground():
    """It commits to one look — a light table, because these are slides and
    that is where slides get reviewed. Committing is allowed; inheriting a
    background from whatever opens it is not."""
    page = render({"categories": []})
    assert "<style>" in page and "background" in page


def test_the_type_survives_with_no_network():
    """The faces are loaded from Google Fonts, so an archive opened on a plane
    has to fall back to something chosen rather than to whatever the browser
    picks."""
    page = render({"categories": []})
    assert "Helvetica Neue" in page and "ui-monospace" in page


def test_motion_can_be_switched_off():
    page = render({"categories": []})
    assert "prefers-reduced-motion" in page


def test_missing_pieces_do_not_break_the_page():
    """The judge is a model: it will leave something out one week."""
    page = render({})
    assert "<html" in page and "</html>" in page


# --- getting the model's answer in ---------------------------------------------

def test_the_model_answers_with_prose_around_its_json():
    """Asking someone to delete the sentences around the block before saving
    it is the step where this stops being used."""
    reply = 'Ecco il recap.\n\n```json\n{"week": "2026-08-23"}\n```\n\nBuona lettura.'
    assert extract_json(reply)["week"] == "2026-08-23"


def test_a_bare_json_file_still_works():
    assert extract_json('{"week": "x"}')["week"] == "x"


def test_a_file_with_no_json_at_all_says_so():
    with pytest.raises(json.JSONDecodeError):
        extract_json("nessun blocco qui")


def test_render_file_writes_next_to_its_source(tmp_path):
    src = tmp_path / "answer.json"
    src.write_text(json.dumps({"week": "x", "categories": []}), encoding="utf-8")
    out = render_file(src, shots=tmp_path / "nope")
    assert out == tmp_path / "answer.html" and out.exists()


def test_the_shape_comes_from_the_findings_and_not_from_the_judge(tmp_path):
    """One more field for a model to fill in is one more field to get wrong,
    and the collector already wrote this one down."""
    from winnow.render import shapes_from
    (tmp_path / "2026-08-23.json").write_text(json.dumps({"posts": [
        {"shortcode": "AAA", "shape": "list"},
        {"shortcode": "BBB", "shape": "other"}]}), encoding="utf-8")
    assert shapes_from(tmp_path) == {"AAA": "list", "BBB": "other"}


def test_a_corrupt_day_does_not_cost_the_page_its_pictures(tmp_path):
    from winnow.render import shapes_from
    (tmp_path / "bad.json").write_text("{{{", encoding="utf-8")
    assert shapes_from(tmp_path) == {}


def test_a_slide_nobody_recorded_is_not_printed_as_slide_zero(tmp_path):
    """`slide: 0` is how the collector says it never wrote one down. Printed
    literally under a picture it reads as an off-by-one in the page."""
    (tmp_path / "ABC_01.png").write_bytes(b"x")
    out = kept_html({"title": "x", "post": "ABC", "slide": 0}, 0, "c",
                    tmp_path, tmp_path)
    assert "slide 0" not in out
    assert "slide 4" in kept_html({"title": "x", "post": "ABC", "slide": 4},
                                  0, "c", tmp_path, tmp_path)
