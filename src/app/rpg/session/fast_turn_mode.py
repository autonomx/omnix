from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

FAST_TURN_ENV = "RPG_FAST_TURN_MODE"
FAST_TURN_SETTINGS_VERSION = "fast_turn_mode_settings_v1"

_TRUE_VALUES = {"1", "true", "yes", "y", "on", "enabled", "fast"}
_FALSE_VALUES = {"0", "false", "no", "n", "off", "disabled"}
_FAST_NARRATION_MODES = {"deferred", "deterministic", "disabled", "blocking"}


@dataclass(frozen=True)
class FastTurnSettings:
    format_version: str = FAST_TURN_SETTINGS_VERSION
    enabled: bool = False
    mode: str = "standard"
    max_context_tokens: int = 3000
    max_output_tokens: int = 180
    one_blocking_narration_call: bool = True
    background_memory: bool = True
    background_audit: bool = True
    background_world_updates: bool = True
    narration_mode: str = "deferred"
    live_narration_llm: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "enabled": self.enabled,
            "mode": self.mode,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "one_blocking_narration_call": self.one_blocking_narration_call,
            "background_memory": self.background_memory,
            "background_audit": self.background_audit,
            "background_world_updates": self.background_world_updates,
            "narration_mode": self.narration_mode,
            "live_narration_llm": self.live_narration_llm,
        }


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().casefold()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def _int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except Exception:
        return default
    return max(minimum, min(maximum, parsed))


def _str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def fast_turn_enabled(performance_override: Mapping[str, Any] | None = None) -> bool:
    """Return whether fast-turn mode is enabled by override or environment."""

    override = _mapping(performance_override)
    if "fast_turn_mode" in override:
        return _bool(override.get("fast_turn_mode"), False)
    if "enabled" in override:
        return _bool(override.get("enabled"), False)
    return _bool(os.environ.get(FAST_TURN_ENV), False)


def resolve_fast_turn_settings(
    performance_override: Mapping[str, Any] | None = None,
    runtime_state: Mapping[str, Any] | None = None,
) -> FastTurnSettings:
    """Resolve stable fast-turn settings from env, runtime state, and overrides."""

    override = _mapping(performance_override)
    runtime = _mapping(runtime_state)
    runtime_settings = _mapping(runtime.get("fast_turn_settings") or runtime.get("settings"))
    enabled = fast_turn_enabled(override) or _bool(runtime_settings.get("fast_turn_mode"), False)
    mode = _str(override.get("fast_turn_mode_name") or runtime_settings.get("fast_turn_mode_name"), "fast" if enabled else "standard")
    narration_mode = _str(
        override.get("narration_mode") or runtime.get("narration_mode") or runtime_settings.get("narration_mode"),
        "deferred",
    ).casefold()
    if narration_mode not in _FAST_NARRATION_MODES:
        narration_mode = "deferred"

    return FastTurnSettings(
        enabled=enabled,
        mode=mode,
        max_context_tokens=_int(
            override.get("max_context_tokens") or runtime_settings.get("max_context_tokens"),
            3000,
            minimum=500,
            maximum=12000,
        ),
        max_output_tokens=_int(
            override.get("max_output_tokens") or runtime_settings.get("max_output_tokens"),
            180,
            minimum=40,
            maximum=600,
        ),
        one_blocking_narration_call=_bool(
            override.get("one_blocking_narration_call")
            if "one_blocking_narration_call" in override
            else runtime_settings.get("one_blocking_narration_call"),
            True,
        ),
        background_memory=_bool(override.get("background_memory", runtime_settings.get("background_memory")), True),
        background_audit=_bool(override.get("background_audit", runtime_settings.get("background_audit")), True),
        background_world_updates=_bool(
            override.get("background_world_updates", runtime_settings.get("background_world_updates")),
            True,
        ),
        narration_mode=narration_mode,
        live_narration_llm=_bool(override.get("enable_live_narration_llm"), False),
    )


def fast_turn_performance_override(
    performance_override: Mapping[str, Any] | None = None,
    runtime_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the runtime performance override used by fast player-facing turns."""

    settings = resolve_fast_turn_settings(performance_override, runtime_state)
    merged = dict(_mapping(performance_override))
    merged["fast_turn_mode"] = settings.enabled
    merged["fast_turn_settings"] = settings.as_dict()
    if settings.enabled:
        merged.setdefault("narration_mode", settings.narration_mode)
        merged.setdefault("enable_live_narration_llm", settings.live_narration_llm)
        merged.setdefault("enable_narration_retry", False)
        merged.setdefault("max_context_tokens", settings.max_context_tokens)
        merged.setdefault("max_output_tokens", settings.max_output_tokens)
        merged.setdefault("one_blocking_narration_call", settings.one_blocking_narration_call)
    return merged
