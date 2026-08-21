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
    "platform": "prodotto o servizio: nessun registro pubblico da interrogare",
    "item": "voce di un elenco, non un prodotto: niente da verificare",
    "news": "notizia: da valutare col profilo, non con una fonte",
    "claim": "asserzione senza artefatto nominato",
}


def enrich(
    http: httpx.Client,
    entity: Entity,
    cache: dict[tuple[str, str], Verification],
    delay: float = 0.0,
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
        # platform, item, news, claim: nessuna fonte da interrogare. Il giudice
        # li valuta a mano, col profilo davanti. Dire *perche'* non e' verificato
        # vale piu' di una riga uguale per tutti.
        v = Verification(checked=False, note=NO_SOURCE.get(
            entity.kind, "nessuna fonte automatica per questo tipo"))

    cache[key] = v
    if delay and entity.kind in ("repo", "model"):
        time.sleep(delay)
    return v


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
                    {
                        **asdict(e),
                        "verification": asdict(
                            verifications.get(
                                (ex.shortcode, e.name), Verification(checked=False)
                            )
                        ),
                    }
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
    todo: list[tuple[str, str]] = []
    for folder in active_folders(cfg):
        missing = cfg.limits.posts_per_run - len(todo)
        if missing <= 0:
            # Listing it would cost a minute of scrolling to then drop every
            # post on the floor. Say so: silence here reads as "empty folder".
            say("folder_skipped", name=folder.name)
            continue
        codes = list_shortcodes(
            page, folder.url,
            enough=lambda cs, n=missing: len(filter_new(seen, cs)) >= n)
        new = filter_new(seen, codes)
        say("folder", name=folder.name, found=len(codes), new=len(new))
        todo.extend((code, folder.name) for code in new[:missing])

    extractions: list[PostExtraction] = []
    verifications: dict[tuple[str, str], Verification] = {}
    cache: dict[tuple[str, str], Verification] = {}
    spend = 0.0

    failed: list[dict] = []

    for n, (code, folder_name) in enumerate(todo, start=1):
        # Un post storto non deve uccidere la nottata. Si registra, si segna
        # come visto (altrimenti lo si ripaga a ogni giro) e si prosegue.
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
                v = enrich(http, e, cache, search_delay)
                verifications[(code, e.name)] = v
                say("verified", name=e.name, checked=v.checked, exists=v.exists,
                    stars=v.stars, note=v.note)
        except Exception as exc:  # noqa: BLE001 - deliberatamente ampio
            if is_unusable(exc):
                # Non segnare visto, non proseguire: la coda resta intatta e
                # il giro riparte da qui quando il problema e' risolto.
                write_findings(findings_path(findings_dir, now.date()),
                               extractions, verifications, spend, failed)
                raise Unusable(str(exc)[:300]) from exc
            failed.append({"shortcode": code, "folder": folder_name,
                           "error": f"{type(exc).__name__}: {exc}"[:300]})
            say("failed", shortcode=code, error=type(exc).__name__)
            mark_seen(seen_path, [code], folder_name, now.date().isoformat())
        else:
            mark_seen(seen_path, [code], folder_name, now.date().isoformat())

    out_path = findings_path(findings_dir, now.date())
    write_findings(out_path, extractions, verifications, spend, failed)
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
