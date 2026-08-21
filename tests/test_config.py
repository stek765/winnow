import pytest
from winnow.config import load_config, active_folders

SAMPLE = """
[instagram]
username = "tizio"
browser_profile = "browser-profile"

[api]
model = "claude-haiku-4-5"

[limits]
warn_eur_week = 3.0
halt_eur_week = 10.0
posts_per_run = 8
max_slides = 15
eur_per_usd = 0.92

[[folders]]
name = "github"
url = "/tizio/saved/github/111/"
active = true
kind = "repo"

[[folders]]
name = "ai"
url = "/tizio/saved/ai/222/"
active = false
kind = "news"
"""


def test_load_config_reads_all_sections(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.username == "tizio"
    assert cfg.model == "claude-haiku-4-5"
    assert cfg.limits.halt_eur_week == 10.0
    assert len(cfg.folders) == 2


def test_active_folders_skips_inactive(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE, encoding="utf-8")
    names = [f.name for f in active_folders(load_config(p))]
    assert names == ["github"]


def test_missing_config_raises_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        load_config(tmp_path / "assente.toml")
    assert "config.example.toml" in str(e.value)


def test_halt_threshold_must_exceed_warn(tmp_path):
    bad = SAMPLE.replace("halt_eur_week = 10.0", "halt_eur_week = 1.0")
    p = tmp_path / "config.toml"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


def test_override_posts_leaves_the_rest_of_the_config_alone(tmp_path):
    """A one-off big run must not quietly become the new nightly setting."""
    from winnow.config import load_config, override_posts

    f = tmp_path / "config.toml"
    f.write_text(SAMPLE, encoding="utf-8")
    cfg = load_config(f)
    bigger = override_posts(cfg, 50)

    assert bigger.limits.posts_per_run == 50
    assert cfg.limits.posts_per_run != 50          # l'originale non cambia
    assert bigger.folders == cfg.folders
    assert bigger.limits.halt_eur_week == cfg.limits.halt_eur_week
    assert f.read_text(encoding="utf-8") == SAMPLE   # il file resta intatto


def test_override_posts_refuses_zero(tmp_path):
    from winnow.config import load_config, override_posts
    f = tmp_path / "config.toml"
    f.write_text(SAMPLE, encoding="utf-8")
    with pytest.raises(ValueError):
        override_posts(load_config(f), 0)
