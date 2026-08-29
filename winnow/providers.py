"""Which model reads the slides, and how it is reached.

winnow needs one thing from a model: look at a few images and answer with JSON.
Three ways to get that, and the difference between them is one HTTP call — so
the choice belongs to the user, made once during `winnow init`, and not to the
code.

Only the OpenAI-compatible path is implemented by hand (httpx, already a
dependency): Ollama, LM Studio, llama.cpp and OpenAI itself all speak it, which
is what makes "connect your own model" a base URL instead of a plugin.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from winnow.budget import cost_usd

class Truncated(RuntimeError):
    """The model ran out of output budget mid-answer."""


ANTHROPIC, OPENAI, LOCAL = "anthropic", "openai", "local"

KEY_ENV = {ANTHROPIC: "ANTHROPIC_API_KEY", OPENAI: "OPENAI_API_KEY"}
CONSOLE = {
    ANTHROPIC: "https://console.anthropic.com/settings/keys",
    OPENAI: "https://platform.openai.com/api-keys",
}
LOCAL_BASE_URL = "http://localhost:11434/v1"      # Ollama


@dataclass(frozen=True)
class Choice:
    label: str
    provider: str
    model: str
    hint: str
    # The same sentence for the window, which speaks to whoever installed
    # winnow rather than to whoever contributes to it. Localisation is
    # duplication by definition; keeping the two on adjacent lines is what
    # stops them drifting, and it is why this is not a separate table.
    hint_it: str = ""


# Few, and each one for a different reason. A longer menu is a longer decision,
# and this one is made by someone who just wants the tool to work.
CHOICES: list[Choice] = [
    Choice("Claude Haiku 4.5", ANTHROPIC, "claude-haiku-4-5",
           "cheapest, ~$0.005 a post — recommended",
           "il più economico, ~$0,005 a post — consigliato"),
    Choice("Claude Sonnet 5", ANTHROPIC, "claude-sonnet-5",
           "reads dense slides better, ~4x the cost",
           "legge meglio le slide fitte, costa circa quattro volte tanto"),
    Choice("OpenAI GPT-4o mini", OPENAI, "gpt-4o-mini",
           "if you already have an OpenAI account",
           "se hai già un account OpenAI"),
    Choice("Your own model", LOCAL, "",
           "Ollama, LM Studio, anything speaking the OpenAI API — free",
           "Ollama, LM Studio, qualunque cosa parli l'API di OpenAI — gratis"),
]


def needs_key(provider: str) -> bool:
    """A local model has no console and no bill."""
    return provider in KEY_ENV


def cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """What that call cost. A model on your own machine costs nothing, and
    saying "0" is the truth, not a missing price."""
    if provider == LOCAL:
        return 0.0
    return cost_usd(model, input_tokens, output_tokens)


def _data_url(path: Path) -> str:
    return ("data:image/png;base64,"
            + base64.standard_b64encode(path.read_bytes()).decode("utf-8"))


def accepts_temperature(create) -> bool:
    """Does this SDK's `create` still take a temperature?

    anthropic 1.0.0 dropped the argument. Sent blind it is a TypeError before
    a single post is read; dropped blind it silently turns off the
    determinism extraction depends on. So it is asked.

    A signature we cannot read — `**kwargs`, a C function, a wrapper — is
    answered "yes": guessing "no" would quietly disable determinism on an SDK
    that supports it, while guessing "yes" fails loudly and gets fixed.

    ⚠️ Sending it no longer buys reproducibility, and nothing here can get it
    back. Measured 2026-08-26 on claude-haiku-4-5: with temperature 0 forced
    through `extra_body` — the API accepts it — two of four posts still came
    back different. Anything that compares two extractions (the bench, most of
    all) has to treat a difference as evidence only when it is bigger than
    that noise floor.
    """
    import inspect

    try:
        params = inspect.signature(create).parameters
    except (TypeError, ValueError):
        return True
    if "temperature" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def _anthropic(model: str, system: str, text: str, images: list[Path],
               max_tokens: int, temperature: float,
               on_progress=None) -> tuple[str, int, int]:
    """One call, streamed.

    Streaming is not a nicety here, it is the only way the call is allowed to
    happen: the SDK refuses a plain `create` whose `max_tokens` could take it
    past ten minutes — «Streaming is required for operations that may take
    longer than 10 minutes» — and a weekly recap of a backlog is exactly that
    request. It also turns three silent minutes into something a person can
    watch, which is what `on_progress` is for.
    """
    import anthropic

    content: list[dict] = [{"type": "text", "text": text}]
    content += [{"type": "image",
                 "source": {"type": "base64", "media_type": "image/png",
                            "data": base64.standard_b64encode(
                                p.read_bytes()).decode("utf-8")}}
                for p in images]
    messages = anthropic.Anthropic().messages
    extra = {"temperature": temperature} if accepts_temperature(
        messages.stream) else {}

    chunks: list[str] = []
    with messages.stream(
            model=model, max_tokens=max_tokens, system=system, **extra,
            messages=[{"role": "user", "content": content}]) as stream:
        for piece in stream.text_stream:
            chunks.append(piece)
            if on_progress:
                # Characters, not tokens: it is what has actually arrived, and
                # the caller decides how often to say anything about it.
                on_progress(sum(len(c) for c in chunks))
        r = stream.get_final_message()

    reply = "".join(chunks) or next(
        (b.text for b in r.content if b.type == "text"), "[]")
    if r.stop_reason == "max_tokens":
        # Truncated JSON parses as "malformed", which sends the reader looking
        # for a prompt bug. Say what actually happened. Measured 2026-08-21: a
        # 13-slide list post ran past 4000 output tokens mid-entity.
        exc = Truncated(f"reply truncated at {max_tokens} tokens: the post has "
                        "too many entries. Raise max_tokens.")
        # The cut-off text already cost real money (this is the weekly recap's
        # heaviest call). Carried on the exception, not returned, so the
        # signature stays "one reply or an error" — a caller that has somewhere
        # to put a partial answer can still reach it.
        exc.partial = reply
        # Same reasoning for the tokens: the API already billed for them, so a
        # caller that wants to record the spend does not have to guess it.
        exc.input_tokens = r.usage.input_tokens
        exc.output_tokens = r.usage.output_tokens
        raise exc
    return reply, r.usage.input_tokens, r.usage.output_tokens


def openai_payload(model: str, system: str, text: str, images: list[Path],
                   max_tokens: int, temperature: float) -> dict:
    """The request body, separated so it can be checked without a server."""
    content: list[dict] = [{"type": "text", "text": text}]
    content += [{"type": "image_url", "image_url": {"url": _data_url(p)}}
                for p in images]
    return {
        "model": model,
        # The recap asks for room a backlog might need (48,000). Anthropic
        # grants it and streams; most OpenAI-compatible models cap far lower
        # and refuse the whole request rather than writing less, so the ask is
        # clamped here instead of failing at the far end.
        "max_tokens": min(max_tokens, 16000),
        "temperature": temperature,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": content}],
    }


def read_openai_reply(data: dict) -> tuple[str, int, int]:
    """Pull out text and token counts, tolerating a server that omits usage —
    a local one often does, and a missing count is zero, not a crash."""
    choice = (data.get("choices") or [{}])[0]
    text = choice.get("message", {}).get("content") or ""
    # Read once: a server that truncates still reports usage in the same
    # response, so the count is here whether or not the finish reason below
    # sends this call down the Truncated branch.
    usage = data.get("usage") or {}
    tin = int(usage.get("prompt_tokens") or 0)
    tout = int(usage.get("completion_tokens") or 0)
    if choice.get("finish_reason") == "length":
        exc = Truncated("reply truncated: the post has too many entries. "
                        "Raise max_tokens.")
        # Same reasoning as the Anthropic path: the words already cost money,
        # so they ride on the exception instead of being thrown away.
        exc.partial = text
        exc.input_tokens = tin
        exc.output_tokens = tout
        raise exc
    return text, tin, tout


def _openai_compatible(base_url: str, key: str | None, model: str, system: str,
                       text: str, images: list[Path], max_tokens: int,
                       temperature: float) -> tuple[str, int, int]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    r = httpx.post(f"{base_url.rstrip('/')}/chat/completions",
                   json=openai_payload(model, system, text, images,
                                       max_tokens, temperature),
                   headers=headers, timeout=180.0)
    r.raise_for_status()
    return read_openai_reply(r.json())


def load_key(provider: str) -> None:
    """The key file, applied at the moment the key is needed.

    It used to be applied by `winnow collect` and nowhere else, which was true
    for as long as the collector was the only thing that called a model. The
    window then started runs of its own — a recap, a draw — inside a server
    process that never went through that command, and every one of them died
    on «Could not resolve authentication method», with the key sitting in
    `config/env` the whole time.

    So it belongs here: one place, the last one before the call, reached by
    the CLI, the window and the scheduled job alike. `setdefault`, never an
    overwrite — a key exported in the shell wins over the file, which is what
    lets a second account be used for one run without editing anything.
    """
    var = KEY_ENV.get(provider)
    if not var or os.environ.get(var):
        return
    from winnow import paths
    from winnow.setup import apply_env_file
    apply_env_file(paths.env_file())


def complete(provider: str, model: str, base_url: str | None, system: str,
             text: str, images: list[Path], max_tokens: int = 8000,
             temperature: float = 0.0,
             on_progress=None) -> tuple[str, int, int]:
    """One call, one reply, and the tokens it took. Same contract everywhere."""
    load_key(provider)
    if provider == ANTHROPIC:
        return _anthropic(model, system, text, images, max_tokens, temperature,
                          on_progress)
    if provider == OPENAI:
        return _openai_compatible("https://api.openai.com/v1",
                                  os.environ.get(KEY_ENV[OPENAI]), model,
                                  system, text, images, max_tokens, temperature)
    if provider == LOCAL:
        return _openai_compatible(base_url or LOCAL_BASE_URL, None, model,
                                  system, text, images, max_tokens, temperature)
    raise ValueError(f"unknown provider: {provider!r}")
