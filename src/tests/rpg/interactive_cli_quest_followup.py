"""CB.5/CE/CE.1/CE.2 — grounded interactive presentation repairs.

This module repairs only player-facing presentation for interactive CLI turns. It
never invents quest rewards, rumors, prices, inventory, success, failure, or
simulation state. Quest/work and rumor/news repairs answer from deterministic
context. CE.2 adds a narrow dialogue/context repair for broad persona/location
questions when the runtime returns blank/no-op visible text.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Tuple

QUEST_FOLLOWUP_SOURCE = "interactive_cli_quest_followup_v4"
QUEST_TERMS = ("quest", "quests", "work", "job", "jobs", "lead", "leads", "task", "errand")
RUMOR_TERMS = ("rumor", "rumors", "news", "gossip")
DIALOGUE_CONTEXT_TERMS = (
    "who are you",
    "what do you know about this place",
    "what is this place",
    "tell me about this place",
    "tell me about the tavern",
    "know about this place",
    "about this place",
    "about the tavern",
)
NOOP_VISIBLE_MARKERS = (
    "the moment responds without producing a major new consequence",
    "no_supported_semantic_action_detected",
)
INVALID_VISIBLE_SPEAKERS = {"", "self", "player", "me", "you", "unknown", "narrator"}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _walk(value: Any, *, depth: int = 0, max_depth: int = 8) -> Iterable[Tuple[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(value, dict):
        yield "", value
        for key, nested in value.items():
            for path, item in _walk(nested, depth=depth + 1, max_depth=max_depth):
                yield f"/{key}{path}", item
    elif isinstance(value, list):
        for index, nested in enumerate(value[:200]):
            for path, item in _walk(nested, depth=depth + 1, max_depth=max_depth):
                yield f"[{index}]{path}", item


def _final_intent(turn_summary: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostics = _safe_dict(_safe_dict(turn_summary).get("interactive_cli_intent_diagnostics"))
    return _safe_dict(diagnostics.get("final_classification"))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _valid_visible_speaker(value: Any) -> str:
    speaker = _safe_str(value).strip()
    if speaker.lower() in INVALID_VISIBLE_SPEAKERS:
        return ""
    return speaker


def _visible_blob(turn_summary: Mapping[str, Any]) -> str:
    raw = _safe_dict(_safe_dict(turn_summary).get("raw_result") or _safe_dict(turn_summary).get("result"))
    npc = _safe_dict(raw.get("npc"))
    raw_npc = _safe_dict(_safe_dict(turn_summary).get("raw_npc"))
    return "\n".join(
        [
            _safe_str(_safe_dict(turn_summary).get("raw_narration")),
            _safe_str(raw_npc.get("speaker")),
            _safe_str(raw_npc.get("line")),
            _safe_str(raw.get("narration")),
            _safe_str(npc.get("speaker")),
            _safe_str(npc.get("line")),
            _safe_str(raw.get("visible_interaction_reason")),
        ]
    ).lower()


def _visible_is_blank_or_noop(turn_summary: Mapping[str, Any]) -> bool:
    blob = _visible_blob(turn_summary)
    raw = _safe_dict(_safe_dict(turn_summary).get("raw_result") or _safe_dict(turn_summary).get("result"))
    npc = _safe_dict(raw.get("npc"))
    raw_npc = _safe_dict(_safe_dict(turn_summary).get("raw_npc"))
    npc_line = _safe_str(raw_npc.get("line") or npc.get("line")).strip()
    if npc_line:
        return False
    return not blob.strip() or any(marker in blob for marker in NOOP_VISIBLE_MARKERS)


def inquiry_kind(player_input: str, turn_summary: Mapping[str, Any] | None = None) -> str:
    """Return quest, rumor, dialogue, or empty for scoped presentation repair."""
    text = _safe_str(player_input).lower()
    turn_summary = _safe_dict(turn_summary)
    intent = _final_intent(turn_summary)
    terms = " ".join(_safe_str(term).lower() for term in _safe_list(intent.get("requested_terms")))
    action_type = _safe_str(intent.get("action_type")).lower()
    service_kind = _safe_str(intent.get("service_kind")).lower()
    explicit_text_and_terms = " ".join([text, terms])
    combined = " ".join([text, terms, action_type, service_kind])

    if _contains_any(explicit_text_and_terms, RUMOR_TERMS):
        return "rumor"
    if action_type == "rumor_inquiry" or service_kind in {"rumor", "news"}:
        if _visible_is_blank_or_noop(turn_summary) and _contains_any(text, DIALOGUE_CONTEXT_TERMS):
            return "dialogue"
        return ""
    if action_type in {"quest_inquiry", "work_inquiry"} or service_kind in {"quest", "work", "paid_information"} or _contains_any(combined, QUEST_TERMS):
        return "quest"
    if _visible_is_blank_or_noop(turn_summary) and _contains_any(text, DIALOGUE_CONTEXT_TERMS):
        return "dialogue"
    return ""


def is_quest_inquiry(player_input: str, turn_summary: Mapping[str, Any] | None = None) -> bool:
    return inquiry_kind(player_input, turn_summary) in {"quest", "rumor"}


def extract_quest_context(raw_result: Mapping[str, Any], *, kind: str = "quest") -> Dict[str, Any]:
    raw_result = _safe_dict(raw_result)
    entries: List[Dict[str, Any]] = []
    sources: List[str] = []
    path_terms = ("rumor", "hook") if kind == "rumor" else ("quest", "hook")
    for path, item in _walk(raw_result):
        if not isinstance(item, dict):
            continue
        path_lower = path.lower()
        if not any(term in path_lower for term in path_terms):
            continue
        if item:
            if any(key in item for key in ("quest_id", "rumor_id", "title", "name", "objective", "summary", "description")):
                title = _safe_str(item.get("title") or item.get("name") or item.get("summary") or item.get("quest_id") or item.get("rumor_id") or kind)
                description = _safe_str(item.get("description") or item.get("objective") or item.get("summary"))
                entries.append({"title": title, "description": description, "path": path})
            sources.append(path)
    entries = [entry for entry in entries if entry.get("title") and entry.get("title") not in {"{}", "[]"}]
    return {
        "quests": entries[:8],
        "source_paths": sorted(set(sources))[:20],
        "has_backed_quest": bool(entries),
        "inquiry_kind": kind,
        "source": QUEST_FOLLOWUP_SOURCE,
    }


def _target_npc(turn_summary: Mapping[str, Any], player_input: str) -> str:
    raw = _safe_dict(_safe_dict(turn_summary).get("raw_result") or _safe_dict(turn_summary).get("result"))
    npc = _safe_dict(raw.get("npc"))
    existing = _valid_visible_speaker(npc.get("speaker"))
    if existing:
        return existing
    if "bran" in _safe_str(player_input).lower():
        return "Bran"
    intent = _final_intent(turn_summary)
    target = _valid_visible_speaker(intent.get("target_npc"))
    if target:
        return target
    return "Bran"


def format_quest_response(context: Mapping[str, Any], *, speaker: str, kind: str = "quest") -> Dict[str, Any]:
    context = _safe_dict(context)
    entries = _safe_list(context.get("quests"))
    if entries:
        labels = []
        for entry in entries:
            entry = _safe_dict(entry)
            title = _safe_str(entry.get("title") or ("Rumor" if kind == "rumor" else "Quest"))
            desc = _safe_str(entry.get("description"))
            labels.append(f"{title}: {desc}" if desc and desc != title else title)
        listing = "; ".join(labels)
        if kind == "rumor":
            return {
                "narration": f"{speaker} shares the backed rumor or news currently available: {listing}.",
                "npc": {"speaker": speaker, "line": f"I can confirm this much: {listing}."},
                "action": "Rumor inquiry answered from authoritative rumor context.",
            }
        return {
            "narration": f"{speaker} lists the backed quest leads currently available: {listing}.",
            "npc": {"speaker": speaker, "line": f"I have this work backed by the current state: {listing}."},
            "action": "Quest inquiry answered from authoritative quest context.",
        }
    if kind == "rumor":
        return {
            "narration": f"{speaker} checks the confirmed rumors and news and finds nothing backed by the current state.",
            "npc": {"speaker": speaker, "line": "I do not have any confirmed rumors or news for you right now."},
            "action": "Rumor inquiry answered with no backed rumor available.",
        }
    return {
        "narration": f"{speaker} checks what he can actually offer and has no backed quest available in the current state.",
        "npc": {"speaker": speaker, "line": "I do not have a confirmed job or quest for you right now."},
        "action": "Quest inquiry answered with no backed quest available.",
    }


def format_dialogue_response(*, speaker: str, player_input: str) -> Dict[str, Any]:
    text = _safe_str(player_input).lower()
    if "who are you" in text:
        line = "I'm Bran, keeper of this tavern, and I keep an ear on the road."
    elif "tavern" in text:
        line = "This tavern sits on the road, a place where travelers trade coin, rest, and cautious stories."
    else:
        line = "This place sits by the road, with the tavern serving as the nearest shelter, meeting point, and source of local talk."
    return {
        "narration": f"{speaker} answers from what is already established about the scene.",
        "npc": {"speaker": speaker, "line": line},
        "action": "Dialogue context inquiry answered from bounded scene/persona context.",
    }


def apply_quest_followup_repair(turn_summary: Mapping[str, Any], *, player_input: str) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn_summary))
    kind = inquiry_kind(player_input, out)
    if not kind:
        return out
    if _safe_dict(out.get("interactive_cli_commerce_followup")).get("applied"):
        return out
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    speaker = _target_npc(out, player_input)

    if kind == "dialogue":
        response = format_dialogue_response(speaker=speaker, player_input=player_input)
        context = {"inquiry_kind": "dialogue", "has_backed_quest": False, "source": QUEST_FOLLOWUP_SOURCE}
    else:
        context = extract_quest_context(raw_result, kind=kind)
        response = format_quest_response(context, speaker=speaker, kind=kind)

    raw_result["narration"] = response["narration"]
    raw_result["npc"] = response["npc"]
    raw_result["visible_interaction_reason"] = response["action"]
    raw_result["interactive_cli_quest_followup"] = {
        "applied": True,
        "source": QUEST_FOLLOWUP_SOURCE,
        "quest_context": context,
        "final_intent": _final_intent(out),
        "inquiry_kind": kind,
    }
    contract = deepcopy(_safe_dict(raw_result.get("turn_contract")))
    contract["quest_inquiry_followup"] = {
        "answered": True,
        "has_backed_quest": bool(context.get("has_backed_quest")),
        "inquiry_kind": kind,
        "source": QUEST_FOLLOWUP_SOURCE,
        "quest_context": context,
    }
    raw_result["turn_contract"] = contract

    out["raw_result"] = raw_result
    out["raw_narration"] = response["narration"]
    out["raw_npc"] = response["npc"]
    extracted = deepcopy(_safe_dict(out.get("extracted")))
    extracted["narration"] = response["narration"]
    extracted["action"] = response["action"]
    extracted["npc_speaker"] = response["npc"]["speaker"]
    extracted["npc_line"] = response["npc"]["line"]
    out["extracted"] = extracted
    out["narration_preview"] = response["narration"]
    out["interactive_cli_quest_followup"] = raw_result["interactive_cli_quest_followup"]
    warnings = list(_safe_list(out.get("scenario_warnings")))
    if kind == "dialogue":
        warning = "interactive_cli_dialogue_context_repaired_from_bounded_context"
    elif context.get("has_backed_quest"):
        warning = f"interactive_cli_{kind}_inquiry_answered_from_authoritative_context"
    else:
        warning = f"interactive_cli_{kind}_inquiry_no_backed_state_available"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings
    return out
