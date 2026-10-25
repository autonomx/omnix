"""Infrastructure-only Environment System 2.0 seed-state helpers.

This module owns the first authoritative environment payload shape used by RPG
sessions.  It intentionally avoids derived values such as temperature,
visibility, light level, terrain condition, and season; later Environment 2.0
slices derive those from this source-of-truth state.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from app.apps.rpg.world.environment_memory import RECENT_CONDITION_KEYS
from app.apps.rpg.world.environment_weather import generate_weather_event

ENVIRONMENT_VERSION = 1
DAYS_PER_YEAR = 360
DEFAULT_REGION_ID = "starting_region"
DEFAULT_CLIMATE_PROFILE_ID = "temperate_hills"
EVENT_HISTORY_LIMIT = 12

EnvironmentSeedState = dict[str, Any]

_RECENT_CONDITION_DEFAULTS: dict[str, int] = dict(RECENT_CONDITION_KEYS)

_CONDITION_ALIASES: dict[str, str] = {
    "rainy": "rain",
    "raining": "rain",
    "cold, windy": "windy",
    "cold windy": "windy",
    "grey and still": "overcast",
    "gray and still": "overcast",
}


def build_initial_environment_seed_state(
    *,
    campaign_seed: int,
    campaign_contract: dict[str, Any] | None,
    location_id: str,
    location: dict[str, Any] | None = None,
    place_environment: dict[str, Any] | None = None,
) -> EnvironmentSeedState:
    """Create E2.0.1 authoritative environment state plus scene context.

    The returned `environment` object is safe to persist under
    `world.environment`. The returned `scene_environment_context` object is safe
    to persist under `scene.environment_context`. Both are deterministic for the
    same campaign seed, contract, and starting location.
    """

    normalized_location_id = _normalize_identifier(location_id, "starting_location")
    # A world's place says how it is met (its region, climate and exposure); the engine has no places of its own.
    location_defaults = place_environment or {}
    region_id = str(location_defaults.get("region_id") or DEFAULT_REGION_ID)
    climate_profile_id = str(location_defaults.get("climate_profile_id") or DEFAULT_CLIMATE_PROFILE_ID)
    time_label = str((location or {}).get("time_label") or "Day 1 • 08:00")
    absolute_minutes = _parse_absolute_minutes(time_label)
    environment_seed = _environment_seed(campaign_seed, campaign_contract or {}, normalized_location_id, climate_profile_id)
    weather_condition = _initial_weather_condition(location_defaults, location)
    recent_conditions = dict(_RECENT_CONDITION_DEFAULTS)
    calendar = _calendar_from_absolute_minutes(absolute_minutes)
    weather_event = generate_weather_event(
        environment_seed=environment_seed,
        region_id=region_id,
        climate_profile_id=climate_profile_id,
        absolute_minutes=absolute_minutes,
        calendar=calendar,
        recent_conditions=recent_conditions,
        condition_override=weather_condition,
    )
    environment = {
        "environment_version": ENVIRONMENT_VERSION,
        "region_id": region_id,
        "climate_profile_id": climate_profile_id,
        "environment_seed": environment_seed,
        "calendar": calendar,
        "absolute_minutes": absolute_minutes,
        "active_events": [weather_event],
        "recent_conditions": recent_conditions,
        "event_history": [],
        "event_history_limit": EVENT_HISTORY_LIMIT,
    }
    scene_context = _scene_environment_context(
        location_id=normalized_location_id,
        region_id=region_id,
        defaults=location_defaults,
        location=location,
    )
    return {"environment": environment, "scene_environment_context": scene_context}


def _environment_seed(campaign_seed: int, campaign_contract: dict[str, Any], location_id: str, climate_profile_id: str) -> int:
    contract_fingerprint = _contract_fingerprint(campaign_contract)
    return _stable_int("rpg_environment_v1", int(campaign_seed), contract_fingerprint, location_id, climate_profile_id)


def _contract_fingerprint(contract: dict[str, Any]) -> str:
    parts = [
        contract.get("contract_version"),
        contract.get("campaign_template"),
        contract.get("genre"),
        contract.get("tone"),
        contract.get("starting_location"),
        contract.get("difficulty"),
        contract.get("world_activity"),
        contract.get("economy_pressure"),
        contract.get("combat_lethality"),
    ]
    player = contract.get("player")
    if isinstance(player, dict):
        parts.extend([player.get("background"), player.get("build")])
    return "|".join(str(part or "") for part in parts)


def _stable_int(*parts: Any) -> int:
    text = "|".join(str(part) for part in parts)
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & 0x7FFF_FFFF


def _initial_weather_condition(location_defaults: dict[str, Any], location: dict[str, Any] | None) -> str:
    explicit = location_defaults.get("weather_condition")
    if explicit:
        return str(explicit)
    weather = str((location or {}).get("weather") or "clear").strip().lower()
    return _CONDITION_ALIASES.get(weather, _normalize_identifier(weather, "clear"))


def _scene_environment_context(
    *,
    location_id: str,
    region_id: str,
    defaults: dict[str, Any],
    location: dict[str, Any] | None,
) -> dict[str, Any]:
    scene_defaults = raw_scene if isinstance(raw_scene := defaults.get("scene"), dict) else {}
    location_name = str((location or {}).get("location") or location_id)
    return {
        "exposure": str(scene_defaults.get("exposure") or "outdoor"),
        "shelter": str(scene_defaults.get("shelter") or "exposed"),
        "light_override": scene_defaults.get("light_override"),
        "region_id": region_id,
        "location_id": location_id,
        "location_label": location_name,
    }


def _calendar_from_absolute_minutes(absolute_minutes: int) -> dict[str, int]:
    day_index = max(0, absolute_minutes // 1440)
    return {"year": 1 + day_index // DAYS_PER_YEAR, "day_of_year": 1 + (day_index % DAYS_PER_YEAR), "days_per_year": DAYS_PER_YEAR}


def _parse_absolute_minutes(time_label: str) -> int:
    match = re.search(r"day\s+(?P<day>\d+).*?(?P<hour>\d{1,2}):(?P<minute>\d{2})", time_label, flags=re.IGNORECASE)
    if not match:
        return 8 * 60
    day = max(1, int(match.group("day")))
    hour = max(0, min(23, int(match.group("hour"))))
    minute = max(0, min(59, int(match.group("minute"))))
    return (day - 1) * 1440 + hour * 60 + minute


def _normalize_identifier(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = re.sub(r"[^a-z0-9_]+", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback
