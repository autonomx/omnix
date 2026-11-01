"""Bundle BF — deterministic survival runtime tick integration.

This module advances canonical BA survival pressure once per authoritative live
turn.  It is intentionally independent from LLM/autoplay code and records its
own bounded evidence so reports, UI, and tests can see why hunger/thirst/fatigue
changed.
"""
from __future__ import annotations

from typing import Dict

from app.apps.rpg.rules.survival import DEFAULT_SURVIVAL_TICK_RATES


SURVIVAL_TICK_RATE_PROFILES: Dict[str, Dict[str, int]] = {
    "standard_turn": dict(DEFAULT_SURVIVAL_TICK_RATES),
    "wait": {"hunger": 1, "thirst": 2, "fatigue": 1},
    "travel": {"hunger": 2, "thirst": 3, "fatigue": 2},
    "rest": {"hunger": 1, "thirst": 1, "fatigue": 0},
    "sleep": {"hunger": 2, "thirst": 2, "fatigue": 0},
    "survival_action": {"hunger": 0, "thirst": 0, "fatigue": 0},
}
