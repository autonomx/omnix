from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable

# Generated split module for app.rpg.session.runtime.
# Phase 8.39: prevent unverified social accomplishment claims from falling
# through to deterministic travel/exploration narration when the first-call
# semantic router marks the player input as a public/social declaration.
from .runtime_part38 import *  # noqa: F401,F403
from .runtime_part38 import _apply_turn_authoritative as _PHASE8_PART39_BASE_APPLY_TURN_AUTHORITATIVE

_PHASE8_PART39_SOURCE = "phase8_social_claim_travel_mismatch_guard_v1"
_PHASE8_PART39_SOCIAL_ACTIONS = {
    "social_activity",
    "social_affection",
    "social_competition",
    "social_performance",
    "persuade",
    "deceive",
    "intimidate",
}
_PHASE8_PART39_TRAVEL_ACTIONS = {"exploration", "travel"}
_PHASE8_PART39_ACHIEVEMENT_VERBS = {
    "beat",
    "defeat",
    "defeated",
    "kill",
    "killed",
    "slay",
    "slayed",
    "slew",
    "vanquish",
    "vanquished",
}
_PHASE8_PART39_CLAIM_MARKERS = {
    "i was able to",
    "i have",
    "i had",
    "i killed",
    "i slew",
    "i defeated",
    "i beat",
    "i vanquished",
    "we killed",
    "we slew",
    "we defeated",
    "we beat",
    "we vanquished",
    "i claim",
    "i report",
    "i announce",
    "i tell",
    "i say",
}


def _phase8_part39_clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return "" if text.casefold() in {"", "[]", "{}", "null", "none", "false", "true"} else text


