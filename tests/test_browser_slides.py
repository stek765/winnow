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


# --- pick_slide: which image on the page is actually the post -----------------

from winnow.browser import MIN_SLIDE_AREA, pick_slide


def _img(x, y, w, h, src="s"):
    return {"x": x, "y": y, "width": w, "height": h, "area": w * h, "src": src}


def test_the_post_slide_is_the_largest_image_on_the_left():
    imgs = [_img(-600, 100, 600, 600, "prev"), _img(0, 100, 600, 600, "now"),
            _img(600, 100, 600, 600, "next")]
    assert pick_slide(imgs)["src"] == "now"


def test_a_thin_banner_is_not_a_slide():
    """The real failure, post DcN9kKpqfDR on 2026-08-20: a 310x130 strip showing
    somebody's chat screenshot passed the old area check by 300 pixels and was
    sent to the model as 'slide 1'. Paying to look at the wrong image is worse
    than admitting there is no image."""
    assert pick_slide([_img(0, 40, 310, 130)]) is None


def test_a_thumbnail_is_not_a_slide():
    assert pick_slide([_img(0, 700, 160, 160)]) is None


def test_a_portrait_four_by_five_post_is_a_slide():
    """Instagram allows 4:5 portrait and 1.91:1 landscape. Both are real posts."""
    assert pick_slide([_img(0, 100, 480, 600)]) is not None
    assert pick_slide([_img(0, 100, 764, 400)]) is not None


def test_no_images_means_no_slide():
    assert pick_slide([]) is None


def test_the_area_floor_is_well_above_a_banner():
    assert MIN_SLIDE_AREA > 310 * 130
