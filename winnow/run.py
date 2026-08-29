"""One collection run: folders -> new posts -> entities -> verifications -> file."""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import httpx

from winnow.browser import capture_post, list_shortcodes
from winnow.budget import check_brake, record_spend
from winnow.config import Config, active_folders
from winnow.describe import describe
from winnow.extract import Entity, PostExtraction, extract_post
from winnow.state import filter_new, load_seen, mark_seen
from winnow.verify import (
    Verification, hardware_note, resolve_repo, verify_model,
)

# GitHub's search endpoint allows 10 requests/minute unauthenticated, 30 with a
# token. A run of 8 posts produces ~70 lookups, so we pace ourselves and cache
# repeated names: the same repo shows up across several posts in the same week.
# Waiting 7s while authenticated is three quarters of the run spent on nothing —
# which is what made clearing a backlog take two hours instead of forty minutes.
SEARCH_DELAY_S = 7.0        # anonimo: 10 ricerche/minuto
SEARCH_DELAY_TOKEN_S = 2.0  # con GITHUB_TOKEN: 30/minuto


def has_github_token(env: dict | None = None) -> bool:
    return bool((env if env is not None else os.environ).get("GITHUB_TOKEN"))


def search_delay(has_token: bool) -> float:
    return SEARCH_DELAY_TOKEN_S if has_token else SEARCH_DELAY_S
BASE_POST_URL = "https://www.instagram.com/p/"


