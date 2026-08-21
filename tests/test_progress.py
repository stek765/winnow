from winnow.progress import line


def test_a_folder_says_how_many_are_new_not_just_how_many_exist():
    out = line("folder", {"name": "Salvati", "found": 24, "new": 8})
    assert "Salvati" in out and "24" in out and "8" in out


def test_a_post_is_numbered_so_you_know_how_far_it_has_got():
    out = line("post", {"i": 3, "n": 8, "account": "pycode.dev", "slides": 7})
    assert "3/8" in out and "pycode.dev" in out and "7" in out


def test_extraction_lists_the_names_it_actually_found():
    out = line("extracted", {"names": ["cline/cline", "firecrawl"], "usd": 0.0081})
    assert "cline/cline" in out and "firecrawl" in out


def test_extraction_says_so_when_a_post_named_nothing():
    out = line("extracted", {"names": [], "usd": 0.0}).lower()
    assert "no concrete name" in out


def test_a_verified_repo_shows_its_real_numbers():
    out = line("verified", {"name": "cline/cline", "checked": True, "exists": True,
                            "stars": 66542, "note": ""})
    assert "cline/cline" in out and "66542" in out and "✓" in out


def test_a_missing_repo_is_not_dressed_up_as_verified():
    out = line("verified", {"name": "ghost/repo", "checked": True, "exists": False,
                            "stars": None, "note": ""})
    assert "✗" in out and "✓" not in out


def test_unchecked_is_its_own_third_state():
    """checked=False is neither a pass nor a fail — collapsing them is the one
    thing this tool must never do."""
    out = line("verified", {"name": "Buzz", "checked": False, "exists": None,
                            "stars": None, "note": "nessuna fonte automatica"})
    assert "✓" not in out and "✗" not in out
    assert "?" in out or "—" in out


def test_the_last_line_is_the_one_you_would_screenshot():
    out = line("written", {"path": "findings/2026-08-20.json", "entities": 42,
                           "verified": 17, "usd": 0.0317})
    assert "2026-08-20.json" in out and "42" in out and "17" in out and "0.03" in out


def test_an_unknown_event_is_ignored_rather_than_crashing_a_paid_run():
    assert line("something-new", {}) == ""


def test_one_slide_is_not_one_slides():
    """Small, but it is the line printed most often in a run."""
    assert "1 slide" in line("post", {"i": 1, "n": 8, "account": "x", "slides": 1})
    assert "2 slides" in line("post", {"i": 1, "n": 8, "account": "x", "slides": 2})
