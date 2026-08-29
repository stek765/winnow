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
    # Arranged, not dumped — but absence still has to be said out loud.
    assert "the source has nothing under this name" in out


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


def test_the_week_is_one_pile_not_one_heading_per_day(tmp_path):
    """A day is how findings are *stored*, not how they are read. Split by
    day, the same project named on Monday and on Thursday is two entries and
    the reader does the merging by hand."""
    files = [_findings(tmp_path, d) for d in ("2026-08-20", "2026-08-21")]
    out = build_bundle("p", "me", files)
    assert "### 2026-08-20" not in out and "### 2026-08-21" not in out
    assert "(2 days)" in out
    assert out.count("**thing0**") == 1


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
    assert "Write the recap in English." in body


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


def test_the_prompt_pins_the_output_language_to_the_chosen_one():
    """Prompt in English, profile in Italian, and nothing saying which language
    to answer in: the model guessed, and could guess differently next week.

    It was pinned to the profile's language first, which was the best anchor
    available while the app had no language of its own. Now it has one, chosen
    explicitly in the window — and an English window whose ideas come back in
    Italian is winnow disagreeing with a setting the reader has just changed.
    Both prompts are pinned, not only the recap's: the draw is a page too."""
    from winnow.recap import package_file, prompt_body
    for name in ("recap-prompt.md", "ideas-prompt.md"):
        assert "{language}" in package_file(name), (
            f"{name} no longer says which language to answer in")
        assert "in English." in prompt_body(package_file(name), "en")
        assert "in Italian." in prompt_body(package_file(name), "it")
        # Never the raw placeholder: a model handed `{language}` answers in
        # whatever it feels like, which is the state this replaced.
        assert "{language}" not in prompt_body(package_file(name), "it")


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


def test_the_prompt_bins_one_thing_per_line_and_never_one_group_per_line():
    """The recap of 2026-08-23 threw away eighteen repos in a single line —
    "the mega-list of eternal repos (~18 entries)" — and in the same breath
    kept four entries of that same list as finds. The bin exists to be
    corrected, and a bucket cannot be corrected: the reader cannot see which
    eighteen, so cannot say "that one was wrong".

    A list post is packaging. Its thirty-fourth entry is a thing somebody
    saved, judged exactly like a thing that was the whole subject of its own
    post."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    assert "One line per thing, never one line per group" in body
    assert "appears exactly once: either above, or here" in body
    # The old wording licensed dropping things entirely.
    assert "not to be exhaustive" not in body


def test_the_mentality_says_the_container_does_not_decide():
    """Block 2, so it holds for everyone: what a thing is worth does not
    depend on whether it arrived alone or as entry 34 of a listicle."""
    from winnow.recap import package_file
    text = package_file("mentality.md")
    assert "The container does not decide" in text


def test_the_prompt_asks_for_the_verdict_that_stopped_each_thing():
    """The page groups rejects by verdict and counts them — that is how the
    reader sees the filter's shape instead of 129 prose lines. Invented by
    hand once on 2026-08-24 and not asked for anywhere, the next recap would
    have come back without them and the section would render as one flat
    heap."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    assert '"verdict"' in body
    for verdict in ("NON ESISTE", "FERMO DA ANNI", "LO CONOSCI",
                    "FUORI BERSAGLIO", "CHI CI GUADAGNA"):
        assert verdict in body, verdict


def test_the_prompt_keeps_section_names_short():
    """Long section names are unreadable as filter chips — measured at eleven
    words on the first run, wrapping over two lines each."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    assert "at most three words" in body


def test_the_prompt_asks_for_no_emoji():
    """The schema used to carry `"icon": "one emoji"`, which is an instruction
    to put one there."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    assert "No emoji" in body
    assert '"icon"' not in body


def test_the_comment_is_asked_to_point_somewhere():
    """First run came back with five paragraphs restating the counts printed
    directly above it. A comment earns its place by saying the thing the
    numbers cannot."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    assert "Never restate a number" in body


def test_the_prompt_makes_each_line_stand_on_its_own():
    """Measured 2026-08-24, from a reader: «devo usare il titolo per dare un
    senso alla frase». Every `why` that week opened on a pronoun — «È l'unica
    cosa della settimana...» — so the reader had to look back up at the
    heading to learn what «it» was, on every entry. And a doubt read «Nessuno
    dai dati.», which is not a sentence at all.

    Three rules kill the whole class: name the subject, one idea per sentence,
    and no fragments."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    assert "Never open on a pronoun" in body
    assert "stand on its own without the heading" in body
    assert "Whole sentences" in body


