"""The recap as a page. Layout is code; judgement is not in here."""
from __future__ import annotations

import json

import pytest

from winnow.render import _stars, item_html, render, render_file


def test_what_it_does_is_the_headline_and_the_repo_is_the_footnote():
    """A repo slug is not scannable, and scanning is the whole point: the
    phrase saying what the thing does has to be the thing you read first."""
    out = item_html({"does": "Rete cifrata su radio a 150 bit/s",
                     "name": "markqvist/Reticulum", "stars": 6965,
                     "state": "alive"})
    assert out.index("Rete cifrata") < out.index("markqvist/Reticulum")
    assert 'class="does"' in out


def test_the_state_is_never_invented():
    """An item with no state is unchecked, not alive: the page must not put a
    tick next to something nobody asked a source about."""
    out = item_html({"does": "x", "name": "y"})
    assert "st-unknown" in out and "st-alive" not in out


@pytest.mark.parametrize("state,cls", [
    ("alive", "st-alive"), ("stale", "st-stale"),
    ("absent", "st-absent"), ("unknown", "st-unknown"),
    ("nonsense", "st-nonsense"),
])
def test_every_state_gets_its_own_mark(state, cls):
    assert cls in item_html({"does": "x", "state": state})


@pytest.mark.parametrize("n,text", [
    (6965, "7k"), (999, "999"), (1000, "1k"), (26930, "26.9k"),
    (None, ""), ("", ""), ("abc", ""),
])
def test_stars_are_read_at_a_glance(n, text):
    assert _stars(n) == text


def test_html_from_a_post_cannot_inject_markup():
    """Captions come from Instagram and the judgement from a model: neither is
    trusted input, and this page gets opened in a browser."""
    out = item_html({"does": '<script>alert(1)</script>',
                     "name": '"><img src=x onerror=alert(1)>'})
    # What matters is that no tag survives as a tag: the word "onerror" as
    # escaped text is inert, an onerror= attribute is not.
    assert "<script>" not in out and "<img" not in out
    assert "&lt;script&gt;" in out and "&lt;img" in out


def test_the_first_category_is_open_and_the_rest_are_not():
    """Everything closed is a page that looks empty; everything open is the
    wall of text this replaces."""
    page = render({"categories": [
        {"name": "uno", "items": [{"does": "a"}]},
        {"name": "due", "items": [{"does": "b"}]},
    ]})
    first, second = page.split('<details class="cat"')[1:3]
    assert first.startswith(" open")
    assert not second.startswith(" open")


def test_categories_carry_their_size():
    page = render({"categories": [{"name": "tanti", "items": [{"does": str(i)}
                                                              for i in range(12)]}]})
    assert '<span class="count">12</span>' in page


def test_a_page_with_no_javascript_still_opens_its_categories():
    """<details> and not JS tabs: it prints, it works from a saved file, and
    the keyboard opens it."""
    page = render({"categories": [{"name": "x", "items": []}]})
    assert "<details" in page and "<script" not in page


def test_the_page_is_self_contained():
    page = render({"categories": []})
    assert "<style>" in page
    assert "http://" not in page and "https://fonts" not in page


def test_the_page_works_in_both_themes():
    page = render({"categories": []})
    assert "prefers-color-scheme: dark" in page
    assert '[data-theme=dark]' in page


def test_render_file_writes_next_to_its_source(tmp_path):
    src = tmp_path / "answer.json"
    src.write_text(json.dumps({"week": "x", "categories": []}), encoding="utf-8")
    out = render_file(src)
    assert out == tmp_path / "answer.html" and out.exists()


def test_missing_pieces_do_not_break_the_page():
    """The judge is a model: it will leave something out one week."""
    page = render({})
    assert "<html" in page and "</html>" in page
