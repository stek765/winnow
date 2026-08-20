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
    assert "console.anthropic.com" in c.todo and "umask" in c.todo


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
