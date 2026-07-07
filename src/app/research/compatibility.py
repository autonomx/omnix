"""Temporary server-only compatibility aliases for retired research inputs."""
from __future__ import annotations

import os
import threading
from collections import Counter

from pydantic import BaseModel, Field

LEGACY_RESEARCH_FIELDS = (
    "web_search_mode",
    "web_search_requested",
    "manualSearchRequested",
)
LEGACY_RESEARCH_MODES = (
    "automatic",
    "manual",
    "quick_search",
    "deep_research",
)

_lock = threading.Lock()
_counts: Counter[str] = Counter()


class ResearchCompatibilityStatus(BaseModel):
    aliases_enabled: bool
    sunset: str | None = None
    total_legacy_requests: int = 0
    alias_counts: dict[str, int] = Field(default_factory=dict)
    canonical_field: str = "web_research_mode"


def legacy_research_aliases_enabled() -> bool:
    value = os.environ.get("OMNIX_RESEARCH_LEGACY_ALIASES_ENABLED", "1")
    return value.strip().lower() not in {"0", "false", "off", "disabled"}


def legacy_research_alias_sunset() -> str | None:
    value = os.environ.get("OMNIX_RESEARCH_LEGACY_ALIAS_SUNSET", "").strip()
    return value or None


def record_legacy_research_aliases(aliases: list[str]) -> None:
    unique = list(dict.fromkeys(alias for alias in aliases if alias))
    if not unique:
        return
    with _lock:
        _counts["__requests__"] += 1
        _counts.update(unique)


def legacy_research_warnings(aliases: list[str]) -> list[str]:
    return [f"legacy_research_alias_deprecated:{alias}" for alias in dict.fromkeys(aliases)]


def research_compatibility_status() -> ResearchCompatibilityStatus:
    with _lock:
        snapshot = dict(_counts)
    total = int(snapshot.pop("__requests__", 0))
    keys = [*LEGACY_RESEARCH_FIELDS, *(f"mode:{mode}" for mode in LEGACY_RESEARCH_MODES)]
    return ResearchCompatibilityStatus(
        aliases_enabled=legacy_research_aliases_enabled(),
        sunset=legacy_research_alias_sunset(),
        total_legacy_requests=total,
        alias_counts={key: int(snapshot.get(key, 0)) for key in keys},
    )


def reset_research_compatibility_telemetry() -> None:
    with _lock:
        _counts.clear()
