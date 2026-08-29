"""The recap as a page. Layout is code; judgement is not in here."""
from __future__ import annotations

import json
from datetime import date

import pytest

from winnow.render import (
    _md, _stars, counts_html, extract_json, kept_html, render, render_file,
    shared_slides, shot_for, slide_note, stopped_html,
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
    assert "untouched" in out


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
    assert slide_note(item, None, shared) == "this slide names many"
    out = kept_html(item | {"title": "x"}, 0, "c", tmp_path, tmp_path,
                    None, shared)
    assert "<img" in out and "this slide names many" in out


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
    assert slide_note(a, {}, shared) == "this slide names many"
    assert slide_note(c, {}, shared) == ""


def test_two_different_things_never_get_the_same_block():
    from winnow.render import plate
    assert plate({"name": "o/alpha"}) != plate({"name": "o/beta"})


# --- the critical point -------------------------------------------------------

def test_the_doubt_is_on_the_page_next_to_the_thing():
    """Knowing where the weak points are is the reason to trust the rest — so
    it is read, not revealed by a click."""
    out = kept_html({"title": "x", "doubt": "quattro omonimi"}, 0, "c", None, None)
    assert "quattro omonimi" in out and "Doubt" in out


def test_no_doubt_means_no_label():
    assert "Doubt" not in kept_html({"title": "x"}, 0, "c", None, None)


def test_why_it_got_through_is_labelled_as_such():
    """The whole complaint was not being able to see why one thing was
    valued over another. The reason is a labelled field, not a paragraph the
    reader has to guess the purpose of."""
    out = kept_html({"title": "x", "why": "tocca la tesi"}, 0, "c", None, None)
    assert "Why it got through" in out and "tocca la tesi" in out


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


# --- getting the answer back out of the chat window ---------------------------

def test_the_answer_can_come_straight_off_the_clipboard(monkeypatch, tmp_path):
    """`winnow recap` puts the bundle *on* the clipboard, so the answer coming
    back *off* it closes the loop with no file handling in between. "Save the
    model's whole answer to a file first" is a step, and a step is where this
    stops being used on a Sunday."""
    import winnow.render as R
    monkeypatch.setattr(R, "paste_from_clipboard",
                        lambda: '```json\n{"week": "2026-08-24"}\n```')
    out = R.render_clipboard(tmp_path, shots=tmp_path / "nope")
    assert out.exists() and out.suffix == ".html"
    # The answer itself is kept, not just the page built from it: a judgement
    # that cost real money must survive the next thing copied.
    assert out.with_suffix(".md").exists()
    assert "2026-08-24" in out.with_suffix(".md").read_text(encoding="utf-8")


def test_an_empty_clipboard_is_a_message_and_not_a_traceback(monkeypatch, tmp_path):
    import winnow.render as R
    monkeypatch.setattr(R, "paste_from_clipboard", lambda: "   ")
    with pytest.raises(ValueError, match="clipboard"):
        R.render_clipboard(tmp_path)


def test_a_clipboard_holding_something_else_says_so(monkeypatch, tmp_path):
    """Copying the wrong thing is the likeliest mistake here, and the message
    has to say which of the two went wrong."""
    import winnow.render as R
    monkeypatch.setattr(R, "paste_from_clipboard", lambda: "ciao come stai")
    with pytest.raises(json.JSONDecodeError):
        R.render_clipboard(tmp_path)


def test_two_answers_in_one_day_do_not_overwrite_each_other(monkeypatch, tmp_path):
    """Re-asking the model after correcting it is the normal way to use this,
    and the second answer must not silently destroy the first."""
    import winnow.render as R
    monkeypatch.setattr(R, "paste_from_clipboard",
                        lambda: '```json\n{"week": "w"}\n```')
    first = R.render_clipboard(tmp_path, shots=tmp_path / "nope")
    second = R.render_clipboard(tmp_path, shots=tmp_path / "nope")
    assert first != second and first.exists() and second.exists()


# --- why this one and not the other forty-nine --------------------------------

def test_a_thing_from_a_list_slide_shows_what_happened_to_its_neighbours():
    """The question a reader actually asks, and the page could not answer:
    «why bumblebee and not the other fifty?». The slide shows a wall of fifty
    links, one of them got through, and the reasons for the other forty-nine
    were a scroll away in a list of 129 rows — which is the same as not being
    there.

    Measured 2026-08-24: `perplexityai/bumblebee` shares slide 5 with ten
    other things. Naming those ten *next to it*, each with the verdict that
    stopped it, turns the wall of links from a confusing picture into the
    argument itself."""
    from winnow.render import siblings_map
    kept = [{"name": "o/keeper", "post": "P", "slide": 5}]
    stopped = [{"name": "o/other", "post": "P", "slide": 5,
                "verdict": "LO CONOSCI"},
               {"name": "o/elsewhere", "post": "P", "slide": 9,
                "verdict": "NON ESISTE"}]
    sib = siblings_map(kept, stopped)
    out = kept_html(kept[0], 0, "c", None, None, siblings=sib)
    assert "o/other" in out and "YOU KNOW IT" in out
    assert "o/elsewhere" not in out          # different slide, not a neighbour
    assert out.count("o/keeper") == 1        # never lists itself


def test_a_thing_alone_on_its_slide_says_nothing_about_neighbours():
    """Fourteen of the fifteen kept things sit alone on their slide. A block
    headed «on the same slide» with nothing in it is noise."""
    from winnow.render import siblings_map
    kept = [{"name": "o/alone", "post": "P", "slide": 1}]
    out = kept_html(kept[0], 0, "c", None, None,
                    siblings=siblings_map(kept, []))
    assert "stessa slide" not in out


def test_the_caption_counts_the_slide_instead_of_saying_many():
    """«this slide names many» is vague where a number is available, and the
    number is what tells you whether it is a list of three or of fifty."""
    from winnow.render import siblings_map
    kept = [{"name": "o/a", "post": "P", "slide": 2}]
    stopped = [{"name": f"o/{i}", "post": "P", "slide": 2} for i in range(11)]
    sib = siblings_map(kept, stopped)
    assert "12" in slide_note(kept[0], None, None, sib)


def test_the_name_is_readable_on_the_picture():
    """A wall of fifty links with no marking does not say which of the fifty
    this entry is. The name goes on the image itself."""
    out = kept_html({"title": "x", "name": "perplexityai/bumblebee",
                     "post": "P"}, 0, "c", None, None)
    assert "stamp" in out and "bumblebee" in out


# --- typography ---------------------------------------------------------------

def test_italian_on_the_page_is_written_with_real_accents():
    """Measured 2026-08-24: 123 words on one page written `e'`, `gia'`,
    `piu'`, `meta'`, `perche'`, `vulnerabilita'`. The meaning survives and the
    page still looks cheap — it is Italian typed like a 1990s terminal, and a
    reader said so before working out why. The file is UTF-8; there was never
    a reason."""
    from winnow.render import CSS, render
    page = render({"categories": [{"name": "c", "items": [
        {"title": "t", "why": "w", "doubt": "d", "post": "P"}]}],
        "discarded": [{"name": "n", "verdict": "V", "why": "r"}]})
    chrome = page.replace(CSS, "")
    for wrong in ("perche'", "e' ", "piu'", "gia'", "cioe'", "meta'", "puo'",
                  "li' ", "cosi'"):
        assert wrong not in chrome.lower(), wrong


def test_the_page_carries_the_winnower_s_mark():
    """A page with no mark is a page from nowhere. The tool is named after
    winnowing — tossing grain so the chaff blows away — which is the same
    gesture the page describes, so the mark is the basket, not a monogram."""
    from winnow.render import render
    page = render({"categories": []})
    assert "<svg" in page and 'class="mark"' in page
    assert "winnow" in page.lower()


def test_the_mark_is_drawn_and_never_fetched():
    """A logo loaded from a file is a logo missing from an archived page."""
    from winnow.render import logo_svg
    assert "<img" not in logo_svg() and "http" not in logo_svg()


# --- the chip has to say something --------------------------------------------

def test_the_chip_states_a_fact_and_not_a_category():
    """«VIVO» is a word about winnow's bookkeeping, not about the project: a
    reader asked, fairly, what it was supposed to mean. The chip is prime
    space — it says the thing that was actually checked."""
    from winnow.render import state_chip
    assert state_chip({"state": "alive", "last_commit": "2026-08"}) \
        == "last commit 2026-08"
    assert state_chip({"state": "stale", "last_commit": "2016-01"}) \
        == "untouched since 2016-01"
    assert state_chip({"state": "unknown"}) == "no source to ask"
    assert state_chip({"state": "absent"}) == "the source does not find it"
    # A date is not always there, and inventing one is worse than a plain word.
    assert state_chip({"state": "alive"}) == "found at the source"


def test_the_date_is_not_printed_twice():
    """Chip and footnote used to carry the same month, which reads as the page
    repeating itself rather than as two facts."""
    out = kept_html({"title": "x", "name": "o/r", "state": "alive",
                     "stars": 100, "last_commit": "2026-08"}, 0, "c", None, None)
    assert out.count("2026-08") == 1


def test_the_painting_travels_with_the_package():
    """The mark of this tool is Millet's winnower — it is the first thing in
    the README, and a recap that borrows the repo's identity has to carry it,
    not link to a checkout that an installed copy does not have."""
    from winnow.render import PAINTING
    assert PAINTING.exists() and PAINTING.stat().st_size > 10_000


def test_the_painting_is_embedded_and_never_linked():
    """The page gets moved, mailed, opened in three years. A file reference is
    a hole waiting to open; a data URI is not."""
    from winnow.render import render
    page = render({"categories": []})
    assert "data:image/jpeg;base64," in page
    assert "winnower.jpg" not in page


def test_the_painting_is_credited():
    """Public domain still has an author, and the repo already names him."""
    from winnow.render import render
    page = render({"categories": []})
    assert "Millet" in page


# --- the first screen ---------------------------------------------------------

def test_the_name_is_the_anchor_of_the_first_screen():
    """«WINNOW» used to be the smallest thing on the page — grey mono, 11px,
    top left — while the tool's name is what the reader has to remember."""
    from winnow.render import render
    page = render({"categories": []})
    assert 'class="wordmark"' in page
    assert ">winnow<" in page


def test_the_comment_is_marked_as_a_comment():
    """Set as plain body copy under the headline it reads as a subtitle, and a
    judgement that reads as a caption gets skimmed. It is the one piece of
    opinion on a page otherwise made of verified facts, and it has to look
    like one."""
    from winnow.render import render
    page = render({"comment": "qualcosa"})
    assert 'class="comment"' in page
    assert "The week's comment" in page


def test_the_painting_bleeds_instead_of_floating():
    """A dark reproduction with four hard edges, dropped on a light page, is a
    picture *on* the page rather than part of it. Masked into a dark band it
    stops being a rectangle."""
    from winnow.render import CSS
    assert "mask-image" in CSS and "-webkit-mask-image" in CSS


def test_the_headline_is_a_sentence_and_not_two_numbers():
    """«144 cose. 15 passate.» is a statistic set in 7rem — a reader said so:
    «il titolo è fatto da 2 numeri». The ratio is the product of this tool, so
    it stays in the headline, but it has to *say* something: what the second
    number means is the whole point, and «passate» is winnow's word, not the
    reader's."""
    from winnow.render import render
    page = render({"counts": {"kept": 15},
                   "categories": [{"name": "c", "items": [{"title": "t"}]}],
                   "discarded": [{"name": "x"}] * 8})
    assert "are worth your time" in page


def test_the_mark_sits_on_the_same_line_as_the_name():
    """The ear's viewBox carried empty space under the stem, so centring the
    box floated the drawing above the word beside it. A logo that does not sit
    on its own wordmark is the first thing anybody notices."""
    from winnow.render import logo_svg
    import re
    box = re.search(r'viewBox="([^"]+)"', logo_svg()).group(1).split()
    assert box[3] == "49", "the box must end where the stem ends"


def test_the_cost_is_a_stat_like_the_others():
    """It was the only cell with no bold number, so it had no first baseline
    to align on and floated above the row. A number and a label, like its
    neighbours."""
    out = counts_html({"posts": 30, "usd": 0.13})
    assert "<b>$0.13</b>" in out and "spent" in out


def test_an_unparsable_answer_is_still_written_down(monkeypatch, tmp_path):
    """`render_clipboard` used to validate before saving, so a JSON error
    destroyed the answer instead of the page: the model's reply is gone from
    the clipboard the moment anything else is copied — including the error
    message you copy to ask for help, which is exactly what happened on
    2026-08-25. Save first, parse second: a broken answer on disk can be
    fixed by hand, a lost one cannot."""
    import winnow.render as R
    monkeypatch.setattr(R, "paste_from_clipboard", lambda: '{\n  week: "x"\n}')
    with pytest.raises(json.JSONDecodeError):
        R.render_clipboard(tmp_path)
    saved = list(tmp_path.glob("*.answer*.md"))
    assert saved and "week" in saved[0].read_text(encoding="utf-8")


def test_the_parse_error_points_at_the_line_that_broke():
    """«Expecting property name enclosed in double quotes: line 2 column 3»
    tells you the grammar rule and not the text. Printing the line is what
    turns it into something you can fix."""
    from winnow.render import blame_json
    err = json.JSONDecodeError("Expecting property name", '{\n  week: 1\n}', 4)
    assert "week: 1" in blame_json('{\n  week: 1\n}', err)


# --- la pagina deve sopravvivere alla pulizia ---------------------------

def test_the_slides_can_travel_inside_the_page(tmp_path):
    """Le pagine puntano a una cartella condivisa che pesa 58 MB in due
    giorni (misurato 2026-08-25) e che nessuno pulisce. Non pulire sono
    decine di GB in un anno; pulire svuota le pagine vecchie — cioè proprio
    l'archivio. Dentro la pagina, come già il quadro, e il problema sparisce."""
    from winnow.render import render
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / "ABC_02.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    page = render({"categories": [{"name": "c", "items": [
        {"title": "t", "post": "ABC", "slide": 2}]}]},
        shots=shots, out_dir=tmp_path, embed_shots=True)
    assert "data:image/png;base64," in page
    assert "shots/ABC_02.png" not in page