def test_a_json_error_is_not_swallowed_by_the_empty_clipboard_handler(
        monkeypatch, tmp_path, capsys):
    """`json.JSONDecodeError` **inherits from `ValueError`**, so an
    `except ValueError` written above it catches every parse error first and
    the JSON branch becomes dead code. Measured 2026-08-25: a broken answer
    printed the bare grammar message and none of the help — the specific
    handler never ran."""
    import winnow.cli as C
    import winnow.render as R
    monkeypatch.setattr(R, "paste_from_clipboard", lambda: '{\n  week: 1\n}')
    monkeypatch.setattr(C.paths, "recap_dir", lambda: tmp_path)
    monkeypatch.setattr(C.paths, "shots_dir", lambda: tmp_path / "shots")
    monkeypatch.setattr(C.paths, "findings_dir", lambda: tmp_path / "f")

    class Args:
        file = None
    assert C._cmd_render(Args()) == 2
    err = capsys.readouterr().err
    assert "not valid JSON" in err
    assert "week: 1" in err          # the line that broke, not just the rule
    assert "Saved anyway" in err     # and where to find the answer


def test_the_prompt_forbids_a_reason_that_fits_twenty_things():
    """Measured twice on 2026-08-25, by two different models on the same
    bundle: «one line per thing» was honoured typographically and gutted in
    substance. One run put the reason in the group heading and left the names
    bare; the other wrote `"why": "famoso"` twenty times. A word that fits
    twenty things is the group's name written again — and it cannot be
    argued with, which is the only reason the bin exists."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    # Checked on a fragment that survives line wrapping.
    assert "twenty things is not a reason" in body


def test_the_prompt_forbids_resolving_an_unchecked_thing_from_memory():
    """`Home Assistant` came back as LO CONOSCI, «famoso» — while the data
    said `checked: false`. The model answered from what it knew instead of
    from what was verified, which is the one thing the mentality forbids, and
    saying it there was not enough."""
    from winnow.recap import package_file, prompt_body
    body = prompt_body(package_file("recap-prompt.md"))
    assert "never becomes `LO CONOSCI`" in body


# --- one command -----------------------------------------------------

def _fixture(tmp_path, monkeypatch, days=("2026-08-25",)):
    """A fake, complete winnow: findings, profile, folders."""
    import json as _json

    import winnow.recap as R
    findings = tmp_path / "findings"
    findings.mkdir()
    for d in days:
        (findings / f"{d}.json").write_text(_json.dumps(
            {"spend_usd": 0.01,
             "posts": [{"shortcode": "A", "shape": "news", "entities": []}]}),
            encoding="utf-8")
    (tmp_path / "profile.md").write_text("# io", encoding="utf-8")
    # A config.toml of our own, minimal but complete: `load_config` requires
    # every one of these keys, and without this the test only passes because
    # a real ~/.config/winnow/config.toml happens to exist on this machine —
    # on a clean checkout or in CI it would raise FileNotFoundError instead.
    (tmp_path / "config.toml").write_text(
        'folders = []\n\n'
        '[instagram]\n'
        'username = "x"\n'
        f'browser_profile = "{tmp_path / "browser-profile"}"\n\n'
        '[api]\n'
        'model = "claude-haiku-4-5"\n\n'
        '[limits]\n'
        'warn_eur_week = 1.0\n'
        'halt_eur_week = 2.0\n'
        'posts_per_run = 5\n'
        'max_slides = 6\n'
        'eur_per_usd = 1.0\n',
        encoding="utf-8")
    monkeypatch.setattr(R.paths, "findings_dir", lambda: findings)
    monkeypatch.setattr(R.paths, "recap_dir", lambda: tmp_path / "recap")
    monkeypatch.setattr(R.paths, "profile_file", lambda: tmp_path / "profile.md")
    monkeypatch.setattr(R.paths, "judged_file", lambda: tmp_path / "judged.json")
    monkeypatch.setattr(R.paths, "shots_dir", lambda: tmp_path / "shots")
    monkeypatch.setattr(R.paths, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(R.paths, "config_file", lambda: tmp_path / "config.toml")
    return findings


ANSWER = '```json\n{"week": "2026-08-25", "counts": {"kept": 1}, ' \
         '"categories": [], "discarded": []}\n```'


def test_one_command_bundles_asks_and_renders(tmp_path, monkeypatch):
    """The three steps of before — prepare, paste, resume — become one."""
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    assert run_recap(open_file=False,
                     ask=lambda *a, **k: (ANSWER, 100, 50)) == 0
    pages = list((tmp_path / "recap").glob("*.html"))
    assert len(pages) == 1


def test_the_marker_moves_only_after_the_page_exists(tmp_path, monkeypatch):
    """Marking as judged a day whose recap failed loses it forever: the next
    run will never look at it again."""
    from winnow.judge import Fatal
    from winnow.recap import run_recap
    from winnow.window import last_judged
    _fixture(tmp_path, monkeypatch)

    def dead(*a, **k):
        raise Fatal("401 invalid api key")

    assert run_recap(open_file=False, ask=dead) == 1
    assert last_judged(tmp_path / "judged.json") is None


def test_a_truncated_reply_is_saved_before_it_fails(tmp_path, monkeypatch):
    """The most expensive call in the tool (max_tokens=16000) used to be the
    one hole in "the answer is written down before it is parsed": the reply
    classified correctly as not-worth-retrying, and its text — real money —
    never touched disk. It must, even though the run still fails."""
    from winnow.providers import Truncated
    from winnow.recap import run_recap
    from winnow.window import last_judged
    _fixture(tmp_path, monkeypatch)

    def cut_off(*a, **k):
        exc = Truncated("reply truncated at 16000 tokens")
        exc.partial = '```json\n{"week": "2026-08-25", "counts": {"kept'
        raise exc

    assert run_recap(open_file=False, ask=cut_off) == 1
    saved = list((tmp_path / "recap").glob("*.answer*.md"))
    assert saved and "counts" in saved[0].read_text(encoding="utf-8")
    # A recap that failed must not be marked as judged: the next run has to
    # see these days again, same as any other failure mid-recap.
    assert last_judged(tmp_path / "judged.json") is None


def test_a_second_run_with_nothing_new_says_so_and_costs_nothing(
        tmp_path, monkeypatch):
    """`now` is fixed a day after the findings, not left to `datetime.now()`:
    the marker only closes a day once it is no longer "today" (see the
    same-day backlog test below), so a run for a day that has already ended
    must say so — and this must hold on every date it happens to run, not
    only on the one date the findings file's name was written down."""
    from datetime import datetime

    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    later = datetime(2026, 8, 26, 9, 0)
    run_recap(now=later, open_file=False, ask=lambda *a, **k: (ANSWER, 100, 50))

    calls = []

    def counted(*a, **k):
        calls.append(1)
        return ANSWER, 100, 50

    assert run_recap(now=later, open_file=False, ask=counted) == 0
    assert calls == []


