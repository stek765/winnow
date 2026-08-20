import pytest
from winnow.browser import slide_url


def test_slide_url_first_slide_has_no_query():
    assert slide_url("AbC123", 1) == "https://www.instagram.com/p/AbC123/"


def test_slide_url_uses_img_index_from_second_slide():
    assert slide_url("AbC123", 5) == "https://www.instagram.com/p/AbC123/?img_index=5"


def test_slide_url_rejects_index_below_one():
    with pytest.raises(ValueError):
        slide_url("AbC123", 0)


META = ('4,922 likes, 194 comments - getintoai su August 15, 2026: '
        '"GitHub is hiding some of the most useful AI tools.\n\nSave this. #ai"')


def test_parse_meta_caption_extracts_the_quoted_body():
    from winnow.browser import parse_meta_caption
    out = parse_meta_caption(META)
    assert out.startswith("GitHub is hiding")
    assert out.endswith("#ai")
    assert "likes" not in out


def test_parse_meta_caption_on_garbage_returns_empty():
    from winnow.browser import parse_meta_caption
    assert parse_meta_caption("nessuna caption qui") == ""


def test_parse_meta_account_extracts_the_handle():
    from winnow.browser import parse_meta_account
    assert parse_meta_account(META) == "getintoai"


def test_parse_meta_account_on_garbage_returns_empty():
    from winnow.browser import parse_meta_account
    assert parse_meta_account("niente") == ""
