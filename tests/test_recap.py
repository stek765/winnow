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
    assert "Hook" in body and "Opening" in body


def test_prompt_body_falls_back_to_the_whole_file():
    from winnow.recap import prompt_body
    assert prompt_body("no marker here") == "no marker here"


# --- pointing at a file you already keep -----------------------------------

def test_include_pulls_in_the_linked_file(tmp_path):
    from winnow.recap import resolve_includes
    (tmp_path / "me.md").write_text("sono io, e ho escluso le crypto",
                                    encoding="utf-8")
    text, missing = resolve_includes(f"# My profile\n\n@{tmp_path / 'me.md'}\n")
    assert "sono io, e ho escluso le crypto" in text
    assert missing == []


def test_a_missing_include_is_reported_not_swallowed(tmp_path):
    """Half a profile that looks whole is the worst outcome: the recap would
    read as personalised while carrying none of the person."""
    from winnow.recap import resolve_includes
    text, missing = resolve_includes(f"@{tmp_path / 'gone.md'}")
    assert missing == [str(tmp_path / "gone.md")]
    assert "MANCA" in text


def test_relative_includes_resolve_next_to_the_profile(tmp_path):
    from winnow.recap import resolve_includes
    (tmp_path / "extra.md").write_text("altro contesto", encoding="utf-8")
    text, missing = resolve_includes("@extra.md", tmp_path)
    assert "altro contesto" in text and missing == []


def test_text_around_an_include_is_kept(tmp_path):
    from winnow.recap import resolve_includes
    (tmp_path / "a.md").write_text("INCLUSO", encoding="utf-8")
    text, _ = resolve_includes(f"prima\n@{tmp_path / 'a.md'}\ndopo")
    assert "prima" in text and "INCLUSO" in text and "dopo" in text


def test_an_email_or_a_path_is_not_an_include():
    """`@` only counts at the start of a line, alone: otherwise every mention
    of a handle would try to open a file."""
    from winnow.recap import resolve_includes
    text, missing = resolve_includes("scrivimi a me@example.com")
    assert missing == [] and text == "scrivimi a me@example.com"


# --- the bundle ends up in a chat window ----------------------------------

import pytest


@pytest.mark.parametrize("line", [
    "key = sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA",
    "GITHUB_TOKEN=ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "aws: AKIAIOSFODNN7EXAMPLE",
    "slack xoxb-1234567890-abcdefghij",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "fal: 2d5e8dcd-3bb6-40b1-bc71-19900099f23d:0198424289e5dea18e86eacfb31063",
])
def test_find_secrets_catches_real_credential_shapes(line):
    from winnow.recap import find_secrets
    assert find_secrets(line), line


@pytest.mark.parametrize("line", [
    "il token JWT serve per autenticare la richiesta",
    "auth = token nell'URL",
    "sk-",
    "parlo di api key in generale",
])
def test_find_secrets_does_not_cry_wolf(line):
    """Warning on every line containing "token" teaches people to skip the
    warning, which is worse than not having one."""
    from winnow.recap import find_secrets
    assert find_secrets(line) == []


def test_find_secrets_reports_the_line_number():
    from winnow.recap import find_secrets
    hits = find_secrets("prima\nseconda\nk = sk-ant-api03-BBBBBBBBBBBBBBBBBBBB")
    assert hits and hits[0].startswith("riga 3:")


def test_the_prompt_pins_the_output_language_to_the_profile():
    """Prompt in English, profile in Italian, and nothing saying which language
    to answer in: the model guessed, and could guess differently next week.
    Tying it to the profile is what makes it right for everyone, not just for
    whoever wrote the tool."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    assert "language my profile is written in" in body
