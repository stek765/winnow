"""Load and validate config.toml. No personal data may live outside it."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from winnow import paths


# Long enough for a sentence, short enough that it is not an essay: it is
# pasted into the extraction prompt for every post in the folder, so it is
# paid for on every single one.
HOLDS_MAX = 200


@dataclass(frozen=True)
class Folder:
    name: str
    url: str
    active: bool
    # What the reader keeps in here, in their own words. It used to be `kind`,
    # a two-value enum — "repo" or "news" — which was one person's way of
    # sorting their saved posts, and explained nothing to anyone else. A name
    # is ambiguous without a subject, and the reader is the only one who knows
    # what theirs is about.
    holds: str = ""


@dataclass(frozen=True)
class Limits:
    warn_eur_week: float
    halt_eur_week: float
    posts_per_run: int
    max_slides: int
    eur_per_usd: float


@dataclass(frozen=True)
class Config:
    username: str
    browser_profile: Path
    folders: list[Folder]
    limits: Limits
    model: str
    provider: str = "anthropic"
    base_url: str | None = None


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run 'winnow init' to create it."
        )
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    limits = Limits(**raw["limits"])
    if limits.halt_eur_week <= limits.warn_eur_week:
        raise ValueError(
            "halt_eur_week deve essere maggiore di warn_eur_week: "
            f"{limits.halt_eur_week} <= {limits.warn_eur_week}"
        )

    folders = []
    for f in raw["folders"]:
        f = dict(f)
        # `kind` is in every config written before this. Carried over rather
        # than dropped: blanking it would silently throw away an answer people
        # gave a question to fill.
        holds = f.pop("holds", None) or f.pop("kind", "") or ""
        f.pop("kind", None)
        if len(holds) > HOLDS_MAX:
            raise ValueError(
                f"la descrizione della cartella {f.get('name')!r} è troppo "
                f"lunga: {len(holds)} caratteri, il massimo è {HOLDS_MAX}")
        folders.append(Folder(**f, holds=holds))

    instagram = raw["instagram"]
    # Il profilo browser sta di default sotto la cartella dati: un comando
    # installato globalmente non ha una directory propria in cui metterlo.
    profile = instagram.get("browser_profile")
    return Config(
        username=instagram["username"],
        browser_profile=Path(profile) if profile else paths.browser_profile(),
        folders=folders,
        limits=limits,
        model=raw["api"]["model"],
        # Assente in ogni config scritta prima che winnow parlasse con
        # qualcun altro: quelle restano su Anthropic, che e' dove erano.
        provider=raw["api"].get("provider", "anthropic"),
        base_url=raw["api"].get("base_url"),
    )


def override_posts(cfg: Config, posts: int) -> Config:
    """One run with a different cap, for clearing a backlog by hand.

    `posts_per_run` is tuned for the daily rhythm; someone who installs winnow
    after two years of saving has hundreds of posts waiting, and eight a day
    means a month of drip-feed. The config on disk is not touched.
    """
    if posts < 1:
        raise ValueError("--posts needs a number above zero")
    return replace(cfg, limits=replace(cfg.limits, posts_per_run=posts))


def active_folders(cfg: Config) -> list[Folder]:
    return [f for f in cfg.folders if f.active]
