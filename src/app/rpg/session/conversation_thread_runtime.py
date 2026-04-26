from __future__ import annotations

from typing import Any, Dict

from app.rpg.world.conversation_threads import maybe_advance_conversation_thread


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def advance_conversation_threads_for_turn(
    *,
    player_input: str,
    simulation_state: Dict[str, Any],
    resolved_result: Dict[str, Any],
    tick: int = 0,
) -> Dict[str, Any]:
    """Advance deterministic NPC conversation threads when eligible.

    Conversation threads are a living-world presentation/state layer. They do
    not alter authoritative player resources, quests, stock, services, or
    location.
    """
    resolved_result = _safe_dict(resolved_result)

    service_result = _safe_dict(resolved_result.get("service_result"))
    travel_result = _safe_dict(resolved_result.get("travel_result"))

    # Keep v1 conservative: do not trigger during service purchases or travel.
    # Passive service inquiries (kind == "service_inquiry") do not block
    # ambient conversation since no transaction is occurring.
    service_kind = _safe_str(service_result.get("kind"))
    if service_result.get("matched") and service_kind == "service_purchase":
        return {
            "triggered": False,
            "reason": "service_turn",
        }
    if travel_result.get("matched"):
        return {
            "triggered": False,
            "reason": "travel_turn",
        }

    return maybe_advance_conversation_thread(
        simulation_state,
        player_input=player_input,
        tick=tick,
    )