def make_http() -> httpx.Client:
    """HTTP client, authenticated against GitHub when a token is available."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(headers=headers)


class Unusable(RuntimeError):
    """The model cannot be reached at all: no key, no credit, wrong address.

    Told apart from a broken post on purpose. Every failure used to mark its
    post seen — right for a post nobody can parse, catastrophic for a key with
    no credit on it: a run of fifty would burn the whole backlog without
    reading a word, and nothing would ever be retried.
    """


# HTTP status codes that mean "stop", not "skip this one". 402 and 429 are
# about the account, not the post; 401 and 403 about the key.
FATAL_STATUS = (401, 402, 403, 429)


def is_unusable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status in FATAL_STATUS:
        return True
    text = str(exc).lower()
    return any(w in text for w in
               ("credit balance", "insufficient_quota", "invalid api key",
                "authentication", "api key"))


NO_SOURCE = {
    "platform": "product or service: no public registry to ask",
    "item": "an entry of a list, not a product: nothing to check",
    "news": "news: to be weighed against the profile, not against a source",
    "claim": "a claim with no artefact named",
}


def enrich(
    http: httpx.Client,
    entity: Entity,
    cache: dict[tuple[str, str], Verification],
    delay: float = 0.0,
    should_stop=None,
) -> Verification:
    key = (entity.kind, entity.name.lower())
    if key in cache:
        return cache[key]

    if entity.kind == "repo":
        v = resolve_repo(http, entity.name)
    elif entity.kind == "model":
        v = verify_model(http, entity.name)
        note = hardware_note(entity.name)
        if note:
            v = Verification(**{**asdict(v), "note": f"{v.note} | {note}"})
    else:
        # platform, item, news, claim: no source to ask. The judge weighs
        # them by hand, with the profile in front of it. Saying *why* it is
        # unverified is worth more than one line for all of them.
        v = Verification(checked=False, note=NO_SOURCE.get(
            entity.kind, "no automatic source for this kind"))

    cache[key] = v
    if delay and entity.kind in ("repo", "model"):
        # Without a GitHub token this is up to a minute between two names, and
        # it is where an unattended run spends most of its life. Slept in
        # slices so «Ferma» is answered in a second rather than at the end of
        # the wait — the same reason `judge.ask` slices its backoff.
        waited = 0.0
        while waited < delay:
            if should_stop and should_stop():
                break
            step = min(1.0, delay - waited)
            time.sleep(step)
            waited += step
    return v


def tally_by_folder(seen: dict[str, dict]) -> dict[str, int]:
    """How many posts each folder has already given, from `seen.json`.

    No new state file: the folder has been recorded beside every post since
    the first run, so the count is already on disk. Records written by an
    older version, or by hand, simply do not count towards anyone.
    """
    out: dict[str, int] = {}
    for rec in seen.values():
        name = rec.get("folder") if isinstance(rec, dict) else None
        if name:
            out[name] = out.get(name, 0) + 1
    return out


def deal(pools: list[tuple[str, list[str]]], want: int,
         tally: dict[str, int] | None = None) -> list[tuple[str, str]]:
    """Share a run between the folders instead of queueing them.

    The run used to take the first folder's posts until it was full, and a
    folder that never runs dry — a saved-repos folder with three hundred
    posts in it — meant every folder under it was skipped for ever. Measured
    on a real account on 2026-08-29: seven folders on, and six days of runs
    had read exactly two of them.

    So: one post from each folder in turn, and round again. A folder with
    nothing new hands its slot to the others, or fairness would cost posts.

    The order only matters when there are more folders than slots, and there
    it matters a great deal: config order would leave out the same folders
    every day, which is the bug one level down. The folder that has given
    least so far picks first, so the queue turns over on its own.
    """
    tally = tally or {}
    order = sorted(range(len(pools)),
                   key=lambda i: (tally.get(pools[i][0], 0), i))
    todo: list[tuple[str, str]] = []
    depth = 0
    while len(todo) < want:
        took = False
        for i in order:
            if len(todo) >= want:
                break
            name, new = pools[i]
            if depth < len(new):
                todo.append((new[depth], name))
                took = True
        if not took:
            break
        depth += 1
    return todo


def findings_path(root: Path, day: date) -> Path:
    return root / f"{day.isoformat()}.json"


def merge_findings(old: dict, new: dict) -> dict:
    """Two runs on the same day are one day of findings, not the later one.

    A file per day is the right unit — the recap reads a week by date — but a
    second run used to *replace* the first. Measured on 2026-08-21: a 48-post
    run costing $0.11 was overwritten by a 19-post run twenty minutes later,
    and because every post had already been marked seen, those 131 entities
    could never be collected again. Paid for, then deleted.
    """
    seen = {p["shortcode"] for p in old.get("posts", [])}
    posts = list(old.get("posts", []))
    posts += [p for p in new.get("posts", []) if p["shortcode"] not in seen]
    failed_seen = {f.get("shortcode") for f in old.get("failed", [])}
    failed = list(old.get("failed", []))
    failed += [f for f in new.get("failed", [])
               if f.get("shortcode") not in failed_seen]
    return {
        # The ledger of the day, not of the last run: this number is what the
        # recap header reports as the week's cost.
        "spend_usd": round(old.get("spend_usd", 0.0) + new.get("spend_usd", 0.0), 6),
        "failed": failed,
        "posts": posts,
    }


def write_findings(
    path: Path,
    extractions: list[PostExtraction],
    verifications: dict[tuple[str, str], Verification],
    spend_usd: float,
    failed: list[dict] | None = None,
    today: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "spend_usd": round(spend_usd, 6),
        "failed": failed or [],
        "posts": [
            {
                "shortcode": ex.shortcode,
                "shape": ex.shape,
                "account": ex.account,
                "caption": ex.caption,
                "url": f"{BASE_POST_URL}{ex.shortcode}/",
                "entities": [
                    describe(
                        asdict(e),
                        asdict(verifications.get((ex.shortcode, e.name),
                                                 Verification(checked=False))),
                        today,
                    )
                    for e in ex.entities
                ],
            }
            for ex in extractions
        ],
    }
    if path.exists():
        try:
            payload = merge_findings(
                json.loads(path.read_text(encoding="utf-8")), payload)
        except json.JSONDecodeError:
            # A corrupt file must not cost the run its output: keep the new
            # findings and put the old ones aside instead of dropping either.
            path.rename(path.with_suffix(".json.corrupt"))
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def collect(
    cfg: Config,
    state_dir: Path,
    findings_dir: Path,
    shots_dir: Path,
    http: httpx.Client,
    page,
    now: datetime,
    search_delay: float = SEARCH_DELAY_S,
    on_event: Callable[[str, dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    spend_path = state_dir / "spend.json"
    seen_path = state_dir / "seen.json"

    # A run waits minutes on GitHub's rate limit. Reporting as it goes is what
    # separates "still working" from "hung" — see winnow/progress.py.
    def say(event: str, **data) -> None:
        if on_event:
            on_event(event, data)

    status = check_brake(state_dir, spend_path, cfg.limits, now)  # may raise Halted

    seen = load_seen(seen_path)
    folders = active_folders(cfg)
    want = cfg.limits.posts_per_run
    # Ceil, not the plain average: eight posts over seven folders asks two of
    # each rather than one, so a folder that comes back empty costs the run
    # nothing. It only caps the *scrolling* — whatever a screenful turned up
    # beyond it is kept and dealt below.
    share = -(-want // len(folders)) if folders else 0

    pools: list[tuple[str, list[str]]] = []
    for folder in folders:
        if should_stop and should_stop():
            say("stopped", done=0, of=0)
            break
        codes = list_shortcodes(
            page, folder.url,
            enough=lambda cs, n=share: len(filter_new(seen, cs)) >= n,
            should_stop=should_stop)
        new = filter_new(seen, codes)
        say("folder", name=folder.name, found=len(codes), new=len(new))
        if new:
            pools.append((folder.name, new))

    todo = deal(pools, want, tally_by_folder(seen))

    extractions: list[PostExtraction] = []
    verifications: dict[tuple[str, str], Verification] = {}
    cache: dict[tuple[str, str], Verification] = {}
    spend = 0.0

    failed: list[dict] = []

    for n, (code, folder_name) in enumerate(todo, start=1):
        # Between posts, never inside one: a post half read is a post paid for
        # and thrown away. Everything read so far is written below exactly as
        # if the queue had ended here.
        if should_stop and should_stop():
            say("stopped", done=n - 1, of=len(todo))
            break
        # One bad post must not kill the run. Record it, mark it seen (or it
        # gets paid for again every run) and carry on.
        try:
            caption, account, shots, is_video = capture_post(
                page, code, shots_dir, cfg.limits.max_slides
            )
            say("post", i=n, n=len(todo), account=account, slides=len(shots),
                is_video=is_video)

            ex = extract_post(cfg, code, account, caption, shots,
                              is_video=is_video)
            extractions.append(ex)
            spend += ex.usd
            record_spend(spend_path, ex.usd, now)
            say("extracted", names=[e.name for e in ex.entities], usd=ex.usd,
                shape=ex.shape)

            for e in ex.entities:
                # Between two names, not only between two posts: a post with
                # twelve names is twelve source lookups, and without a token
                # that is minutes.
                if should_stop and should_stop():
                    break
                v = enrich(http, e, cache, search_delay,
                           should_stop=should_stop)
                verifications[(code, e.name)] = v
                say("verified", name=e.name, checked=v.checked, exists=v.exists,
                    stars=v.stars, note=v.note)
        except Exception as exc:  # noqa: BLE001 - deliberatamente ampio
            if is_unusable(exc):
                # Do not mark seen, do not carry on: the queue stays intact
                # and the run resumes here once the problem is fixed.
                write_findings(findings_path(findings_dir, now.date()),
                               extractions, verifications, spend, failed,
                               today=now.date().isoformat())
                raise Unusable(str(exc)[:300]) from exc
            failed.append({"shortcode": code, "folder": folder_name,
                           "error": f"{type(exc).__name__}: {exc}"[:300]})
            say("failed", shortcode=code, error=type(exc).__name__)
            mark_seen(seen_path, [code], folder_name, now.date().isoformat())
        else:
            mark_seen(seen_path, [code], folder_name, now.date().isoformat())

    out_path = findings_path(findings_dir, now.date())
    write_findings(out_path, extractions, verifications, spend, failed,
                   today=now.date().isoformat())
    say("written", path=str(out_path),
        entities=sum(len(e.entities) for e in extractions),
        verified=sum(1 for v in verifications.values() if v.checked and v.exists),
        usd=spend)

    return {
        "status": status,
        "posts": len(extractions),
        "failed": len(failed),
        "entities": sum(len(e.entities) for e in extractions),
        "spend_usd": round(spend, 4),
    }
