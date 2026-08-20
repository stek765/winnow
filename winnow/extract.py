"""Slides -> structured entities, via a cheap vision model.

This module never judges. It extracts what is written and nothing else.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

from winnow.budget import cost_usd

KINDS = {"repo", "model", "platform", "claim"}

SYSTEM_PROMPT = """You read slides from a social media carousel and extract, \
verbatim, the concrete things they name.

Return ONLY a JSON array. Each element:
  kind:  "repo" for a code repository (prefer the "owner/name" form when shown),
         "model" for an AI model, "platform" for a product or service,
         "claim" for a factual assertion with no named artifact.
  name:  the exact name as written. Never invent, never expand an acronym.
  blurb: one sentence, from the slide, of what it is. Empty string if absent.
  slide: the 1-based index of the slide it came from.

Rules:
- Extract only what is actually written or visible. If a slide promises items \
but names none, return nothing for it.
- Do not judge quality, usefulness, or credibility. That is not your job.
- If the slides name nothing concrete, return [].
"""

USER_TEMPLATE = (
    "Post by @{account}.\n\nCaption:\n{caption}\n\n"
    "{n} slides follow, in order. Extract the entities."
)


@dataclass(frozen=True)
class Entity:
    kind: str
    name: str
    blurb: str
    slide: int


@dataclass(frozen=True)
class PostExtraction:
    shortcode: str
    account: str
    caption: str
    entities: list[Entity]
    usd: float


def parse_entities(text: str) -> list[Entity]:
    cleaned = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"risposta non JSON dal modello: {text[:200]!r}") from e
    if not isinstance(data, list):
        raise ValueError(f"attesa una lista, ricevuto {type(data).__name__}")

    out: list[Entity] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        kind, name = item.get("kind"), (item.get("name") or "").strip()
        if kind not in KINDS or not name:
            continue
        out.append(
            Entity(
                kind=kind,
                name=name,
                blurb=(item.get("blurb") or "").strip(),
                slide=int(item.get("slide") or 1),
            )
        )
    return out


def _image_block(path: Path) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.standard_b64encode(path.read_bytes()).decode("utf-8"),
        },
    }


def extract_post(
    client,
    model: str,
    shortcode: str,
    account: str,
    caption: str,
    slide_paths: list[Path],
) -> PostExtraction:
    content: list[dict] = [
        {
            "type": "text",
            "text": USER_TEMPLATE.format(
                account=account, caption=caption, n=len(slide_paths)
            ),
        }
    ]
    content.extend(_image_block(p) for p in slide_paths)

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "[]")

    return PostExtraction(
        shortcode=shortcode,
        account=account,
        caption=caption,
        entities=parse_entities(text),
        usd=cost_usd(model, response.usage.input_tokens, response.usage.output_tokens),
    )
