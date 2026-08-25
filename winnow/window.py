"""Quali findings devono ancora essere giudicati.

`week_files()` prendeva gli ultimi sette giorni di calendario, e da nessuna
parte esisteva uno stato "fin dove ho già giudicato". Due conseguenze, e la
seconda è quella grave: due recap ravvicinati rileggono e ripagano gli stessi
giorni; dieci giorni di pausa e tre giorni di findings escono dalla finestra e
non li vede mai più nessuno — pagati, raccolti, mai giudicati.

winnow esiste perché i post salvati non si riguardano mai: perderne un pezzo in
silenzio è esattamente il difetto che dovrebbe curare.

Il marcatore è un file solo, come `seen.json` per i post, e si muove solo in
avanti: rigiudicare una settimana vecchia non deve far dimenticare quelle già
fatte dopo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def last_judged(path: Path) -> str | None:
    """L'ultimo giorno giudicato, o None se non è mai stato fatto un recap."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    day = data.get("last_judged")
    return day if isinstance(day, str) and DAY_RE.match(day) else None


def mark_judged(path: Path, day: str) -> None:
    """Sposta il segno in avanti. Mai indietro."""
    if not DAY_RE.match(day):
        return
    if (last_judged(path) or "") >= day:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_judged": day}, indent=2),
                    encoding="utf-8")


def pending_files(findings_dir: Path, after: str | None) -> list[Path]:
    """I findings da giudicare, dal più vecchio.

    Selezionati per la data nel nome, non per mtime: un file riscritto da una
    corsa successiva dello stesso giorno non deve sembrare un giorno diverso.
    """
    if not findings_dir.is_dir():
        return []
    out = [p for p in findings_dir.glob("*.json") if DAY_RE.match(p.stem)]
    if after:
        out = [p for p in out if p.stem > after]
    return sorted(out)
