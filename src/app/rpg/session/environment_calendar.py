"""Pure calendar and season helpers for RPG Environment 2.0."""
from __future__ import annotations

import hashlib
from typing import Any

DEFAULT_DAYS_PER_YEAR = 360
MINUTES_PER_DAY = 1440

SEASON_ORDER = ("early_spring", "spring", "summer", "early_autumn", "late_autumn", "winter")
SEASON_LABELS = {
    "early_spring": "Early Spring",
    "spring": "Spring",
    "summer": "Summer",
    "early_autumn": "Early Autumn",
    "late_autumn": "Late Autumn",
    "winter": "Winter",
}

REGION_SEASON_BIAS = {
    "market_road": "spring",
    "town": "spring",
    "trade_road": "early_autumn",
    "road_lowlands": "early_autumn",
    "mountain_pass": "winter",
    "northern_mountains": "winter",
    "abandoned_works": "late_autumn",
    "quarry_hills": "late_autumn",
}

CalendarState = dict[str, Any]


def derive_calendar_state(absolute_minutes: int, calendar: dict[str, Any] | None = None) -> CalendarState:
    """Derive day/year/minute/season state from absolute minutes.

    `season_id` is always derived from `absolute_minutes` and calendar config;
    callers should not persist it as mutable source-of-truth.
    """

    days_per_year = _days_per_year(calendar)
    minutes = max(0, int(absolute_minutes))
    day_index = minutes // MINUTES_PER_DAY
    minute_of_day = minutes % MINUTES_PER_DAY
    day = day_index + 1
    day_of_year = 1 + (day_index % days_per_year)
    year = 1 + (day_index // days_per_year)
    season_id = season_id_for_day(day_of_year, days_per_year=days_per_year)
    return {
        "absolute_minutes": minutes,
        "day": day,
        "year": year,
        "day_of_year": day_of_year,
        "days_per_year": days_per_year,
        "minute_of_day": minute_of_day,
        "season_id": season_id,
        "season_label": SEASON_LABELS[season_id],
        "day_label": f"Day {day}",
        "time_label": _time_label(day, minute_of_day),
    }


def season_id_for_day(day_of_year: int, *, days_per_year: int = DEFAULT_DAYS_PER_YEAR) -> str:
    """Return the derived season id for a day in the configured year."""

    normalized_day = 1 + ((max(1, int(day_of_year)) - 1) % max(1, int(days_per_year)))
    segment_size = max(1, int(days_per_year) // len(SEASON_ORDER))
    segment_index = min(len(SEASON_ORDER) - 1, (normalized_day - 1) // segment_size)
    return SEASON_ORDER[segment_index]


def absolute_minutes_for_calendar_day(day: int, minute_of_day: int = 0) -> int:
    """Convert a 1-based campaign day and minute-of-day to absolute minutes."""

    return max(0, int(day) - 1) * MINUTES_PER_DAY + max(0, min(MINUTES_PER_DAY - 1, int(minute_of_day)))


def absolute_minutes_for_day_of_year(year: int, day_of_year: int, minute_of_day: int = 0, *, days_per_year: int = DEFAULT_DAYS_PER_YEAR) -> int:
    """Convert calendar coordinates to absolute minutes."""

    safe_year = max(1, int(year))
    safe_days_per_year = max(1, int(days_per_year))
    safe_day = 1 + ((max(1, int(day_of_year)) - 1) % safe_days_per_year)
    campaign_day = (safe_year - 1) * safe_days_per_year + safe_day
    return absolute_minutes_for_calendar_day(campaign_day, minute_of_day)


def derive_initial_day_of_year(
    *,
    campaign_contract: dict[str, Any] | None,
    campaign_seed: int,
    region_id: str | None,
    days_per_year: int = DEFAULT_DAYS_PER_YEAR,
) -> dict[str, Any]:
    """Resolve deterministic initial day-of-year metadata.

    Contract values win, region bias can choose a seasonal window, and the seed
    selects a stable day within that window.
    """

    contract = campaign_contract if isinstance(campaign_contract, dict) else {}
    safe_days_per_year = max(1, int(days_per_year))
    explicit_day = _first_int(
        contract.get("initial_day_of_year"),
        contract.get("day_of_year"),
        _nested_get(contract, "world_options", "initial_day_of_year"),
        _nested_get(contract, "environment", "initial_day_of_year"),
    )
    if explicit_day is not None:
        return {
            "day_of_year": _normalize_day_of_year(explicit_day, safe_days_per_year),
            "source": "contract_day_of_year",
            "season_id": season_id_for_day(explicit_day, days_per_year=safe_days_per_year),
        }

    requested_season = _first_season_id(
        contract.get("initial_season"),
        contract.get("season_id"),
        _nested_get(contract, "world_options", "initial_season"),
        _nested_get(contract, "environment", "season_id"),
    )
    if requested_season:
        return _day_from_season(requested_season, campaign_seed, safe_days_per_year, source="contract_season")

    region_season = REGION_SEASON_BIAS.get(_normalize_identifier(region_id))
    if region_season:
        return _day_from_season(region_season, campaign_seed, safe_days_per_year, source="region_bias")

    day = 1 + (_stable_int("initial_day_of_year", campaign_seed, region_id or "default") % safe_days_per_year)
    return {"day_of_year": day, "source": "seed_default", "season_id": season_id_for_day(day, days_per_year=safe_days_per_year)}


def _day_from_season(season_id: str, seed: int, days_per_year: int, *, source: str) -> dict[str, Any]:
    season_index = SEASON_ORDER.index(season_id)
    segment_size = max(1, days_per_year // len(SEASON_ORDER))
    start = season_index * segment_size + 1
    end = min(days_per_year, start + segment_size - 1)
    span = max(1, end - start + 1)
    day = start + (_stable_int("season_day", season_id, seed) % span)
    return {"day_of_year": day, "source": source, "season_id": season_id}


def _days_per_year(calendar: dict[str, Any] | None) -> int:
    if isinstance(calendar, dict):
        value = _first_int(calendar.get("days_per_year"))
        if value is not None and value > 0:
            return value
    return DEFAULT_DAYS_PER_YEAR


def _time_label(day: int, minute_of_day: int) -> str:
    hour = minute_of_day // 60
    minute = minute_of_day % 60
    return f"Day {day} • {hour:02d}:{minute:02d}"


def _first_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
    return None


def _first_season_id(*values: Any) -> str | None:
    for value in values:
        normalized = _normalize_identifier(value)
        if normalized in SEASON_ORDER:
            return normalized
    return None


def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _normalize_day_of_year(day_of_year: int, days_per_year: int) -> int:
    return 1 + ((max(1, int(day_of_year)) - 1) % max(1, int(days_per_year)))


def _normalize_identifier(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _stable_int(*parts: Any) -> int:
    text = "|".join(str(part) for part in parts)
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & 0x7FFF_FFFF
