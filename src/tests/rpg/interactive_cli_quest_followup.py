"""CB.5 — grounded quest/rumor inquiry repair for interactive CLI runs.

The LLM intent router may correctly recognize that the player is asking Bran for
quests, rumors, work, or news, but the deterministic runtime can still return
`no_supported_semantic_action_detected` with empty NPC text when no backed quest
state exists.  This module patches only the presentation/diagnostic layer: it
never invents quest rewards or quest state.  If no authoritative quest is present,
Bran says so explicitly.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Tuple

QUEST_FOLLOWUP_SOURCE = "interactive_cli_quest_followup_v1"
QUEST_TERMS = ("quest", "quests", "work", "job", "jobs", "rumor", "rumors", "news", "lead", "leads", "task", "errand")


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


def is_quest_inquiry(player_input: str, turn_summary: Mapping[str, Any] | None = None) -> bool:
    text = _safe_str(player_input).lower()
    if any(term in text for term in QUEST_TERMS):
        return True
    intent = _final_intent(_safe_dict(turn_summary))
    terms = " ".join(_safe_str(term).lower() for term in _safe_list(intent.get("requested_terms")))
    if any(term in terms for term in QUEST_TERMS):
        return True
    action_type = _safe_str(intent.get("action_type")).lower()
    service_kind = _safe_str(intent.get("service_kind")).lower()
    if action_type in {"quest_inquiry", "rumor_inquiry", "work_inquiry"}:
        return True
    if service_kind in {"quest", "rumor", "paid_information", "work"}:
        return True
    raw = _safe_str(_safe_dict(_safe_dict(turn_summary).get("interactive_cli_intent_diagnostics")).get("raw_text_excerpt")).lower()
    return any(term in raw for term in QUEST_TERMS)


def extract_quest_context(raw_result: Mapping[str, Any]) -> Dict[str, Any]:
    raw_result = _safe_dict(raw_result)
    quest_entries: List[Dict[str, Any]] = []
    sources: List[str] = []
    for path, item in _walk(raw_result):
        if not isinstance(item, dict):
            continue
        path_lower = path.lower()
        if "quest" not in path_lower and "rumor" not in path_lower and "hook" not in path_lower:
            continue
        if item:
            if any(key in item for key in ("quest_id", "title", "name", "objective", "summary", "description")):
                title = _safe_str(item.get("title") or item.get("name") or item.get("summary") or item.get("quest_id") or "quest")
                description = _safe_str(item.get("description") or item.get("objective") or item.get("summary"))
                quest_entries.append({"title": title, "description": description, "path": path})
            sources.append(path)
    # Empty companion summaries are not quest offers.
    quest_entries = [entry for entry in quest_entries if entry.get("title") and entry.get("title") not in {"{}", "[]"}]
    return {
        "quests": quest_entries[:8],
        "source_paths": sorted(set(sources))[:20],
        "has_backed_quest": bool(quest_entries),
        "source": QUEST_FOLLOWUP_SOURCE,
    }


def _target_npc(turn_summary: Mapping[str, Any], player_input: str) -> str:
    intent = _final_intent(turn_summary)
    target = _safe_str(intent.get("target_npc")).strip()
    if target:
        return target
    if "bran" in _safe_str(player_input).lower():
        return "Bran"
    raw = _safe_dict(_safe_dict(turn_summary).get("raw_result") or _safe_dict(turn_summary).get("result"))
    npc = _safe_dict(raw.get("npc"))
    return _safe_str(npc.get("speaker") or "Bran").strip() or "Bran"


def format_quest_response(context: Mapping[str, Any], *, speaker: str) -> Dict[str, Any]:
    context = _safe_dict(context)
    quests = _safe_list(context.get("quests"))
    if quests:
        labels = []
        for quest in quests:
            quest = _safe_dict(quest)
            title = _safe_str(quest.get("title") or "Quest")
            desc = _safe_str(quest.get("description"))
            labels.append(f"{title}: {desc}" if desc and desc != title else title)
        listing = "; ".join(labels)
        return {
            "narration": f"{speaker} lists the backed quest leads currently available: {listing}.",
            "npc": {"speaker": speaker, "line": f"I have this work backed by the current state: {listing}."},
            "action": "Quest inquiry answered from authoritative quest context.",
        }
    return {
        "narration": f"{speaker} checks what he can actually offer and has no backed quest available in the current state.",
        "npc": {"speaker": speaker, "line": "I do not have a confirmed job or quest for you right now."},
        "action": "Quest inquiry answered with no backed quest available.",
    }


def apply_quest_followup_repair(turn_summary: Mapping[str, Any], *, player_input: str) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn_summary))
    if not is_quest_inquiry(player_input, out):
        return out
    if _safe_dict(out.get("interactive_cli_commerce_followup")).get("applied"):
        return out
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    context = extract_quest_context(raw_result)
    speaker = _target_npc(out, player_input)
    response = format_quest_response(context, speaker=speaker)

    raw_result["narration"] = response["narration"]
    raw_result["npc"] = response["npc"]
    raw_result["visible_interaction_reason"] = response["action"]
    raw_result["interactive_cli_quest_followup"] = {
        "applied": True,
        "source": QUEST_FOLLOWUP_SOURCE,
        "quest_context": context,
        "final_intent": _final_intent(out),
    }
    contract = deepcopy(_safe_dict(raw_result.get("turn_contract")))
    contract["quest_inquiry_followup"] = {
        "answered": True,
        "has_backed_quest": bool(context.get("has_backed_quest")),
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
    warning = "interactive_cli_quest_inquiry_answered_from_authoritative_quest_context"
    if not context.get("has_backed_quest"):
        warning = "interactive_cli_quest_inquiry_no_backed_quest_available"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings
    return out
