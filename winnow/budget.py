"""Spend accounting and the emergency brake.

This is the only module that can stop the whole system. Keep it boring.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from winnow.config import Limits

HALT_FILE = "HALTED"

# usd per 1M tokens: (input, output). Fissati 2026-08-20.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (5.00, 25.00),
    # OpenAI, listino dichiarato dal fornitore. Da ricontrollare come gli altri:
    # un prezzo vecchio non rompe niente, falsa solo il registro della spesa.
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


class Halted(RuntimeError):
    """Raised when the run must not proceed. Never caught to retry."""


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES[model]
    return input_tokens / 1_000_000 * price_in + output_tokens / 1_000_000 * price_out


def record_spend(path: Path, usd: float, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    runs = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    runs.append({"ts": when.isoformat(), "usd": round(usd, 6)})
    path.write_text(json.dumps(runs, indent=2), encoding="utf-8")


def weekly_spend(path: Path, now: datetime) -> float:
    if not path.exists():
        return 0.0
    cutoff = now - timedelta(days=7)
    runs = json.loads(path.read_text(encoding="utf-8"))
    return sum(r["usd"] for r in runs if datetime.fromisoformat(r["ts"]) >= cutoff)


def is_halted(state_dir: Path) -> bool:
    return (state_dir / HALT_FILE).exists()


def write_halt(state_dir: Path, reason: str, spend_eur: float, when: datetime) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / HALT_FILE).write_text(
        f"winnow si e' fermato il {when.date()} ({when:%H:%M}).\n\n"
        f"Motivo: {reason}\n"
        f"Spesa registrata negli ultimi 7 giorni: EUR {spend_eur:.2f}\n\n"
        "La spesa attesa e' di circa 0,50 USD a settimana. Una cifra molto piu'\n"
        "alta non e' 'un po' caro': e' un difetto. Controlla seen.json e i log\n"
        "prima di ripartire.\n\n"
        "Per ripartire, cancella questo file a mano. Il programma non lo tocca.\n",
        encoding="utf-8",
    )


def check_brake(
    state_dir: Path, spend_path: Path, limits: Limits, now: datetime
) -> str:
    """Return 'ok' or 'warn'. Raise Halted if the run must not proceed."""
    if is_halted(state_dir):
        raise Halted(
            f"{state_dir / HALT_FILE} esiste. Leggilo e cancellalo a mano "
            "per ripartire."
        )

    spend_eur = weekly_spend(spend_path, now) * limits.eur_per_usd

    if spend_eur >= limits.halt_eur_week:
        write_halt(
            state_dir,
            f"spesa settimanale oltre la soglia di EUR {limits.halt_eur_week:.2f}",
            spend_eur,
            now,
        )
        raise Halted(
            f"Spesa settimanale EUR {spend_eur:.2f} oltre la soglia "
            f"EUR {limits.halt_eur_week:.2f}. Arresto definitivo."
        )

    return "warn" if spend_eur >= limits.warn_eur_week else "ok"
