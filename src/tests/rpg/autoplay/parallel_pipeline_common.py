from __future__ import annotations

# ruff: noqa: F401,F811

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

__all__ = [name for name in globals() if not name.startswith("__")]
