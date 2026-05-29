from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


_STATEFUL_ACTION_TYPES = {
    "attack_melee", "attack_ranged", "attack_unarmed", "block", "dodge", "parry",
    "trade", "use_item", "pickup_item", "drop_item", "equip_item", "unequip_item",
    "cast_spell", "sneak", "hack", "travel", "move", "flee", "threat", "intimidate",
    "persuade", "deceive", "quest_accept", "quest_complete", "buy", "sell",
}


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _s(value: Any) -> str:
    return str(value) if value is not None else ""


def _b(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _visible_response_text(visible_response: Dict[str, Any]) -> str:
    visible_response = _d(visible_response)
    npc = _d(visible_response.get("npc"))
    line = _s(npc.get("line")).strip()
    speaker = _s(npc.get("speaker")).strip()
    narration = _s(visible_response.get("narration")).strip()
    if speaker and line:
        return f"{speaker}: {line}"
    if line:
        return line
    return narration


def _looks_stateful(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    action_type = _s(advisory.get("action_type")).strip().lower()
    semantic_family = _s(advisory.get("semantic_family")).strip().lower()
    if action_type in _STATEFUL_ACTION_TYPES:
        return True
    if semantic_family in {"combat", "trade", "item", "travel", "threat"}:
        return True
    return False


def choose_first_call_visible_response(
    *,
    action_advisory: Dict[str, Any] | None = None,
    semantic_advisory: Dict[str, Any] | None = None,
    service_matched: bool = False,
) -> Dict[str, Any]:
    """Return the safe first-call visible response, if runtime may consume it.

    CE.1 rule:
    - deterministic service/commerce/runtime matches win first;
    - stateful or needs_runtime_resolution=true LLM output is never consumed;
    - only non-stateful interpretive dialogue may be shown directly;
    - semantic advisory wins over generic action advisory when both exist.
    """

    if service_matched:
        return {
            "consumable": False,
            "reason": "service_or_commerce_runtime_wins",
            "source": "first_call_dialogue_v1",
        }

    candidates = [
        ("semantic_advisory", _d(semantic_advisory)),
        ("action_advisory", _d(action_advisory)),
    ]
    for source, advisory in candidates:
        if not advisory:
            continue
        if _b(advisory.get("stateful"), True):
            continue
        if _b(advisory.get("needs_runtime_resolution"), True):
            continue
        if _looks_stateful(advisory):
            continue
        visible_response = _d(advisory.get("visible_response"))
        text = _visible_response_text(visible_response)
        if not text:
            continue
        return {
            "consumable": True,
            "reason": "non_stateful_interpretive_dialogue",
            "source": source,
            "visible_response": deepcopy(visible_response),
            "narration": _s(visible_response.get("narration")).strip() or text,
            "npc": deepcopy(_d(visible_response.get("npc"))),
            "text": text,
            "first_call_grounding_diagnostics": deepcopy(
                _d(advisory.get("first_call_grounding_diagnostics"))
            ),
            "advisory": deepcopy(advisory),
            "format_version": "first_call_visible_response_v1",
        }

    return {
        "consumable": False,
        "reason": "no_safe_non_stateful_visible_response",
        "source": "first_call_dialogue_v1",
    }


def build_non_stateful_dialogue_result(
    *,
    session: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_input: str,
    action_advisory: Dict[str, Any] | None = None,
    semantic_advisory: Dict[str, Any] | None = None,
    service_matched: bool = False,
) -> Dict[str, Any]:
    selected = choose_first_call_visible_response(
        action_advisory=action_advisory,
        semantic_advisory=semantic_advisory,
        service_matched=service_matched,
    )
    if not selected.get("consumable"):
        return {"consumed": False, "selection": selected}

    visible_response = _d(selected.get("visible_response"))
    npc = _d(selected.get("npc"))
    narration = _s(selected.get("narration") or selected.get("text")).strip()
    resolved_result = {
        "ok": True,
        "action_type": "npc_interpretive_dialogue",
        "semantic_action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_interaction_reason": "first_call_non_stateful_dialogue",
        "outcome": "non_stateful_visible_response",
        "summary": narration,
        "npc": deepcopy(npc),
        "visible_response": deepcopy(visible_response),
        "conversation_result": {
            "triggered": True,
            "reason": "first_call_non_stateful_interpretive_dialogue",
            "source": "first_call_dialogue_v1",
        },
        "first_call_visible_response": deepcopy(selected),
        "first_call_grounding_diagnostics": deepcopy(
            _d(selected.get("first_call_grounding_diagnostics"))
        ),
        "source": "first_call_dialogue_v1",
    }
    return {
        "consumed": True,
        "ok": True,
        "result": deepcopy(resolved_result),
        "resolved_result": deepcopy(resolved_result),
        "narration": narration,
        "final_narration": narration,
        "summary": narration,
        "npc": deepcopy(npc),
        "visible_response": deepcopy(visible_response),
        "llm_called": True,
        "llm_purpose": "first_call_interpretive_dialogue",
        "stateful": False,
        "needs_runtime_resolution": False,
        "simulation_state": deepcopy(_d(simulation_state)),
        "runtime_state": deepcopy(_d(runtime_state)),
        "session": deepcopy(_d(session)),
        "player_input": _s(player_input),
        "first_call_visible_response": deepcopy(selected),
        "first_call_grounding_diagnostics": deepcopy(
            _d(selected.get("first_call_grounding_diagnostics"))
        ),
        "narration_context": {
            "player_input": _s(player_input),
            "action_type": "npc_interpretive_dialogue",
            "resolved_result": deepcopy(resolved_result),
            "simulation_state": deepcopy(_d(simulation_state)),
            "runtime_state": deepcopy(_d(runtime_state)),
            "first_call_grounding_diagnostics": deepcopy(
                _d(selected.get("first_call_grounding_diagnostics"))
            ),
        },
        "source": "first_call_dialogue_v1",
    }
