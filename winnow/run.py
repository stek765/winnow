"""One collection run: folders -> new posts -> entities -> verifications -> file."""
from __future__ import annotations

import json
import os
import time
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

# GitHub's search endpoint allows 10 requests/minute unauthenticated (30 with a
# token). A run of 8 posts produces ~70 lookups, so we pace ourselves and cache
# repeated names: the same repo shows up across several posts in the same week.
SEARCH_DELAY_S = 7.0
BASE_POST_URL = "https://www.instagram.com/p/"


def make_http() -> httpx.Client:
    """HTTP client, authenticated against GitHub when a token is available."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(headers=headers)


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
        # platform e claim: nessuna fonte automatica. Il giudice li valuta a mano.
        v = Verification(checked=False, note="nessuna fonte automatica per questo tipo")

    cache[key] = v
    if delay and entity.kind in ("repo", "model"):
        time.sleep(delay)
    return v


def findings_path(root: Path, day: date) -> Path:
    return root / f"{day.isoformat()}.json"


def write_findings(
    path: Path,
    extractions: list[PostExtraction],
    verifications: dict[tuple[str, str], Verification],
    spend_usd: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "spend_usd": round(spend_usd, 6),
        "posts": [
            {
                "shortcode": ex.shortcode,
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
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def collect(
    cfg: Config,
    state_dir: Path,
    findings_dir: Path,
    shots_dir: Path,
    client,
    http: httpx.Client,
    page,
    now: datetime,
    search_delay: float = SEARCH_DELAY_S,
) -> dict:
    spend_path = state_dir / "spend.json"
    seen_path = state_dir / "seen.json"

    status = check_brake(state_dir, spend_path, cfg.limits, now)  # may raise Halted

    seen = load_seen(seen_path)
    todo: list[tuple[str, str]] = []
    for folder in active_folders(cfg):
        for code in filter_new(seen, list_shortcodes(page, folder.url)):
            todo.append((code, folder.name))
    todo = todo[: cfg.limits.posts_per_run]

    extractions: list[PostExtraction] = []
    verifications: dict[tuple[str, str], Verification] = {}
    cache: dict[tuple[str, str], Verification] = {}
    spend = 0.0

    for code, folder_name in todo:
        caption, account, shots = capture_post(
            page, code, shots_dir, cfg.limits.max_slides
        )
        ex = extract_post(client, cfg.model, code, account, caption, shots)
        extractions.append(ex)
        spend += ex.usd
        record_spend(spend_path, ex.usd, now)

        for e in ex.entities:
            verifications[(code, e.name)] = enrich(http, e, cache, search_delay)

        mark_seen(seen_path, [code], folder_name, now.date().isoformat())

    write_findings(
        findings_path(findings_dir, now.date()), extractions, verifications, spend
    )

    return {
        "status": status,
        "posts": len(extractions),
        "entities": sum(len(e.entities) for e in extractions),
        "spend_usd": round(spend, 4),
    }
