from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, List


_STATEFUL_ACTION_TYPES = {
    "attack_melee", "attack_ranged", "attack_unarmed", "block", "dodge", "parry",
    "trade", "use_item", "pickup_item", "drop_item", "equip_item", "unequip_item",
    "cast_spell", "sneak", "hack", "travel", "move", "flee", "threat", "intimidate",
    "persuade", "deceive", "quest_accept", "quest_complete", "buy", "sell",
}

_PLAYER_SPEAKER_ALIASES = {"player", "you", "the player", "adventurer", "traveler"}


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _s(value: Any) -> str:
    return str(value) if value is not None else ""


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _s(value).casefold()).strip()


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


def _grounding_packet(advisory: Dict[str, Any]) -> Dict[str, Any]:
    return _d(_d(advisory.get("first_call_grounding_diagnostics")).get("turn_grounding_packet"))


def _addressed_profiles(advisory: Dict[str, Any]) -> List[Dict[str, Any]]:
    packet = _grounding_packet(advisory)
    npc_context = _d(packet.get("npc_context"))
    return [_d(row) for row in _l(npc_context.get("addressed_npcs"))]


def _addressed_ids(advisory: Dict[str, Any]) -> List[str]:
    packet = _grounding_packet(advisory)
    priority = _d(packet.get("priority_context"))
    return [_s(x) for x in _l(priority.get("addressed_npc_ids")) if _s(x)]


def _expected_npc_names(advisory: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for profile in _addressed_profiles(advisory):
        for key in ("name", "id", "npc_id"):
            value = _s(profile.get(key)).strip()
            if value:
                names.append(value)
                if value.startswith("npc:"):
                    names.append(value.split(":", 1)[1])
    for value in (_s(advisory.get("target_name")), _s(advisory.get("target_id"))):
        value = value.strip()
        if value:
            names.append(value)
            if value.startswith("npc:"):
                names.append(value.split(":", 1)[1])
    return [name for name in names if name]


def _is_direct_npc_dialogue(advisory: Dict[str, Any]) -> bool:
    action_type = _s(advisory.get("action_type")).lower()
    semantic_family = _s(advisory.get("semantic_family")).lower()
    interaction_mode = _s(advisory.get("interaction_mode")).lower()
    return bool(
        _addressed_ids(advisory)
        or _addressed_profiles(advisory)
        or _s(advisory.get("target_id"))
        or _s(advisory.get("target_name"))
        or interaction_mode == "direct"
        or action_type in {"social_activity", "persuade", "deceive", "intimidate"}
        or semantic_family == "social"
    )


def _speaker_matches_expected_npc(speaker: str, advisory: Dict[str, Any]) -> bool:
    speaker_norm = _norm(speaker)
    if not speaker_norm or speaker_norm in _PLAYER_SPEAKER_ALIASES:
        return False
    names = _expected_npc_names(advisory)
    if not names:
        return True
    return any(_norm(name) == speaker_norm for name in names if _norm(name))


def _line_restates_player_input(line: str, player_input: str) -> bool:
    line_norm = _norm(line)
    input_norm = _norm(player_input)
    if not line_norm or not input_norm:
        return False
    if line_norm == input_norm:
        return True
    if input_norm in line_norm and len(line_norm) <= len(input_norm) + 30:
        return True
    return False


def _visible_response_rejection(advisory: Dict[str, Any], visible_response: Dict[str, Any]) -> str:
    visible_response = _d(visible_response)
    npc = _d(visible_response.get("npc"))
    speaker = _s(npc.get("speaker")).strip()
    line = _s(npc.get("line")).strip()
    narration = _s(visible_response.get("narration")).strip()
    player_input = _s(_grounding_packet(advisory).get("player_input"))

    if _is_direct_npc_dialogue(advisory):
        if not speaker:
            return "missing_npc_speaker_for_direct_npc_dialogue"
        if not _speaker_matches_expected_npc(speaker, advisory):
            return "speaker_does_not_match_addressed_npc"
        if not line:
            return "missing_npc_line_for_direct_npc_dialogue"
        if _line_restates_player_input(line, player_input):
            return "npc_line_restates_player_input"
        if narration and _line_restates_player_input(narration, player_input) and not line:
            return "narration_restates_player_input"
    else:
        text = _visible_response_text(visible_response)
        if not text:
            return "missing_visible_response_text"
        if _line_restates_player_input(text, player_input):
            return "visible_response_restates_player_input"

    return ""


def choose_first_call_visible_response(
    *,
    action_advisory: Dict[str, Any] | None = None,
    semantic_advisory: Dict[str, Any] | None = None,
    service_matched: bool = False,
) -> Dict[str, Any]:
    """Return the safe first-call visible response, if runtime may consume it.

    CE.1.3 rule:
    - deterministic service/commerce/runtime matches win first;
    - stateful or needs_runtime_resolution=true LLM output is never consumed;
    - direct NPC dialogue requires matching npc.speaker and non-empty npc.line;
    - player/restatement-only narration is not consumed as an NPC answer.
    """

    if service_matched:
        return {
            "consumable": False,
            "reason": "service_or_commerce_runtime_wins",
            "source": "first_call_dialogue_v1",
        }

    rejection_reasons: List[str] = []
    candidates = [
        ("semantic_advisory", _d(semantic_advisory)),
        ("action_advisory", _d(action_advisory)),
    ]
    for source, advisory in candidates:
        if not advisory:
            continue
        if _b(advisory.get("stateful"), True):
            rejection_reasons.append(f"{source}:stateful")
            continue
        if _b(advisory.get("needs_runtime_resolution"), True):
            rejection_reasons.append(f"{source}:needs_runtime_resolution")
            continue
        if _looks_stateful(advisory):
            rejection_reasons.append(f"{source}:stateful_action_type")
            continue
        visible_response = _d(advisory.get("visible_response"))
        text = _visible_response_text(visible_response)
        if not text:
            rejection_reasons.append(f"{source}:missing_visible_response_text")
            continue
        rejection = _visible_response_rejection(advisory, visible_response)
        if rejection:
            rejection_reasons.append(f"{source}:{rejection}")
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
        "rejection_reasons": rejection_reasons,
        "source": "first_call_dialogue_v1",
    }


def _first_call_grounding_validation(selected: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = _d(selected.get("first_call_grounding_diagnostics"))
    packet = _d(diagnostics.get("turn_grounding_packet"))
    addressed = _l(_d(packet.get("priority_context")).get("addressed_npc_ids"))
    return {
        "selected_candidate": "first_call_visible_response",
        "fallback_used": False,
        "fallback_source": "",
        "violations": [],
        "primary_violations": [],
        "first_call_grounding_packet_version": _s(packet.get("format_version")),
        "first_call_addressed_npc_ids": addressed,
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
    grounding_validation = _first_call_grounding_validation(selected)
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
        "grounding_validation": deepcopy(grounding_validation),
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
        "grounding_validation": deepcopy(grounding_validation),
        "narration_context": {
            "player_input": _s(player_input),
            "action_type": "npc_interpretive_dialogue",
            "resolved_result": deepcopy(resolved_result),
            "simulation_state": deepcopy(_d(simulation_state)),
            "runtime_state": deepcopy(_d(runtime_state)),
            "first_call_grounding_diagnostics": deepcopy(
                _d(selected.get("first_call_grounding_diagnostics"))
            ),
            "grounding_validation": deepcopy(grounding_validation),
        },
        "source": "first_call_dialogue_v1",
    }
