import json
from winnow.state import load_seen, filter_new, mark_seen


def test_load_seen_on_missing_file_returns_empty(tmp_path):
    assert load_seen(tmp_path / "seen.json") == {}


def test_filter_new_keeps_order_and_drops_known():
    seen = {"AAA": {"date": "2026-08-01", "folder": "github"}}
    assert filter_new(seen, ["AAA", "BBB", "CCC"]) == ["BBB", "CCC"]


def test_filter_new_drops_duplicates_within_the_batch():
    assert filter_new({}, ["AAA", "BBB", "AAA"]) == ["AAA", "BBB"]


def test_mark_seen_persists_and_is_read_back(tmp_path):
    p = tmp_path / "seen.json"
    mark_seen(p, ["AAA", "BBB"], "github", "2026-08-20")
    seen = load_seen(p)
    assert set(seen) == {"AAA", "BBB"}
    assert seen["AAA"] == {"date": "2026-08-20", "folder": "github"}


def test_mark_seen_is_additive(tmp_path):
    p = tmp_path / "seen.json"
    mark_seen(p, ["AAA"], "github", "2026-08-20")
    mark_seen(p, ["BBB"], "must-rewatch", "2026-08-21")
    assert set(load_seen(p)) == {"AAA", "BBB"}


def test_mark_seen_creates_parent_directory(tmp_path):
    p = tmp_path / "state" / "seen.json"
    mark_seen(p, ["AAA"], "github", "2026-08-20")
    assert p.exists()


def test_corrupt_seen_file_does_not_crash(tmp_path):
    """Un seen.json rotto non deve far ripartire tutto da capo in silenzio."""
    p = tmp_path / "seen.json"
    p.write_text("{ questo non e' json", encoding="utf-8")
    try:
        load_seen(p)
    except ValueError as e:
        assert "seen.json" in str(e)
    else:
        raise AssertionError("un file corrotto deve alzare ValueError, non tornare {}")
