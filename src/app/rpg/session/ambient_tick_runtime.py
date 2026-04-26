from __future__ import annotations

from typing import Any, Dict

from app.rpg.world.conversation_settings import (
    conversation_settings_from_runtime,
    should_attempt_autonomous_conversation,
)
from app.rpg.world.conversation_threads import maybe_advance_conversation_thread

AMBIENT_TICK_COMMANDS = {
    "__ambient_tick__",
    "__idle_tick__",
    "__world_tick__",
    "__ambient_tick_player_addressed__",
    "__ambient_tick_player_invited__",
    "__ambient_tick_quest__",
    "__ambient_tick_event__",
    "__ambient_tick_rumor__",
}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_ambient_tick_command(player_input: str) -> bool:
    return _safe_str(player_input).strip().lower() in AMBIENT_TICK_COMMANDS


def _forced_player_mode(command: str) -> str:
    command = _safe_str(command).strip().lower()
    if command == "__ambient_tick_player_invited__":
        return "player_invited"
    if command == "__ambient_tick_player_addressed__":
        return "player_addressed"
    return ""


def _forced_topic_type(command: str) -> str:
    command = _safe_str(command).strip().lower()
    if command == "__ambient_tick_quest__":
        return "quest"
    if command == "__ambient_tick_event__":
        return "recent_event"
    if command == "__ambient_tick_rumor__":
        return "rumor"
    return ""


def advance_autonomous_ambient_tick(
    *,
    player_input: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    tick: int,
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    settings = conversation_settings_from_runtime(runtime_state)
    command = _safe_str(player_input).strip().lower()

    force = is_ambient_tick_command(command)
    force_mode = _forced_player_mode(command)
    force_topic = _forced_topic_type(command)

    conversation_state = _safe_dict(simulation_state.get("conversation_thread_state"))
    debug = _safe_dict(conversation_state.get("debug"))
    last_tick = int(debug.get("last_autonomous_conversation_tick") or 0)

    should_attempt = should_attempt_autonomous_conversation(
        tick=tick,
        last_conversation_tick=last_tick,
        settings=settings,
        force=force,
    )

    if not should_attempt:
        return {
            "matched": force,
            "applied": False,
            "status": "ambient_tick_no_conversation",
            "reason": "settings_or_cooldown_prevented_conversation",
            "conversation_settings": settings,
            "source": "deterministic_ambient_tick_runtime",
        }

    conversation_result = maybe_advance_conversation_thread(
        simulation_state,
        player_input="__autonomous_ambient_tick__",
        tick=tick,
        settings=settings,
        autonomous=True,
        force=True,
        force_player_mode=force_mode,
        forced_topic_type=force_topic,
    )

    conversation_state = _safe_dict(simulation_state.get("conversation_thread_state"))
    debug = _safe_dict(conversation_state.get("debug"))
    if conversation_result.get("triggered"):
        debug["last_autonomous_conversation_tick"] = int(tick or 0)
    conversation_state["debug"] = debug
    simulation_state["conversation_thread_state"] = conversation_state

    return {
        "matched": force,
        "applied": bool(conversation_result.get("triggered")),
        "status": "ambient_tick_conversation" if conversation_result.get("triggered") else "ambient_tick_no_conversation",
        "conversation_result": conversation_result,
        "conversation_settings": settings,
        "source": "deterministic_ambient_tick_runtime",
    }