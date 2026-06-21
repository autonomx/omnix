"""Ecology read model derived from environment snapshots."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

PRESSURE_LEVELS = ("none", "low", "moderate", "high", "severe")


def derive_ecology_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic ecology signals without owning environment state."""

    snap = deepcopy(snapshot) if isinstance(snapshot, dict) else {}
    calendar = snap.get("calendar") if isinstance(snap.get("calendar"), dict) else {}
    weather = snap.get("weather") if isinstance(snap.get("weather"), dict) else {}
    resources = snap.get("resources") if isinstance(snap.get("resources"), dict) else {}
    condition = str(weather.get("condition") or "clear")
    intensity = str(weather.get("intensity") or "light")
    season_id = str(calendar.get("season_id") or "early_spring")
    temperature = _coerce_int(snap.get("temperature_c"), 12)
    water = _coerce_int(resources.get("water_availability"), 50)
    vegetation = _coerce_int(resources.get("vegetation"), 50)
    forage = _coerce_int(resources.get("forage_availability"), 50)
    snowpack = _coerce_int(resources.get("snowpack"), 0)
    drought = _coerce_int(resources.get("drought_pressure"), 0)
    frost = _coerce_int(resources.get("frost_pressure"), 0)

    plant_score = _plant_score(season_id, vegetation, water, drought, frost, condition)
    fish_score = _fish_score(season_id, water, condition, intensity, temperature)
    wildlife_score = _wildlife_score(season_id, forage, water, snowpack, drought)
    predator_score = _predator_score(snowpack, forage, water, drought, season_id)
    pest_score = _pest_score(season_id, temperature, water, condition, intensity)

    return {
        "wildlife_activity": _activity_label(wildlife_score),
        "fish_activity": _activity_label(fish_score),
        "plant_growth": _activity_label(plant_score),
        "herb_availability": _activity_label((plant_score + vegetation) // 2),
        "migration_pressure": _pressure_label(max(snowpack, drought, 100 - forage) // 20),
        "predator_pressure": _pressure_label(predator_score // 20),
        "pest_disease_risk": _pressure_label(pest_score // 20),
        "water_point_encounter_pressure": _pressure_label(max(0, drought + (60 - water)) // 20),
        "inputs": {
            "season_id": season_id,
            "condition": condition,
            "intensity": intensity,
            "temperature_c": temperature,
            "water_availability": water,
            "vegetation": vegetation,
            "forage_availability": forage,
            "snowpack": snowpack,
            "drought_pressure": drought,
            "frost_pressure": frost,
        },
    }


def _plant_score(
    season_id: str,
    vegetation: int,
    water: int,
    drought: int,
    frost: int,
    condition: str,
) -> int:
    seasonal = {
        "spring": 18,
        "summer": 10,
        "early_spring": 8,
        "early_autumn": 2,
        "late_autumn": -12,
        "winter": -25,
    }
    rain_bonus = 8 if condition in {"rain", "storm"} else 0
    score = vegetation + water // 5 + seasonal.get(season_id, 0) + rain_bonus
    score -= drought // 3 + frost // 3
    return _clamp(score)


def _fish_score(season_id: str, water: int, condition: str, intensity: str, temperature: int) -> int:
    if season_id in {"spring", "early_spring"}:
        seasonal = 10
    elif season_id == "winter":
        seasonal = -8
    else:
        seasonal = 0
    rain_bonus = 10 if condition in {"rain", "storm"} and intensity != "severe" else 0
    temperature_penalty = 10 if temperature <= -8 or temperature >= 34 else 0
    return _clamp(water + seasonal + rain_bonus - temperature_penalty)


def _wildlife_score(season_id: str, forage: int, water: int, snowpack: int, drought: int) -> int:
    if season_id in {"spring", "summer", "early_autumn"}:
        seasonal = 8
    elif season_id == "winter":
        seasonal = -10
    else:
        seasonal = 0
    return _clamp((forage + water) // 2 + seasonal - snowpack // 3 - drought // 4)


def _predator_score(snowpack: int, forage: int, water: int, drought: int, season_id: str) -> int:
    winter_bonus = 18 if season_id == "winter" else 0
    scarcity = max(0, 60 - forage) + max(0, 45 - water)
    return _clamp(snowpack // 2 + drought // 2 + scarcity // 2 + winter_bonus)


def _pest_score(season_id: str, temperature: int, water: int, condition: str, intensity: str) -> int:
    warm = 18 if 16 <= temperature <= 30 else 0
    wet = 16 if condition in {"rain", "storm", "fog"} and intensity != "trace" else 0
    seasonal = 12 if season_id in {"spring", "summer"} else 0
    return _clamp(warm + wet + seasonal + water // 8)


def _activity_label(score: int) -> str:
    if score >= 75:
        return "abundant"
    if score >= 55:
        return "active"
    if score >= 35:
        return "sparse"
    if score > 0:
        return "scarce"
    return "dormant"


def _pressure_label(index: int) -> str:
    return PRESSURE_LEVELS[max(0, min(len(PRESSURE_LEVELS) - 1, index))]


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


def _clamp(value: int) -> int:
    return max(0, min(100, int(value)))
