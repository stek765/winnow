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

KINDS = {"repo", "model", "platform", "claim", "item", "news"}

# The shape of a post, not the nature of each thing in it. Asking "is this an
# idea or a product?" per entity proved unstable — three prompt wordings on
# 2026-08-20 each fixed one case and broke another. Asking "is this post a list,
# or a piece of news?" is observable, and the answer decides what to pull out.
SHAPES = {"list", "news", "other"}

SYSTEM_PROMPT = """You read a social media post — its caption and the slides of \
its carousel — and write down what it puts on the table. You never judge whether \
any of it is any good: somebody else does that, with context you do not have.

FIRST decide the shape of the post:
  "list"  — it enumerates things: tools, sites, repos, ideas to build, steps.
            The caption alone is often the whole list, with the slides just
            repeating it. If you see an enumeration, this is a list.
  "news"  — it announces or reports something: a release, a launch, a finding,
            a change in the market. Usually one thing, often a talking-head
            video where the caption carries all of it.
  "other" — neither.

THEN extract accordingly:
  From a "list", take EVERY entry, one element each. Do not skip an entry
    because it has no product behind it: an entry of "10 software ideas that
    make money" is worth exactly as much as a repo.
  From "news", take the thing that was announced, and any artifact it names.
  From "other", take whatever concrete things are named, or nothing.

Return ONLY JSON, shaped like this:
{"shape": "<list|news|other>", "entities": [ ... ]}

Each entity:
  kind:  "repo" for a code repository (prefer the "owner/name" form when shown),
         "model" for an AI model,
         "platform" for a product or service that already exists,
         "item" for an entry of a list that is not a product you could sign up
           for — a thing to build, a technique, a step,
         "news" for what a news post announces,
         "claim" for a factual assertion with no named artifact.
  name:  the exact name as written. Never invent, never expand an acronym.
         For "item" and "news", a short title, at most 8 words.
  blurb: one sentence, from the post. For "item" and "news", concrete enough to
         act on months later.
  slide: the 1-based index of the slide it came from, or 0 when it came from
         the caption rather than from a slide.

Extract only what is actually written or visible, in the slides or the caption.
An invitation to comment, follow or DM is never an entity. Do not judge quality,
usefulness or credibility — that is not your job. If the post puts nothing on the
table, return an empty entities list.
"""

USER_TEMPLATE = (
    "Post by @{account}.\n\nCaption:\n{caption}\n\n"
    "{n} slides follow, in order. Extract the entities."
)

# A reel has no slide to read. Without saying so, the extractor receives zero
# images and treats the post as empty — when in fact the caption is all there is,
# and on a talking-head video it usually carries the whole substance.
VIDEO_TEMPLATE = (
    "Post by @{account}.\n\nCaption:\n{caption}\n\n"
    "This post is a video, so there are no slides to read: everything the post "
    "states in writing is in the caption above. Extract the entities from it."
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
    shape: str = "other"


FENCED_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _json_blob(text: str) -> str:
    """Pull the JSON out of a model reply, object or array.

    Models wrap it in a fence and sometimes explain themselves afterwards, so
    neither 'strip the fences' nor 'the whole reply is JSON' survives contact.
    Take the fenced block if there is one, otherwise the outermost { } or [ ].
    """
    m = FENCED_RE.search(text)
    if m:
        return m.group(1).strip()
    # Whichever opens FIRST: in a bare array the first "{" is an element, not
    # the envelope, and slicing from it yields invalid JSON.
    candidates = [(text.find(o), o, c) for o, c in (("{", "}"), ("[", "]"))
                  if text.find(o) != -1]
    if candidates:
        start, _, close_c = min(candidates)
        end = text.rfind(close_c)
        if end > start:
            return text[start:end + 1]
    return text.strip()


def parse_extraction(text: str) -> tuple[str, list[Entity]]:
    """Return (shape, entities) from a model reply.

    Accepts both the object form `{"shape": ..., "entities": [...]}` and a bare
    array: a paid run must not be thrown away over a formatting detail.
    """
    try:
        data = json.loads(_json_blob(text))
    except json.JSONDecodeError as e:
        raise ValueError(f"risposta non JSON dal modello: {text[:200]!r}") from e

    shape = "other"
    if isinstance(data, dict):
        raw = (data.get("shape") or "").strip().lower()
        shape = raw if raw in SHAPES else "other"
        data = data.get("entities") or []
    return shape, _entities(data)


def parse_entities(text: str) -> list[Entity]:
    """Entities only. Kept for callers that do not care about the shape."""
    return parse_extraction(text)[1]


def _entities(data) -> list[Entity]:
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
                slide=_slide_index(item.get("slide")),
            )
        )
    return out


def _slide_index(raw) -> int:
    """0 means "from the caption", so it cannot be treated as missing."""
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 1


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
    is_video: bool = False,
) -> PostExtraction:
    template = VIDEO_TEMPLATE if (is_video and not slide_paths) else USER_TEMPLATE
    content: list[dict] = [
        {
            "type": "text",
            "text": template.format(
                account=account, caption=caption, n=len(slide_paths)
            ),
        }
    ]
    content.extend(_image_block(p) for p in slide_paths)

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        # Extraction is not a creative task: the same post must yield the same
        # list twice. The default (1.0) made runs differ from each other.
        temperature=0.0,
        messages=[{"role": "user", "content": content}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "[]")
    shape, entities = parse_extraction(text)

    return PostExtraction(
        shortcode=shortcode,
        account=account,
        caption=caption,
        entities=entities,
        usd=cost_usd(model, response.usage.input_tokens, response.usage.output_tokens),
        shape=shape,
    )