def test_by_default_the_page_still_links_its_slides(tmp_path):
    """Il comportamento di oggi non cambia da sotto i piedi a nessuno."""
    from winnow.render import render
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / "ABC_02.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    page = render({"categories": [{"name": "c", "items": [
        {"title": "t", "post": "ABC", "slide": 2}]}]},
        shots=shots, out_dir=tmp_path)
    assert "shots/ABC_02.png" in page


def test_a_missing_slide_does_not_break_an_embedded_page(tmp_path):
    from winnow.render import render
    page = render({"categories": [{"name": "c", "items": [
        {"title": "t", "post": "NOPE", "slide": 1}]}]},
        shots=tmp_path, out_dir=tmp_path, embed_shots=True)
    assert "<html" in page and "data:image/png" not in page


# --- the slides have to survive leaving the folder --------------------------

def test_a_page_written_from_the_clipboard_carries_its_slides(
        tmp_path, monkeypatch):
    """It did not, and every image in it was broken the moment the page was
    read anywhere but from its own folder — over the app's own reader, for
    instance, where a relative `../state/shots/...` resolves to nothing.

    The comment on the other call site already said embedding is what makes a
    page outlive `state/shots/`. The clipboard path — the documented one —
    simply did not do it."""
    import winnow.render as R

    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / "ABC_01.png").write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")
    answer = json.dumps({
        "week": "2026-08-24", "counts": {"posts": 1, "kept": 1, "usd": 0.01},
        "comment": "x", "categories": [{"name": "X", "items": [
            {"name": "a/b", "why": "perché", "post": "ABC", "slide": 1}]}],
        "discarded": []})
    monkeypatch.setattr(R, "paste_from_clipboard", lambda: answer)

    out = R.render_clipboard(tmp_path / "recap", shots=shots,
                             now=date(2026, 8, 24))
    html = out.read_text(encoding="utf-8")
    assert "../state/shots/" not in html
    assert "data:image/png;base64," in html