def _phase8_part39_norm(value: Any) -> str:
    text = _phase8_part39_clean_text(value).casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def _phase8_part39_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _phase8_part39_iter_sources(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    payload = _safe_dict(payload)
    seen: set[int] = set()

    def emit(source: Any) -> Iterable[Dict[str, Any]]:
        if not isinstance(source, dict):
            return
        source_id = id(source)
        if source_id in seen:
            return
        seen.add(source_id)
        yield source

    for source in _phase8_part38_iter_candidate_sources(payload):
        yield from emit(source)
    try:
        for source in _phase8_part31_iter_payload_dicts(payload):
            yield from emit(source)
    except Exception:
        pass


def _phase8_part39_source_field(source: Dict[str, Any], key: str) -> str:
    source = _safe_dict(source)
    semantic = _safe_dict(source.get("semantic_advisory"))
    action_intent = _safe_dict(source.get("action_intent"))
    return _phase8_part39_clean_text(
        source.get(key)
        or semantic.get(key)
        or action_intent.get(key)
    )


def _phase8_part39_source_text(source: Dict[str, Any], player_input: str) -> str:
    source = _safe_dict(source)
    semantic = _safe_dict(source.get("semantic_advisory"))
    visible = _safe_dict(source.get("visible_response") or source.get("final_narration_candidate"))
    npc = _safe_dict(visible.get("npc"))
    pieces = [
        player_input,
        source.get("activity_label"),
        source.get("intent_summary"),
        source.get("reason"),
        semantic.get("activity_label"),
        semantic.get("intent_summary"),
        visible.get("narration"),
        npc.get("line"),
    ]
    pieces.extend(_safe_list(source.get("evidence_spans")))
    pieces.extend(_safe_list(semantic.get("evidence_spans")))
    return _phase8_part39_norm(
        " ".join(_phase8_part39_clean_text(piece) for piece in pieces)
    )


def _phase8_part39_is_social_claim_source(source: Dict[str, Any], player_input: str) -> bool:
    source = _safe_dict(source)
    semantic = _safe_dict(source.get("semantic_advisory"))
    action_type = _phase8_part39_source_field(source, "action_type").casefold()
    semantic_family = _phase8_part39_source_field(source, "semantic_family").casefold()
    utterance_mode = _phase8_part39_source_field(source, "utterance_mode").casefold()
    activity_label = _phase8_part39_source_field(source, "activity_label").casefold()
    risk_domain = _phase8_part39_source_field(source, "risk_domain").casefold()
    literal_action = _phase8_part39_bool(
        semantic.get("literal_action_requested", source.get("literal_action_requested")),
        False,
    )

    is_social = (
        semantic_family == "social"
        or action_type in _PHASE8_PART39_SOCIAL_ACTIONS
        or risk_domain in {"social", "relationship_change", "social_reputation"}
    )
    if not is_social:
        return False

    text = _phase8_part39_source_text(source, player_input)
    has_claim_marker = any(marker in text for marker in _PHASE8_PART39_CLAIM_MARKERS)
    has_achievement = any(verb in text.split() for verb in _PHASE8_PART39_ACHIEVEMENT_VERBS)
    looks_declarative = (
        utterance_mode in {"declarative", "report", "reporting", "statement"}
        or "report" in activity_label
        or "claim" in activity_label
    )

    # A player statement such as "I killed a dragon" is a claim heard in the
    # scene. It is not proof that combat, rewards, quests, or world facts changed.
    return bool((has_claim_marker or looks_declarative) and has_achievement and not literal_action)


def _phase8_part39_find_social_claim(payload: Dict[str, Any], player_input: str) -> Dict[str, Any]:
    for source in _phase8_part39_iter_sources(payload):
        if _phase8_part39_is_social_claim_source(source, player_input):
            return source
    return {}


def _phase8_part39_has_travel_mismatch(payload: Dict[str, Any]) -> bool:
    payload = _safe_dict(payload)
    for source in _phase8_part39_iter_sources(payload):
        action_type = _phase8_part39_source_field(source, "action_type").casefold()
        travel_result = _safe_dict(source.get("travel_result"))
        action_text = _phase8_part39_norm(
            " ".join(
                _phase8_part39_clean_text(source.get(key))
                for key in (
                    "action",
                    "narration",
                    "final_narration",
                    "summary",
                    "outcome",
                    "visible_interaction_reason",
                )
            )
        )
        if action_type in _PHASE8_PART39_TRAVEL_ACTIONS and (
            travel_result
            or "travel" in action_text
            or "moving from" in action_text
            or "village square" in action_text
        ):
            return True
        if travel_result and travel_result.get("matched") is not False:
            return True
    return False


def _phase8_part39_claim_narration(player_input: str) -> str:
    utterance = _phase8_part39_clean_text(player_input) or "I report an accomplishment."
    return (
        f'You say, "{utterance}" The statement is treated as an unverified claim '
        "heard in the current scene, not as confirmation that the event happened. "
        "No travel, combat victory, reward, quest progress, or world-fact mutation is applied."
    )


def _phase8_part39_guard_fields(player_input: str, claim_source: Dict[str, Any]) -> Dict[str, Any]:
    narration = _phase8_part39_claim_narration(player_input)
    guard = {
        "format_version": "social_claim_runtime_guard_v1",
        "source": _PHASE8_PART39_SOURCE,
        "reason": "social_claim_must_not_fall_through_to_travel",
        "claim_veracity": "unverified",
        "verified_world_fact": False,
        "original_semantic_action_type": _phase8_part39_source_field(claim_source, "action_type"),
        "original_activity_label": _phase8_part39_source_field(claim_source, "activity_label"),
    }
    return {
        "narration": narration,
        "final_narration": narration,
        "raw_payload_narration": narration,
        "deterministic_fallback_narration": narration,
        "summary": narration,
        "action": "Social claim recorded as an unverified statement; no travel is performed.",
        "action_type": "social_activity",
        "semantic_action_type": "social_activity",
        "semantic_family": "social",
        "activity_label": "unverified_accomplishment_claim",
        "state_mutation_requested": False,
        "claim_veracity": "unverified",
        "verified_world_fact": False,
        "travel_result": {
            "matched": False,
            "status": "blocked",
            "reason": "social_claim_not_travel",
            "source": _PHASE8_PART39_SOURCE,
        },
        "social_claim_guard": guard,
        "narration_status": "completed",
        "used_llm": True,
        "llm_called": True,
        "llm_purpose": "semantic_social_claim_guard",
        "fallback_narration_source": _PHASE8_PART39_SOURCE,
        "skip_full_structured_narrator": True,
        "npc": {},
    }


def _phase8_part39_patch_target(target: Dict[str, Any], fields: Dict[str, Any]) -> Dict[str, Any]:
    target = dict(_safe_dict(target))
    for key, value in fields.items():
        target[key] = deepcopy(value)
    semantic_action = _safe_dict(target.get("semantic_action") or target.get("semantic_action_record"))
    if semantic_action:
        semantic_action = dict(semantic_action)
        semantic_action["state_mutation_requested"] = False
        semantic_action["claim_veracity"] = "unverified"
        semantic_action["verified_world_fact"] = False
        target["semantic_action"] = semantic_action
    return target


def _phase8_part39_patch_social_claim_mismatch(payload: Any, *, player_input: str) -> Any:
    if not isinstance(payload, dict):
        return payload
    claim_source = _phase8_part39_find_social_claim(payload, player_input)
    if not claim_source:
        return payload
    if not _phase8_part39_has_travel_mismatch(payload):
        return payload

    fields = _phase8_part39_guard_fields(player_input, claim_source)
    patched = _phase8_part39_patch_target(payload, fields)
    for nested_key in ("result", "authoritative", "resolved_result", "payload"):
        nested = _safe_dict(patched.get(nested_key))
        if nested:
            patched[nested_key] = _phase8_part39_patch_target(nested, fields)

    narration_context = _safe_dict(patched.get("narration_context"))
    if narration_context:
        narration_context = dict(narration_context)
        resolved = _safe_dict(narration_context.get("resolved_result"))
        if resolved:
            narration_context["resolved_result"] = _phase8_part39_patch_target(resolved, fields)
        narration_context["social_claim_guard"] = deepcopy(fields["social_claim_guard"])
        patched["narration_context"] = narration_context

    if not _safe_dict(patched.get("result")):
        patched["result"] = {key: value for key, value in patched.items() if key != "authoritative"}
    if not _safe_dict(patched.get("authoritative")):
        patched["authoritative"] = dict(_safe_dict(patched.get("result")))
    return patched


def _apply_turn_authoritative(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
    _base_authoritative: Any = _PHASE8_PART39_BASE_APPLY_TURN_AUTHORITATIVE,
) -> Dict[str, Any]:
    payload = _base_authoritative(
        session_id,
        player_input,
        action,
        performance_override=performance_override,
    )
    return _phase8_part39_patch_social_claim_mismatch(payload, player_input=player_input)


__all__ = [name for name in globals() if not name.startswith("__")]
