from __future__ import annotations

import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Tuple

from app.rpg.narration.runtime_narration_contract import build_runtime_narration_payload

try:
    from app.providers.base import ChatMessage
except Exception:
    ChatMessage = None
from app.rpg.advisory.candidates import (
    advisory_candidate_summary,
    build_deterministic_advisory_candidates,
    normalize_advisory_candidates,
    stable_json_for_prompt,
)
from app.rpg.advisory.runtime_store import ingest_deferred_advisory_candidates
from tests.rpg.autoplay.checkpoints import validate_save_load_checkpoint
from tests.rpg.autoplay.performance import elapsed_ms, now_perf
from tests.rpg.autoplay.progress import state_digest


def _queue_timing(
    *,
    queued_at: float,
    started_at: float,
    finished_at: float,
) -> Dict[str, Any]:
    return {
        "queued_at": round(queued_at, 6),
        "started_at": round(started_at, 6),
        "finished_at": round(finished_at, 6),
        "queue_wait_ms": round((started_at - queued_at) * 1000.0, 3),
        "run_ms": round((finished_at - started_at) * 1000.0, 3),
        "total_ms": round((finished_at - queued_at) * 1000.0, 3),
    }


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    """Normalize lightweight action/NPC text for deterministic packet checks.

    N116.9 added current-action/NPC-response architecture helpers to this
    module, but those helpers called ``_norm`` without defining it here. That
    only surfaced inside background LLM jobs, so turns kept running while every
    combined background job failed with ``name '_norm' is not defined``. Keep
    the helper local to avoid importing heavier normalization utilities into the
    background worker path.
    """
    import re

    text = _safe_str(value).lower().strip()
    text = re.sub(r"[^a-z0-9_]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


PRESENTATION_INTENT_ALLOWED_CATEGORIES = {
    "dialogue",
    "evidence",
    "investigation",
    "travel",
    "combat",
    "service",
    "economy",
    "stealth",
    "social",
    "lore",
    "quest",
    "mixed",
    "general",
}


def _normalize_presentation_category(value: Any) -> str:
    category = _safe_str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "conversation": "dialogue",
        "talk": "dialogue",
        "social": "dialogue",
        "buying": "economy",
        "purchase": "economy",
        "shop": "economy",
        "lodging": "service",
        "room": "service",
        "rest": "service",
        "clue": "evidence",
        "proof": "evidence",
        "search": "investigation",
        "scouting": "investigation",
        "move": "travel",
        "movement": "travel",
        "fight": "combat",
        "battle": "combat",
    }
    category = aliases.get(category, category)
    if category not in PRESENTATION_INTENT_ALLOWED_CATEGORIES:
        return "general"
    return category


def _normalize_presentation_intent(value: Any) -> Dict[str, Any]:
    raw = _safe_dict(value)
    primary = _normalize_presentation_category(
        raw.get("primary_category")
        or raw.get("category")
        or raw.get("primary")
        or raw.get("intent_category")
        or raw.get("label")
    )
    secondary: List[str] = []
    for item in _safe_list(
        raw.get("secondary_categories")
        or raw.get("secondary")
        or raw.get("categories")
        or raw.get("secondary_intents")
    ):
        normalized = _normalize_presentation_category(item)
        if normalized and normalized != primary and normalized not in secondary:
            secondary.append(normalized)

    try:
        confidence = float(raw.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "format_version": "presentation_intent_v1",
        "primary_category": primary,
        "secondary_categories": secondary[:4],
        "confidence": round(confidence, 3),
        "reason": _safe_str(raw.get("reason") or raw.get("rationale"))[:240],
    }


def _normalize_current_action_response(value: Any) -> Dict[str, Any]:
    """Normalize provider self-check that the NPC line answers this turn.

    This is not authoritative simulation. It is presentation metadata used to
    keep the provider focused on the current player action before older quest
    context, memories, or recent investigation threads.
    """
    raw = _safe_dict(value)
    required_focus: List[str] = []
    for item in _safe_list(
        raw.get("required_focus")
        or raw.get("required_response_focus")
        or raw.get("focus")
        or raw.get("must_address")
    ):
        text = _safe_str(item).strip().lower().replace(" ", "_").replace("-", "_")
        if text and text not in required_focus:
            required_focus.append(text[:64])

    addresses_raw = raw.get("npc_line_addresses_current_action")
    if addresses_raw is None:
        addresses_raw = raw.get("addresses_current_action")
    addresses_current_action = bool(addresses_raw) if addresses_raw is not None else False

    return {
        "format_version": "current_action_response_v1",
        "required_focus": required_focus[:6],
        "npc_line_addresses_current_action": addresses_current_action,
        "reason": _safe_str(raw.get("reason") or raw.get("rationale"))[:240],
    }


def _find_current_action_response_candidate(payload: Any) -> Tuple[Dict[str, Any], str]:
    payload = _safe_dict(payload)
    if not payload:
        return {}, "missing"

    direct_keys = (
        "current_action_response",
        "response_focus",
        "required_response_focus",
        "current_action_focus",
        "npc_line_relevance",
    )
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value, key

    nested_paths = (
        ("presentation", "current_action_response"),
        ("presentation", "response_focus"),
        ("narration_payload", "current_action_response"),
        ("narration_payload", "response_focus"),
        ("structured_narration", "current_action_response"),
        ("structured_narration", "response_focus"),
        ("result", "current_action_response"),
        ("data", "current_action_response"),
        ("payload", "current_action_response"),
    )
    for path in nested_paths:
        cursor: Any = payload
        ok = True
        for key in path:
            cursor = _safe_dict(cursor).get(key)
            if cursor is None:
                ok = False
                break
        if ok and isinstance(cursor, dict):
            return cursor, ".".join(path)
    return {}, "missing"


