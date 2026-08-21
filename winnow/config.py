"""Load and validate config.toml. No personal data may live outside it."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from winnow import paths


@dataclass(frozen=True)
class Folder:
    name: str
    url: str
    active: bool
    kind: str


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


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} non trovato. Copia config.example.toml in config.toml "
            "e riempilo."
        )
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    limits = Limits(**raw["limits"])
    if limits.halt_eur_week <= limits.warn_eur_week:
        raise ValueError(
            "halt_eur_week deve essere maggiore di warn_eur_week: "
            f"{limits.halt_eur_week} <= {limits.warn_eur_week}"
        )

    folders = [Folder(**f) for f in raw["folders"]]
    for f in folders:
        if f.kind not in ("repo", "news"):
            raise ValueError(f"kind sconosciuto per la cartella {f.name!r}: {f.kind!r}")

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
    )


def override_posts(cfg: Config, posts: int) -> Config:
    """One run with a different cap, for clearing a backlog by hand.

    `posts_per_run` is tuned for the nightly rhythm; someone who installs winnow
    after two years of saving has hundreds of posts waiting, and eight a night
    means a month of drip-feed. The config on disk is not touched.
    """
    if posts < 1:
        raise ValueError("--posts vuole un numero maggiore di zero")
    return replace(cfg, limits=replace(cfg.limits, posts_per_run=posts))


def active_folders(cfg: Config) -> list[Folder]:
    return [f for f in cfg.folders if f.active]
