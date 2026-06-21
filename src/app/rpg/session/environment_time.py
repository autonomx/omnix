"""Deterministic time advancement for RPG Environment 2.0."""
from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from app.rpg.session.environment_calendar import derive_calendar_state

DEFAULT_TURN_MINUTES = 10
RECENT_24H_MINUTES = 24 * 60
RECENT_72H_MINUTES = 72 * 60
DEFAULT_HISTORY_LIMIT = 12

RAIN_CONDITIONS = {"rain", "storm"}
SNOW_CONDITIONS = {"snow", "blizzard"}
DRY_CONDITIONS = {"clear", "cloudy", "overcast", "windy"}
INTENSITIES = ("trace", "light", "moderate", "heavy", "severe")
WEATHER_ROTATION = ("clear", "cloudy", "rain", "fog", "windy", "snow", "storm")


def advance_environment_time(environment: dict[str, Any], *, elapsed_minutes: int = DEFAULT_TURN_MINUTES) -> dict[str, Any]:
    """Advance authoritative environment state by deterministic elapsed minutes.

    The helper returns a new environment dictionary. It increments absolute time,
    decrements event timers, moves expired events into bounded history, updates
    recent-condition counters, and creates deterministic replacement weather only
    when the prior weather event expires and no other weather event remains.
    """

    env = deepcopy(environment) if isinstance(environment, dict) else {}
    elapsed = max(0, int(elapsed_minutes))
    previous_minutes = _coerce_int(env.get("absolute_minutes"), 0)
    next_minutes = previous_minutes + elapsed
    env["absolute_minutes"] = next_minutes
    env["calendar"] = _calendar_for_environment(next_minutes, env.get("calendar"))

    active_events = [dict(event) for event in env.get("active_events", []) if isinstance(event, dict)]
    kept_events: list[dict[str, Any]] = []
    expired_events: list[dict[str, Any]] = []
    active_weather_condition = _current_weather_condition(active_events)

    for event in active_events:
        event_elapsed = elapsed if _event_counts_down(event) else 0
        remaining = _coerce_int(event.get("remaining_minutes"), 0) - event_elapsed
        event["remaining_minutes"] = remaining
        if remaining > 0:
            kept_events.append(event)
        else:
            expired = dict(event)
            expired["ended_at_minute"] = next_minutes
            expired["expired_after_elapsed_minutes"] = elapsed
            expired_events.append(expired)

    weather_expired = any(event.get("type") == "weather" for event in expired_events)
    if weather_expired and not any(event.get("type") == "weather" for event in kept_events):
        kept_events.append(_next_weather_event(env, previous_minutes=previous_minutes, started_at_minute=next_minutes))

    env["active_events"] = kept_events
    env["event_history"] = _bounded_history(env.get("event_history"), expired_events, _history_limit(env))
    env["recent_conditions"] = _advance_recent_conditions(env.get("recent_conditions"), active_weather_condition, elapsed)
    return env


def _calendar_for_environment(absolute_minutes: int, calendar: Any) -> dict[str, int]:
    derived = derive_calendar_state(absolute_minutes, calendar if isinstance(calendar, dict) else None)
    return {"year": derived["year"], "day_of_year": derived["day_of_year"], "days_per_year": derived["days_per_year"]}


def _event_counts_down(event: dict[str, Any]) -> bool:
    return event.get("remaining_minutes") is not None


def _current_weather_condition(events: list[dict[str, Any]]) -> str:
    for event in events:
        if event.get("type") == "weather":
            return str(event.get("condition") or "clear")
    return "clear"


def _next_weather_event(environment: dict[str, Any], *, previous_minutes: int, started_at_minute: int) -> dict[str, Any]:
    seed = _coerce_int(environment.get("environment_seed"), 0)
    region_id = str(environment.get("region_id") or "starting_region")
    climate_profile_id = str(environment.get("climate_profile_id") or "temperate_hills")
    roll = _stable_int("next_weather", seed, region_id, climate_profile_id, previous_minutes, started_at_minute)
    condition = WEATHER_ROTATION[roll % len(WEATHER_ROTATION)]
    intensity = INTENSITIES[(roll // 17) % len(INTENSITIES)]
    duration = (6 + ((roll // 31) % 18)) * 60
    return {
        "id": f"weather_{roll % 1_000_000:06d}",
        "type": "weather",
        "condition": condition,
        "intensity": intensity,
        "remaining_minutes": duration,
        "started_at_minute": started_at_minute,
        "region_id": region_id,
    }


def _bounded_history(history: Any, expired_events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    existing = [dict(event) for event in history if isinstance(event, dict)] if isinstance(history, list) else []
    combined = existing + expired_events
    return combined[-limit:]


def _history_limit(environment: dict[str, Any]) -> int:
    limit = _coerce_int(environment.get("event_history_limit"), DEFAULT_HISTORY_LIMIT)
    return max(1, limit)


def _advance_recent_conditions(recent_conditions: Any, condition: str, elapsed: int) -> dict[str, int]:
    recent = recent_conditions if isinstance(recent_conditions, dict) else {}
    rain = _coerce_int(recent.get("rain_minutes_24h"), 0)
    snow = _coerce_int(recent.get("snow_minutes_24h"), 0)
    dry = _coerce_int(recent.get("dry_minutes_72h"), 0)
    freezing = _coerce_int(recent.get("freezing_minutes_24h"), 0)
    if condition in RAIN_CONDITIONS:
        rain += elapsed
        dry = max(0, dry - elapsed)
    elif condition in SNOW_CONDITIONS:
        snow += elapsed
        freezing += elapsed
        dry = max(0, dry - elapsed)
    elif condition in DRY_CONDITIONS:
        dry += elapsed
    else:
        dry = max(0, dry - elapsed // 2)
    return {
        "rain_minutes_24h": min(RECENT_24H_MINUTES, rain),
        "snow_minutes_24h": min(RECENT_24H_MINUTES, snow),
        "dry_minutes_72h": min(RECENT_72H_MINUTES, dry),
        "freezing_minutes_24h": min(RECENT_24H_MINUTES, freezing),
    }


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


def _stable_int(*parts: Any) -> int:
    text = "|".join(str(part) for part in parts)
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & 0x7FFF_FFFF
