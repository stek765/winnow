from winnow.setup import (
    CONFIG_TEMPLATE, check_api_key, check_browser_profile, check_config,
)


def test_missing_config_is_not_ok(tmp_path):
    assert not check_config(tmp_path / "config.toml").ok


def test_untouched_template_counts_as_not_configured(tmp_path):
    """Un template scaricato e mai aperto non e' una configurazione."""
    p = tmp_path / "config.toml"
    p.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    c = check_config(p)
    assert not c.ok and "to be filled in" in c.detail


def test_filled_config_is_ok(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(CONFIG_TEMPLATE.replace("YOUR_USERNAME", "tizio"), encoding="utf-8")
    assert check_config(p).ok


def test_api_key_found_in_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-finta")
    assert check_api_key(tmp_path / "env").ok


def test_api_key_found_in_the_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    f = tmp_path / "env"
    f.write_text("ANTHROPIC_API_KEY=sk-ant-finta\n", encoding="utf-8")
    assert check_api_key(f).ok


def test_missing_api_key_explains_how_to_create_it(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = check_api_key(tmp_path / "env")
    assert not c.ok
    assert "console.anthropic.com" in c.todo and "winnow init" in c.todo


def test_empty_browser_dir_is_not_a_session(tmp_path):
    """Una cartella vuota non e' un accesso: era il bug del 20/08/2026."""
    (tmp_path / "prof").mkdir()
    assert not check_browser_profile(tmp_path / "prof").ok


def test_profile_with_cookies_counts_as_logged_in(tmp_path):
    d = tmp_path / "prof" / "Default"
    d.mkdir(parents=True)
    (d / "Cookies").write_text("", encoding="utf-8")
    assert check_browser_profile(tmp_path / "prof").ok


def test_browsers_root_honours_the_playwright_override(monkeypatch):
    from pathlib import Path
    from winnow.setup import browsers_root
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/altrove")
    assert browsers_root() == Path("/altrove")


def test_chromium_installed_looks_for_a_chromium_directory(tmp_path):
    from winnow.setup import chromium_installed
    assert not chromium_installed(tmp_path)
    (tmp_path / "firefox-1234").mkdir()
    assert not chromium_installed(tmp_path), "firefox non e' chromium"
    (tmp_path / "chromium-1234").mkdir()
    assert chromium_installed(tmp_path)


def test_chromium_installed_is_false_when_the_root_does_not_exist(tmp_path):
    from winnow.setup import chromium_installed
    assert not chromium_installed(tmp_path / "mai-creata")


def test_load_env_file_parses_key_value_lines(tmp_path):
    from winnow.setup import load_env_file
    f = tmp_path / "env"
    f.write_text("# commento\nANTHROPIC_API_KEY=sk-ant-finta\n\nGITHUB_TOKEN='abc'\n",
                 encoding="utf-8")
    assert load_env_file(f) == {"ANTHROPIC_API_KEY": "sk-ant-finta",
                                "GITHUB_TOKEN": "abc"}


def test_load_env_file_on_missing_file_is_empty(tmp_path):
    from winnow.setup import load_env_file
    assert load_env_file(tmp_path / "assente") == {}


def test_apply_env_file_does_not_override_the_environment(tmp_path, monkeypatch):
    from winnow.setup import apply_env_file
    monkeypatch.setenv("ANTHROPIC_API_KEY", "quella-vera")
    f = tmp_path / "env"
    f.write_text("ANTHROPIC_API_KEY=quella-del-file\n", encoding="utf-8")
    apply_env_file(f)
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "quella-vera"


# --- winnow init writes the config from what it found -----------------------

def test_render_config_is_loadable(tmp_path):
    """Whatever init writes must survive load_config — a config that parses
    only in someone's head is the same as no config."""
    from winnow.config import load_config
    from winnow.setup import render_config

    f = tmp_path / "config.toml"
    f.write_text(render_config("someone", [
        ("github", "/someone/saved/github/1/", True),
        ("gym", "/someone/saved/gym/2/", False),
    ]), encoding="utf-8")
    cfg = load_config(f)
    assert cfg.username == "someone"
    assert [(x.name, x.active) for x in cfg.folders] == [
        ("github", True), ("gym", False)]


def test_render_config_keeps_folders_you_did_not_pick(tmp_path):
    """Turning one on later should be flipping a flag, not hunting a URL."""
    from winnow.setup import render_config
    text = render_config("someone", [("gym", "/someone/saved/gym/2/", False)])
    assert "/someone/saved/gym/2/" in text and "active = false" in text


import pytest


@pytest.mark.parametrize("text,expected", [
    ("1,3-5", {1, 3, 4, 5}),
    ("2 4", {2, 4}),
    ("", set()),
    ("99", set()),          # out of range: dropped, not fatal
    ("abc", set()),
    ("5-3", {3, 4, 5}),     # backwards range still means the same range
])
def test_parse_selection(text, expected):
    from winnow.setup import parse_selection
    assert parse_selection(text, 6) == expected


# --- the profile is written from answers, not left as homework -------------

def test_render_profile_keeps_the_headings_the_judge_reads():
    from winnow.setup import PROFILE_QUESTIONS, render_profile
    text = render_profile([("Who I am", "firmware dev"),
                           ("Open questions", "thesis abroad or not")])
    assert "## Who I am\nfirmware dev\n" in text
    assert "## Open questions\nthesis abroad or not\n" in text
    # the heading that follows must not be glued to the last answer
    assert "\n\n## Interesting even if unrelated to work" in text
    assert "## What I never want to see" in text
    # every question maps onto a heading that exists in the template
    from pathlib import Path
    template = (Path(__file__).resolve().parents[1] / "winnow"
                / "profile-template.md").read_text(encoding="utf-8")
    for _, heading in PROFILE_QUESTIONS:
        assert f"## {heading}" in template


def test_a_written_profile_no_longer_counts_as_the_example(tmp_path):
    """check_profile keys off the template's title: if render_profile ever
    emitted it, init would loop forever asking the same four questions."""
    from winnow.setup import check_profile, render_profile
    f = tmp_path / "profile.md"
    f.write_text(render_profile([("Who I am", "x")]), encoding="utf-8")
    assert check_profile(f).ok


def test_ask_survives_the_end_of_input(monkeypatch):
    """Ctrl-D or a closed pipe means "not now", not a traceback."""
    import winnow.setup as setup
    monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(EOFError))
    assert setup.ask("domanda? ") == ""


# --- winnow config: editing must not reset what it does not touch ----------

def test_editing_folders_keeps_tuned_limits_and_the_model(tmp_path):
    """`render_config` rebuilds from the template, which is right for a first
    setup and wrong as an editor: it would silently put posts_per_run back to 8
    and the provider back to Anthropic."""
    from winnow.config import load_config
    from winnow.setup import render_folders_section

    f = tmp_path / "config.toml"
    f.write_text('''[instagram]
username = "vecchio"

[api]
provider = "local"
model = "qwen2.5vl"
base_url = "http://localhost:11434/v1"

[limits]
warn_eur_week = 3.0
halt_eur_week = 10.0
posts_per_run = 42
max_slides = 15
eur_per_usd = 0.92

[[folders]]
name = "vecchia"
url = "/vecchio/saved/vecchia/1/"
active = true
kind = "repo"
''', encoding="utf-8")

    f.write_text(render_folders_section(
        f.read_text(encoding="utf-8"), "nuovo",
        [("nuova", "/nuovo/saved/nuova/2/", True)]), encoding="utf-8")

    cfg = load_config(f)
    assert [x.name for x in cfg.folders] == ["nuova"], "le cartelle cambiano"
    assert cfg.username == "nuovo"
    assert cfg.limits.posts_per_run == 42, "il limite messo a mano sopravvive"
    assert cfg.provider == "local" and cfg.base_url.endswith("/v1")
    assert cfg.model == "qwen2.5vl"


def test_a_large_file_to_link_is_flagged_at_the_moment_of_choosing(
        tmp_path, capsys, monkeypatch):
    """A 128 KB profile made up a quarter of the bundle and the recap came
    back auditing saved posts against a plan. Saying so afterwards is too
    late — the choice is made here."""
    from winnow import setup
    big = tmp_path / "huge.md"
    big.write_text("x" * 200_000, encoding="utf-8")
    monkeypatch.setattr(setup, "PROFILE_CANDIDATES", (str(big),))
    monkeypatch.setattr(setup, "ask", lambda *_a, **_k: "1")
    setup.ask_profile(tmp_path / "profile.md")
    assert "large" in capsys.readouterr().out


# --- editing the config from somewhere that is not a terminal ---------------
#
# `winnow config` asks questions at a prompt. The window cannot ask questions:
# it sends the whole change at once and needs to be told, in one answer,
# whether it was accepted. So the edit is a pure text transform with its own
# validation, and every refusal carries a sentence a person can read.

CONFIG_SAMPLE = '''[instagram]
username = "someone"

[api]
provider = "anthropic"
model = "claude-haiku-4-5"

[limits]
warn_eur_week = 5.0
halt_eur_week = 10.0
posts_per_run = 8       # per run
max_slides = 12
eur_per_usd = 0.92

[[folders]]
name = "github"
url = "https://instagram.com/x/saved/github/1/"
active = true
kind = "repo"

[[folders]]
name = "ai"
url = "https://instagram.com/x/saved/ai/2/"
active = false
kind = "news"
'''


def _reread(text):
    import tomllib
    return tomllib.loads(text)


def test_the_model_can_be_changed_without_touching_anything_else():
    from winnow.setup import apply_config_patch
    out = apply_config_patch(CONFIG_SAMPLE, {"model": "claude-sonnet-5"})
    raw = _reread(out)
    assert raw["api"]["model"] == "claude-sonnet-5"
    # The whole reason this is a patch and not a rewrite: a config editor that
    # resets the limits somebody tuned is worse than no editor.
    assert raw["limits"]["posts_per_run"] == 8
    assert raw["limits"]["halt_eur_week"] == 10.0
    assert len(raw["folders"]) == 2


def test_a_folder_is_switched_on_by_name_and_keeps_its_url():
    """The window can toggle a folder. It cannot invent one: finding the URL
    means scraping Instagram, which is what `winnow init` is for."""
    from winnow.setup import apply_config_patch
    out = apply_config_patch(CONFIG_SAMPLE, {"folders": [{"name": "ai", "active": True}]})
    by_name = {f["name"]: f for f in _reread(out)["folders"]}
    assert by_name["ai"]["active"] is True
    assert by_name["ai"]["url"].endswith("/ai/2/")
    assert by_name["github"]["active"] is True      # untouched


def test_a_folder_that_does_not_exist_is_refused_and_named():
    from winnow.setup import apply_config_patch
    with pytest.raises(ValueError, match="nonesuch"):
        apply_config_patch(CONFIG_SAMPLE, {"folders": [{"name": "nonesuch", "active": True}]})


def test_posts_per_run_is_changed_and_must_be_above_zero():
    from winnow.setup import apply_config_patch
    assert _reread(apply_config_patch(
        CONFIG_SAMPLE, {"posts_per_run": 30}))["limits"]["posts_per_run"] == 30
    for bad in (0, -1, "eight", 1.5):
        with pytest.raises(ValueError):
            apply_config_patch(CONFIG_SAMPLE, {"posts_per_run": bad})


def test_an_unknown_provider_is_refused():
    """Written through, it would be found only at the next run — by then the
    screen has said "saved" and the failure looks like a different bug."""
    from winnow.setup import apply_config_patch
    with pytest.raises(ValueError, match="provider"):
        apply_config_patch(CONFIG_SAMPLE, {"provider": "wishful", "model": "x"})


def test_a_local_model_without_an_address_is_refused():
    from winnow.setup import apply_config_patch
    with pytest.raises(ValueError, match="indirizzo"):
        apply_config_patch(CONFIG_SAMPLE, {"provider": "local", "model": "qwen2.5vl"})
    out = apply_config_patch(CONFIG_SAMPLE, {
        "provider": "local", "model": "qwen2.5vl",
        "base_url": "http://localhost:11434/v1"})
    assert _reread(out)["api"]["base_url"] == "http://localhost:11434/v1"


def test_leaving_a_local_model_drops_the_address_it_needed():
    """Kept, it would sit in the file pointing at a machine nobody asks any
    more — and reappear the day somebody switches back to local, stale."""
    from winnow.setup import apply_config_patch
    local = apply_config_patch(CONFIG_SAMPLE, {
        "provider": "local", "model": "qwen2.5vl",
        "base_url": "http://localhost:11434/v1"})
    back = apply_config_patch(local, {"provider": "anthropic",
                                      "model": "claude-haiku-4-5"})
    assert "base_url" not in _reread(back)["api"]


def test_an_empty_model_name_is_refused():
    from winnow.setup import apply_config_patch
    with pytest.raises(ValueError, match="modello"):
        apply_config_patch(CONFIG_SAMPLE, {"model": "  "})


def test_a_key_nobody_offered_is_refused_rather_than_ignored():
    """Silently dropped, the screen says "saved" for a change that never
    happened. The api key is the one that matters: it lives in a 600 file,
    never in config.toml, and must not be settable from a window."""
    from winnow.setup import apply_config_patch
    with pytest.raises(ValueError, match="api_key"):
        apply_config_patch(CONFIG_SAMPLE, {"api_key": "sk-ant-nope"})
    with pytest.raises(ValueError, match="username"):
        apply_config_patch(CONFIG_SAMPLE, {"username": "someone-else"})


def test_an_empty_patch_changes_nothing_and_is_not_an_error():
    from winnow.setup import apply_config_patch
    assert apply_config_patch(CONFIG_SAMPLE, {}) == CONFIG_SAMPLE


# --- adding a folder the window actually went and found --------------------
#
# "The window cannot invent a folder" was true while the only way to learn a
# folder's URL was `winnow init`. Once the window can ask Instagram itself,
# the rule becomes narrower: it may add a folder it was *told about*, and the
# URL has to look like one Instagram would have given it.

def test_a_discovered_folder_can_be_added_with_its_url():
    """The URL is the *relative* form Instagram's own links carry and
    `parse_saved_folders` hands back — `/{user}/saved/{name}/{id}/`. Demanding
    an absolute one would have refused every folder winnow can actually find,
    which is exactly what a first version of this check did."""
    from winnow.setup import apply_config_patch
    out = apply_config_patch(CONFIG_SAMPLE, {"folders": [
        {"name": "elettronica", "active": True,
         "url": "/someone/saved/elettronica/999/"}]})
    by_name = {f["name"]: f for f in _reread(out)["folders"]}
    assert by_name["elettronica"]["active"] is True
    # The two it already had are still there, untouched.
    assert by_name["github"]["active"] is True and by_name["ai"]["active"] is False


def test_a_new_folder_without_a_url_is_refused():
    """Written with an empty URL it would be a folder the collector opens and
    finds nothing in — a silent zero, which is the failure mode this repo
    keeps paying for."""
    from winnow.setup import apply_config_patch
    with pytest.raises(ValueError, match="indirizzo"):
        apply_config_patch(CONFIG_SAMPLE, {"folders": [
            {"name": "brand-new", "active": True}]})


def test_a_url_that_is_not_a_saved_folder_is_refused():
    """Saved folders are /{user}/saved/{name}/{id}/. Anything else is either a
    typo or something that was never a folder, and both produce a run that
    quietly reads nothing."""
    from winnow.setup import apply_config_patch
    for bad in ("https://example.com/x", "/someone/saved/",
                "/someone/saved/all-posts/", "not a url", ""):
        with pytest.raises(ValueError, match="indirizzo"):
            apply_config_patch(CONFIG_SAMPLE, {"folders": [
                {"name": "brand-new", "active": True, "url": bad}]})


def test_a_config_written_before_this_still_loads():
    """`kind = "repo"` is in every config written so far, and `holds` in the
    ones written for a day. Both are ignored now, and *ignored* is the word: a
    key that stopped meaning anything must not stop somebody's tool from
    starting."""
    from winnow.config import load_config
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "c.toml"
        f.write_text(CONFIG_SAMPLE.replace('kind = "news"', 'holds = "roba"'),
                     encoding="utf-8")
        by_name = {x.name: x for x in load_config(f).folders}
    assert set(by_name) == {"github", "ai"}
    assert by_name["github"].active is True


