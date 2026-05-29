"""CB.5/CE — grounded quest, work, rumor, and news inquiry repair.

The LLM intent router may correctly recognize that the player is asking Bran for
quests, rumors, work, or news, but the deterministic runtime can still return
`no_supported_semantic_action_detected` with empty NPC text when no backed state
exists.  This module patches only the presentation/diagnostic layer: it never
invents quest rewards, rumors, or quest state.

CE narrows the repair scope so generic dialogue, observe, and survival/inventory
self-use turns cannot be swallowed by quest repair. Rumor/news has a separate
no-backed-state response instead of saying there is no quest.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Tuple

QUEST_FOLLOWUP_SOURCE = "interactive_cli_quest_followup_v2"
QUEST_TERMS = ("quest", "quests", "work", "job", "jobs", "lead", "leads", "task", "errand")
RUMOR_TERMS = ("rumor", "rumors", "news")


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


def inquiry_kind(player_input: str, turn_summary: Mapping[str, Any] | None = None) -> str:
    """Return quest, rumor, or empty for CE-scoped follow-up repair.

    The user's visible text and final intent are both considered, but raw LLM
    excerpts are no longer enough to trigger repair. This prevents provider JSON
    or prompt echoes from causing quest repair on unrelated talk/observe/survival
    turns.
    """
    text = _safe_str(player_input).lower()
    intent = _final_intent(_safe_dict(turn_summary))
    terms = " ".join(_safe_str(term).lower() for term in _safe_list(intent.get("requested_terms")))
    action_type = _safe_str(intent.get("action_type")).lower()
    service_kind = _safe_str(intent.get("service_kind")).lower()
    combined = " ".join([text, terms, action_type, service_kind])

    if action_type == "rumor_inquiry" or service_kind in {"rumor", "news"} or _contains_any(combined, RUMOR_TERMS):
        return "rumor"
    if action_type in {"quest_inquiry", "work_inquiry"} or service_kind in {"quest", "work", "paid_information"} or _contains_any(combined, QUEST_TERMS):
        return "quest"
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
    intent = _final_intent(turn_summary)
    target = _safe_str(intent.get("target_npc")).strip()
    if target:
        return target
    if "bran" in _safe_str(player_input).lower():
        return "Bran"
    raw = _safe_dict(_safe_dict(turn_summary).get("raw_result") or _safe_dict(turn_summary).get("result"))
    npc = _safe_dict(raw.get("npc"))
    return _safe_str(npc.get("speaker") or "Bran").strip() or "Bran"


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


def apply_quest_followup_repair(turn_summary: Mapping[str, Any], *, player_input: str) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn_summary))
    kind = inquiry_kind(player_input, out)
    if not kind:
        return out
    if _safe_dict(out.get("interactive_cli_commerce_followup")).get("applied"):
        return out
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    context = extract_quest_context(raw_result, kind=kind)
    speaker = _target_npc(out, player_input)
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
    if context.get("has_backed_quest"):
        warning = f"interactive_cli_{kind}_inquiry_answered_from_authoritative_context"
    else:
        warning = f"interactive_cli_{kind}_inquiry_no_backed_state_available"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings
    return out
