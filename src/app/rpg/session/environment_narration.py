"""Narration guardrails for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any

FORBIDDEN_ENVIRONMENT_MUTATIONS = (
    "create_new_weather",
    "clear_weather",
    "advance_time",
    "change_season",
    "invent_temperature",
    "invent_visibility",
    "invent_hazards",
    "contradict_current_environment",
)

ALLOWED_ENVIRONMENT_NARRATION = (
    "describe_current_snapshot",
    "emphasize_sensory_details",
    "interpret_from_actor_perspective",
    "mention_encoded_practical_implications",
)


EnvironmentNarrationResult = dict[str, Any]


def build_environment_narration_contract(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Return read-only environment context for narrator prompts/contracts."""

    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    return {
        "authority": "read_only_environment_snapshot",
        "environment_snapshot": safe_snapshot,
        "allowed": list(ALLOWED_ENVIRONMENT_NARRATION),
        "forbidden": list(FORBIDDEN_ENVIRONMENT_MUTATIONS),
        "instruction": "Describe the current environment snapshot; do not create, clear, advance, or contradict environment state.",
    }


def environment_narration_prompt_block(snapshot: dict[str, Any] | None) -> str:
    """Return a compact prompt block that makes environment authority explicit."""

    contract = build_environment_narration_contract(snapshot)
    weather = _weather_label(contract["environment_snapshot"])
    display = contract["environment_snapshot"].get("display") if isinstance(contract["environment_snapshot"].get("display"), dict) else {}
    return "\n".join(
        [
            "Environment Snapshot (read-only):",
            f"- Time: {display.get('day_time') or 'Not tracked yet'}",
            f"- Weather: {weather}",
            f"- Temperature: {display.get('temperature') or 'Not tracked yet'}",
            f"- Terrain: {display.get('terrain') or 'Not tracked yet'}",
            "Narration rule: describe these values only; never mutate weather, time, season, temperature, visibility, hazards, or terrain.",
        ]
    )


def validate_environment_narration(narration: str, snapshot: dict[str, Any] | None) -> EnvironmentNarrationResult:
    """Soft-check narration for obvious environment contradictions."""

    text = str(narration or "")
    lowered = text.lower()
    weather = _weather_condition(snapshot)
    violations: list[str] = []
    if weather != "storm" and ("storm rolls in" in lowered or "sudden storm" in lowered):
        violations.append("invented_storm")
    if weather not in {"clear", "windy"} and ("clear sky" in lowered or "sunny and dry" in lowered):
        violations.append("contradicts_weather")
    if weather != "rain" and ("rain begins" in lowered or "rain starts" in lowered):
        violations.append("invented_rain")
    if "hours pass" in lowered or "time passes" in lowered or "season changes" in lowered:
        violations.append("mutates_time_or_season")
    ok = not violations
    return {
        "ok": ok,
        "violations": violations,
        "corrected_narration": text if ok else environment_safe_narration_fallback(snapshot),
    }


def environment_safe_narration_fallback(snapshot: dict[str, Any] | None) -> str:
    """Return deterministic fallback prose grounded only in the snapshot."""

    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    display = safe_snapshot.get("display") if isinstance(safe_snapshot.get("display"), dict) else {}
    weather = display.get("weather") or _weather_label(safe_snapshot)
    terrain = display.get("terrain") or str(safe_snapshot.get("terrain_condition") or "Not tracked yet")
    context = display.get("context") or _context_label(safe_snapshot)
    return f"The current environment remains {weather}; the ground is {terrain}, and the scene context is {context}."


def _weather_condition(snapshot: dict[str, Any] | None) -> str:
    weather = snapshot.get("weather") if isinstance(snapshot, dict) and isinstance(snapshot.get("weather"), dict) else {}
    return str(weather.get("condition") or "clear")


def _weather_label(snapshot: dict[str, Any]) -> str:
    display = snapshot.get("display") if isinstance(snapshot.get("display"), dict) else {}
    if display.get("weather"):
        return str(display["weather"])
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    condition = str(weather.get("condition") or "Not tracked yet")
    intensity = str(weather.get("intensity") or "").strip()
    return f"{intensity.title()} {condition.title()}".strip()


def _context_label(snapshot: dict[str, Any]) -> str:
    context = snapshot.get("context") if isinstance(snapshot.get("context"), dict) else {}
    exposure = str(context.get("exposure") or "Not tracked yet")
    shelter = str(context.get("shelter") or "Not tracked yet")
    return f"{exposure} / {shelter}"
