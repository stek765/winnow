"""Load and validate config.toml. No personal data may live outside it."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


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

    return Config(
        username=raw["instagram"]["username"],
        browser_profile=Path(raw["instagram"]["browser_profile"]),
        folders=folders,
        limits=limits,
        model=raw["api"]["model"],
    )


def active_folders(cfg: Config) -> list[Folder]:
    return [f for f in cfg.folders if f.active]
