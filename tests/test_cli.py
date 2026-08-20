from winnow.cli import main


def test_no_command_prints_usage_and_fails(capsys):
    assert main([]) == 2
    assert "collect" in capsys.readouterr().out


def test_status_reports_halt(tmp_path, capsys):
    (tmp_path / "HALTED").write_text("fermo per test", encoding="utf-8")
    code = main(["status", "--state-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "HALTED" in out or "fermo" in out


def test_reset_halt_removes_the_file(tmp_path):
    (tmp_path / "HALTED").write_text("fermo", encoding="utf-8")
    assert main(["reset-halt", "--state-dir", str(tmp_path)]) == 0
    assert not (tmp_path / "HALTED").exists()


def test_reset_halt_when_not_halted_is_a_noop(tmp_path):
    assert main(["reset-halt", "--state-dir", str(tmp_path)]) == 0


def test_status_without_halt_reports_the_weekly_spend(tmp_path, capsys):
    assert main(["status", "--state-dir", str(tmp_path)]) == 0
    assert "USD" in capsys.readouterr().out
