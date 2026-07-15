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
_NON_NPC_SPEAKER_ALIASES = {
    "scene", "narrator", "narration", "gm", "game master", "omnix", "system",
}
_INTERPRETIVE_DIALOGUE_ACTION_TYPES = {
    "ask", "conversation", "dialogue", "observe", "social_activity", "talk",
}
_SAFE_DIRECT_RISK_DOMAINS = {"", "none"}
_RUNTIME_RISK_DOMAINS = {
    "combat", "commerce", "inventory", "item", "persuasion_outcome", "quest",
    "relationship_change", "reward", "service", "threat", "travel", "unknown",
}
_SAFE_UTTERANCE_MODES = {
    "", "casual_conversation", "clarification", "emotional_expression", "greeting",
    "identity_inquiry", "local_knowledge", "lore_question", "opinion_question",
    "wellbeing_inquiry",
}


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
    return line or narration


def _looks_stateful(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    action_type = _s(advisory.get("action_type")).strip().lower()
    semantic_family = _s(advisory.get("semantic_family")).strip().lower()
    return action_type in _STATEFUL_ACTION_TYPES or semantic_family in {
        "combat", "trade", "item", "travel", "threat",
    }


def _grounding_packet(advisory: Dict[str, Any]) -> Dict[str, Any]:
    return _d(_d(advisory.get("first_call_grounding_diagnostics")).get("turn_grounding_packet"))


def _addressed_profiles(advisory: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_d(row) for row in _l(_d(_grounding_packet(advisory).get("npc_context")).get("addressed_npcs"))]


def _addressed_ids(advisory: Dict[str, Any]) -> List[str]:
    priority = _d(_grounding_packet(advisory).get("priority_context"))
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


def _is_interpretive_dialogue_candidate(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    if not _is_direct_npc_dialogue(advisory) or _looks_stateful(advisory):
        return False
    action_type = _s(advisory.get("action_type")).strip().lower()
    semantic_family = _s(advisory.get("semantic_family")).strip().lower()
    return action_type in _INTERPRETIVE_DIALOGUE_ACTION_TYPES or (
        semantic_family == "social" and action_type in {"", "observe"}
    )


def _direct_response_gate_allows(advisory: Dict[str, Any]) -> bool:
    gate = _d(_d(advisory).get("direct_response_gate"))
    if gate:
        return _b(gate.get("safe_to_display_now"), False)
    return not (
        _b(_d(advisory).get("stateful"), True)
        or _b(_d(advisory).get("needs_runtime_resolution"), True)
    )


def _semantic_risk_rejection(advisory: Dict[str, Any]) -> str:
    advisory = _d(advisory)
    risk_domain = _s(advisory.get("risk_domain")).strip().lower()
    utterance_mode = _s(advisory.get("utterance_mode")).strip().lower()
    if _b(advisory.get("state_mutation_requested"), False):
        return "semantic_state_mutation_requested"
    if risk_domain in _RUNTIME_RISK_DOMAINS:
        return f"semantic_runtime_risk:{risk_domain}"
    if risk_domain not in _SAFE_DIRECT_RISK_DOMAINS:
        return f"semantic_unknown_risk:{risk_domain}"
    if utterance_mode and utterance_mode not in _SAFE_UTTERANCE_MODES:
        return f"semantic_unsafe_utterance_mode:{utterance_mode}"
    if _b(advisory.get("literal_action_requested"), False) and utterance_mode == "action_request":
        return "semantic_literal_action_request"
    return ""


def _speaker_matches_expected_npc(speaker: str, advisory: Dict[str, Any]) -> bool:
    speaker_norm = _norm(speaker)
    if not speaker_norm or speaker_norm in _PLAYER_SPEAKER_ALIASES or speaker_norm in _NON_NPC_SPEAKER_ALIASES:
        return False
    names = _expected_npc_names(advisory)
    return not names or any(_norm(name) == speaker_norm for name in names if _norm(name))


def _line_restates_player_input(line: str, player_input: str) -> bool:
    line_norm = _norm(line)
    input_norm = _norm(player_input)
    if not line_norm or not input_norm:
        return False
    return line_norm == input_norm or (
        input_norm in line_norm and len(line_norm) <= len(input_norm) + 30
    )


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
    return ""


def _safe_direct_intent(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    return bool(
        advisory
        and _is_direct_npc_dialogue(advisory)
        and not _looks_stateful(advisory)
        and not _semantic_risk_rejection(advisory)
        and (
            _is_interpretive_dialogue_candidate(advisory)
            or not _b(advisory.get("stateful"), False)
        )
    )


def choose_first_call_visible_response(
    *,
    action_advisory: Dict[str, Any] | None = None,
    semantic_advisory: Dict[str, Any] | None = None,
    service_matched: bool = False,
) -> Dict[str, Any]:
    """Classify whether a first-call result is safe for canonical dialogue routing."""

    if service_matched:
        return {"consumable": False, "reason": "service_or_commerce_runtime_wins", "source": "first_call_dialogue_v2"}
    rejection_reasons: List[str] = []
    for source, advisory in (("semantic_advisory", _d(semantic_advisory)), ("action_advisory", _d(action_advisory))):
        if not advisory:
            continue
        if not _safe_direct_intent(advisory):
            rejection_reasons.append(f"{source}:not_safe_direct_dialogue")
            continue
        visible_response = _d(advisory.get("visible_response"))
        rejection = _visible_response_rejection(advisory, visible_response) if visible_response else ""
        if rejection:
            rejection_reasons.append(f"{source}:{rejection}")
        return {
            "consumable": True,
            "reason": "canonical_non_stateful_dialogue_intent",
            "source": source,
            "legacy_visible_response_ignored": bool(visible_response),
            "legacy_visible_response_rejection": rejection,
            "direct_response_gate": deepcopy(_d(advisory.get("direct_response_gate"))),
            "semantic_intent_gate": {
                "utterance_mode": _s(advisory.get("utterance_mode")).strip(),
                "literal_action_requested": _b(advisory.get("literal_action_requested"), False),
                "state_mutation_requested": _b(advisory.get("state_mutation_requested"), False),
                "risk_domain": _s(advisory.get("risk_domain")).strip(),
                "intent_summary": _s(advisory.get("intent_summary")).strip(),
                "evidence_spans": deepcopy(_l(advisory.get("evidence_spans"))),
            },
            "first_call_grounding_diagnostics": deepcopy(_d(advisory.get("first_call_grounding_diagnostics"))),
            "advisory": deepcopy(advisory),
            "format_version": "canonical_dialogue_intent_v1",
        }
    return {
        "consumable": False,
        "reason": "no_safe_non_stateful_dialogue_intent",
        "rejection_reasons": rejection_reasons,
        "source": "first_call_dialogue_v2",
    }


def _session_id(session: Dict[str, Any]) -> str:
    manifest = _d(session.get("manifest"))
    return _s(manifest.get("session_id") or manifest.get("id") or session.get("session_id") or session.get("id") or "runtime")


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
    """Route safe dialogue intent directly into the canonical narrative writer."""

    selected = choose_first_call_visible_response(
        action_advisory=action_advisory,
        semantic_advisory=semantic_advisory,
        service_matched=service_matched,
    )
    if not selected.get("consumable"):
        for source, advisory in (("semantic_advisory", _d(semantic_advisory)), ("action_advisory", _d(action_advisory))):
            if _safe_direct_intent(advisory):
                selected = {
                    "consumable": True,
                    "reason": "canonical_direct_dialogue_forced",
                    "source": source,
                    "legacy_visible_response_ignored": bool(_d(advisory.get("visible_response"))),
                    "first_call_grounding_diagnostics": deepcopy(_d(advisory.get("first_call_grounding_diagnostics"))),
                    "advisory": deepcopy(advisory),
                    "format_version": "canonical_dialogue_intent_v1",
                }
                break
    if not selected.get("consumable"):
        return {"consumed": False, "selection": selected}

    from .canonical_direct_dialogue import build_canonical_direct_dialogue_intent
    from .narrative_engine_bridge import canonicalize_direct_dialogue_result

    intent = build_canonical_direct_dialogue_intent(
        session=session,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        player_input=player_input,
        action_advisory=_d(action_advisory),
        semantic_advisory=_d(semantic_advisory),
    )
    intent["selection"] = deepcopy(selected)
    intent["first_call_visible_response_selection"] = deepcopy(selected)
    intent["turn_id"] = _s(intent.get("turn_id")) or _s(runtime_state.get("turn_id"))
    return canonicalize_direct_dialogue_result(
        intent,
        session_id=_session_id(session),
        player_input=_s(player_input),
    )
