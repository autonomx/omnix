"""Environmental memory and terrain derivation for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any

RECENT_24H_MINUTES = 24 * 60
RECENT_72H_MINUTES = 72 * 60
RECENT_7D_MINUTES = 7 * 24 * 60

RECENT_CONDITION_KEYS = {
    "rain_minutes_24h": 0,
    "snow_minutes_24h": 0,
    "dry_minutes_72h": 0,
    "freezing_minutes_24h": 0,
    "storm_minutes_24h": 0,
    "mud_minutes_72h": 0,
    "snowpack_minutes_72h": 0,
    "dust_minutes_72h": 0,
    "drought_minutes_7d": 0,
    "thaw_minutes_24h": 0,
}


def normalize_recent_conditions(recent_conditions: dict[str, Any] | None) -> dict[str, int]:
    recent = recent_conditions if isinstance(recent_conditions, dict) else {}
    return {key: max(0, _coerce_int(recent.get(key), default)) for key, default in RECENT_CONDITION_KEYS.items()}


def _bounded_memory(memory: dict[str, int]) -> dict[str, int]:
    memory["rain_minutes_24h"] = min(RECENT_24H_MINUTES, memory["rain_minutes_24h"])
    memory["snow_minutes_24h"] = min(RECENT_24H_MINUTES, memory["snow_minutes_24h"])
    memory["freezing_minutes_24h"] = min(RECENT_24H_MINUTES, memory["freezing_minutes_24h"])
    memory["storm_minutes_24h"] = min(RECENT_24H_MINUTES, memory["storm_minutes_24h"])
    memory["thaw_minutes_24h"] = min(RECENT_24H_MINUTES, memory["thaw_minutes_24h"])
    memory["dry_minutes_72h"] = min(RECENT_72H_MINUTES, memory["dry_minutes_72h"])
    memory["mud_minutes_72h"] = min(RECENT_72H_MINUTES, memory["mud_minutes_72h"])
    memory["snowpack_minutes_72h"] = min(RECENT_72H_MINUTES, memory["snowpack_minutes_72h"])
    memory["dust_minutes_72h"] = min(RECENT_72H_MINUTES, memory["dust_minutes_72h"])
    memory["drought_minutes_7d"] = min(RECENT_7D_MINUTES, memory["drought_minutes_7d"])
    return memory


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
