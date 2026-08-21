"""Check claims against their source. Never report unverified as verified."""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

import httpx

GITHUB_API = "https://api.github.com"
HF_API = "https://huggingface.co"
REPO_RE = re.compile(r"^([A-Za-z0-9][\w.-]*)/([\w.-]+?)(?:\.git)?$")


@dataclass(frozen=True)
class Verification:
    checked: bool
    exists: bool | None = None
    stars: int | None = None
    last_commit: str | None = None
    archived: bool | None = None
    license: str | None = None
    description: str | None = None
    url: str | None = None
    note: str = ""


def normalize_repo_name(text: str) -> str | None:
    s = text.strip()
    if not s:
        return None
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^(www\.)?github\.com/", "", s)
    s = s.rstrip("/")
    m = REPO_RE.match(s)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def http_note(status: int, what: str = "GitHub") -> str:
    """Say which failure it was.

    Every non-200 used to read "(rate limit?)". A token expires a year after you
    create it, and a year later that note sends you hunting for a rate limit
    that is not there. The outcome stays the same — not checked, never a
    fabricated verification — but the reason has to be true.
    """
    if status == 401:
        return f"{what}: token non valido o scaduto (controlla GITHUB_TOKEN)"
    if status in (403, 429):
        return f"{what}: rate limit raggiunto, riprova piu' tardi"
    return f"{what} ha risposto {status}: non verificato"


def verify_repo(http: httpx.Client, owner_repo: str) -> Verification:
    try:
        r = http.get(
            f"{GITHUB_API}/repos/{owner_repo}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=15.0,
            # A renamed or transferred repository answers 301 with the new
            # location, and httpx does not follow redirects on its own. Left
            # unfollowed, `oobabooga/text-generation-webui` came back as
            # "GitHub ha risposto 301: non verificato" — a live 40k-star
            # project reported as unknown.
            follow_redirects=True,
        )
    except httpx.HTTPError as e:
        return Verification(checked=False, note=f"errore di rete: {e}")

    if r.status_code == 404:
        return Verification(checked=True, exists=False, note="repository inesistente")
    if r.status_code != 200:
        return Verification(checked=False, note=http_note(r.status_code))

    d = r.json()
    pushed = (d.get("pushed_at") or "")[:10] or None
    return Verification(
        checked=True,
        exists=True,
        stars=d.get("stargazers_count"),
        last_commit=pushed,
        archived=d.get("archived"),
        license=(d.get("license") or {}).get("spdx_id"),
        description=d.get("description"),
        url=d.get("html_url"),
    )


