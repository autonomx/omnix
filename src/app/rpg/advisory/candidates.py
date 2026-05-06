from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List


ADVISORY_CANDIDATE_VERSION = "deferred_advisory_candidates_v1"

ALLOWED_CANDIDATE_KINDS = {
    "semantic_intent",
    "relationship_delta",
    "memory",
    "world_signal",
    "future_hook",
}

FORBIDDEN_AUTHORITATIVE_KEYS = {
    "inventory",
    "items",
    "currency",
    "gold",
    "xp",
    "experience",
    "quest_status",
    "quest_completion",
    "combat_damage",
    "damage",
    "hit",
    "miss",
    "location",
    "travel",
    "service_purchase",
    "reward",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def stable_json_for_prompt(value: Any, max_chars: int = 6000) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text


def advisory_candidate_id(
    *,
    session_id: str,
    turn_index: int,
    kind: str,
    payload: Dict[str, Any],
) -> str:
    raw = stable_json(
        {
            "session_id": session_id,
            "turn_index": turn_index,
            "kind": kind,
            "payload": payload,
        }
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"adv:{turn_index}:{kind}:{digest}"


def contains_forbidden_authoritative_claim(value: Any) -> bool:
    text = stable_json(value).lower()
    return any(key in text for key in FORBIDDEN_AUTHORITATIVE_KEYS)


def turn_contract_backing_action(turn_contract: Dict[str, Any]) -> str:
    turn_contract = _safe_dict(turn_contract)
    semantic_action = _safe_dict(turn_contract.get("semantic_action"))
    resolved_action = turn_contract.get("resolved_action")
    resolved_result = turn_contract.get("resolved_result")

    return (
        _safe_str(turn_contract.get("action"))
        or _safe_str(turn_contract.get("result"))
        or _safe_str(turn_contract.get("player_action"))
        or _safe_str(turn_contract.get("player_input"))
        or _safe_str(resolved_action)
        or _safe_str(_safe_dict(resolved_action).get("action"))
        or _safe_str(_safe_dict(resolved_action).get("type"))
        or _safe_str(resolved_result)
        or _safe_str(_safe_dict(resolved_result).get("summary"))
        or _safe_str(_safe_dict(resolved_result).get("result"))
        or _safe_str(semantic_action.get("semantic_action_type"))
        or _safe_str(semantic_action.get("semantic_family"))
        or _safe_str(semantic_action.get("intent"))
    )


def _kind_from_group_key(key: str) -> str:
    if key == "semantic_intent_candidates":
        return "semantic_intent"
    if key == "relationship_delta_candidates":
        return "relationship_delta"
    if key == "memory_candidates":
        return "memory"
    if key == "world_signal_candidates":
        return "world_signal"
    if key == "future_hook_candidates":
        return "future_hook"
    return "future_hook"


def normalize_advisory_candidate(
    *,
    session_id: str,
    turn_index: int,
    player_input: str,
    turn_contract: Dict[str, Any],
    raw: Dict[str, Any],
) -> Dict[str, Any]:
    raw = deepcopy(_safe_dict(raw))
    kind = _safe_str(raw.get("kind")).strip() or _safe_str(raw.get("type")).strip()
    if kind not in ALLOWED_CANDIDATE_KINDS:
        kind = "future_hook"

    payload = deepcopy(_safe_dict(raw.get("payload")) or raw)
    for transient_key in ("candidate_id", "status", "promoted", "promotion", "backing", "safety"):
        payload.pop(transient_key, None)

    candidate = {
        "format_version": ADVISORY_CANDIDATE_VERSION,
        "candidate_id": advisory_candidate_id(
            session_id=session_id,
            turn_index=turn_index,
            kind=kind,
            payload=payload,
        ),
        "session_id": session_id,
        "turn_index": int(turn_index),
        "kind": kind,
        "status": "pending",
        "created_at": _now_iso(),
        "source": "deferred_advisory",
        "player_input": player_input,
        "payload": payload,
        "promotion": {
            "eligible_from_turn": int(turn_index) + 1,
            "accepted": False,
            "rejected": False,
            "reason": "",
        },
        "backing": {
            "turn_contract_action": turn_contract_backing_action(turn_contract),
            "turn_contract_keys": sorted([str(k) for k in turn_contract.keys()]),
        },
        "safety": {
            "contains_forbidden_authoritative_claim": contains_forbidden_authoritative_claim(payload),
        },
    }
    return candidate


def normalize_advisory_candidates(
    *,
    session_id: str,
    turn_index: int,
    player_input: str,
    turn_contract: Dict[str, Any],
    payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    payload = _safe_dict(payload)
    raw_candidates: List[Dict[str, Any]] = []

    for key in (
        "candidates",
        "semantic_intent_candidates",
        "relationship_delta_candidates",
        "memory_candidates",
        "world_signal_candidates",
        "future_hook_candidates",
    ):
        for value in _safe_list(payload.get(key)):
            if not isinstance(value, dict):
                continue
            normalized = deepcopy(value)
            if key != "candidates" and "kind" not in normalized and "type" not in normalized:
                normalized["kind"] = _kind_from_group_key(key)
            raw_candidates.append(normalized)

    candidates = [
        normalize_advisory_candidate(
            session_id=session_id,
            turn_index=turn_index,
            player_input=player_input,
            turn_contract=turn_contract,
            raw=raw,
        )
        for raw in raw_candidates
    ]

    seen = set()
    deduped: List[Dict[str, Any]] = []
    for candidate in candidates:
        cid = candidate.get("candidate_id")
        if cid in seen:
            continue
        seen.add(cid)
        deduped.append(candidate)
    return deduped


def build_deterministic_advisory_candidates(
    *,
    session_id: str,
    turn_index: int,
    player_input: str,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    semantic = _safe_dict(semantic_action_record)
    intent = (
        _safe_str(semantic.get("semantic_action_type"))
        or _safe_str(semantic.get("semantic_family"))
        or _safe_str(semantic.get("intent"))
        or _safe_str(turn_contract.get("action"))
        or _safe_str(turn_contract.get("player_action"))
        or "unknown"
    )
    raw = {
        "kind": "semantic_intent",
        "payload": {
            "intent": intent,
            "summary": f"Fast deterministic interpretation of player input: {player_input[:180]}",
            "confidence": 0.45,
            "deterministic_fallback": True,
        },
    }
    return [
        normalize_advisory_candidate(
            session_id=session_id,
            turn_index=turn_index,
            player_input=player_input,
            turn_contract=turn_contract,
            raw=raw,
        )
    ]


def advisory_candidate_summary(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {
        "total": len(candidates),
        "by_kind": {},
        "pending": 0,
        "accepted": 0,
        "rejected": 0,
        "forbidden_claims": 0,
    }
    for candidate in candidates:
        kind = _safe_str(candidate.get("kind")) or "unknown"
        summary["by_kind"][kind] = int(summary["by_kind"].get(kind) or 0) + 1
        status = _safe_str(candidate.get("status")) or "pending"
        if status in ("pending", "accepted", "rejected"):
            summary[status] += 1
        if _safe_dict(candidate.get("safety")).get("contains_forbidden_authoritative_claim"):
            summary["forbidden_claims"] += 1
    return summary