def test_the_answer_is_written_down_before_it_is_parsed(tmp_path, monkeypatch):
    """A judgement costs real money. If the JSON is broken it gets fixed by
    hand — but only if it still exists."""
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    assert run_recap(open_file=False,
                     ask=lambda *a, **k: ("not json", 100, 50)) == 1
    saved = list((tmp_path / "recap").glob("*.answer*.md"))
    assert saved and "not json" in saved[0].read_text(encoding="utf-8")


def test_it_reports_as_it_goes(tmp_path, monkeypatch):
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    seen = []
    run_recap(open_file=False, ask=lambda *a, **k: (ANSWER, 100, 50),
              on_event=lambda e, d: seen.append(e))
    assert "bundling" in seen and "judged" in seen and "rendered" in seen


def test_a_leaked_profile_stops_before_it_is_sent(tmp_path, monkeypatch):
    """The bundle now goes straight to a model provider instead of sitting on
    a clipboard where a person could notice it first — so a key found in the
    profile has to stop the recap before it is sent, not just be logged.
    Declining must cost nothing: the model is never asked."""
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    (tmp_path / "profile.md").write_text(
        "# io\nkey = sk-abcdefghijklmnopqrstuvwxyz1234567890\n",
        encoding="utf-8")

    calls = []

    def counted(*a, **k):
        calls.append(1)
        return ANSWER, 100, 50

    assert run_recap(open_file=False, ask=counted,
                     confirm=lambda prompt: False) == 1
    assert calls == []


