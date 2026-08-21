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
    assert not c.ok and "compilare" in c.detail


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
        ("github", "/someone/saved/github/1/", True, "repo"),
        ("gym", "/someone/saved/gym/2/", False, "news"),
    ]), encoding="utf-8")
    cfg = load_config(f)
    assert cfg.username == "someone"
    assert [(x.name, x.active, x.kind) for x in cfg.folders] == [
        ("github", True, "repo"), ("gym", False, "news")]


def test_render_config_keeps_folders_you_did_not_pick(tmp_path):
    """Turning one on later should be flipping a flag, not hunting a URL."""
    from winnow.setup import render_config
    text = render_config("someone", [("gym", "/someone/saved/gym/2/", False, "news")])
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
