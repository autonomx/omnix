"""Fitting a dubbed line to the time the original took (Voice Studio Phase 6).

Each line has a budget: how long the source speaker took. A take that lands
within ``FIT_TOLERANCE`` of it fits as rendered. Otherwise it is time-stretched,
never by more than ``STRETCH_LIMIT``; a take still too long after that goes back
to the translator for a shorter wording (at most ``MAX_SHORTENINGS`` times) and
is then flagged for review. Engines with a duration control (OmniVoice) render
to the budget directly.
"""
from __future__ import annotations

from dataclasses import dataclass

FIT_TOLERANCE = 0.10
STRETCH_LIMIT = 0.15
MAX_SHORTENINGS = 2
DURATION_ENGINES = frozenset({"omnivoice"})


@dataclass(frozen=True)
class Fit:
    # fits: within tolerance as rendered; stretched: within the stretch limit; over: still too
    # long at the limit (shorten, then review); short: too short even slowed to the limit.
    status: str
    # Take length over budget, before stretching.
    ratio: float
    # Tempo to apply (>1 plays faster); 1.0 for none.
    tempo: float

    @property
    def fitted_ratio(self) -> float:
        return self.ratio / self.tempo


def plan_fit(take_seconds: float, budget_seconds: float) -> Fit:
    """How to fit a take of ``take_seconds`` into ``budget_seconds``."""
    if budget_seconds <= 0:
        return Fit("fits", 1.0, 1.0)
    ratio = take_seconds / budget_seconds
    if abs(ratio - 1.0) <= FIT_TOLERANCE:
        return Fit("fits", ratio, 1.0)
    # Stretch toward the budget, never past the limit; the status says where the stretched take lands
    # (a take 20% short slowed by 15% is within tolerance: stretched, not short).
    tempo = min(max(ratio, 1.0 - STRETCH_LIMIT), 1.0 + STRETCH_LIMIT)
    fitted = ratio / tempo
    if abs(fitted - 1.0) <= FIT_TOLERANCE:
        return Fit("stretched", ratio, tempo)
    return Fit("over" if fitted > 1.0 else "short", ratio, tempo)


def within_tolerance(take_seconds: float, budget_seconds: float) -> bool:
    return budget_seconds > 0 and abs(take_seconds / budget_seconds - 1.0) <= FIT_TOLERANCE
