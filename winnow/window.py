"""Which findings still need to be judged.

`week_files()` used to grab the last seven calendar days with no state for "how
far the judgement has progressed". Two consequences, the second one severe: two
back-to-back recaps re-read and re-pay for the same days; ten days of downtime
and three days of findings slide out of the window — paid for, collected, never
judged.

winnow exists because saved posts never get reviewed again: silently losing a
piece of it is exactly the defect it should prevent.

The marker is a single file, like `seen.json` for posts, and moves forward only:
re-judging an old week must not make you forget ones already done after it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def last_judged(path: Path) -> str | None:
    """The last day judged, or None if no recap has ever been done."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    day = data.get("last_judged")
    return day if isinstance(day, str) and DAY_RE.match(day) else None


def mark_judged(path: Path, day: str) -> None:
    """Move the marker forward. Never backward."""
    if not DAY_RE.match(day):
        return
    if (last_judged(path) or "") >= day:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_judged": day}, indent=2),
                    encoding="utf-8")


def pending_files(findings_dir: Path, after: str | None) -> list[Path]:
    """Findings that need to be judged, oldest first.

    Selected by the date in the filename, not by mtime: a file rewritten by a
    later run of the same day must not look like a different day.
    """
    if not findings_dir.is_dir():
        return []
    out = [p for p in findings_dir.glob("*.json") if DAY_RE.match(p.stem)]
    if after:
        out = [p for p in out if p.stem > after]
    return sorted(out)