def test_a_recap_records_its_spend(tmp_path, monkeypatch):
    """`run.py` checks and records around every extraction; the recap call —
    a week in, up to 16k tokens out — was the one gap: paid for, but invisible
    to `weekly_spend` and to the brake."""
    import json as _json

    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    assert run_recap(open_file=False,
                     ask=lambda *a, **k: (ANSWER, 100, 50)) == 0
    runs = _json.loads((tmp_path / "spend.json").read_text(encoding="utf-8"))
    assert len(runs) == 1
    # claude-haiku-4-5: 100 in @ $1/M + 50 out @ $5/M.
    assert runs[0]["usd"] == pytest.approx(0.00035)


def test_a_tripped_brake_stops_the_recap_before_it_asks(tmp_path, monkeypatch):
    """The freeze must sit before the model is asked, not after: a recap run
    with the brake already tripped must not spend a cent."""
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    (tmp_path / "HALTED").write_text("stopped by hand", encoding="utf-8")

    calls = []

    def counted(*a, **k):
        calls.append(1)
        return ANSWER, 100, 50

    assert run_recap(open_file=False, ask=counted) == 1
    assert calls == []


# --- a day is not closed for good until it stops being today --------------

def test_a_same_day_backlog_collect_is_not_lost(tmp_path, monkeypatch):
    """The defect `window.py` exists to close, reopened by another door.
    `winnow collect --posts 30` — the CLI's own documented way to clear a
    backlog — writes into `findings/<today>.json`, same file the morning's
    recap already read. `pending_files` only ever returns a day once
    (`stem > after`, strictly): if that day got closed while it was still
    today, the afternoon's new posts would never be looked at by anyone,
    silently, forever — collected, paid for, judged by nobody."""
    from datetime import datetime

    from winnow.recap import run_recap
    from winnow.window import last_judged
    findings = _fixture(tmp_path, monkeypatch)
    morning = datetime(2026, 8, 25, 9, 0)
    next_day = datetime(2026, 8, 26, 9, 0)

    bundles = []

    def capture(bundle, *a, **k):
        bundles.append(bundle)
        return ANSWER, 100, 50

    # The morning recap: one day, its own findings, nothing else pending yet.
    assert run_recap(now=morning, open_file=False, ask=capture) == 0
    assert "BACKLOG-THING" not in bundles[0]
    # Still today when it ran: not closed yet, on purpose.
    assert last_judged(tmp_path / "judged.json") is None

    # The afternoon's backlog collect: same file, one more post.
    (findings / "2026-08-25.json").write_text(json.dumps(
        {"spend_usd": 0.02,
         "posts": [{"shortcode": "A", "shape": "news", "entities": []},
                   {"shortcode": "BACKLOG", "shape": "repo", "account": "x",
                    "caption": "", "url": "", "entities": [
                        {"name": "BACKLOG-THING", "kind": "repo",
                         "verification": {"checked": True, "exists": True}}]}]}),
        encoding="utf-8")

    # The next recap, the following day: the file is pending again — it was
    # never closed — and this time the new post is in the bundle.
    assert run_recap(now=next_day, open_file=False, ask=capture) == 0
    assert "BACKLOG-THING" in bundles[1]
    # Now that the day has actually ended, it closes.
    assert last_judged(tmp_path / "judged.json") == "2026-08-25"


