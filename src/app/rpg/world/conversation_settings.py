from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


DEFAULT_CONVERSATION_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "autonomous_ticks_enabled": False,
    "show_ambient_conversations": True,
    "frequency": "normal",
    "min_ticks_between_conversations": 3,
    "thread_cooldown_ticks": 8,
    "max_active_threads": 2,
    "max_beats_per_thread": 4,
    "conversation_chance_percent": 30,
    "allow_player_addressed": True,
    "allow_player_invited": False,
    "player_inclusion_chance_percent": 10,
    "require_relevant_memory_to_address_player": True,
    "pending_response_timeout_ticks": 3,
    "allow_world_signals": True,
    "allow_world_events": True,
    "allow_relationship_effects": False,
    "allow_quest_discussion": True,
    "allow_event_discussion": True,
    "allow_rumor_discussion": True,
    "allow_memory_discussion": True,
    "max_world_signals_per_thread": 2,
    "max_world_events_per_thread": 4,
    "signal_strength_cap": 1,
}


FREQUENCY_TO_CHANCE = {
    "off": 0,
    "rare": 15,
    "normal": 30,
    "frequent": 60,
    "always": 100,
}


def conversation_settings_from_runtime(runtime_state: Dict[str, Any] | None) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    runtime_settings = _safe_dict(runtime_state.get("runtime_settings"))
    explicit = _safe_dict(runtime_settings.get("conversation_settings"))
    living_world = _safe_dict(runtime_settings.get("living_world"))
    nested = _safe_dict(living_world.get("conversation_settings"))

    settings = deepcopy(DEFAULT_CONVERSATION_SETTINGS)
    settings.update(nested)
    settings.update(explicit)
    return normalize_conversation_settings(settings)


def normalize_conversation_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    settings = deepcopy(_safe_dict(settings))
    merged = deepcopy(DEFAULT_CONVERSATION_SETTINGS)
    merged.update(settings)

    frequency = str(merged.get("frequency") or "normal").strip().lower()
    if frequency not in FREQUENCY_TO_CHANCE:
        frequency = "normal"
    merged["frequency"] = frequency

    merged["enabled"] = _safe_bool(merged.get("enabled"), True)
    merged["autonomous_ticks_enabled"] = _safe_bool(merged.get("autonomous_ticks_enabled"), False)
    merged["show_ambient_conversations"] = _safe_bool(merged.get("show_ambient_conversations"), True)

    merged["min_ticks_between_conversations"] = max(0, _safe_int(merged.get("min_ticks_between_conversations"), 3))
    merged["thread_cooldown_ticks"] = max(0, _safe_int(merged.get("thread_cooldown_ticks"), 8))
    merged["max_active_threads"] = max(1, _safe_int(merged.get("max_active_threads"), 2))
    merged["max_beats_per_thread"] = max(1, _safe_int(merged.get("max_beats_per_thread"), 4))
    merged["conversation_chance_percent"] = max(
        0,
        min(100, _safe_int(merged.get("conversation_chance_percent"), FREQUENCY_TO_CHANCE[frequency])),
    )

    merged["allow_player_addressed"] = _safe_bool(merged.get("allow_player_addressed"), True)
    merged["allow_player_invited"] = _safe_bool(merged.get("allow_player_invited"), False)
    merged["player_inclusion_chance_percent"] = max(
        0,
        min(100, _safe_int(merged.get("player_inclusion_chance_percent"), 10)),
    )
    merged["require_relevant_memory_to_address_player"] = _safe_bool(
        merged.get("require_relevant_memory_to_address_player"),
        True,
    )
    merged["pending_response_timeout_ticks"] = max(1, _safe_int(merged.get("pending_response_timeout_ticks"), 3))

    merged["allow_world_signals"] = _safe_bool(merged.get("allow_world_signals"), True)
    merged["allow_world_events"] = _safe_bool(merged.get("allow_world_events"), True)
    merged["allow_relationship_effects"] = _safe_bool(merged.get("allow_relationship_effects"), False)
    merged["allow_quest_discussion"] = _safe_bool(merged.get("allow_quest_discussion"), True)
    merged["allow_event_discussion"] = _safe_bool(merged.get("allow_event_discussion"), True)
    merged["allow_rumor_discussion"] = _safe_bool(merged.get("allow_rumor_discussion"), True)
    merged["allow_memory_discussion"] = _safe_bool(merged.get("allow_memory_discussion"), True)
    merged["max_world_signals_per_thread"] = max(0, _safe_int(merged.get("max_world_signals_per_thread"), 2))
    merged["max_world_events_per_thread"] = max(0, _safe_int(merged.get("max_world_events_per_thread"), 4))
    merged["signal_strength_cap"] = max(1, _safe_int(merged.get("signal_strength_cap"), 1))
    return merged


def write_conversation_settings_to_runtime(
    runtime_state: Dict[str, Any],
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    runtime_settings = _safe_dict(runtime_state.get("runtime_settings"))
    runtime_settings["conversation_settings"] = normalize_conversation_settings(settings)
    runtime_state["runtime_settings"] = runtime_settings
    return runtime_state


def should_attempt_autonomous_conversation(
    *,
    tick: int,
    last_conversation_tick: int,
    settings: Dict[str, Any],
    force: bool = False,
) -> bool:
    settings = normalize_conversation_settings(settings)
    if not settings.get("enabled"):
        return False
    if force:
        return True
    if not settings.get("autonomous_ticks_enabled"):
        return False
    min_delta = int(settings.get("min_ticks_between_conversations") or 0)
    if last_conversation_tick and int(tick or 0) - int(last_conversation_tick) < min_delta:
        return False

    chance = int(settings.get("conversation_chance_percent") or 0)
    if chance <= 0:
        return False
    if chance >= 100:
        return True

    # Deterministic pseudo-randomness from tick. This is replay-safe enough for
    # the current deterministic harness and avoids global RNG.
    bucket = (int(tick or 0) * 37 + 17) % 100
    return bucket < chance