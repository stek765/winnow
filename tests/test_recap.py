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


def test_the_profile_comes_after_the_facts_and_the_mentality(tmp_path):
    """The week a profile drove the judgement, fifteen saved posts were
    dismissed by quoting the reader's own plan back at them. Contents first,
    then how to read them, then who is reading — and the ask last, because in a
    long context the last thing read is the thing that gets done."""
    f = _findings(tmp_path, "2026-08-21")
    out = build_bundle("THE-ASK", "THE-PROFILE", [f], "THE-MENTALITY")
    assert (out.index("thing0") < out.index("THE-MENTALITY")
            < out.index("THE-PROFILE") < out.index("THE-ASK"))


def test_the_profile_is_labelled_as_a_tint_not_a_filter(tmp_path):
    out = build_bundle("a", "me", [_findings(tmp_path, "2026-08-21")], "m")
    assert "tints it, it does not drive it" in out


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
    assert "language my profile is written in" in body


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
    assert "MISSING" in text


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


def test_the_bundle_carries_its_own_instructions():
    """`winnow recap` claims section 1 is the prompt, so section 1 has to be
    the prompt: otherwise the message is telling the user not to write
    something nobody wrote."""
    from winnow.recap import build_bundle
    out = build_bundle("THE ASK", "PROFILE", [], "MENTALITY")
    assert "## 4. What to produce" in out
    assert out.index("## 4. What to produce") < out.index("THE ASK")


# --- the mentality ships and is the same for everyone ---------------------

def test_the_mentality_travels_with_the_package():
    """It has to work from an installed copy, with no repo checkout in sight —
    and it is the block that makes winnow useful to someone who has not written
    a profile yet."""
    from winnow.recap import package_file
    text = package_file("mentality.md")
    assert "A saved post is a question, not a vote" in text
    assert "applies to advice, never to curiosity" in text


def test_the_mentality_says_nothing_about_one_particular_person():
    """It is block 2 precisely because it is identical for every user. A name,
    a city or a plan leaking in here would make it somebody's profile."""
    from winnow.recap import package_file
    text = package_file("mentality.md").lower()
    for personal in ("stefano", "eindhoven", "cra", "red directive", "firmware",
                     "vwce", "thesis"):
        assert personal not in text, personal


def test_the_mentality_carries_the_lessons_that_were_paid_for():
    from winnow.recap import package_file
    text = package_file("mentality.md")
    assert "watermark" in text                       # OmniGet, 29 posts
    assert "checked: false" in text                  # Claude, not absent
    assert "trusted" in text                         # caption vs source
    assert "may belong to another project" in text or "discarded" in text


def test_the_blocks_stay_the_top_level_of_the_bundle():
    """The mentality and the profile are whole documents with their own `##`
    headings. Pasted in raw they sit at the same rank as the four blocks and
    the reader loses the structure entirely."""
    from winnow.recap import build_bundle
    out = build_bundle("ask", "# My profile\n\n## Who I am\nx",
                       [], "# Mentality\n\n## A rule\ny")
    top = [l for l in out.splitlines() if l.startswith("## ")]
    assert all(l[3].isdigit() for l in top), top
