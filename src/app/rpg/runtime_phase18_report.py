"""Phase 18 wrapper for runtime integration reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.rpg.narration_prompt_runtime import build_narration_prompt_runtime_metadata
from app.rpg.runtime_integration_report import build_turn_runtime_integration_report

PHASE18_RUNTIME_REPORT_SOURCE = "phase18_runtime_report_wrapper_v1"


def build_phase18_turn_report(
    turn_result: Mapping[str, object],
    *,
    turn_index: int,
    player_action: str,
    recent_narrations: Sequence[str] = (),
    valid_actions: Sequence[str] = (),
) -> dict[str, object]:
    """Build a Phase 17 report decorated with Phase 18 metadata."""

    base = build_turn_runtime_integration_report(
        turn_result,
        turn_index=turn_index,
        player_action=player_action,
        recent_narrations=recent_narrations,
        valid_actions=valid_actions,
    )
    state = _mapping(turn_result.get("simulation_state") or turn_result.get("state"))
    narration_payload = _mapping(turn_result.get("narration_payload"))
    narration = str(turn_result.get("narration") or narration_payload.get("text") or "")
    action_kind = _action_kind(turn_result, player_action)
    result = dict(base)
    result["phase18_runtime"] = build_narration_prompt_runtime_metadata(
        narration=narration,
        action_kind=action_kind,
        state_facts=_state_facts(turn_result, state),
        recent_texts=tuple(recent_narrations)[-5:],
    )
    result["phase18_source"] = PHASE18_RUNTIME_REPORT_SOURCE
    return result


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _state_facts(turn_result: Mapping[str, object], state: Mapping[str, object]) -> Mapping[str, object]:
    facts = _mapping(turn_result.get("state_facts"))
    if facts:
        return facts
    keys = ("world", "player", "party", "npcs", "quests", "map", "inventory", "combat", "memory")
    return {key: state[key] for key in keys if key in state}


def _action_kind(turn_result: Mapping[str, object], player_action: str) -> str:
    for key in ("action_kind", "action_category", "validated_presentation_category"):
        value = turn_result.get(key)
        if value:
            return str(value)
    return player_action.split(" ", 1)[0].lower() if player_action else "general"
