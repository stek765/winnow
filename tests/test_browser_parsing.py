import pytest
from winnow.browser import parse_shortcodes, looks_logged_out


def test_parse_shortcodes_extracts_post_links():
    hrefs = [
        "/", "/reels/", "/explore/",
        "/p/DcEYSBomGEy/", "/p/DcG0M83DmSS/",
        "/tizio/saved/github/111/",
    ]
    assert parse_shortcodes(hrefs) == ["DcEYSBomGEy", "DcG0M83DmSS"]


def test_parse_shortcodes_handles_absolute_urls_and_query():
    hrefs = ["https://www.instagram.com/p/AbC123/?img_index=3"]
    assert parse_shortcodes(hrefs) == ["AbC123"]


def test_parse_shortcodes_deduplicates_preserving_order():
    hrefs = ["/p/AAA/", "/p/BBB/", "/p/AAA/"]
    assert parse_shortcodes(hrefs) == ["AAA", "BBB"]


def test_parse_shortcodes_ignores_reel_links():
    """I reel hanno /reel/, non /p/. Fuori perimetro: non sono caroselli."""
    assert parse_shortcodes(["/reel/XYZ/", "/p/AAA/"]) == ["AAA"]


def test_looks_logged_out_detects_login_page():
    assert looks_logged_out(
        "https://www.instagram.com/accounts/login/", "Accedi a Instagram"
    )


def test_looks_logged_out_detects_login_text_on_any_url():
    assert looks_logged_out(
        "https://www.instagram.com/tizio/saved/github/111/",
        "Accedi a Instagram\nPassword dimenticata?",
    )


def test_looks_logged_out_is_false_on_a_real_page():
    assert not looks_logged_out(
        "https://www.instagram.com/tizio/saved/github/111/",
        "Solo tu puoi vedere gli elementi che hai salvato",
    )


def test_parse_saved_folders_takes_named_folders_only():
    """Instagram's own 'All posts' has no id: it must not become a folder."""
    from winnow.browser import parse_saved_folders
    hrefs = [
        "/someone/saved/github/111/",
        "/someone/saved/all-posts/",          # pseudo-folder
        "/someone/saved/github/111/",   # duplicate link
        "/someone/saved/gym/222/?next=1",
        "/explore/", "/p/ABCdefGHIjk/", None,
    ]
    assert parse_saved_folders(hrefs) == [
        ("github", "/someone/saved/github/111/"),
        ("gym", "/someone/saved/gym/222/"),
    ]
