"""Which posts have already been processed."""
from __future__ import annotations

import json
from pathlib import Path


def load_seen(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{path.name} is corrupt ({e}). I will not overwrite it on my "
            "own: reprocessing everything would cost money. Check it or "
            "delete it by hand."
        ) from e


def filter_new(seen: dict[str, dict], shortcodes: list[str]) -> list[str]:
    out: list[str] = []
    for code in shortcodes:
        if code not in seen and code not in out:
            out.append(code)
    return out


def mark_seen(path: Path, shortcodes: list[str], folder: str, today: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = load_seen(path)
    for code in shortcodes:
        seen[code] = {"date": today, "folder": folder}
    path.write_text(json.dumps(seen, indent=2, sort_keys=True), encoding="utf-8")
