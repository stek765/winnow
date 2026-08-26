"""Load and validate config.toml. No personal data may live outside it."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from winnow import paths


@dataclass(frozen=True)
class Folder:
    """A saved folder: its name, where it is, and whether winnow reads it.

    There used to be a third thing — `kind`, then `holds` — meant to tell the
    extractor what the folder was about. Both are gone, and the reason is
    worth keeping: `kind` was validated, stored and exposed for months and
    read by nobody, and `holds` was measured on 2026-08-26 against a control
    arm. A description that actively *contradicted* a folder's contents moved
    the extraction 5 times in 12, while the same post run twice with no
    description at all moved 4 times in 12 — indistinguishable from noise, and
    not one thing changed its kind. A field that survives only because nobody
    checked is the kind this repo keeps finding.
    """
    name: str
    url: str
    active: bool


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
        # Every config written so far carries one of these. Ignored, not
        # rejected: a key that stopped meaning anything must not stop somebody
        # else's tool from starting.
        f.pop("kind", None)
        f.pop("holds", None)
        folders.append(Folder(**f))

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
