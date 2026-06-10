"""Presentation-only response quality cleanup for interactive RPG turns.

This module is runtime-safe: it does not mutate simulation state, award items,
change quests, or invent new mechanics. It only rewrites weak/generic
player-facing presentation when the existing turn classification and payload
already support a safer, more specific presentation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping

RESPONSE_QUALITY_SOURCE = "interactive_cli_response_quality_v1"
_GENERIC_MOVEMENT_NARRATION = "the scene shifts with the movement"
_GENERIC_MOMENT_NARRATION = "the moment responds without producing a major new consequence"
_NON_PERSON_SPEAKERS = {
    "the tavern",
    "tavern",
    "tavern (location)",
    "the tavern (location)",
    "this place",
    "the road",
    "road",
    "the place",
    "place",
    "the room",
    "room",
}
_FALLBACK_ENVIRONMENT_SPEAKERS = {
    "environment/location (tavern)",
    "environment/npcs",
    "the environment/npcs",
    "general environment/npcs",
    "general area/local npcs",
    "the town/tavern atmosphere",
    "town/tavern atmosphere",
    "tavern atmosphere",
    "the tavern atmosphere",
    "the tavern (general)",
    "tavern (general)",
    "general atmosphere/locals",
    "atmosphere/locals",
    "general atmosphere/npcs",
}
_FALLBACK_ENVIRONMENT_SUFFIXES = (
    " in tavern",
    " in the tavern",
    " at tavern",
    " at the tavern",
)
_SELL_REQUEST_TERMS = ("sell", "sold", "trade", "barter", "value", "worth", "copper would you give", "give me for")
_SELL_ITEM_TERMS = ("ration", "rations", "provision", "provisions", "item", "gear", "inventory")
_SELL_RESPONSE_TERMS = ("sell", "trade", "ration", "copper", "cannot", "can't", "not set up", "buy")
_SELL_BAD_SURVIVAL_TERMS = ("you eat a ration", "hunger improves", "consume ration")


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _speaker_key(value: Any) -> str:
    return " ".join(_safe_str(value).strip().lower().split())


def _is_fallback_environment_speaker(value: Any) -> bool:
    key = _speaker_key(value)
    if key in _FALLBACK_ENVIRONMENT_SPEAKERS:
        return True
    for suffix in _FALLBACK_ENVIRONMENT_SUFFIXES:
        if key.endswith(suffix) and key[: -len(suffix)] in _FALLBACK_ENVIRONMENT_SPEAKERS:
            return True
    return False


def _is_sell_request(player_input: str, intent: Mapping[str, Any]) -> bool:
    text = _safe_str(player_input).strip().lower()
    terms = " ".join(_safe_str(term).lower() for term in _safe_list(_safe_dict(intent).get("requested_terms")))
    combined = " ".join([text, terms])
    if not _contains_any(combined, _SELL_REQUEST_TERMS):
        return False
    return _contains_any(combined, _SELL_ITEM_TERMS)


def _final_intent(turn_summary: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostics = _safe_dict(_safe_dict(turn_summary).get("interactive_cli_intent_diagnostics"))
    return _safe_dict(diagnostics.get("final_classification"))


def _requested_terms(intent: Mapping[str, Any], player_input: str) -> str:
    terms = [_safe_str(term).strip() for term in _safe_list(_safe_dict(intent).get("requested_terms"))]
    terms = [term for term in terms if term]
    if terms:
        return " ".join(terms)
    return _safe_str(player_input).strip()


def _target_label(intent: Mapping[str, Any], player_input: str) -> str:
    target = _safe_str(_safe_dict(intent).get("target_npc")).strip()
    terms = _requested_terms(intent, player_input)
    text = " ".join([target, terms, player_input]).lower()
    if "old mill" in text:
        return "the old mill"
    if "bandit" in text:
        return "the road bandit"
    if target and target.lower() not in _NON_PERSON_SPEAKERS:
        return target
    return "the road ahead"


def _direction_label(intent: Mapping[str, Any], player_input: str) -> str:
    text = _requested_terms(intent, player_input).lower()
    for direction in ("north", "south", "east", "west"):
        if direction in text:
            return direction
    return "along the road"


def _set_visible_response(
    out: Dict[str, Any],
    *,
    narration: str,
    speaker: str = "",
    line: str = "",
    source: str,
) -> Dict[str, Any]:
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    raw_result["narration"] = narration
    raw_result["visible_interaction_reason"] = "Interactive CLI presentation cleaned up from existing turn classification."
    raw_result["interactive_cli_response_quality"] = {
        "applied": True,
        "source": RESPONSE_QUALITY_SOURCE,
        "cleanup_source": source,
    }
    if speaker or line:
        raw_result["npc"] = {"speaker": speaker, "line": line}
    elif "npc" not in raw_result:
        raw_result["npc"] = {"speaker": "", "line": ""}

    out["raw_result"] = raw_result
    out["raw_narration"] = narration
    out["narration_preview"] = narration
    out["interactive_cli_response_quality"] = raw_result["interactive_cli_response_quality"]
    if speaker or line:
        out["raw_npc"] = {"speaker": speaker, "line": line}

    extracted = deepcopy(_safe_dict(out.get("extracted")))
    extracted["narration"] = narration
    extracted["action"] = raw_result["visible_interaction_reason"]
    if speaker or line:
        extracted["npc_speaker"] = speaker
        extracted["npc_line"] = line
    out["extracted"] = extracted

    warnings = list(_safe_list(out.get("scenario_warnings")))
    warning = f"interactive_cli_response_quality:{source}"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings

    diagnostics = deepcopy(_safe_dict(out.get("interactive_cli_intent_diagnostics")))
    if diagnostics:
        diagnostics["first_call_visible_response_suppressed_by_response_quality"] = True
        diagnostics["response_quality_source"] = RESPONSE_QUALITY_SOURCE
        out["interactive_cli_intent_diagnostics"] = diagnostics
    return out


def _cleanup_sell_request(out: Dict[str, Any], player_input: str, intent: Mapping[str, Any]) -> Dict[str, Any] | None:
    if not _is_sell_request(player_input, intent):
        return None
    raw = _safe_dict(out.get("raw_result") or out.get("result"))
    narration = _safe_str(out.get("raw_narration") or raw.get("narration")).lower()
    npc = _safe_dict(out.get("raw_npc") or raw.get("npc"))
    line = _safe_str(npc.get("line")).lower()
    output_text = " ".join([narration, line])
    if _contains_any(output_text, _SELL_BAD_SURVIVAL_TERMS):
        cleanup_source = "sell_request_not_survival_consumption"
    elif not _contains_any(output_text, _SELL_RESPONSE_TERMS):
        cleanup_source = "sell_request_specificity"
    else:
        target = _safe_str(_safe_dict(intent).get("target_npc")).strip().lower()
        if target and target != "bran":
            cleanup_source = "sell_request_target_stability"
        else:
            return None
    narration_text = "Bran treats the request as a trade question, not a survival action."
    line_text = "I can't buy that ration from you yet; selling provisions is not set up in the current trade state."
    return _set_visible_response(out, narration=narration_text, speaker="Bran", line=line_text, source=cleanup_source)


def _cleanup_dialogue_speaker(out: Dict[str, Any], player_input: str, intent: Mapping[str, Any]) -> Dict[str, Any] | None:
    raw = _safe_dict(out.get("raw_result") or out.get("result"))
    npc = _safe_dict(out.get("raw_npc") or raw.get("npc"))
    speaker = _safe_str(npc.get("speaker")).strip()
    text = _safe_str(player_input).lower()
    if speaker.lower() not in _NON_PERSON_SPEAKERS:
        return None
    if not _contains_any(text, ("what do you know", "this place", "tavern", "road", "town")):
        return None
    line = _safe_str(npc.get("line")).strip() or "This place sits by the road, with the tavern serving as shelter, meeting point, and source of local talk."
    return _set_visible_response(out, narration="Bran answers from what is already established about the scene.", speaker="Bran", line=line, source="dialogue_speaker_stability")


def _cleanup_no_backed_fallback_speaker(out: Dict[str, Any], player_input: str, intent: Mapping[str, Any]) -> Dict[str, Any] | None:
    raw = _safe_dict(out.get("raw_result") or out.get("result"))
    npc = _safe_dict(out.get("raw_npc") or raw.get("npc"))
    speaker = _safe_str(npc.get("speaker")).strip()
    line = _safe_str(npc.get("line")).strip()
    narration = _safe_str(out.get("raw_narration") or raw.get("narration")).strip()
    source = _safe_str(out.get("narration_source") or raw.get("narration_source")).lower()
    combined = " ".join([_safe_str(player_input), narration, line, source]).lower()
    if not _is_fallback_environment_speaker(speaker):
        return None
    if "no backed" not in combined and "do not have" not in line.lower():
        return None
    if not _contains_any(combined, ("quest", "job", "rumor", "news")):
        return None
    if _contains_any(combined, ("rumor", "news")):
        cleaned_narration = "Bran checks the confirmed rumors and news and finds nothing backed by the current state."
        cleanup_source = "rumor_fallback_speaker_stability"
    else:
        cleaned_narration = "Bran checks what he can actually offer and has no backed quest available in the current state."
        cleanup_source = "quest_fallback_speaker_stability"
    return _set_visible_response(out, narration=cleaned_narration, speaker="Bran", line=line, source=cleanup_source)


def _cleanup_party(out: Dict[str, Any], player_input: str, intent: Mapping[str, Any]) -> Dict[str, Any] | None:
    text = _safe_str(player_input).lower()
    terms = " ".join(_safe_str(term).lower() for term in _safe_list(_safe_dict(intent).get("requested_terms")))
    combined = " ".join([text, terms])
    if not _contains_any(combined, ("join my party", "join party", "companion", "stay close")):
        return None
    raw = _safe_dict(out.get("raw_result") or out.get("result"))
    npc = _safe_dict(out.get("raw_npc") or raw.get("npc"))
    line = _safe_str(npc.get("line"))
    narration = _safe_str(out.get("raw_narration") or raw.get("narration"))
    preview = _safe_str(out.get("narration_preview"))
    extracted = _safe_dict(out.get("extracted"))
    extracted_narration = _safe_str(extracted.get("narration"))
    if "help the player" in line.lower():
        return _set_visible_response(out, narration=narration or "Bran joins your party and falls in beside you.", speaker="Bran", line="Then I am with you. I'll help you survive the road ahead.", source="companion_acceptance_voice")
    if not line.strip() and _contains_any(combined, ("join my party", "join party")):
        return _set_visible_response(out, narration="Bran joins your party and falls in beside you.", speaker="Bran", line="Then I am with you. I'll help you survive the road ahead.", source="companion_acceptance_voice")
    if line.strip() and narration.strip() and (_GENERIC_MOMENT_NARRATION in preview.lower() or _GENERIC_MOMENT_NARRATION in extracted_narration.lower() or not _safe_str(extracted.get("npc_speaker")).strip()):
        return _set_visible_response(out, narration=narration, speaker=_safe_str(npc.get("speaker")).strip() or "Bran", line=line, source="companion_response_sync")
    return None


def _cleanup_travel(out: Dict[str, Any], player_input: str, intent: Mapping[str, Any]) -> Dict[str, Any] | None:
    raw = _safe_dict(out.get("raw_result") or out.get("result"))
    narration = _safe_str(out.get("raw_narration") or raw.get("narration")).lower()
    action_type = _safe_str(_safe_dict(intent).get("action_type")).lower()
    if action_type != "travel" and not _contains_any(player_input, ("travel", "continue along", "toward")):
        return None
    if _GENERIC_MOVEMENT_NARRATION not in narration:
        return None
    destination = _target_label(intent, player_input)
    direction = _direction_label(intent, player_input)
    if direction == "along the road":
        cleaned = f"You continue along the road toward {destination}, keeping the current lead in view."
    else:
        cleaned = f"You travel {direction} toward {destination}, leaving the tavern behind while keeping the road in sight."
    return _set_visible_response(out, narration=cleaned, source="travel_location_specificity")


def _cleanup_combat(out: Dict[str, Any], player_input: str, intent: Mapping[str, Any]) -> Dict[str, Any] | None:
    raw = _safe_dict(out.get("raw_result") or out.get("result"))
    narration = _safe_str(out.get("raw_narration") or raw.get("narration")).lower()
    action_type = _safe_str(_safe_dict(intent).get("action_type")).lower()
    if action_type != "combat" and "attack" not in _safe_str(player_input).lower():
        return None
    if _GENERIC_MOVEMENT_NARRATION not in narration:
        return None
    target = _target_label(intent, player_input)
    cleaned = f"You close with {target} and commit to the attack; the confrontation is now in motion."
    return _set_visible_response(out, narration=cleaned, source="combat_opening_specificity")


def apply_interactive_response_quality_cleanup(turn_summary: Mapping[str, Any], *, player_input: str) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn_summary))
    intent = _final_intent(out)
    for cleanup in (_cleanup_sell_request, _cleanup_dialogue_speaker, _cleanup_no_backed_fallback_speaker, _cleanup_party, _cleanup_travel, _cleanup_combat):
        repaired = cleanup(out, player_input, intent)
        if repaired is not None:
            return repaired
    return out


def apply_response_quality_to_matrix_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply cleanup in-place to a matrix result object and return a summary."""

    changed = 0
    scenarios = []
    result_dict = _safe_dict(result)
    for item in _safe_list(result_dict.get("results")):
        scenario = item.get("scenario")
        scenario_id = _safe_str(getattr(scenario, "scenario_id", "") or _safe_dict(scenario).get("scenario_id"))
        scenario_result = _safe_dict(item.get("result"))
        turns = []
        scenario_changed = 0
        for turn in _safe_list(scenario_result.get("turns")):
            turn_dict = _safe_dict(turn)
            cleaned = apply_interactive_response_quality_cleanup(turn_dict, player_input=_safe_str(turn_dict.get("player_input")))
            if _safe_dict(cleaned).get("interactive_cli_response_quality"):
                scenario_changed += 1
            turns.append(cleaned)
        if scenario_changed:
            scenario_result["turns"] = turns
            item["result"] = scenario_result
            changed += scenario_changed
        scenarios.append({"scenario_id": scenario_id, "changed_turns": scenario_changed})
    return {"ok": True, "source": RESPONSE_QUALITY_SOURCE, "changed_turns": changed, "scenarios": scenarios}
