"""Long horizon environment signals for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any

SIGNAL_DEFAULTS = {
    "water_availability": 50,
    "vegetation": 50,
    "soil_moisture": 50,
    "forage_availability": 50,
    "snowpack": 0,
    "drought_pressure": 0,
    "flood_pressure": 0,
    "frost_pressure": 0,
}


def derive_environment_signals(profile: dict[str, Any], recent_conditions: dict[str, Any] | None = None) -> dict[str, int]:
    baselines = profile.get("resource_baselines") if isinstance(profile.get("resource_baselines"), dict) else {}
    return {key: _coerce_int(baselines.get(key), fallback) for key, fallback in SIGNAL_DEFAULTS.items()}


def _coerce_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return fallback
