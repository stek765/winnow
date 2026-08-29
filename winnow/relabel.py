"""Rewrite every page winnow has built, in the language it is now set to.

The judgement is the model's words and never changes here. What changes is
everything winnow itself writes around them: «Perché passa», «Dubbio», the
verdict headings, the counts, the credit under the painting.

The first answer to "does an old recap follow a language changed today?" was
no — the file on disk is the artifact, and an artifact does not retranslate
itself. That is right about the *judgement* and wrong about the chrome: a
reader who has just switched the window to English opens the recap they made
yesterday and finds it captioned in Italian, and there is nothing they can do
about it except make a new one. The chrome is not part of what was decided.

So the pages are rebuilt, once, when the language changes. Rebuilt and not
re-judged: every one of them is produced from the answer saved beside it, the
same file `render.py` reads when the page is first written. Nothing is asked
of a model and nothing costs anything.

A page whose answer is missing or unreadable is left exactly as it is. Half a
page, or a page replaced by an error, would lose a judgement that was paid
for — and that is a far worse outcome than a caption in the wrong language.
"""
from __future__ import annotations

import json
from pathlib import Path

from winnow.i18n import DEFAULT

# The same patterns the archive lists by. Imported rather than written again:
# two copies of a filename rule drift, and the one that drifts is the one that
# quietly stops matching a file that exists.
from winnow.api import IDEAS_PAGE, MERGE_PAGE, WEEK_PAGE


def _answer(page: Path) -> Path:
    """The model's words beside a page. From the page's own stem, never
    rebuilt from its date: `…answer-3.html` is answered by `…answer-3.md`,
    and guessing reads a different judgement."""
    return page.with_suffix(".md")


def rebuild_week(page: Path, lang: str) -> bool:
    from winnow.render import extract_json, render_file

    src = _answer(page)
    data = extract_json(src.read_text(encoding="utf-8"))
    # embed_shots=True: this page has already outlived the run that made it,
    # so it must not start depending on `state/shots/` now.
    render_file(src, out=page, data=data, embed_shots=True, lang=lang)
    return True


def rebuild_ideas(page: Path, lang: str) -> bool:
    from winnow.ideas import render_ideas
    from winnow.render import extract_json

    data = extract_json(_answer(page).read_text(encoding="utf-8"))
    side = json.loads(page.with_suffix(".json").read_text(encoding="utf-8"))
    # `render_ideas` wants the things that were drawn, but only ever counts
    # them — and the sidecar keeps their names, which is the count.
    drawn = side.get("drawn") or []
    page.write_text(
        render_ideas(data, [{}] * len(drawn), side.get("of") or 0,
                     side.get("usd") or 0.0, lang),
        encoding="utf-8")
    return True


def rebuild_merge(page: Path, lang: str) -> bool:
    from winnow.harvest import label_for, merge, render_harvest
    from winnow.render import extract_json

    side = json.loads(page.with_suffix(".json").read_text(encoding="utf-8"))
    d = page.parent
    answers = []
    for name in side.get("files") or []:
        f = d / (Path(name).name[:-len(".html")] + ".md")
        answers.append(extract_json(f.read_text(encoding="utf-8")))
    if not answers:
        # Merges made before `files` was written down. The days are still
        # there, and one recap a day is the ordinary case.
        for week in side.get("weeks") or []:
            f = d / f"{week}.answer.md"
            answers.append(extract_json(f.read_text(encoding="utf-8")))
    label = label_for(side.get("weeks") or [], side.get("name") or "", lang)
    page.write_text(render_harvest(merge(answers), label, lang),
                    encoding="utf-8")
    return True


# Which rebuilder a page belongs to, matched on the same patterns the archive
# lists by. Not a prefix test: the folder holds pages winnow did not write —
# a demo, an export, something dropped in by hand — and reporting those as
# failures teaches the reader to ignore the list of failures.
KINDS = (
    (IDEAS_PAGE, rebuild_ideas),
    (MERGE_PAGE, rebuild_merge),
    (WEEK_PAGE, rebuild_week),
)


def rebuild_all(recap_dir: Path, lang: str = DEFAULT) -> tuple[int, list[str]]:
    """Every page in the folder, rebuilt. Returns how many, and what failed.

    Failures are collected rather than raised: one unreadable answer among
    forty pages must not stop the other thirty-nine from following the
    language the reader just chose.
    """
    if not recap_dir.is_dir():
        return 0, []
    done, failed = 0, []
    for page in sorted(recap_dir.glob("*.html")):
        for pattern, rebuild in KINDS:
            if not pattern.match(page.name):
                continue
            try:
                rebuild(page, lang)
                done += 1
            except Exception as exc:                  # noqa: BLE001
                failed.append(f"{page.name}: {exc}")
            break
    return done, failed