def _slug(text: str) -> str:
    """Comparable form of a name: 'Open Notebook' and 'open-notebook' match."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _model_matches(model_id: str, wanted: str) -> bool:
    """Does this HuggingFace id really name the model we asked for?

    An id is `owner/model`. A slide names either the bare model ('Qwen3-32B')
    or the full id, so both forms count — but only as the whole thing, never as
    a fragment of a longer name. 'Codex' must not match
    'Opus4.7-GODs.Ghost.Codex-4B'.
    """
    if not model_id:
        return False
    bare = model_id.split("/")[-1]
    return wanted in (_slug(model_id), _slug(bare))


def _from_item(item: dict, note: str) -> Verification:
    return Verification(
        checked=True,
        exists=True,
        stars=item.get("stargazers_count"),
        last_commit=(item.get("pushed_at") or "")[:10] or None,
        archived=item.get("archived"),
        license=(item.get("license") or {}).get("spdx_id"),
        description=item.get("description"),
        url=item.get("html_url"),
        note=note,
    )


def search_repo(http: httpx.Client, name: str) -> Verification:
    """Find a repository from a display name, e.g. 'Open Notebook'.

    Slides print the product name, not the owner/name slug. Refusing to guess
    the owner is correct, but on its own nothing ever gets verified — so we ask
    GitHub instead of guessing.

    Two rules keep this honest, both learned from real failures on 2026-08-20:
      - search `in:name` only. Searching descriptions too matched 'AI Job
        Search' to a repo called career-ops.
      - require the repo name to actually equal the queried name. Sorting by
        stars alone returns the most famous repo containing those words, which
        is how 'No AI Slop' became a website builder with 9.6k stars.
    Attaching real numbers to the wrong project is worse than not checking.
    """
    query = name.strip()
    if not query:
        return Verification(checked=False, note="nome vuoto")
    try:
        r = http.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": f"{query} in:name", "sort": "stars",
                    "order": "desc", "per_page": 10},
            headers={"Accept": "application/vnd.github+json"},
            timeout=20.0,
        )
    except httpx.HTTPError as e:
        return Verification(checked=False, note=f"errore di rete: {e}")

    if r.status_code != 200:
        return Verification(
            checked=False,
            note=http_note(r.status_code, "ricerca GitHub"),
        )

    items = r.json().get("items", [])
    wanted = _slug(query)
    exact = [i for i in items if _slug((i.get("name") or "")) == wanted]

    if not exact:
        near = ", ".join(i.get("full_name", "?") for i in items[:3])
        # NOT exists=False. Search failing to find a name is weaker than the
        # thing being absent: a renamed repository disappears from the index
        # under its old name, which is how `text-generation-webui` and
        # `Open Interpreter` — both alive, both moved — were declared
        # non-existent. `checked=False` says what actually happened.
        return Verification(
            checked=False,
            note=f"la ricerca non trova un repository chiamato {name!r} "
                 "(puo' essere stato rinominato, o non essere un repository)"
                 + (f" | simili scartati: {near}" if near else ""),
        )

    top = exact[0]
    note = f"corrispondenza esatta del nome per {name!r}"
    if len(exact) > 1:
        rivals = ", ".join(
            f"{i.get('full_name')} (⭐{i.get('stargazers_count')}, "
            f"{(i.get('pushed_at') or '')[:10]})"
            for i in exact[1:3]
        )
        note += f" | ⚠️ omonimi: {rivals}"
    return _from_item(top, note)


def resolve_repo(http: httpx.Client, name: str) -> Verification:
    """Verify a repo whether the slide gave a slug or just a display name."""
    slug = normalize_repo_name(name)
    if slug is not None:
        return verify_repo(http, slug)
    return search_repo(http, name)


def verify_model(http: httpx.Client, name: str) -> Verification:
    """Look a model up on HuggingFace.

    Sorted by downloads, not by HuggingFace's default order: a plain search for
    'Qwen3-32B' returns a random community conversion with zero downloads above
    the official model. Download count is also the only cheap signal of whether
    a hit is the canonical model or somebody's fine-tune, so it is reported.
    """
    try:
        r = http.get(
            f"{HF_API}/api/models",
            params={"search": name, "limit": 5, "sort": "downloads",
                    "direction": -1},
            timeout=15.0,
        )
    except httpx.HTTPError as e:
        return Verification(checked=False, note=f"errore di rete: {e}")

    if r.status_code != 200:
        return Verification(checked=False, note=http_note(r.status_code, "HuggingFace"))

    hits = r.json()
    if not hits:
        return Verification(
            checked=True,
            exists=False,
            note=f"nessun modello su HuggingFace corrisponde a {name!r}",
        )

    # Same rule as search_repo: the name has to actually match. Searching
    # 'Claude Code' on 2026-08-20 returned DavidAU/Qwen3.6-40B-Claude-4.6-Opus-
    # Deckard-NEO-GGUF, and its 707 likes were reported as Claude Code's. A
    # substring is not an identification.
    wanted = _slug(name)
    exact = [h for h in hits if _model_matches(h.get("modelId") or "", wanted)]
    if not exact:
        near = ", ".join(h.get("modelId", "?") for h in hits[:3])
        return Verification(
            checked=True, exists=False,
            note=f"nessun modello si chiama esattamente {name!r}"
                 + (f" | simili scartati: {near}" if near else ""),
        )

    top = exact[0]
    downloads = top.get("downloads") or 0
    others = ", ".join(h.get("modelId", "?") for h in exact[1:3])
    note = f"{downloads} download"
    if downloads < 1000:
        note += " — marginale, forse non e' il modello canonico"
    if others:
        note += f" | altri: {others}"

    return Verification(
        checked=True,
        exists=True,
        stars=top.get("likes"),
        description=top.get("modelId"),
        url=f"{HF_API}/{top.get('modelId')}",
        note=note,
    )


def llmfit_available() -> bool:
    return shutil.which("llmfit") is not None


def hardware_note(name: str) -> str:
    """Ask llmfit whether this model fits the local machine. Best effort."""
    if not llmfit_available():
        return ""
    try:
        out = subprocess.run(
            ["llmfit", "fit", name, "--json"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as e:
        return f"llmfit non eseguibile: {e}"
    return out.stdout.strip() if out.returncode == 0 else out.stderr.strip()[:200]