def test_a_corrupt_day_is_not_marked_as_judged(tmp_path, monkeypatch):
    """The marker used to move to `files[-1].stem` without asking whether
    that file made it into the bundle. If the most recent pending day is the
    corrupt one, `load_days` reports it and drops it — but the old code still
    told every future recap to skip that day, having judged none of it."""
    from datetime import datetime

    from winnow.recap import run_recap
    from winnow.window import last_judged
    findings = _fixture(tmp_path, monkeypatch)
    (findings / "2026-08-23.json").write_text(json.dumps(
        {"spend_usd": 0.0,
         "posts": [{"shortcode": "A", "shape": "news", "entities": []}]}),
        encoding="utf-8")
    (findings / "2026-08-24.json").write_text("{{{not json", encoding="utf-8")
    now = datetime(2026, 8, 25, 9, 0)   # the fixture's own day is "today"

    assert run_recap(now=now, open_file=False,
                     ask=lambda *a, **k: (ANSWER, 100, 50)) == 0
    # Not "2026-08-24" (corrupt, never entered the bundle) and not
    # "2026-08-25" (today — see the test above).
    assert last_judged(tmp_path / "judged.json") == "2026-08-23"


def test_the_readme_does_not_describe_a_flow_that_is_gone():
    """Il copia-incolla non esiste più: un README che lo racconta manda
    l'utente a cercare un passaggio che non c'è."""
    import pathlib
    text = pathlib.Path("README.md").read_text(encoding="utf-8")
    body = text.lower()
    assert "copy the model's whole answer" not in body
    assert "winnow recap" in body


def test_every_way_a_recap_can_end_badly_says_why(tmp_path, monkeypatch):
    """The window cannot read stdout. On 2026-08-28 a real recap was cut off
    at 16,000 tokens and the panel said «non ha detto perché» — which is the
    one thing a run that cost money must never do."""
    from winnow import paths, providers, recap

    monkeypatch.setattr(paths, "profile_file", lambda: tmp_path / "nope.md")
    said = []
    assert recap.run_recap(on_event=lambda e, d: said.append((e, d))) == 1
    assert said and said[-1][0] == "failed" and said[-1][1]["why"]


def test_the_ceiling_leaves_room_for_a_backlog():
    """The answer grows with the pile, not with what got through: every
    rejected thing carries a sentence. A backlog is when a recap matters most
    and it is exactly what broke the old ceiling."""
    from winnow.judge import MAX_OUT

    assert MAX_OUT >= 32_000


def _day(tmp_path, name, things):
    """A findings file holding `things` named things, spread over posts."""
    posts = [{"shortcode": f"{name}-{i}", "entities": [{"name": f"t{i}-{j}"}
                                                       for j in range(2)]}
             for i in range((things + 1) // 2)]
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps({"posts": posts, "spend_usd": 0.0, "failed": []}),
                 encoding="utf-8")
    return p


def test_a_backlog_is_cut_into_recaps_oldest_first(tmp_path):
    """46 posts over five days came back cut off mid-JSON. Oldest first
    matters: judging the newest first would bury the old days under a marker
    that only moves forward, and they would never be judged at all."""
    from winnow.recap import slice_days

    files = [_day(tmp_path, "2026-08-20", 100), _day(tmp_path, "2026-08-21", 100),
             _day(tmp_path, "2026-08-22", 100)]
    taken, left = slice_days(files, cap=250)
    assert [f.stem for f in taken] == ["2026-08-20", "2026-08-21"]
    assert left == 100


def test_a_single_day_over_the_cap_is_still_taken_whole(tmp_path):
    """Half a day judged is a day that can never be finished: the marker moves
    a day at a time."""
    from winnow.recap import slice_days

    files = [_day(tmp_path, "2026-08-20", 400), _day(tmp_path, "2026-08-21", 10)]
    taken, left = slice_days(files, cap=250)
    assert [f.stem for f in taken] == ["2026-08-20"] and left == 10


def test_a_pile_that_fits_is_not_cut(tmp_path):
    from winnow.recap import slice_days

    files = [_day(tmp_path, "2026-08-20", 40), _day(tmp_path, "2026-08-21", 40)]
    taken, left = slice_days(files, cap=250)
    assert len(taken) == 2 and left == 0


def test_a_day_that_cannot_be_read_does_not_stop_the_slicing(tmp_path):
    from winnow.recap import slice_days

    bad = tmp_path / "2026-08-20.json"
    bad.write_text("{ not json", encoding="utf-8")
    files = [bad, _day(tmp_path, "2026-08-21", 40)]
    taken, left = slice_days(files, cap=250)
    assert len(taken) == 2 and left == 0
