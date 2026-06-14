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
_INTERPRETIVE_DIALOGUE_ACTION_TYPES = {
    "ask",
    "conversation",
    "dialogue",
    "observe",
    "social_activity",
    "talk",
    "social_affection",
    "social_performance",
}
_SAFE_DIRECT_RISK_DOMAINS = {
    "",
    "none",
}
_RUNTIME_RISK_DOMAINS = {
    "combat",
    "commerce",
    "inventory",
    "item",
    "persuasion_outcome",
    "quest",
    "relationship_change",
    "reward",
    "service",
    "threat",
    "travel",
    "unknown",
}
_SAFE_UTTERANCE_MODES = {
    "",
    "casual_conversation",
    "clarification",
    "emotional_expression",
    "greeting",
    "identity_inquiry",
    "local_knowledge",
    "lore_question",
    "opinion_question",
    "wellbeing_inquiry",
}
_HARD_STATE_DOMAINS = {
    "combat",
    "commerce",
    "currency",
    "gold",
    "inventory",
    "item",
    "location",
    "persuasion_outcome",
    "quest",
    "relationship_change",
    "reputation",
    "reward",
    "service",
    "travel",
    "world_state",
}
_MUTATION_STRUCTURAL_KEYS = {
    "currency_delta",
    "gold_delta",
    "money_delta",
    "inventory_delta",
    "item_delta",
    "quest_delta",
    "quest_state_delta",
    "relationship_delta",
    "reputation_delta",
    "location_delta",
    "travel_delta",
    "combat_delta",
    "damage_delta",
    "xp_delta",
    "level_delta",
    "reward_delta",
    "state_delta",
    "state_mutation",
    "state_mutation_claim",
    "state_mutation_claims",
    "applied_mutation",
    "applied_mutations",
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
    if line:
        return line
    return narration


def _is_hybrid_flavor_action(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    return _s(advisory.get("semantic_route")).strip().lower() == "flavor_action"


def _is_unsupported_consequential_action(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    route = _s(advisory.get("semantic_route")).strip().lower()
    if route == "unsupported_consequential_action":
        return True
    if _b(advisory.get("unsupported_consequential_action"), False):
        return True
    if route == "mixed":
        for component in _l(advisory.get("route_components")):
            component = _d(component)
            if _s(component.get("semantic_route")).strip().lower() == "unsupported_consequential_action":
                return True
            if component.get("supported") is False:
                return True
    return False


def _looks_stateful(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    if _is_hybrid_flavor_action(advisory):
        return False
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
        or action_type in {"social_activity", "social_affection", "social_performance", "persuade", "deceive", "intimidate"}
        or semantic_family == "social"
    )


def _is_interpretive_dialogue_candidate(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    if _is_hybrid_flavor_action(advisory):
        return True
    if not _is_direct_npc_dialogue(advisory):
        return False
    if _looks_stateful(advisory):
        return False
    action_type = _s(advisory.get("action_type")).strip().lower()
    semantic_family = _s(advisory.get("semantic_family")).strip().lower()
    if action_type in _INTERPRETIVE_DIALOGUE_ACTION_TYPES:
        return True
    return semantic_family == "social" and action_type in {"", "observe"}


def _direct_response_gate_allows(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    if _is_hybrid_flavor_action(advisory) and not _b(advisory.get("state_mutation_requested"), False):
        return True
    gate = _d(advisory.get("direct_response_gate"))
    if gate:
        return _b(gate.get("safe_to_display_now"), False)
    return not (
        _b(advisory.get("stateful"), True)
        or _b(advisory.get("needs_runtime_resolution"), True)
    )


def _semantic_risk_rejection(advisory: Dict[str, Any]) -> str:
    advisory = _d(advisory)
    if _is_hybrid_flavor_action(advisory):
        return ""
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


def _normalized_domains(values: Any) -> List[str]:
    domains: List[str] = []
    raw_values = values if isinstance(values, list) else [values]
    for value in raw_values:
        domain = _s(value).strip().lower().replace(" ", "_")
        if domain and domain != "none" and domain not in domains:
            domains.append(domain)
    return domains


def _classification_review(advisory: Dict[str, Any]) -> Dict[str, Any]:
    advisory = _d(advisory)
    review = _d(advisory.get("classification_review") or advisory.get("semantic_self_audit"))
    gate = _d(advisory.get("direct_response_gate"))
    return {
        **review,
        "hidden_state_change_risk": review.get(
            "hidden_state_change_risk",
            advisory.get("hidden_state_change_risk", gate.get("hidden_state_change_risk")),
        ),
        "hard_state_domains": review.get(
            "hard_state_domains",
            advisory.get("hard_state_domains", gate.get("hard_state_domains")),
        ),
        "mutation_claims": review.get(
            "mutation_claims",
            advisory.get("mutation_claims", gate.get("mutation_claims")),
        ),
    }


def _walk_structural_mutation_claims(value: Any, prefix: str = "") -> List[str]:
    claims: List[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_norm = _s(key).strip().lower()
            path = f"{prefix}.{key_norm}" if prefix else key_norm
            if key_norm in _MUTATION_STRUCTURAL_KEYS:
                if nested not in (None, "", [], {}, 0, False):
                    claims.append(path)
            claims.extend(_walk_structural_mutation_claims(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value[:12]):
            claims.extend(_walk_structural_mutation_claims(nested, f"{prefix}[{index}]"))
    return claims


def _state_invariant_violation(advisory: Dict[str, Any], visible_response: Dict[str, Any]) -> str:
    """Reject unsafe direct display using structured state claims, not raw text keywords."""

    advisory = _d(advisory)
    visible_response = _d(visible_response)
    if _b(advisory.get("authoritative_state_mutation_allowed"), False):
        return "direct_response_attempted_authoritative_mutation"
    if _b(visible_response.get("authoritative_state_mutation_allowed"), False):
        return "visible_response_attempted_authoritative_mutation"
    if _b(advisory.get("state_mutation_applied"), False):
        return "direct_response_claimed_state_mutation_applied"
    if _b(visible_response.get("state_mutation_applied"), False):
        return "visible_response_claimed_state_mutation_applied"

    review = _classification_review(advisory)
    hard_domains = [
        domain
        for domain in _normalized_domains(review.get("hard_state_domains"))
        if domain in _HARD_STATE_DOMAINS or domain == "unknown"
    ]
    if hard_domains:
        return f"semantic_self_audit_hard_state_domain:{hard_domains[0]}"

    hidden_risk = _s(review.get("hidden_state_change_risk")).strip().lower()
    if hidden_risk in {"true", "yes", "medium", "high", "hard", "possible"}:
        return "semantic_self_audit_hidden_state_change_risk"

    mutation_claims = _l(review.get("mutation_claims"))
    if mutation_claims:
        return "semantic_self_audit_mutation_claims"

    structural_claims = _walk_structural_mutation_claims(advisory) + _walk_structural_mutation_claims(visible_response)
    if structural_claims:
        return f"structured_state_mutation_claim:{structural_claims[0]}"

    return ""


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

    Hybrid rule:
    - deterministic service/commerce/runtime matches win first;
    - stateful or needs_runtime_resolution=true LLM output is never consumed;
    - semantic_route=flavor_action may be consumed without matching a flavor verb enum;
    - semantic_route=unsupported_consequential_action is gracefully failed without state mutation;
    - structured hard-state self-audit/mutation claims block direct display without keyword gates;
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
        if _is_unsupported_consequential_action(advisory):
            return {
                "consumable": True,
                "reason": "unsupported_consequential_graceful_failure",
                "source": source,
                "unsupported_consequential_action": True,
                "semantic_route": _s(advisory.get("semantic_route")),
                "advisory": deepcopy(advisory),
                "first_call_grounding_diagnostics": deepcopy(_d(advisory.get("first_call_grounding_diagnostics"))),
                "format_version": "first_call_visible_response_v2_state_invariant_guard",
            }
        if _looks_stateful(advisory):
            rejection_reasons.append(f"{source}:stateful_action_type")
            continue
        visible_response = _d(advisory.get("visible_response"))
        text = _visible_response_text(visible_response)
        if not text:
            rejection_reasons.append(f"{source}:missing_visible_response_text")
            continue
        if not _direct_response_gate_allows(advisory):
            rejection_reasons.append(f"{source}:direct_response_gate_blocked")
            continue
        semantic_rejection = _semantic_risk_rejection(advisory)
        if semantic_rejection:
            rejection_reasons.append(f"{source}:{semantic_rejection}")
            continue
        state_invariant_rejection = _state_invariant_violation(advisory, visible_response)
        if state_invariant_rejection:
            rejection_reasons.append(f"{source}:{state_invariant_rejection}")
            continue
        if (
            (_b(advisory.get("stateful"), True) or _b(advisory.get("needs_runtime_resolution"), True))
            and not _is_interpretive_dialogue_candidate(advisory)
        ):
            rejection_reasons.append(f"{source}:stateful")
            continue
        rejection = _visible_response_rejection(advisory, visible_response)
        if rejection:
            rejection_reasons.append(f"{source}:{rejection}")
            continue
        classification_review = _classification_review(advisory)
        return {
            "consumable": True,
            "reason": "non_stateful_flavor_action" if _is_hybrid_flavor_action(advisory) else "non_stateful_interpretive_dialogue",
            "source": source,
            "visible_response": deepcopy(visible_response),
            "narration": _s(visible_response.get("narration")).strip() or text,
            "npc": deepcopy(_d(visible_response.get("npc"))),
            "text": text,
            "direct_response_gate": deepcopy(_d(advisory.get("direct_response_gate"))),
            "semantic_intent_gate": {
                "semantic_route": _s(advisory.get("semantic_route")).strip(),
                "utterance_mode": _s(advisory.get("utterance_mode")).strip(),
                "literal_action_requested": _b(advisory.get("literal_action_requested"), False),
                "state_mutation_requested": _b(advisory.get("state_mutation_requested"), False),
                "risk_domain": _s(advisory.get("risk_domain")).strip(),
                "intent_summary": _s(advisory.get("intent_summary")).strip(),
                "evidence_spans": deepcopy(_l(advisory.get("evidence_spans"))),
                "classification_review": deepcopy(classification_review),
                "hard_state_domains": deepcopy(_normalized_domains(classification_review.get("hard_state_domains"))),
                "state_invariant_guard": {
                    "checked": True,
                    "source": "structured_semantic_fields",
                    "raw_text_keyword_gate": False,
                },
            },
            "first_call_grounding_diagnostics": deepcopy(
                _d(advisory.get("first_call_grounding_diagnostics"))
            ),
            "advisory": deepcopy(advisory),
            "format_version": "first_call_visible_response_v2_state_invariant_guard",
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
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "turn_grounding_packet": deepcopy(packet),
        "source": "first_call_dialogue_v1",
    }


def _unsupported_failure_narration(selected: Dict[str, Any], player_input: str) -> str:
    advisory = _d(selected.get("advisory"))
    summary = _s(advisory.get("intent_summary")).strip()
    unsupported_reason = _s(advisory.get("unsupported_reason")).strip()
    if summary:
        base = summary
    else:
        base = f"The attempted action could not be resolved: {_s(player_input).strip()}"
    if unsupported_reason:
        return f"{base} The attempt fails without changing the world state because this consequential action is not supported yet."
    return f"{base} The attempt fails cleanly without changing the world state."


def _build_unsupported_consequential_result(
    *,
    session: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_input: str,
    selected: Dict[str, Any],
) -> Dict[str, Any]:
    advisory = _d(selected.get("advisory"))
    diagnostics = _d(selected.get("first_call_grounding_diagnostics"))
    grounding_validation = _first_call_grounding_validation(selected)
    narration = _unsupported_failure_narration(selected, player_input)
    resolved_result = {
        "ok": True,
        "action_type": "unsupported_consequential_action",
        "semantic_action_type": "unsupported_consequential_action",
        "semantic_family": _s(advisory.get("semantic_family") or "unknown"),
        "semantic_route": _s(advisory.get("semantic_route") or "unsupported_consequential_action"),
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_interaction_reason": "unsupported_consequential_graceful_failure",
        "outcome": "unsupported_consequential_action_failed",
        "success": False,
        "state_mutation_applied": False,
        "authoritative_state_mutation_allowed": False,
        "graceful_failure_required": True,
        "summary": narration,
        "unsupported_reason": _s(advisory.get("unsupported_reason")),
        "route_components": deepcopy(_l(advisory.get("route_components"))),
        "first_call_visible_response": deepcopy(selected),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "grounding_validation": deepcopy(grounding_validation),
        "source": "first_call_dialogue_unsupported_consequential_v1",
    }
    return {
        "consumed": True,
        "ok": True,
        "result": deepcopy(resolved_result),
        "resolved_result": deepcopy(resolved_result),
        "narration": narration,
        "final_narration": narration,
        "summary": narration,
        "llm_called": True,
        "llm_purpose": "first_call_unsupported_consequential_graceful_failure",
        "stateful": False,
        "needs_runtime_resolution": False,
        "state_mutation_applied": False,
        "authoritative_state_mutation_allowed": False,
        "simulation_state": deepcopy(_d(simulation_state)),
        "runtime_state": deepcopy(_d(runtime_state)),
        "session": deepcopy(_d(session)),
        "player_input": _s(player_input),
        "first_call_visible_response": deepcopy(selected),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "grounding_validation": deepcopy(grounding_validation),
        "narration_context": {
            "player_input": _s(player_input),
            "action_type": "unsupported_consequential_action",
            "resolved_result": deepcopy(resolved_result),
            "simulation_state": deepcopy(_d(simulation_state)),
            "runtime_state": deepcopy(_d(runtime_state)),
            "first_call_grounding_diagnostics": deepcopy(diagnostics),
            "grounding_validation": deepcopy(grounding_validation),
        },
        "source": "first_call_dialogue_unsupported_consequential_v1",
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
    if selected.get("reason") == "unsupported_consequential_graceful_failure":
        return _build_unsupported_consequential_result(
            session=session,
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            player_input=player_input,
            selected=selected,
        )

    visible_response = _d(selected.get("visible_response"))
    npc = _d(selected.get("npc"))
    narration = _s(selected.get("narration") or selected.get("text")).strip()
    grounding_validation = _first_call_grounding_validation(selected)
    interaction_reason = "first_call_flavor_action" if selected.get("reason") == "non_stateful_flavor_action" else "first_call_non_stateful_dialogue"
    resolved_result = {
        "ok": True,
        "action_type": "npc_interpretive_dialogue",
        "semantic_action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "semantic_route": "flavor_action" if selected.get("reason") == "non_stateful_flavor_action" else "dialogue",
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_interaction_reason": interaction_reason,
        "outcome": "non_stateful_visible_response",
        "summary": narration,
        "npc": deepcopy(npc),
        "visible_response": deepcopy(visible_response),
        "conversation_result": {
            "triggered": True,
            "reason": interaction_reason,
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
        "llm_purpose": "first_call_flavor_action" if selected.get("reason") == "non_stateful_flavor_action" else "first_call_interpretive_dialogue",
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
