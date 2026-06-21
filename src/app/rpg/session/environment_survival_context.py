"""Read-only survival exposure context from environment snapshots."""
from __future__ import annotations

from typing import Any

RISK_LABELS = ("none", "low", "moderate", "high", "severe")


def derive_survival_exposure_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic exposure context without mutating environment state."""

    snap = snapshot if isinstance(snapshot, dict) else {}
    context = snap.get("context") if isinstance(snap.get("context"), dict) else {}
    weather = snap.get("weather") if isinstance(snap.get("weather"), dict) else {}
    exposure = str(context.get("exposure") or "outdoor")
    shelter = str(context.get("shelter") or "exposed")
    condition = str(weather.get("condition") or "clear")
    intensity = str(weather.get("intensity") or "light")
    terrain = str(snap.get("terrain_condition") or "dry")
    wind = str(snap.get("wind") or "light")
    temperature = _coerce_int(snap.get("temperature_c"), 12)

    cold_score = _temperature_cold_score(temperature)
    heat_score = _temperature_heat_score(temperature)
    wet_score = _weather_wet_score(condition, intensity, exposure)
    wind_score = 1 if wind in {"moderate", "strong"} and cold_score > 0 and exposure != "indoor" else 0
    terrain_score = 1 if terrain in {"deep_snow", "slush", "muddy"} and exposure != "indoor" else 0
    mitigation = _shelter_mitigation(exposure, shelter)
    exposure_score = max(0, cold_score + heat_score + wet_score + wind_score + terrain_score - mitigation)

    return {
        "cold_risk": RISK_LABELS[max(0, min(len(RISK_LABELS) - 1, cold_score + wind_score - mitigation))],
        "heat_risk": RISK_LABELS[max(0, min(len(RISK_LABELS) - 1, heat_score - mitigation))],
        "wet_exposure": RISK_LABELS[max(0, min(len(RISK_LABELS) - 1, wet_score - mitigation))],
        "terrain_exposure": RISK_LABELS[max(0, min(len(RISK_LABELS) - 1, terrain_score))],
        "overall_exposure": RISK_LABELS[max(0, min(len(RISK_LABELS) - 1, exposure_score))],
        "shelter_quality": _shelter_quality(exposure, shelter),
        "rest_context": _rest_context(exposure, shelter, exposure_score),
        "inputs": {
            "temperature_c": temperature,
            "exposure": exposure,
            "shelter": shelter,
            "condition": condition,
            "intensity": intensity,
            "wind": wind,
            "terrain_condition": terrain,
        },
    }


def _temperature_cold_score(temperature_c: int) -> int:
    if temperature_c <= -15:
        return 4
    if temperature_c <= -5:
        return 3
    if temperature_c <= 2:
        return 2
    if temperature_c <= 8:
        return 1
    return 0


def _temperature_heat_score(temperature_c: int) -> int:
    if temperature_c >= 42:
        return 4
    if temperature_c >= 35:
        return 3
    if temperature_c >= 30:
        return 2
    if temperature_c >= 26:
        return 1
    return 0


def _weather_wet_score(condition: str, intensity: str, exposure: str) -> int:
    if exposure == "indoor":
        return 0
    if condition not in {"rain", "storm", "snow", "blizzard"}:
        return 0
    if intensity in {"heavy", "severe", "extreme"}:
        return 2
    return 1


def _shelter_mitigation(exposure: str, shelter: str) -> int:
    if exposure == "indoor":
        return 4
    if shelter in {"sheltered", "partial", "covered"}:
        return 2
    return 0


def _shelter_quality(exposure: str, shelter: str) -> str:
    if exposure == "indoor":
        return "protected"
    if shelter in {"sheltered", "covered"}:
        return "good"
    if shelter == "partial":
        return "partial"
    return "exposed"


def _rest_context(exposure: str, shelter: str, exposure_score: int) -> str:
    if exposure == "indoor" or shelter in {"sheltered", "covered"}:
        return "rest_friendly"
    if exposure_score >= 3:
        return "rest_difficult"
    if exposure_score > 0:
        return "rest_watchful"
    return "rest_neutral"


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
