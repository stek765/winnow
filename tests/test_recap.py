"""The weekly bundle: gathering, never weighing."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from winnow.recap import build_bundle, week_files


def _findings(d: Path, day: str, entities: int = 2) -> Path:
    f = d / f"{day}.json"
    f.write_text(json.dumps({
        "spend_usd": 0.01, "failed": [],
        "posts": [{"shortcode": "AAA", "shape": "list", "account": "x",
                   "caption": "", "url": "", "entities": [
                       {"name": f"thing{i}", "kind": "repo",
                        "verification": {"checked": True, "exists": i == 0}}
                       for i in range(entities)]}]}), encoding="utf-8")
    return f


def test_week_is_the_last_seven_dates(tmp_path):
    for day in ("2026-08-21", "2026-08-15", "2026-08-14", "2026-07-01"):
        _findings(tmp_path, day)
    got = [p.stem for p in week_files(tmp_path, date(2026, 8, 21))]
    assert got == ["2026-08-15", "2026-08-21"]   # 08-14 is the 8th day back


def test_week_files_are_oldest_first(tmp_path):
    for day in ("2026-08-20", "2026-08-18", "2026-08-19"):
        _findings(tmp_path, day)
    assert [p.stem for p in week_files(tmp_path, date(2026, 8, 20))] == [
        "2026-08-18", "2026-08-19", "2026-08-20"]


def test_missing_findings_dir_is_empty_not_an_error(tmp_path):
    assert week_files(tmp_path / "nope", date(2026, 8, 21)) == []


def test_bundle_keeps_every_entity(tmp_path):
    """The bundler must not become the judge: what went in comes out, dead
    entries included. Dropping the unverified ones here would quietly decide
    what the model is allowed to see."""
    f = _findings(tmp_path, "2026-08-21", entities=4)
    out = build_bundle("PROMPT", "PROFILE", [f])
    for i in range(4):
        assert f"thing{i}" in out
    assert '"exists": false' in out


def test_bundle_order_is_prompt_profile_findings(tmp_path):
    f = _findings(tmp_path, "2026-08-21")
    out = build_bundle("THE-PROMPT", "THE-PROFILE", [f])
    assert out.index("THE-PROMPT") < out.index("THE-PROFILE") < out.index("thing0")


def test_bundle_names_each_day(tmp_path):
    files = [_findings(tmp_path, d) for d in ("2026-08-20", "2026-08-21")]
    out = build_bundle("p", "me", files)
    assert "### 2026-08-20" in out and "### 2026-08-21" in out
    assert "(2 days)" in out


def test_shipped_prompt_and_template_are_installed():
    """`winnow recap` runs from an installed copy, where docs/ does not exist."""
    pkg = Path(__file__).resolve().parents[1] / "winnow"
    assert (pkg / "recap-prompt.md").exists()
    assert (pkg / "profile-template.md").exists()


def test_prompt_body_starts_at_the_marker():
    """The file explains itself to a human first; a model must not be handed
    documentation about the instruction it is being given."""
    from winnow.recap import package_file, prompt_body
    full = package_file("recap-prompt.md")
    body = prompt_body(full)
    assert "The judge is not code" in full
    assert "The judge is not code" not in body
    assert body.startswith(">")
    assert "Aggancio" in body and "Apertura" in body


def test_prompt_body_falls_back_to_the_whole_file():
    from winnow.recap import prompt_body
    assert prompt_body("no marker here") == "no marker here"
