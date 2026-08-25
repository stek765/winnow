"""Quali findings devono ancora essere giudicati."""
from __future__ import annotations

import json

from winnow.window import last_judged, mark_judged, pending_files


def _findings(tmp_path, *days):
    d = tmp_path / "findings"
    d.mkdir(exist_ok=True)
    for day in days:
        (d / f"{day}.json").write_text(json.dumps({"posts": []}),
                                       encoding="utf-8")
    return d


def test_with_no_recap_ever_everything_is_pending(tmp_path):
    """Alla prima volta non c'è un "da dove": si prende tutto quello che c'è."""
    d = _findings(tmp_path, "2026-08-20", "2026-08-23", "2026-08-25")
    got = [p.stem for p in pending_files(d, None)]
    assert got == ["2026-08-20", "2026-08-23", "2026-08-25"]


def test_only_the_days_after_the_last_judgement(tmp_path):
    d = _findings(tmp_path, "2026-08-20", "2026-08-23", "2026-08-25")
    got = [p.stem for p in pending_files(d, "2026-08-23")]
    assert got == ["2026-08-25"]


def test_a_gap_of_ten_days_loses_nothing(tmp_path):
    """Il difetto che questo modulo esiste per chiudere: con una finestra
    mobile di sette giorni, il 2026-08-10 sarebbe uscito e non lo avrebbe più
    visto nessuno — pagato, raccolto, mai giudicato."""
    d = _findings(tmp_path, "2026-08-10", "2026-08-24", "2026-08-25")
    got = [p.stem for p in pending_files(d, "2026-08-09")]
    assert got == ["2026-08-10", "2026-08-24", "2026-08-25"]


def test_nothing_new_is_an_empty_list_and_not_an_error(tmp_path):
    d = _findings(tmp_path, "2026-08-25")
    assert pending_files(d, "2026-08-25") == []


def test_a_missing_findings_dir_is_empty(tmp_path):
    assert pending_files(tmp_path / "nope", None) == []


def test_a_file_that_is_not_a_date_is_ignored(tmp_path):
    """`.gitkeep` e i file di appoggio non sono giorni."""
    d = _findings(tmp_path, "2026-08-25")
    (d / ".gitkeep").write_text("", encoding="utf-8")
    (d / "note.json").write_text("{}", encoding="utf-8")
    assert [p.stem for p in pending_files(d, None)] == ["2026-08-25"]


def test_the_marker_round_trips(tmp_path):
    f = tmp_path / "judged.json"
    assert last_judged(f) is None
    mark_judged(f, "2026-08-25")
    assert last_judged(f) == "2026-08-25"


def test_the_marker_only_moves_forward(tmp_path):
    """Rigiudicare una settimana vecchia non deve far dimenticare quelle
    già fatte dopo."""
    f = tmp_path / "judged.json"
    mark_judged(f, "2026-08-25")
    mark_judged(f, "2026-08-20")
    assert last_judged(f) == "2026-08-25"


def test_a_corrupt_marker_is_a_shrug_and_not_a_crash(tmp_path):
    f = tmp_path / "judged.json"
    f.write_text("{{{", encoding="utf-8")
    assert last_judged(f) is None
