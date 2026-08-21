from datetime import datetime, timedelta
import pytest

from winnow.budget import (
    Halted, cost_usd, record_spend, weekly_spend,
    is_halted, write_halt, check_brake,
)
from winnow.config import Limits

NOW = datetime(2026, 8, 20, 3, 0, 0)
LIMITS = Limits(
    warn_eur_week=3.0, halt_eur_week=10.0,
    posts_per_run=8, max_slides=15, eur_per_usd=0.92,
)


def test_cost_uses_haiku_prices():
    assert cost_usd("claude-haiku-4-5", 1_000_000, 0) == pytest.approx(1.0)
    assert cost_usd("claude-haiku-4-5", 0, 1_000_000) == pytest.approx(5.0)
    assert cost_usd("claude-haiku-4-5", 20_000, 1_000) == pytest.approx(0.025)


def test_cost_of_unknown_model_raises():
    with pytest.raises(KeyError):
        cost_usd("modello-inventato", 1000, 10)


def test_weekly_spend_sums_last_seven_days_only(tmp_path):
    p = tmp_path / "spend.json"
    record_spend(p, 1.0, NOW - timedelta(days=2))
    record_spend(p, 2.0, NOW - timedelta(days=6))
    record_spend(p, 99.0, NOW - timedelta(days=30))
    assert weekly_spend(p, NOW) == pytest.approx(3.0)


def test_weekly_spend_on_missing_file_is_zero(tmp_path):
    assert weekly_spend(tmp_path / "spend.json", NOW) == 0.0


def test_check_brake_returns_ok_under_warning(tmp_path):
    p = tmp_path / "spend.json"
    record_spend(p, 0.50, NOW)
    assert check_brake(tmp_path, p, LIMITS, NOW) == "ok"


def test_check_brake_warns_over_warn_threshold(tmp_path):
    p = tmp_path / "spend.json"
    record_spend(p, 5.0, NOW)
    assert check_brake(tmp_path, p, LIMITS, NOW) == "warn"


def test_check_brake_halts_over_halt_threshold(tmp_path):
    p = tmp_path / "spend.json"
    record_spend(p, 12.0, NOW)
    with pytest.raises(Halted):
        check_brake(tmp_path, p, LIMITS, NOW)
    assert is_halted(tmp_path)


def test_halt_file_survives_and_blocks_every_later_run(tmp_path):
    write_halt(tmp_path, "test", 11.04, NOW)
    p = tmp_path / "spend.json"
    with pytest.raises(Halted):
        check_brake(tmp_path, p, LIMITS, NOW)


def test_halt_file_explains_itself(tmp_path):
    write_halt(tmp_path, "weekly threshold exceeded", 11.04, NOW)
    text = (tmp_path / "HALTED").read_text(encoding="utf-8")
    assert "11.04" in text
    assert "2026-08-20" in text
    assert "delete this file by hand" in text.lower()