def _find_presentation_intent_candidate(payload: Any) -> Tuple[Dict[str, Any], str]:
    """Return provider intent from common local-model JSON shapes.

    N115 runs showed the finalizer was often seeing `general` because useful
    intent was either omitted or nested under a different key. Keep this
    extractor liberal, then let deterministic validation clamp unsupported
    categories later.
    """
    payload = _safe_dict(payload)
    if not payload:
        return {}, "missing"

    direct_keys = (
        "presentation_intent",
        "current_action_response",
        "response_focus",
        "intent",
        "presentationIntent",
        "classification",
        "category",
        "intent_category",
    )
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value, key
        if isinstance(value, str) and value.strip():
            return {"primary_category": value.strip()}, key

    nested_paths = (
        ("presentation", "intent"),
        ("presentation", "presentation_intent"),
        ("narration", "presentation_intent"),
        ("narration", "intent"),
        ("narration_payload", "presentation_intent"),
        ("narration_payload", "intent"),
        ("structured_narration", "presentation_intent"),
        ("structured_narration", "intent"),
        ("result", "presentation_intent"),
        ("result", "intent"),
        ("data", "presentation_intent"),
        ("data", "intent"),
        ("payload", "presentation_intent"),
        ("payload", "intent"),
    )
    for path in nested_paths:
        cursor: Any = payload
        ok = True
        for key in path:
            cursor = _safe_dict(cursor).get(key)
            if cursor is None:
                ok = False
                break
        if not ok:
            continue
        if isinstance(cursor, dict):
            return cursor, ".".join(path)
        if isinstance(cursor, str) and cursor.strip():
            return {"primary_category": cursor.strip()}, ".".join(path)

    return {}, "missing"


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _row_runtime_state(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a mutable runtime_state object attached to the transcript row.

    Autoplay rows may store raw result/session in different shapes depending on
    harness mode. This helper creates a row-local runtime_state mirror for report
    and promotion integration without mutating live simulation snapshots.
    """
    turn_result = _safe_dict(row.get("turn_result"))
    session = _safe_dict(turn_result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    if not runtime_state:
        runtime_state = _safe_dict(row.get("runtime_state"))
    if not runtime_state:
        runtime_state = {}
    row["runtime_state"] = runtime_state
    return runtime_state


def compact_json_for_prompt(value: Any, max_chars: int = 6000) -> str:
    """Stable compact JSON for prompt context.

    This preserves information while removing whitespace/token waste.
    Section-level caps should be applied before this where possible.
    """
    import json

    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text


def _short_text(value: Any, max_chars: int = 600) -> str:
    text = _safe_str(value).strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "...[truncated]"
    return text


def _list_tail(value: Any, limit: int) -> List[Any]:
    values = value if isinstance(value, list) else []
    if limit <= 0:
        return []
    return values[-limit:]


def _dict_subset(value: Any, keys: List[str]) -> Dict[str, Any]:
    source = _safe_dict(value)
    return {key: source.get(key) for key in keys if key in source and source.get(key) not in (None, "", [], {}, {})}


def _safe_npc_name(npc: Any) -> str:
    if isinstance(npc, str):
        return npc
    npc_dict = _safe_dict(npc)
    return (
        _safe_str(npc_dict.get("name"))
        or _safe_str(npc_dict.get("id"))
        or _safe_str(npc_dict.get("npc_id"))
        or _safe_str(npc_dict.get("speaker"))
    )


def _compact_present_npcs(simulation_state: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    present = (
        _safe_list(simulation_state.get("present_npcs"))
        or _safe_list(simulation_state.get("nearby_npcs"))
        or _safe_list(simulation_state.get("visible_npcs"))
    )
    npcs_by_id = _safe_dict(simulation_state.get("npcs"))
    compact: List[Dict[str, Any]] = []

    for item in present[:limit]:
        npc_id = _safe_npc_name(item)
        npc_record = _safe_dict(npcs_by_id.get(npc_id)) or _safe_dict(item)
        compact.append(
            {
                "id": npc_id,
                "name": _safe_str(npc_record.get("name")) or npc_id,
                "role": _safe_str(npc_record.get("role") or npc_record.get("occupation")),
                "mood": _safe_str(npc_record.get("mood") or npc_record.get("emotional_state")),
                "relationship": _safe_dict(npc_record.get("relationship")),
            }
        )

    if not compact and npcs_by_id:
        for npc_id, npc_record_any in list(npcs_by_id.items())[:limit]:
            npc_record = _safe_dict(npc_record_any)
            compact.append(
                {
                    "id": str(npc_id),
                    "name": _safe_str(npc_record.get("name")) or str(npc_id),
                    "role": _safe_str(npc_record.get("role") or npc_record.get("occupation")),
                    "mood": _safe_str(npc_record.get("mood") or npc_record.get("emotional_state")),
                }
            )

    return [item for item in compact if item.get("id") or item.get("name")]


def _compact_scene_context(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    scene = _safe_dict(simulation_state.get("scene"))
    location = _safe_dict(simulation_state.get("location"))
    current_location = (
        _safe_str(simulation_state.get("current_location"))
        or _safe_str(location.get("name"))
        or _safe_str(scene.get("location"))
        or _safe_str(scene.get("name"))
    )
    return {
        "location": current_location,
        "scene_title": _safe_str(scene.get("title") or scene.get("name")),
        "scene_summary": _short_text(
            scene.get("summary") or scene.get("description") or simulation_state.get("scene_summary"),
            900,
        ),
        "time": _safe_str(simulation_state.get("time") or simulation_state.get("world_time")),
        "weather": _safe_str(simulation_state.get("weather")),
    }


def _compact_recent_events(simulation_state: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    raw_events = (
        _safe_list(simulation_state.get("recent_events"))
        or _safe_list(simulation_state.get("world_events"))
        or _safe_list(simulation_state.get("event_log"))
    )
    events = []
    for event in _list_tail(raw_events, limit):
        event_dict = _safe_dict(event)
        if event_dict:
            events.append(
                {
                    "kind": _safe_str(event_dict.get("kind") or event_dict.get("type")),
                    "summary": _short_text(
                        event_dict.get("summary")
                        or event_dict.get("description")
                        or event_dict.get("text"),
                        400,
                    ),
                }
            )
        elif isinstance(event, str):
            events.append({"summary": _short_text(event, 400)})
    return [event for event in events if event.get("summary")]


def _compact_player_visible_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    player = _safe_dict(simulation_state.get("player"))
    inventory = _safe_dict(simulation_state.get("inventory") or player.get("inventory"))
    currency = _safe_dict(simulation_state.get("currency") or player.get("currency"))
    return {
        "name": _safe_str(player.get("name") or simulation_state.get("player_name")),
        "status": _safe_str(player.get("status")),
        "visible_conditions": _safe_list(player.get("conditions"))[:8],
        "inventory_item_count": len(_safe_list(inventory.get("items"))),
        "currency": currency,
    }


def _compact_loaded_npc_profiles(runtime_state: Dict[str, Any], limit: int = 6) -> Dict[str, Any]:
    npc_evolution = _safe_dict(_safe_dict(runtime_state).get("npc_evolution"))
    loaded = _safe_dict(npc_evolution.get("loaded_profiles"))
    out: Dict[str, Any] = {}
    for npc_id, row_any in list(loaded.items())[:limit]:
        row = _safe_dict(row_any)
        profile = _safe_dict(row.get("profile"))
        out[str(npc_id)] = {
            "arc_stage": _safe_str(profile.get("arc_stage")) or "stable",
            "axes": _safe_dict(profile.get("axes")),
            "memories": _safe_list(profile.get("memories"))[-4:],
            "future_hooks": _safe_list(profile.get("future_hooks"))[-4:],
            "world_signals": _safe_list(profile.get("world_signals"))[-3:],
            "semantic_intents": _safe_list(profile.get("semantic_intents"))[-3:],
            "milestones": _safe_list(profile.get("milestones"))[-3:],
            "signals_applied_count": profile.get("signals_applied_count"),
        }
    return out


def _loaded_profile_context_summary(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    """Tiny diagnostic for prompt/report quality.

    Keep this separate from the actual context payload so reports can quickly
    tell whether profile context was available without dumping full profile data.
    """
    loaded = _compact_loaded_npc_profiles(runtime_state, limit=12)
    return {
        "available": bool(loaded),
        "npc_count": len(loaded),
        "npc_ids": sorted(list(loaded.keys())),
        "arc_stages": {
            npc_id: _safe_str(profile.get("arc_stage")) or "stable"
            for npc_id, profile in loaded.items()
        },
        "memory_counts": {
            npc_id: len(_safe_list(profile.get("memories")))
            for npc_id, profile in loaded.items()
        },
        "future_hook_counts": {
            npc_id: len(_safe_list(profile.get("future_hooks")))
            for npc_id, profile in loaded.items()
        },
    }



COMMERCE_ACTION_VERBS = (
    "buy",
    "bought",
    "purchase",
    "purchased",
    "pay for",
    "pay bran for",
    "pay the innkeeper for",
    "order",
    "sell",
    "trade",
    "hire",
)

COMMERCE_OBJECT_TERMS = (
    "ration",
    "rations",
    "supply",
    "supplies",
    "meal",
    "ale",
    "room",
    "lodging",
    "bed",
    "service",
)

EVIDENCE_PAYMENT_FALSE_POSITIVE_TERMS = (
    "marked coin",
    "coin proof",
    "coin lead",
    "payment mark",
    "payment marks",
    "manifest payment",
    "sealed order",
    "sealed orders",
    "route paper",
    "route papers",
    "captured order",
    "captured orders",
    "captured route paper",
    "captured route papers",
    "written order",
    "written orders",
    "orders from",
    "orders signed",
    "orders naming",
    "ledger",
    "ledger entries",
    "paymaster",
    "funded",
    "backer",
    "proof",
    "evidence",
)


def _action_is_evidence_payment_phrase(action: str) -> bool:
    return any(term in action for term in EVIDENCE_PAYMENT_FALSE_POSITIVE_TERMS)


def _action_is_commerce_request(action: str, service_result: Dict[str, Any]) -> bool:
    service_result = _safe_dict(service_result)
    if service_result.get("purchase") or service_result.get("sale"):
        return True
    if _action_is_evidence_payment_phrase(action) and not any(
        verb in action for verb in COMMERCE_ACTION_VERBS
    ):
        return False
    has_commerce_verb = any(verb in action for verb in COMMERCE_ACTION_VERBS)
    has_commerce_object = any(term in action for term in COMMERCE_OBJECT_TERMS)
    return bool(has_commerce_verb and (has_commerce_object or "coin" in action or "price" in action))


def _action_is_service_request(action: str, service_result: Dict[str, Any]) -> bool:
    service_result = _safe_dict(service_result)
    if service_result.get("service"):
        return True
    if _action_is_evidence_payment_phrase(action) and not any(
        verb in action for verb in ("rent", "sleep", "rest", "book", "pay for")
    ):
        return False
    return any(term in action for term in ("rent room", "rent a room", "lodging", "book room", "sleep", "rest here", "pay for room"))


def _current_action_required_focus(
    *,
    player_action: str,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> List[str]:
    """Deterministically identify what NPC dialogue must answer first.

    Keep commerce/service detection narrow.  Long investigation arcs often use
    words like "marked coin", "payment marks", "ledger", and
    "paymaster" as evidence, not as purchase requests.
    """
    action = _norm(player_action)
    contract = _safe_dict(turn_contract)
    semantic = _safe_dict(semantic_action_record)
    focus: List[str] = []

    def add(item: str) -> None:
        if item and item not in focus:
            focus.append(item)

    resolved = _norm(contract.get("resolved_action") or contract.get("resolved_result"))
    semantic_kind = _norm(
        semantic.get("kind")
        or semantic.get("intent")
        or semantic.get("semantic_action")
        or _safe_dict(contract.get("semantic_action")).get("kind")
    )
    service_result = _safe_dict(contract.get("service_result"))
    if _action_is_commerce_request(action, service_result):
        add("purchase_acknowledgement")
        add("item_quantity_or_availability")
        add("price_or_payment")
    if _action_is_service_request(action, service_result):
        add("service_request_acknowledgement")
        add("lodging_or_rest_terms")
    if any(term in action for term in ("ask", "question", "tell", "report", "warn", "explain")) or semantic_kind in {"social", "dialogue"}:
        add("answer_current_question")
    if any(term in action for term in ("look", "inspect", "search", "scout", "examine", "listen", "study", "decode")):
        add("observed_evidence_or_limits")
    if any(term in action for term in ("travel", "follow", "leave", "go to", "road", "route")) or "travel" in resolved:
        add("current_travel_or_route_action")
    return focus[:8]


def _target_npc_name_from_action(player_action: str, simulation_state: Dict[str, Any]) -> str:
    action = _norm(player_action)
    present = _compact_present_npcs(simulation_state, limit=8)
    for npc in present:
        name = _safe_str(_safe_dict(npc).get("name"))
        if name and _norm(name) in action:
            return name
    if "bran" in action or "innkeeper" in action:
        return "Bran"
    if "mira" in action:
        return "Mira"
    if "patron" in action:
        return "Local Patron"
    return _safe_str(_safe_dict(present[0]).get("name")) if present else ""


def _loaded_profile_for_target(
    *,
    runtime_state: Dict[str, Any],
    target_npc_name: str,
) -> Tuple[str, Dict[str, Any]]:
    loaded = _compact_loaded_npc_profiles(runtime_state, limit=12)
    target_n = _norm(target_npc_name)
    if not loaded:
        return "", {}
    for npc_id, profile in loaded.items():
        candidates = [
            npc_id,
            _safe_str(_safe_dict(profile).get("name")),
            _safe_str(_safe_dict(profile).get("display_name")),
        ]
        for candidate in candidates:
            candidate_n = _norm(candidate)
            if candidate_n and target_n and (candidate_n == target_n or candidate_n in target_n or target_n in candidate_n):
                return npc_id, _safe_dict(profile)
    if target_n and len(loaded) == 1:
        npc_id, profile = next(iter(loaded.items()))
        return npc_id, _safe_dict(profile)
    return "", {}


def _build_npc_response_architecture_packet(
    *,
    player_action: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Compact prompt packet that prioritizes current action over old context.

    Loaded profiles and memories are file-backed characterization context only.
    They can shape voice and continuity but cannot create outcomes.
    """
    target_name = _target_npc_name_from_action(player_action, simulation_state)
    npc_id, profile = _loaded_profile_for_target(
        runtime_state=runtime_state,
        target_npc_name=target_name,
    )
    memories = _safe_list(profile.get("memories"))[-3:]
    future_hooks = _safe_list(profile.get("future_hooks"))[-2:]
    return {
        "format_version": "npc_response_architecture_v1",
        "current_action_first": True,
        "current_action": _short_text(player_action, 500),
        "required_focus": _current_action_required_focus(
            player_action=player_action,
            turn_contract=turn_contract,
            semantic_action_record=semantic_action_record,
        ),
        "target_npc": {
            "npc_id": npc_id,
            "name": target_name,
            "profile_available": bool(profile),
            "arc_stage": _safe_str(profile.get("arc_stage")) or "stable",
            "axes": _safe_dict(profile.get("axes")),
            "file_backed_memory_snippets": memories,
            "future_hooks": future_hooks,
        },
        "persona_usage": "tone_only_no_new_outcomes",
        "memory_usage": "file_backed_tone_or_continuity_only",
        "forbidden": [
            "do_not_answer_stale_investigation_topic_unless_current_action_asks",
            "do_not_invent_profile_memory",
            "do_not_create_authoritative_outcomes",
        ],
    }


def _compact_turn_contract(turn_contract: Dict[str, Any]) -> Dict[str, Any]:
    contract = _safe_dict(turn_contract)
    semantic_action = _safe_dict(contract.get("semantic_action"))
    state_delta = _safe_dict(contract.get("state_delta"))
    return {
        "version": contract.get("version"),
        "player_input": _short_text(contract.get("player_input"), 500),
        "resolved_action": contract.get("resolved_action"),
        "resolved_result": contract.get("resolved_result"),
        "semantic_action": semantic_action,
        "service_result": contract.get("service_result"),
        "state_delta": _dict_subset(
            state_delta,
            ["summary", "changed_keys", "relationship_delta", "memory_delta", "world_signal_delta"],
        ),
        "narration_brief": _short_text(contract.get("narration_brief"), 700),
        "presentation": _dict_subset(_safe_dict(contract.get("presentation")), ["title", "summary", "npc"]),
    }



def build_current_turn_prompt_contract(
    *,
    player_action: str,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the highest-priority provider prompt contract for one turn.

    Older compact context is still useful for tone and continuity, but this
    packet is intentionally current-turn-first so NPC lines do not answer stale
    memories, rumors, or investigation topics when the player just bought,
    rented, rested, attacked, travelled, or asked a direct question.
    """
    turn_contract = _safe_dict(turn_contract)
    semantic_action_record = _safe_dict(semantic_action_record)
    semantic_action = _safe_dict(turn_contract.get("semantic_action")) or semantic_action_record
    resolved_action = _safe_str(turn_contract.get("resolved_action"))
    resolved_result = _safe_str(turn_contract.get("resolved_result"))
    service_result = _safe_dict(turn_contract.get("service_result"))
    action_lower = " ".join(
        [
            _safe_str(player_action),
            resolved_action,
            resolved_result,
            _safe_str(semantic_action.get("intent")),
            _safe_str(semantic_action.get("action_type")),
            _safe_str(service_result.get("service_type")),
        ]
    ).lower()

    required_focus: List[str] = [
        "answer_the_current_player_action_before_old_context",
        "state_only_the_resolved_result_from_turn_contract",
    ]
    forbidden_stale_topics: List[str] = [
        "do_not_continue_previous_quest_investigation_unless_current_action_asks",
        "do_not_answer_profile_memory_instead_of_current_action",
    ]

    commerce_or_service_request = _action_is_commerce_request(action_lower, service_result) or _action_is_service_request(action_lower, service_result)
    if commerce_or_service_request:
        required_focus.insert(0, "acknowledge_the_service_or_economy_request_first")
        required_focus.append("mention_item_quantity_price_or_refusal_only_if_present_in_contract")
        forbidden_stale_topics.extend(
            [
                "ambush_investigation",
                "bandit_road_investigation",
                "traveler_or_road_question",
                "who_frightened_them_followup",
            ]
        )
    elif any(token in action_lower for token in ("ask", "tell", "warn", "report", "say", "question")):
        required_focus.insert(0, "answer_the_direct_dialogue_or_reported_evidence_first")
        required_focus.append("npc_line_must_be_a_response_not_a_new_unprompted_topic")
    elif any(token in action_lower for token in ("attack", "strike", "punch", "fight", "defend")):
        required_focus.insert(0, "reflect_the_combat_or_hostile_result_first")
    elif any(token in action_lower for token in ("travel", "go to", "move", "leave", "road", "bridge")):
        required_focus.insert(0, "reflect_the_route_or_movement_result_first")

    return {
        "format_version": "current_turn_prompt_contract_v1",
        "priority": "highest",
        "turn_index_scope": "current_turn_only",
        "current_player_action": _short_text(player_action, 800),
        "resolved_action": resolved_action,
        "resolved_result": resolved_result,
        "semantic_action": semantic_action,
        "service_result": service_result,
        "required_focus": required_focus,
        "forbidden_stale_topics": sorted(set(forbidden_stale_topics)),
        "background_only_sections": [
            "recent_events",
            "loaded_npc_profiles",
            "profile_context_summary",
            "advisory_context",
            "old_quest_or_rumor_context",
        ],
        "npc_line_rules": [
            "must_answer_current_action_first",
            "may_use_profile_for_tone_only",
            "must_not_use_memory_as_new_authoritative_fact",
            "must_not_introduce_rewards_or_outcomes_absent_from_turn_contract",
        ],
    }


def build_combined_background_context_packet(
    *,
    player_action: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Quality-preserving compact context for combined background LLM.

    This intentionally keeps the highest-value world and turn facts while
    excluding raw session/debug/history blobs.
    """
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    turn_contract = _safe_dict(turn_contract)
    semantic_action_record = _safe_dict(semantic_action_record)

    current_turn_prompt_contract = build_current_turn_prompt_contract(
        player_action=player_action,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
    )

    return {
        "player_action": _short_text(player_action, 800),
        "current_turn_prompt_contract": current_turn_prompt_contract,
        "scene": _compact_scene_context(simulation_state),
        "present_npcs": _compact_present_npcs(simulation_state, limit=6),
        "player_visible_state": _compact_player_visible_state(simulation_state),
        "recent_events": _compact_recent_events(simulation_state, limit=5),
        "loaded_npc_profiles": _compact_loaded_npc_profiles(runtime_state, limit=6),
        "profile_context_summary": _loaded_profile_context_summary(runtime_state),
        "npc_response_architecture": _build_npc_response_architecture_packet(
            player_action=player_action,
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            turn_contract=turn_contract,
            semantic_action_record=semantic_action_record,
        ),
        "turn_contract": _compact_turn_contract(turn_contract),
        "fast_semantic_action": semantic_action_record,
    }


def prompt_section_metrics(sections: Dict[str, str]) -> Dict[str, Any]:
    by_section: Dict[str, Dict[str, Any]] = {}
    total_chars = 0
    for name, text in sections.items():
        text_value = text if isinstance(text, str) else str(text)
        chars = len(text_value)
        total_chars += chars
        by_section[name] = {
            "chars": chars,
            # Rough heuristic; exact tokenizer is provider/model-dependent.
            "estimated_tokens": round(chars / 4.0, 1),
        }
    return {
        "total_chars": total_chars,
        "estimated_tokens": round(total_chars / 4.0, 1),
        "by_section": by_section,
    }


def _provider_shape(provider: Any) -> Dict[str, Any]:
    if provider is None:
        return {"present": False}
    return {
        "present": True,
        "type": type(provider).__name__,
        "module": getattr(type(provider), "__module__", ""),
        "has_chat_completion": callable(getattr(provider, "chat_completion", None)),
        "has_complete": callable(getattr(provider, "complete", None)),
        "provider_name": getattr(provider, "provider_name", ""),
        "provider_display_name": getattr(provider, "provider_display_name", ""),
    }


def freeze_snapshot(value: Any) -> Any:
    """Create a worker-owned copy so background jobs never touch live state."""
    return deepcopy(value)


def _queue_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    timings = [
        _safe_dict(row.get("queue_timing"))
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("queue_timing"), dict)
    ]
    if not timings:
        return {
            "count": 0,
            "avg_queue_wait_ms": 0.0,
            "max_queue_wait_ms": 0.0,
            "avg_run_ms": 0.0,
            "max_run_ms": 0.0,
            "avg_total_ms": 0.0,
            "max_total_ms": 0.0,
        }

    def avg(key: str) -> float:
        return round(sum(float(item.get(key) or 0.0) for item in timings) / len(timings), 3)

    def maxv(key: str) -> float:
        return round(max(float(item.get(key) or 0.0) for item in timings), 3)

    return {
        "count": len(timings),
        "avg_queue_wait_ms": avg("queue_wait_ms"),
        "max_queue_wait_ms": maxv("queue_wait_ms"),
        "avg_run_ms": avg("run_ms"),
        "max_run_ms": maxv("run_ms"),
        "avg_total_ms": avg("total_ms"),
        "max_total_ms": maxv("total_ms"),
    }


def _deferred_narration_job(
    *,
    queued_at: float,
    provider: Any,
    session_id: str,
    turn_index: int,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    prefer_provider: bool,
) -> Dict[str, Any]:
    started = now_perf()
    wall_started = time.perf_counter()
    before_digest = state_digest(_safe_dict(simulation_state))
    frozen_state = freeze_snapshot(_safe_dict(simulation_state))
    diagnostics: Dict[str, Any] = {
        "prefer_provider": bool(prefer_provider),
        "provider_shape": _provider_shape(provider),
        "turn_contract_keys": sorted(list(_safe_dict(turn_contract).keys())),
        "state_keys": sorted(list(frozen_state.keys()))[:80],
    }
    try:
        build_started = now_perf()
        payload = build_runtime_narration_payload(
            provider=provider,
            player_action=player_action,
            simulation_state=frozen_state,
            turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
            prefer_provider=bool(prefer_provider),
        )
        diagnostics["build_runtime_narration_payload_ms"] = elapsed_ms(build_started)
        diagnostics["payload_source"] = payload.get("source") if isinstance(payload, dict) else ""
        diagnostics["payload_has_narration"] = bool(_safe_str(_safe_dict(payload).get("narration")))
        diagnostics["payload_error"] = _safe_str(_safe_dict(payload).get("error"))
        diagnostics["payload_original_error"] = _safe_str(_safe_dict(payload).get("original_error"))
        after_digest = state_digest(_safe_dict(simulation_state))
        finished = now_perf()
        return {
            "ok": True,
            "kind": "deferred_narration",
            "session_id": session_id,
            "turn_index": turn_index,
            "narration_status": "ready",
            "narration_job_id": f"narration:{session_id}:{turn_index}",
            "narration": _safe_str(payload.get("narration")),
            "npc": _safe_dict(payload.get("npc")),
            "narration_payload": payload,
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "worker_wall_seconds": round(time.perf_counter() - wall_started, 3),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
            "state_digest_before": before_digest,
            "state_digest_after": after_digest,
            "mutated_authoritative_snapshot": before_digest != after_digest,
        }
    except Exception as exc:
        finished = now_perf()
        diagnostics["exception"] = f"{type(exc).__name__}: {exc}"
        return {
            "ok": False,
            "kind": "deferred_narration",
            "session_id": session_id,
            "turn_index": turn_index,
            "narration_status": "error",
            "narration_job_id": f"narration:{session_id}:{turn_index}",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "worker_wall_seconds": round(time.perf_counter() - wall_started, 3),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }


def _provider_text_from_response(response: Any) -> str:
    for attr in ("content", "text", "message"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(response, dict):
        for key in ("content", "text", "message"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _extract_json_object_from_text(text: str) -> Dict[str, Any]:
    """Extract a JSON object from raw provider text.

    Local models often return ```json fences or a short preamble before JSON.
    Advisory extraction is background-only, so be permissive and normalize the
    first valid object we can find.
    """
    import json
    import re

    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty_provider_text")

    cleaned = text.strip()

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start = cleaned.find("{")
    if start < 0:
        raise ValueError("no_json_object_start")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : index + 1])

    raise ValueError("unterminated_json_object")


def _candidate_arrays_present(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in (
        "candidates",
        "semantic_intent_candidates",
        "relationship_delta_candidates",
        "memory_candidates",
        "world_signal_candidates",
        "future_hook_candidates",
    ):
        if isinstance(payload.get(key), list):
            return True
    return False


def _has_expected_combined_provider_keys(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    expected_keys = {
        "presentation_intent",
        "current_action_response",
        "response_focus",
        "intent",
        "narration",
        "action",
        "npc",
        "reward",
        "followup_hooks",
        "semantic_intent_candidates",
        "relationship_delta_candidates",
        "memory_candidates",
        "world_signal_candidates",
        "future_hook_candidates",
        "candidates",
    }
    return any(key in payload for key in expected_keys)


def _normalize_followup_hooks(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _extract_nested_combined_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize common provider shapes into the combined background schema.

    Local models may return:
      - the exact requested shape
      - {"narration_payload": {...}, "advisory": {...}}
      - {"narration": {...}, "candidates": [...]}
      - {"result": {...}}
      - {"data": {...}}

    Combined mode should accept any of these if they contain usable narration
    and/or advisory candidates.
    """
    payload = _safe_dict(payload)
    for wrapper_key in ("result", "data", "payload", "response"):
        nested = _safe_dict(payload.get(wrapper_key))
        if nested:
            payload = nested
            break

    normalized: Dict[str, Any] = dict(payload)

    # Preserve the exact combined schema when the model already returned it.
    # Latest artifact showed LM Studio returned all expected keys directly, but
    # the useful-content check still rejected it. Keep these fields explicit.
    if "narration" in payload and isinstance(payload.get("narration"), str):
        normalized["narration"] = payload.get("narration")
    if "action" in payload and isinstance(payload.get("action"), str):
        normalized["action"] = payload.get("action")
    if "npc" in payload and isinstance(payload.get("npc"), dict):
        normalized["npc"] = payload.get("npc")
    if "reward" in payload and isinstance(payload.get("reward"), str):
        normalized["reward"] = payload.get("reward")
    if "followup_hooks" in payload:
        normalized["followup_hooks"] = _normalize_followup_hooks(payload.get("followup_hooks"))
    provider_intent_candidate, provider_intent_source = _find_presentation_intent_candidate(payload)
    if provider_intent_candidate:
        normalized["presentation_intent"] = _normalize_presentation_intent(provider_intent_candidate)
        normalized["presentation_intent_parse_source"] = provider_intent_source
    response_candidate, response_source = _find_current_action_response_candidate(payload)
    if response_candidate:
        normalized["current_action_response"] = _normalize_current_action_response(response_candidate)
        normalized["current_action_response_parse_source"] = response_source
    if isinstance(payload.get("npc_response_architecture_ack"), dict):
        normalized["npc_response_architecture_ack"] = _safe_dict(payload.get("npc_response_architecture_ack"))

    narration_payload = _safe_dict(
        payload.get("narration_payload")
        or payload.get("structured_narration")
        or payload.get("narration_result")
    )

    narration_value = payload.get("narration")
    if isinstance(narration_value, dict):
        narration_payload = {**narration_value, **narration_payload}
        narration_value = narration_payload.get("narration") or narration_payload.get("text") or ""

    if narration_payload:
        normalized["narration"] = (
            _safe_str(narration_payload.get("narration"))
            or _safe_str(narration_payload.get("text"))
            or _safe_str(narration_value)
        )
        normalized["action"] = (
            _safe_str(narration_payload.get("action"))
            or _safe_str(payload.get("action"))
        )
        normalized["npc"] = _safe_dict(narration_payload.get("npc") or payload.get("npc"))
        normalized["reward"] = _safe_str(narration_payload.get("reward") or payload.get("reward"))
        normalized["followup_hooks"] = (
            _normalize_followup_hooks(narration_payload.get("followup_hooks"))
            or _normalize_followup_hooks(payload.get("followup_hooks"))
        )
        provider_intent_candidate, provider_intent_source = _find_presentation_intent_candidate(
            {**payload, "narration_payload": narration_payload}
        )
        normalized["presentation_intent"] = _normalize_presentation_intent(provider_intent_candidate)
        normalized["presentation_intent_parse_source"] = provider_intent_source
        response_candidate, response_source = _find_current_action_response_candidate(
            {**payload, "narration_payload": narration_payload}
        )
        if response_candidate:
            normalized["current_action_response"] = _normalize_current_action_response(response_candidate)
            normalized["current_action_response_parse_source"] = response_source
        if isinstance(payload.get("npc_response_architecture_ack"), dict):
            normalized["npc_response_architecture_ack"] = _safe_dict(payload.get("npc_response_architecture_ack"))
        elif isinstance(narration_payload.get("npc_response_architecture_ack"), dict):
            normalized["npc_response_architecture_ack"] = _safe_dict(narration_payload.get("npc_response_architecture_ack"))

    advisory_payload = _safe_dict(
        payload.get("advisory")
        or payload.get("advisory_payload")
        or payload.get("deferred_advisory")
        or payload.get("advisory_candidates")
    )
    if advisory_payload:
        for key in (
            "candidates",
            "semantic_intent_candidates",
            "relationship_delta_candidates",
            "memory_candidates",
            "world_signal_candidates",
            "future_hook_candidates",
        ):
            candidate_list = advisory_payload.get(key)
            if isinstance(candidate_list, list):
                normalized[key] = candidate_list

    return normalized


def _combined_payload_has_useful_content(payload: Dict[str, Any]) -> bool:
    payload = _safe_dict(payload)
    return bool(
        _has_expected_combined_provider_keys(payload)
        or
        _safe_str(payload.get("narration"))
        or _safe_str(payload.get("action"))
        or _safe_dict(payload.get("npc"))
        or _candidate_arrays_present(payload)
    )


def _decode_provider_json_string(value: str) -> str:
    if not isinstance(value, str):
        return ""
    try:
        import json

        return _safe_str(json.loads(f'"{value}"')).strip()
    except Exception:
        try:
            return bytes(value, "utf-8").decode("unicode_escape").strip()
        except Exception:
            return value.strip()


def _extract_provider_string_field(text: str, field_name: str, max_chars: int = 2000) -> str:
    import re

    if not isinstance(text, str) or not field_name:
        return ""
    pattern = r'"' + re.escape(field_name) + r'"\s*:\s*"((?:\\.|[^"\\])*)"'
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return ""
    return _decode_provider_json_string(match.group(1))[:max_chars].strip()


def _extract_provider_bool_field(text: str, field_name: str) -> bool | None:
    import re

    if not isinstance(text, str) or not field_name:
        return None
    pattern = r'"' + re.escape(field_name) + r'"\s*:\s*(true|false)'
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _extract_provider_npc_object_from_text(text: str) -> Dict[str, Any]:
    import re

    if not isinstance(text, str):
        return {}
    npc_match = re.search(r'"npc"\s*:\s*\{(?P<body>.*?)\}', text, flags=re.DOTALL)
    if not npc_match:
        return {}
    body = npc_match.group("body")
    speaker = _extract_provider_string_field("{" + body + "}", "speaker", max_chars=120)
    line = _extract_provider_string_field("{" + body + "}", "line", max_chars=600)
    if not speaker and not line:
        return {}
    return {"speaker": speaker, "line": line}


def _repair_truncated_json_object_text(text: str) -> str:
    """Best-effort close for provider JSON that was cut off near the end.

    This is intentionally conservative: it never invents field values.  It only
    closes an open string, drops a trailing dangling key separator, and appends
    the missing object/array delimiters so json.loads gets one more chance.
    """
    if not isinstance(text, str) or not text.strip():
        return ""
    cleaned = text.strip()
    start = cleaned.find("{")
    if start < 0:
        return ""
    candidate = cleaned[start:]

    in_string = False
    escape = False
    stack: List[str] = []
    for char in candidate:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]" and stack and stack[-1] == char:
            stack.pop()

    repaired = candidate.rstrip()
    if in_string:
        repaired += '"'
    repaired = repaired.rstrip()
    while repaired and repaired[-1] in {":", ","}:
        repaired = repaired[:-1].rstrip()
    repaired += "".join(reversed(stack))
    return repaired


def _try_parse_repaired_combined_json(text: str) -> Dict[str, Any]:
    import json

    repaired = _repair_truncated_json_object_text(text)
    if not repaired:
        return {}
    try:
        parsed = json.loads(repaired)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    normalized = _extract_nested_combined_payload(parsed)
    if not (_combined_payload_has_useful_content(normalized) or _has_expected_combined_provider_keys(parsed)):
        return {}
    normalized["ok"] = True
    normalized["partial"] = True
    normalized["json_repair_applied"] = True
    normalized.setdefault("raw_provider_shape_keys", sorted(list(parsed.keys()))[:80])
    return normalized


def _salvage_combined_narration_from_text(text: str) -> Dict[str, Any]:
    """Recover useful combined payload fields from malformed provider JSON.

    Local providers sometimes return a nearly complete object but omit a final
    brace or truncate one candidate array.  Combined background output is
    non-authoritative, so it is safer to salvage complete visible fields
    (narration/action/npc/intent/ack) than to discard the whole provider result
    and count the turn as deterministic fallback.  Incomplete strings are not
    displayed; they are ignored and the deterministic runtime fallback can still
    handle the turn.
    """
    if not isinstance(text, str):
        return {}

    repaired = _try_parse_repaired_combined_json(text)
    if repaired:
        return repaired

    narration = _extract_provider_string_field(text, "narration", max_chars=2200)
    action = _extract_provider_string_field(text, "action", max_chars=700)
    reward = _extract_provider_string_field(text, "reward", max_chars=300)
    npc = _extract_provider_npc_object_from_text(text)

    category = _extract_provider_string_field(text, "primary_category", max_chars=80)
    intent_reason = _extract_provider_string_field(text, "reason", max_chars=240)
    response_reason = _extract_provider_string_field(text, "reason", max_chars=240)

    if not (narration or action or _safe_str(npc.get("line"))):
        return {}

    payload: Dict[str, Any] = {
        "ok": True,
        "partial": True,
        "regex_salvage_applied": True,
        "narration": narration or "The scene settles after the action.",
        "action": action or "The action has been resolved.",
        "npc": npc or {"speaker": "", "line": ""},
        "reward": reward,
        "followup_hooks": [],
    }
    if category:
        payload["presentation_intent"] = _normalize_presentation_intent(
            {
                "primary_category": category,
                "confidence": 0.45,
                "reason": intent_reason or "salvaged_from_partial_provider_json",
            }
        )
        payload["presentation_intent_parse_source"] = "partial_json_regex.primary_category"

    addresses = _extract_provider_bool_field(text, "npc_line_addresses_current_action")
    if addresses is None:
        addresses = _extract_provider_bool_field(text, "addresses_current_action")
    if addresses is not None:
        payload["current_action_response"] = _normalize_current_action_response(
            {
                "required_focus": [],
                "npc_line_addresses_current_action": addresses,
                "reason": response_reason or "salvaged_from_partial_provider_json",
            }
        )
        payload["current_action_response_parse_source"] = "partial_json_regex.current_action_response"

    used_contract = _extract_provider_bool_field(text, "used_current_turn_prompt_contract")
    answered_first = _extract_provider_bool_field(text, "answered_current_action_first")
    ignored_stale = _extract_provider_bool_field(text, "ignored_forbidden_stale_topics")
    if used_contract is not None or answered_first is not None or ignored_stale is not None:
        payload["prompt_contract_ack"] = {
            "used_current_turn_prompt_contract": bool(used_contract),
            "answered_current_action_first": bool(answered_first),
            "ignored_forbidden_stale_topics": bool(ignored_stale),
            "reason": "salvaged_from_partial_provider_json",
        }
    return payload


def _provider_messages(messages: List[Dict[str, str]]) -> List[Any]:
    if ChatMessage is None:
        return messages
    converted: List[Any] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        try:
            converted.append(ChatMessage(role=role, content=content))
        except TypeError:
            converted.append(ChatMessage(role, content))
    return converted


def _build_provider_advisory_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    if provider is None or not callable(getattr(provider, "chat_completion", None)):
        return {"ok": False, "error": "provider_missing_or_unsupported"}

    messages = [
        {
            "role": "system",
            "content": (
                "You are an RPG advisory extractor. Return JSON only. "
                "You may suggest candidates, but you must not assert authoritative outcomes. "
                "Do not grant items, currency, quest completion, damage, travel, or rewards. "
                "Return one JSON object and no markdown fences, no prose, no commentary."
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract advisory candidates from this turn.\n\n"
                f"PLAYER_INPUT:\n{player_action}\n\n"
                f"TURN_CONTRACT_JSON:\n{stable_json_for_prompt(turn_contract)}\n\n"
                f"FAST_SEMANTIC_JSON:\n{stable_json_for_prompt(semantic_action_record)}\n\n"
                "Return JSON with optional arrays: semantic_intent_candidates, "
                "relationship_delta_candidates, memory_candidates, world_signal_candidates, "
                "future_hook_candidates.\n\n"
                "Example shape:\n"
                "{\n"
                '  "semantic_intent_candidates": [\n'
                '    {"intent": "inspect", "summary": "The player studies the room.", "confidence": 0.7}\n'
                "  ],\n"
                '  "future_hook_candidates": [\n'
                '    {"summary": "An NPC may respond to the player noticing suspicious details."}\n'
                "  ]\n"
                "}"
            ),
        },
    ]

    provider_messages = _provider_messages(messages)
    try:
        response = provider.chat_completion(messages=provider_messages, stream=False)
    except TypeError:
        response = provider.chat_completion(provider_messages, stream=False)

    content = _provider_text_from_response(response)
    if not content:
        return {"ok": False, "error": "provider_empty_advisory_response"}

    try:
        parsed = _extract_json_object_from_text(content)
        if isinstance(parsed, dict):
            parsed["ok"] = True
            return parsed
        return {"ok": False, "error": "provider_advisory_json_not_object", "raw": content[:1000]}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"provider_advisory_json_parse_error:{type(exc).__name__}: {exc}",
            "raw": content[:1000],
        }


def _build_combined_background_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    turn_index: int,
) -> Dict[str, Any]:
    """One provider call that returns both narration and advisory candidates."""
    if provider is None or not callable(getattr(provider, "chat_completion", None)):
        return {"ok": False, "error": "provider_missing_or_unsupported"}

    context_packet = build_combined_background_context_packet(
        player_action=player_action,
        simulation_state=simulation_state,
        runtime_state=runtime_state or {},
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
    )
    current_turn_prompt_contract = _safe_dict(context_packet.get("current_turn_prompt_contract"))
    current_turn_contract_json = compact_json_for_prompt(
        current_turn_prompt_contract,
        max_chars=4500,
    )
    context_json = compact_json_for_prompt(context_packet, max_chars=7000)
    schema_text = (
        "{"
        '"presentation_intent":{"primary_category":"dialogue|evidence|investigation|travel|combat|service|economy|mixed|general","secondary_categories":[],"confidence":0.0,"reason":"short diagnostic reason"},'
        '"current_action_response":{"required_focus":[],"npc_line_addresses_current_action":true,"reason":"how the NPC line answers the current player action first"},'
        '"prompt_contract_ack":{"used_current_turn_prompt_contract":true,"answered_current_action_first":true,"ignored_forbidden_stale_topics":true,"reason":"short diagnostic reason"},'
        '"npc_response_architecture_ack":{"used_current_action_first":true,"used_file_backed_persona":false,"used_file_backed_memory":false,"reason":"short diagnostic reason"},'
        '"narration":"2-5 sentences describing the resolved scene without repeating player input.",'
        '"action":"Short result of the player action.",'
        '"npc":{"speaker":"","line":""},'
        '"reward":"",'
        '"followup_hooks":[],'
        '"semantic_intent_candidates":[{"intent":"","summary":"","confidence":0.0}],'
        '"relationship_delta_candidates":[{"target":"","axis":"trust","delta":0,"summary":""}],'
        '"memory_candidates":[{"owner":"","summary":"","importance":0.0}],'
        '"world_signal_candidates":[{"kind":"","summary":""}],'
        '"future_hook_candidates":[{"kind":"","summary":""}]'
        "}"
    )
    prompt_metrics = prompt_section_metrics(
        {
            "system_contract": "combined_background_worker_v1",
            "current_turn_prompt_contract": current_turn_contract_json,
            "context_packet": context_json,
            "output_schema": schema_text,
        }
    )
    profile_context_summary = _loaded_profile_context_summary(runtime_state or {})

    messages = [
        {
            "role": "system",
            "content": (
                "You are an RPG background enrichment worker. Return JSON only. "
                "The CURRENT_TURN_PROMPT_CONTRACT_JSON is the highest-priority input. Narration and NPC dialogue must answer that current action first before older quest, memory, or investigation context. "
                "You must obey required_focus and forbidden_stale_topics from that contract. "
                "You must set prompt_contract_ack with whether the contract was followed. "
                "You must not assert authoritative outcomes that are not in the turn contract. "
                "Do not grant items, currency, quest completion, damage, travel, or rewards. "
                "You MUST set presentation_intent.primary_category to the most specific semantic intent. "
                "Do not use general unless no specific category applies. "
                "Category labels are presentation metadata only; they do not create facts. "
                "Use combat only when compact context shows combat actually started, advanced, or resolved. "
                "Use travel only when the turn is primarily movement or location change; asking about a route is dialogue. "
                "Use service/economy only when the resolved turn actually rents, rests, buys, sells, or pays. "
                "Words like ambush, bandit, scout, road, room, supplies, or coin are not enough by themselves to classify the turn as combat, travel, service, or economy. "
                "For reporting evidence, questioning NPCs, warning NPCs, or asking about routes, prefer dialogue/evidence/investigation over combat/travel. "
                "Return one JSON object and no markdown fences, no prose, no commentary. "
                "Maintain rich 2-5 sentence narration quality. Use only the provided compact context. "
                "Return compact candidate objects. Prefer at most 1 high-quality candidate per category. "
                "Do not include long explanations inside candidates. "
                "Loaded NPC profiles are characterization context only. "
                "You may use loaded_npc_profiles to shape NPC tone, dialogue, memory continuity, and future-hook suggestions. "
                "You must follow npc_response_architecture.required_focus before any older quest, rumor, memory, or investigation topic. "
                "If npc_response_architecture.target_npc.profile_available is true, use it only for tone/persona and continuity. "
                "You must not treat profile memories or hooks as newly resolved actions. "
                "You must not invent profile memories that are absent from loaded_npc_profiles, npc_response_architecture, or current turn facts. "
                "If an NPC has arc_stage, axes, memories, or future_hooks, reflect them subtly in the NPC line or candidate summaries when relevant. "
                "For economy/service turns, the NPC line must acknowledge the transaction/request (item, quantity, price, sale, lodging, rest, or refusal) before optional story flavor. "
                "Do not answer an older investigation topic unless the current player action asks about that topic. "
                "Set npc_response_architecture_ack to explain whether current-action-first and file-backed persona/memory were used."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create background narration and advisory candidates for this resolved RPG turn.\n\n"
                "CURRENT_TURN_PROMPT_CONTRACT_JSON (highest priority; obey before all background context):\n"
                f"{current_turn_contract_json}\n\n"
                "COMPACT_CONTEXT_JSON (background/tone/continuity only unless consistent with current turn):\n"
                f"{context_json}\n\n"
                "Return exactly this JSON shape:\n"
                f"{schema_text}\n\n"
                "Candidate limits: max 1 semantic_intent, max 1 relationship_delta, "
                "max 1 memory, max 1 world_signal, max 1 future_hook. "
                "Each candidate summary must be under 160 characters. "
                "Narration remains high quality and should not be shortened below 2 sentences.\n\n"
                "presentation_intent rules:\n"
                "- Choose exactly one primary_category from the schema. Never omit presentation_intent.\n"
                "- Prefer the most specific true intent over general or mixed.\n"
                "- Use mixed only for genuinely multi-objective turns where no single category dominates.\n"
                "- 'I report the ambush evidence to Bran' => evidence, secondary dialogue/investigation, not combat.\n"
                "- 'I scout the quarry road for ambush signs' => investigation, secondary evidence, not combat.\n"
                "- 'I ask Bran if the east road leads to a bridge' => dialogue, secondary travel, not travel.\n"
                "- 'I ask Bran who left through the side door' => dialogue, secondary investigation.\n"
                "- 'I rent a room from Bran' => service.\n\n"
                "Current-turn prompt contract rule: obey CURRENT_TURN_PROMPT_CONTRACT_JSON.required_focus and avoid forbidden_stale_topics. "
                "Recent events, profile memory, and old advisory context are background/tone-only unless the current player action explicitly asks about them. "
                "NPC response architecture rule: obey COMPACT_CONTEXT_JSON.npc_response_architecture. "
                "The NPC line must satisfy required_focus for the current action before using memories. "
                "Profile grounding rule: when loaded_npc_profiles is non-empty, use it only for NPC continuity. "
                "For example, a trusting NPC may sound warmer, a guarded NPC may be cautious, "
                "and a remembered prior topic may be acknowledged only when it does not displace the current action. "
                "Do not create authoritative outcomes from profile context."
            ),
        },
    ]

    provider_messages = _provider_messages(messages)
    started_ms = int(time.perf_counter() * 1000)
    print(
        "[AUTOPLAY-PROBE] "
        f"ts={datetime.now().isoformat(timespec='seconds')} "
        f"event=combined_background_provider_call.start "
        f"turn_index={turn_index} "
        f"provider_type={type(provider).__name__} "
        f"message_count={len(provider_messages)} "
        f"prompt_chars={sum(len(getattr(message, 'content', '') or '') for message in provider_messages)}",
        flush=True,
    )
    try:
        response = provider.chat_completion(messages=provider_messages, stream=False)
    except TypeError:
        response = provider.chat_completion(provider_messages, stream=False)
    print(
        "[AUTOPLAY-PROBE] "
        f"ts={datetime.now().isoformat(timespec='seconds')} "
        f"event=combined_background_provider_call.end "
        f"turn_index={turn_index} "
        f"elapsed_ms={int(time.perf_counter() * 1000) - started_ms}",
        flush=True,
    )

    content = _provider_text_from_response(response)
    if not content:
        return {"ok": False, "error": "provider_empty_combined_response"}

    try:
        parsed = _extract_json_object_from_text(content)
        if isinstance(parsed, dict):
            normalized = _extract_nested_combined_payload(parsed)
            if (
                _combined_payload_has_useful_content(normalized)
                or _has_expected_combined_provider_keys(parsed)
            ):
                normalized["ok"] = True
                provider_intent_candidate, provider_intent_source = _find_presentation_intent_candidate(
                    {**parsed, **normalized}
                )
                normalized["presentation_intent"] = _normalize_presentation_intent(provider_intent_candidate)
                normalized["presentation_intent_parse_source"] = provider_intent_source
                normalized.setdefault("prompt_contract_ack", _safe_dict(parsed.get("prompt_contract_ack")))
                normalized.setdefault("current_turn_prompt_contract", current_turn_prompt_contract)
                normalized.setdefault("prompt_debug", {
                    "format_version": "combined_background_prompt_debug_v1",
                    "turn_index": turn_index,
                    "current_turn_prompt_contract": current_turn_prompt_contract,
                    "current_turn_prompt_contract_json": current_turn_contract_json,
                    "compact_context_keys": sorted(list(context_packet.keys())),
                    "prompt_metrics": prompt_metrics,
                    "system_contract": "combined_background_worker_v1",
                })
                normalized.setdefault("raw_provider_shape_keys", sorted(list(parsed.keys()))[:80])
                normalized.setdefault("prompt_metrics", prompt_metrics)
                normalized.setdefault("context_packet_keys", sorted(list(context_packet.keys())))
                normalized.setdefault("profile_context_summary", profile_context_summary)
                normalized.setdefault("npc_response_architecture", _safe_dict(context_packet.get("npc_response_architecture")))
                return normalized
            return {
                "ok": False,
                "error": "provider_combined_json_missing_useful_content",
                "raw": content[:1000],
                "parsed_keys": sorted(list(parsed.keys()))[:80],
                "prompt_metrics": prompt_metrics,
                "context_packet_keys": sorted(list(context_packet.keys())),
                "profile_context_summary": profile_context_summary,
                "current_turn_prompt_contract": current_turn_prompt_contract,
                "prompt_debug": {
                    "format_version": "combined_background_prompt_debug_v1",
                    "turn_index": turn_index,
                    "current_turn_prompt_contract": current_turn_prompt_contract,
                    "current_turn_prompt_contract_json": current_turn_contract_json,
                    "compact_context_keys": sorted(list(context_packet.keys())),
                    "prompt_metrics": prompt_metrics,
                    "system_contract": "combined_background_worker_v1",
                },
            }
        return {"ok": False, "error": "provider_combined_json_not_object", "raw": content[:4000]}
    except Exception as exc:
        salvaged = _salvage_combined_narration_from_text(content)
        if salvaged:
            provider_intent_candidate, provider_intent_source = _find_presentation_intent_candidate(salvaged)
            if provider_intent_candidate:
                salvaged["presentation_intent"] = _normalize_presentation_intent(provider_intent_candidate)
                salvaged.setdefault("presentation_intent_parse_source", provider_intent_source)
            response_candidate, response_source = _find_current_action_response_candidate(salvaged)
            if response_candidate:
                salvaged["current_action_response"] = _normalize_current_action_response(response_candidate)
                salvaged.setdefault("current_action_response_parse_source", response_source)
            salvaged.setdefault("prompt_contract_ack", {
                "used_current_turn_prompt_contract": True,
                "answered_current_action_first": bool(
                    _safe_dict(salvaged.get("current_action_response")).get("npc_line_addresses_current_action")
                    or _safe_str(_safe_dict(salvaged.get("npc")).get("line"))
                ),
                "ignored_forbidden_stale_topics": True,
                "reason": "provider_json_salvaged_after_parse_error",
            })
            salvaged.setdefault("current_turn_prompt_contract", current_turn_prompt_contract)
            salvaged.setdefault("prompt_debug", {
                "format_version": "combined_background_prompt_debug_v1",
                "turn_index": turn_index,
                "current_turn_prompt_contract": current_turn_prompt_contract,
                "current_turn_prompt_contract_json": current_turn_contract_json,
                "compact_context_keys": sorted(list(context_packet.keys())),
                "prompt_metrics": prompt_metrics,
                "system_contract": "combined_background_worker_v1",
                "provider_json_salvage_applied": True,
            })
            salvaged["raw"] = content[:4000]
            salvaged["parse_error"] = f"{type(exc).__name__}: {exc}"
            salvaged["provider_payload_repaired"] = True
            salvaged["prompt_metrics"] = prompt_metrics
            salvaged["context_packet_keys"] = sorted(list(context_packet.keys()))
            salvaged["profile_context_summary"] = profile_context_summary
            return salvaged
        return {
            "ok": False,
            "error": f"provider_combined_json_parse_error:{type(exc).__name__}: {exc}",
            "raw": content[:4000],
            "prompt_metrics": prompt_metrics,
            "context_packet_keys": sorted(list(context_packet.keys())),
            "profile_context_summary": profile_context_summary,
        }


def _deferred_advisory_job(
    *,
    queued_at: float,
    provider: Any,
    session_id: str,
    turn_index: int,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    prefer_provider: bool,
) -> Dict[str, Any]:
    started = now_perf()
    diagnostics: Dict[str, Any] = {
        "prefer_provider": bool(prefer_provider),
        "provider_shape": _provider_shape(provider),
        "turn_contract_keys": sorted(list(_safe_dict(turn_contract).keys())),
        "semantic_keys": sorted(list(_safe_dict(semantic_action_record).keys())),
    }
    try:
        payload: Dict[str, Any] = {}
        source = "deterministic_deferred_advisory"
        if prefer_provider and provider is not None:
            provider_started = now_perf()
            payload = _build_provider_advisory_payload(
                provider=provider,
                player_action=player_action,
                simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
                turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
                semantic_action_record=freeze_snapshot(_safe_dict(semantic_action_record)),
            )
            diagnostics["provider_advisory_ms"] = elapsed_ms(provider_started)
            diagnostics["provider_payload_error"] = _safe_str(payload.get("error"))
            if payload.get("ok"):
                source = "provider_deferred_advisory"
            else:
                source = "deterministic_deferred_advisory_fallback"

        if source == "provider_deferred_advisory":
            candidates = normalize_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                payload=_safe_dict(payload),
            )
        else:
            candidates = build_deterministic_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                semantic_action_record=_safe_dict(semantic_action_record),
            )

        finished = now_perf()
        return {
            "ok": True,
            "kind": "deferred_advisory",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": source,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "summary": advisory_candidate_summary(candidates),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }
    except Exception as exc:
        finished = now_perf()
        return {
            "ok": False,
            "kind": "deferred_advisory",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": "deferred_advisory_error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }


def _combined_background_llm_job(
    *,
    queued_at: float,
    provider: Any,
    session_id: str,
    turn_index: int,
    player_action: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    prefer_provider: bool,
) -> Dict[str, Any]:
    print(f"Starting combined background LLM job for turn {turn_index}")
    started = now_perf()
    diagnostics: Dict[str, Any] = {
        "prefer_provider": bool(prefer_provider),
        "provider_shape": _provider_shape(provider),
        "turn_contract_keys": sorted(list(_safe_dict(turn_contract).keys())),
        "semantic_keys": sorted(list(_safe_dict(semantic_action_record).keys())),
    }
    try:
        source = "combined_background_llm_fallback"
        provider_payload: Dict[str, Any] = {}
        if prefer_provider and provider is not None:
            provider_started = now_perf()
            provider_payload = _build_combined_background_payload(
                provider=provider,
                player_action=player_action,
                simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
                runtime_state=freeze_snapshot(_safe_dict(runtime_state)),
                turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
                semantic_action_record=freeze_snapshot(_safe_dict(semantic_action_record)),
                turn_index=turn_index,
            )
            diagnostics["provider_combined_ms"] = elapsed_ms(provider_started)
            diagnostics["provider_payload_error"] = _safe_str(provider_payload.get("error"))
            diagnostics["provider_raw_excerpt"] = _safe_str(provider_payload.get("raw"))[:4000]
            diagnostics["provider_payload_keys"] = (
                sorted(list(provider_payload.keys()))[:80]
                if isinstance(provider_payload, dict)
                else []
            )
            diagnostics["prompt_metrics"] = _safe_dict(provider_payload.get("prompt_metrics"))
            diagnostics["prompt_debug"] = _safe_dict(provider_payload.get("prompt_debug"))
            diagnostics["current_turn_prompt_contract"] = _safe_dict(
                provider_payload.get("current_turn_prompt_contract")
            )
            diagnostics["prompt_contract_ack"] = _safe_dict(provider_payload.get("prompt_contract_ack"))
            diagnostics["context_packet_keys"] = (
                provider_payload.get("context_packet_keys")
                if isinstance(provider_payload.get("context_packet_keys"), list)
                else []
            )
            diagnostics["profile_context_summary"] = _safe_dict(
                provider_payload.get("profile_context_summary")
            )
            diagnostics["provider_parsed_keys"] = (
                provider_payload.get("parsed_keys")
                if isinstance(provider_payload.get("parsed_keys"), list)
                else []
            )
            diagnostics["provider_raw_shape_keys"] = (
                provider_payload.get("raw_provider_shape_keys")
                if isinstance(provider_payload.get("raw_provider_shape_keys"), list)
                else []
            )
            if provider_payload.get("ok"):
                source = "provider_combined_background_llm"
            else:
                source = "combined_background_llm_fallback"
        else:
            diagnostics["provider_payload_error"] = "provider_missing_or_not_preferred"
            source = "combined_background_llm_fallback"

        if source == "provider_combined_background_llm":
            presentation_intent = _normalize_presentation_intent(provider_payload.get("presentation_intent"))
            current_action_response = _normalize_current_action_response(
                provider_payload.get("current_action_response")
            )
            diagnostics["provider_intent_parse_source"] = _safe_str(
                provider_payload.get("presentation_intent_parse_source")
            ) or "missing"
            diagnostics["current_action_response_parse_source"] = _safe_str(
                provider_payload.get("current_action_response_parse_source")
            ) or "missing"
            diagnostics["provider_intent_missing"] = presentation_intent.get("primary_category") == "general" and not presentation_intent.get("secondary_categories")
            diagnostics["provider_intent_general"] = presentation_intent.get("primary_category") == "general"
            narration_payload = {
                "format_version": "rpg_narration_v2",
                "source": "provider_runtime_narration",
                "presentation_intent": presentation_intent,
                "current_action_response": current_action_response,
                "prompt_contract_ack": _safe_dict(provider_payload.get("prompt_contract_ack")),
                "narration": _safe_str(provider_payload.get("narration")) or "The scene settles after the action.",
                "action": _safe_str(provider_payload.get("action")) or "The action has been resolved.",
                "npc": _safe_dict(provider_payload.get("npc")),
                "reward": _safe_str(provider_payload.get("reward")),
                "followup_hooks": _normalize_followup_hooks(provider_payload.get("followup_hooks")),
            }
            candidates = normalize_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                payload=_safe_dict(provider_payload),
            )
            if not candidates:
                diagnostics["advisory_candidate_fallback_reason"] = "provider_combined_returned_no_candidates"
                candidates = build_deterministic_advisory_candidates(
                    session_id=session_id,
                    turn_index=turn_index,
                    player_input=player_action,
                    turn_contract=_safe_dict(turn_contract),
                    semantic_action_record=_safe_dict(semantic_action_record),
                )
        else:
            # Fallback keeps the same output shape and preserves correctness.
            diagnostics["fallback_reason"] = _safe_str(
                diagnostics.get("provider_payload_error")
            ) or "provider_combined_unavailable"
            narration_payload = build_runtime_narration_payload(
                provider=None,
                player_action=player_action,
                simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
                turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
                prefer_provider=False,
            )
            narration_payload["presentation_intent"] = {
                "format_version": "presentation_intent_v1",
                "primary_category": "general",
                "secondary_categories": [],
                "confidence": 0.0,
                "reason": "deterministic_fallback_no_provider_intent",
            }
            fallback_contract = build_current_turn_prompt_contract(
                player_action=player_action,
                turn_contract=_safe_dict(turn_contract),
                semantic_action_record=_safe_dict(semantic_action_record),
            )
            diagnostics["current_turn_prompt_contract"] = fallback_contract
            narration_payload["current_action_response"] = {
                "format_version": "current_action_response_v1",
                "required_focus": _safe_list(fallback_contract.get("required_focus")),
                "npc_line_addresses_current_action": False,
                "reason": "deterministic_fallback_no_provider_response_focus",
            }
            narration_payload["prompt_contract_ack"] = {
                "used_current_turn_prompt_contract": False,
                "answered_current_action_first": False,
                "ignored_forbidden_stale_topics": False,
                "reason": "deterministic_fallback_no_provider_response",
            }
            candidates = build_deterministic_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                semantic_action_record=_safe_dict(semantic_action_record),
            )

        finished = now_perf()
        print(f"Finished combined background LLM job for turn {turn_index}")
        return {
            "ok": True,
            "kind": "combined_background_llm",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": source,
            "narration": _safe_str(narration_payload.get("narration")),
            "npc": _safe_dict(narration_payload.get("npc")),
            "narration_payload": narration_payload,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "advisory_summary": advisory_candidate_summary(candidates),
            "diagnostics": diagnostics,
            "prompt_metrics": _safe_dict(diagnostics.get("prompt_metrics")),
            "presentation_intent": _safe_dict(narration_payload.get("presentation_intent")),
            "current_action_response": _safe_dict(narration_payload.get("current_action_response")),
            "prompt_contract_ack": _safe_dict(narration_payload.get("prompt_contract_ack") or diagnostics.get("prompt_contract_ack")),
            "current_turn_prompt_contract": _safe_dict(diagnostics.get("current_turn_prompt_contract")),
            "prompt_debug": _safe_dict(diagnostics.get("prompt_debug")),
            "llm_fallback_diagnostics": {
                "format_version": "llm_fallback_diagnostics_v1",
                "source": source,
                "fallback_source": "llm_valid" if source == "provider_combined_background_llm" else "deterministic_fallback",
                "reason": _safe_str(diagnostics.get("fallback_reason") or diagnostics.get("provider_payload_error") or "llm_valid"),
                "valid_known_reason": bool(
                    source == "provider_combined_background_llm"
                    or _safe_str(diagnostics.get("fallback_reason") or diagnostics.get("provider_payload_error"))
                    in {"provider_missing_or_not_preferred", "provider_missing_or_unsupported", "provider_empty_combined_response", "provider_combined_unavailable"}
                ),
            },
            "profile_context_summary": _safe_dict(diagnostics.get("profile_context_summary")),
            "worker_ms": elapsed_ms(started),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }
    except Exception as exc:
        finished = now_perf()
        print(f"Error in combined background LLM job for turn {turn_index}: {exc}")
        diagnostics["exception"] = f"{type(exc).__name__}: {exc}"
        return {
            "ok": False,
            "kind": "combined_background_llm",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": "combined_background_llm_error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "queue_timing": _queue_timing(
                queued_at=queued_at,
                started_at=started,
                finished_at=finished,
            ),
        }


def _checkpoint_job(
    *,
    session_id: str,
    turn_index: int,
    checkpoint_dir: Any,
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    started = now_perf()
    try:
        result = validate_save_load_checkpoint(
            session_id=session_id,
            turn_index=turn_index,
            checkpoint_dir=checkpoint_dir,
            simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
        )
        result["kind"] = "checkpoint"
        result["turn_index"] = turn_index
        result["worker_ms"] = elapsed_ms(started)
        return result
    except Exception as exc:
        return {
            "ok": False,
            "kind": "checkpoint",
            "turn_index": turn_index,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "worker_ms": elapsed_ms(started),
        }


class AutoplayBackgroundPipeline:
    """Thread pool for non-authoritative autoplay jobs.

    The simulation turn still runs synchronously. Jobs submitted here must only
    receive frozen snapshots and may only return presentation, diagnostic,
    checkpoint, or report artifacts.
    """

    def __init__(self, *, background_workers: int = 4, provider_workers: int = 1) -> None:
        self.background_workers = max(1, int(background_workers or 1))
        self.provider_workers = max(1, int(provider_workers or 1))
        self._background_executor = ThreadPoolExecutor(
            max_workers=self.background_workers,
            thread_name_prefix="rpg-autoplay-bg",
        )
        self._provider_executor = ThreadPoolExecutor(
            max_workers=self.provider_workers,
            thread_name_prefix="rpg-autoplay-provider",
        )
        self._futures: List[Future] = []
        self._future_job_ids: Dict[Future, str] = {}
        self._job_futures: Dict[str, Future] = {}
        self._completed_results: Dict[str, Dict[str, Any]] = {}

    def _register_future(self, job_id: str, future: Future) -> str:
        self._futures.append(future)
        self._future_job_ids[future] = job_id
        self._job_futures[job_id] = future
        return job_id

    def _finalize_future_result(self, future: Future) -> Dict[str, Any]:
        job_id = self._future_job_ids.get(future, "")
        try:
            value = future.result()
            result = (
                value if isinstance(value, dict)
                else {"ok": False, "kind": "unknown", "error": "worker_returned_non_dict"}
            )
        except Exception as exc:
            result = {
                "ok": False,
                "kind": "unknown",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        if job_id:
            result.setdefault("job_id", job_id)
            self._completed_results[job_id] = result
            self._job_futures.pop(job_id, None)
        self._future_job_ids.pop(future, None)
        try:
            self._futures.remove(future)
        except ValueError:
            pass
        return result

    def _finalize_unfinished_future(
        self,
        future: Future,
        *,
        reason: str = "final_drain_timeout",
        cancel: bool = True,
    ) -> Dict[str, Any]:
        job_id = self._future_job_ids.get(future, "")
        cancelled = False
        if cancel:
            try:
                cancelled = bool(future.cancel())
            except Exception:
                cancelled = False
        result = {
            "ok": False,
            "kind": "background_timeout",
            "job_id": job_id,
            "error": reason,
            "cancelled": cancelled,
            "done": bool(future.done()),
        }
        if job_id:
            self._completed_results[job_id] = result
            self._job_futures.pop(job_id, None)
        self._future_job_ids.pop(future, None)
        try:
            self._futures.remove(future)
        except ValueError:
            pass
        return result

    def get_completed_result(self, job_id: str, timeout: float = 0.0) -> Dict[str, Any]:
        """Return a completed result for job_id without waiting by default."""
        if not job_id:
            return {}
        cached = self._completed_results.get(job_id)
        if isinstance(cached, dict) and cached:
            return cached
        future = self._job_futures.get(job_id)
        if future is None:
            return {}
        if timeout and timeout > 0:
            try:
                value = future.result(timeout=timeout)
                result = (
                    value if isinstance(value, dict)
                    else {"ok": False, "kind": "unknown", "error": "worker_returned_non_dict"}
                )
                result.setdefault("job_id", job_id)
                self._completed_results[job_id] = result
                self._job_futures.pop(job_id, None)
                self._future_job_ids.pop(future, None)
                try:
                    self._futures.remove(future)
                except ValueError:
                    pass
                return result
            except TimeoutError:
                return {}
            except Exception as exc:
                result = {
                    "ok": False,
                    "kind": "unknown",
                    "job_id": job_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
                self._completed_results[job_id] = result
                self._job_futures.pop(job_id, None)
                self._future_job_ids.pop(future, None)
                try:
                    self._futures.remove(future)
                except ValueError:
                    pass
                return result
        if not future.done():
            return {}
        return self._finalize_future_result(future)

    def drain_completed(self) -> List[Dict[str, Any]]:
        """Drain all currently completed futures without blocking."""
        completed: List[Dict[str, Any]] = []
        for future in list(self._futures):
            if future.done():
                completed.append(self._finalize_future_result(future))
        return completed

    def pending_job_count(self) -> int:
        return len(list(self._futures))

    def pending_job_ids(self) -> List[str]:
        return [
            self._future_job_ids.get(future, "")
            for future in list(self._futures)
            if self._future_job_ids.get(future, "")
        ]

    def executor_thread_diagnostics(self) -> Dict[str, Any]:
        provider_threads = [
            {
                "name": getattr(thread, "name", ""),
                "alive": bool(thread.is_alive()),
                "daemon": bool(thread.daemon),
            }
            for thread in list(getattr(self._provider_executor, "_threads", []) or [])
        ]
        background_threads = [
            {
                "name": getattr(thread, "name", ""),
                "alive": bool(thread.is_alive()),
                "daemon": bool(thread.daemon),
            }
            for thread in list(getattr(self._background_executor, "_threads", []) or [])
        ]
        return {
            "pending_job_count": self.pending_job_count(),
            "pending_job_ids": self.pending_job_ids()[:50],
            "provider_threads": provider_threads,
            "background_threads": background_threads,
            "alive_provider_thread_count": sum(1 for row in provider_threads if row.get("alive")),
            "alive_background_thread_count": sum(1 for row in background_threads if row.get("alive")),
        }

    def submit_deferred_narration(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        turn_contract: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"narration:{session_id}:{turn_index}"
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _deferred_narration_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            prefer_provider=prefer_provider,
        )
        return self._register_future(job_id, future)

    def submit_checkpoint(
        self,
        *,
        session_id: str,
        turn_index: int,
        checkpoint_dir: Any,
        simulation_state: Dict[str, Any],
    ) -> str:
        job_id = f"checkpoint:{session_id}:{turn_index}"
        future = self._background_executor.submit(
            _checkpoint_job,
            session_id=session_id,
            turn_index=turn_index,
            checkpoint_dir=checkpoint_dir,
            simulation_state=freeze_snapshot(simulation_state),
        )
        return self._register_future(job_id, future)

    def submit_deferred_advisory(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        turn_contract: Dict[str, Any],
        semantic_action_record: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"advisory:{session_id}:{turn_index}"
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _deferred_advisory_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            semantic_action_record=freeze_snapshot(semantic_action_record),
            prefer_provider=prefer_provider,
        )
        return self._register_future(job_id, future)

    def submit_combined_background_llm(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        runtime_state: Dict[str, Any] | None = None,
        turn_contract: Dict[str, Any],
        semantic_action_record: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"combined_background_llm:{session_id}:{turn_index}"
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _combined_background_llm_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            runtime_state=freeze_snapshot(runtime_state or {}),
            turn_contract=freeze_snapshot(turn_contract),
            semantic_action_record=freeze_snapshot(semantic_action_record),
            prefer_provider=prefer_provider,
        )
        self._register_future(job_id, future)
        print(f"Submitted combined background LLM job {job_id}")
        return job_id

    def drain(
        self,
        *,
        timeout_seconds: float | None = None,
        cancel_unfinished: bool = False,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        futures = list(self._futures)
        if not futures:
            return results
        try:
            iterator = as_completed(futures, timeout=timeout_seconds)
            for future in iterator:
                results.append(self._finalize_future_result(future))
        except FuturesTimeoutError:
            # Attach whatever completed just before timeout; mark the rest.
            pass

        for future in list(self._futures):
            if future.done():
                results.append(self._finalize_future_result(future))
            elif cancel_unfinished:
                results.append(
                    self._finalize_unfinished_future(
                        future,
                        reason="final_drain_timeout",
                        cancel=True,
                    )
                )
        return results

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        try:
            self._provider_executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        except TypeError:
            self._provider_executor.shutdown(wait=wait)
        try:
            self._background_executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        except TypeError:
            self._background_executor.shutdown(wait=wait)


def attach_background_results_to_transcript(
    transcript: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    *,
    timing_tracker: Dict[str, Any] = None,
    attach_turn: int = None,
    session_id: str = "",
) -> Dict[str, Any]:
    by_turn = {
        int(row.get("turn_index") or 0): row
        for row in transcript
        if isinstance(row, dict)
    }
    summary = {
        "total_jobs": len(results),
        "ok_jobs": 0,
        "failed_jobs": 0,
        "narration_jobs": 0,
        "checkpoint_jobs": 0,
        "advisory_jobs": 0,
        "combined_background_llm_jobs": 0,
        "advisory_candidates_ingested": 0,
        "background_job_seconds": 0.0,
        "deferred_narration_sources": {},
        "deferred_narration_provider_present": 0,
        "deferred_narration_provider_missing": 0,
        "deferred_narration_payload_errors": {},
        "errors": [],
    }
    for result in results:
        if result.get("ok"):
            summary["ok_jobs"] += 1
        else:
            summary["failed_jobs"] += 1
            if result.get("error"):
                summary["errors"].append(result.get("error"))

        summary["background_job_seconds"] += float(result.get("worker_ms") or 0.0) / 1000.0
        turn_index = int(result.get("turn_index") or 0)
        row = by_turn.get(turn_index)
        if not row:
            continue

        if result.get("kind") == "deferred_narration":
            summary["narration_jobs"] += 1
            payload = _safe_dict(result.get("narration_payload"))
            diagnostics = _safe_dict(result.get("diagnostics"))
            source = _safe_str(payload.get("source")) or "unknown"
            summary["deferred_narration_sources"][source] = (
                int(summary["deferred_narration_sources"].get(source) or 0) + 1
            )
            provider_shape = _safe_dict(diagnostics.get("provider_shape"))
            if provider_shape.get("present"):
                summary["deferred_narration_provider_present"] += 1
            else:
                summary["deferred_narration_provider_missing"] += 1
            payload_error = (
                _safe_str(payload.get("error"))
                or _safe_str(payload.get("original_error"))
                or _safe_str(diagnostics.get("payload_error"))
                or _safe_str(diagnostics.get("payload_original_error"))
            )
            if payload_error:
                summary["deferred_narration_payload_errors"][payload_error] = (
                    int(summary["deferred_narration_payload_errors"].get(payload_error) or 0) + 1
                )
            row["deferred_narration_result"] = result
            row["narration_status"] = result.get("narration_status")
            row["deferred_narration_source"] = _safe_str(payload.get("source"))
            row["deferred_narration_diagnostics"] = diagnostics
            if result.get("ok") and result.get("narration"):
                # Do not overwrite row["turn_result"]. That object represents
                # the blocking/manual runtime result and is used to diagnose
                # whether deferred mode really avoided blocking provider
                # narration. Store background narration separately.
                row["resolved_narration"] = result.get("narration")
                row["resolved_narration_payload"] = result.get("narration_payload") or {}
                row["narration"] = result.get("narration")
        elif result.get("kind") == "checkpoint":
            summary["checkpoint_jobs"] += 1
            row["save_load_checkpoint"] = result
        elif result.get("kind") == "deferred_advisory":
            summary["advisory_jobs"] += 1
            row["deferred_advisory_result"] = result
            row["deferred_advisory_status"] = "ready" if result.get("ok") else "error"
            if result.get("ok"):
                runtime_state = _row_runtime_state(row)
                row["deferred_advisory_ingest_result"] = ingest_deferred_advisory_candidates(
                    runtime_state=runtime_state,
                    candidates=result.get("candidates") if isinstance(result.get("candidates"), list) else [],
                    turn_index=int(result.get("turn_index") or row.get("turn_index") or 0),
                    source=_safe_str(result.get("source")) or "deferred_advisory",
                )
        elif result.get("kind") == "combined_background_llm":
            summary["combined_background_llm_jobs"] += 1
            # Use timing-aware attachment if tracker provided
            if timing_tracker and attach_turn is not None:
                from tests.rpg.autoplay_llm_campaign import (
                    _attach_completed_background_job_to_record,
                )
                attached = _attach_completed_background_job_to_record(
                    record=row,
                    job_id=_safe_str(
                        row.get("combined_background_llm_job_id")
                        or row.get("background_llm_job_id")
                        or row.get("combined_background_job_id")
                        or f"combined_background_llm:{session_id}:{row.get('turn_index')}"
                    ),
                    result=result,
                    attach_turn=attach_turn,
                    phase="final",
                    timing_tracker=timing_tracker,
                )
                if attached:
                    print(
                        f"Attaching combined background LLM result for turn {row.get('turn_index')} "
                        f"phase=final lag={max(0, attach_turn - int(row.get('turn_index') or 0))}"
                    )
            else:
                # Legacy path
                if not _safe_dict(row.get("combined_background_llm_result")):
                    row["combined_background_llm_result"] = result
                    print(f"Attaching combined background LLM result for turn {turn_index}")

                    # Attach narration in the same slots used by split narration jobs.
                    row["deferred_narration_result"] = {
                        "ok": result.get("ok"),
                        "kind": "deferred_narration",
                        "session_id": result.get("session_id"),
                        "turn_index": result.get("turn_index"),
                        "narration_status": "ready" if result.get("ok") else "error",
                        "narration": result.get("narration"),
                        "npc": result.get("npc") or {},
                        "narration_payload": result.get("narration_payload") or {},
                        "diagnostics": result.get("diagnostics") or {},
                        "worker_ms": result.get("worker_ms"),
                        "queue_timing": result.get("queue_timing") or {},
                    }
                    row["narration_status"] = "ready" if result.get("ok") else "error"
                    if result.get("ok") and result.get("narration"):
                        row["resolved_narration"] = result.get("narration")
                        row["resolved_narration_payload"] = result.get("narration_payload") or {}
                        row["narration"] = result.get("narration")

                    # Attach advisory in the same slots used by split advisory jobs.
                    row["deferred_advisory_result"] = {
                        "ok": result.get("ok"),
                        "kind": "deferred_advisory",
                        "session_id": result.get("session_id"),
                        "turn_index": result.get("turn_index"),
                        "source": result.get("source"),
                        "candidate_count": result.get("candidate_count"),
                        "candidates": result.get("candidates") or [],
                        "summary": result.get("advisory_summary") or {},
                        "diagnostics": result.get("diagnostics") or {},
                        "worker_ms": result.get("worker_ms"),
                        "queue_timing": result.get("queue_timing") or {},
                    }
                    row["deferred_advisory_status"] = "ready" if result.get("ok") else "error"
                    if result.get("ok"):
                        runtime_state = _row_runtime_state(row)
                        row["deferred_advisory_ingest_result"] = ingest_deferred_advisory_candidates(
                            runtime_state=runtime_state,
                            candidates=result.get("candidates") if isinstance(result.get("candidates"), list) else [],
                            turn_index=int(result.get("turn_index") or row.get("turn_index") or 0),
                            source=_safe_str(result.get("source")) or "combined_background_llm",
                        )

    provider_jobs = [
        result
        for result in results
        if result.get("kind") in {"deferred_narration", "deferred_advisory", "combined_background_llm"}
    ]
    summary["advisory_candidates_ingested"] = sum(
        int(_safe_dict(row.get("deferred_advisory_ingest_result")).get("added") or 0)
        for row in transcript
        if isinstance(row, dict)
    )
    summary["provider_queue_summary"] = _queue_summary(provider_jobs)
    summary["provider_queue_by_kind"] = {
        kind: _queue_summary([result for result in provider_jobs if result.get("kind") == kind])
        for kind in ("deferred_narration", "deferred_advisory", "combined_background_llm")
    }

    summary["background_job_seconds"] = round(summary["background_job_seconds"], 3)
    return summary