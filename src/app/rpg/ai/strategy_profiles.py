"""Strategy Profiles for the Dynamic NPC Intent System.

This module defines strategy profiles that drive NPC behavior
and decision-making in different contexts.
"""

from __future__ import annotations

from typing import Any, Dict

# Strategy profile definitions
STRATEGY_PROFILES: Dict[str, Dict[str, float]] = {
    "aggressive": {
        "attack_bias": 1.5,
        "diplomacy_bias": 0.5,
        "risk_tolerance": 0.8,
        "cooperation_bias": 0.3,
    },
    "diplomatic": {
        "attack_bias": 0.5,
        "diplomacy_bias": 1.5,
        "risk_tolerance": 0.3,
        "cooperation_bias": 0.8,
    },
    "chaotic": {
        "randomness": 0.5,
        "attack_bias": 1.0,
        "diplomacy_bias": 1.0,
        "risk_tolerance": 0.9,
        "cooperation_bias": 0.4,
    },
    "defensive": {
        "defend_bias": 1.5,
        "attack_bias": 0.7,
        "risk_tolerance": 0.2,
        "cooperation_bias": 0.6,
    },
    "opportunistic": {
        "attack_bias": 1.1,
        "diplomacy_bias": 0.9,
        "risk_tolerance": 0.7,
        "cooperation_bias": 0.5,
        "ambush_bias": 1.3,
    },
    "passive": {
        "attack_bias": 0.3,
        "diplomacy_bias": 1.0,
        "risk_tolerance": 0.1,
        "cooperation_bias": 0.7,
        "avoidance_bias": 1.4,
    },
}


def get_strategy_profile(strategy: str) -> Dict[str, float]:
    """Get a strategy profile by name.

    Args:
        strategy: Strategy name (e.g., "aggressive", "diplomatic").

    Returns:
        Strategy profile dict with bias values.
    """
    return STRATEGY_PROFILES.get(strategy, STRATEGY_PROFILES["diplomatic"])


def get_strategy_bias(strategy: str) -> Dict[str, float]:
    """Get strategy bias values.

    Args:
        strategy: Strategy name.

    Returns:
        Dict with bias values for action weighting.
    """
    return get_strategy_profile(strategy)


def list_strategies() -> list:
    """List all available strategy profiles.

    Returns:
        List of strategy names.
    """
    return list(STRATEGY_PROFILES.keys())