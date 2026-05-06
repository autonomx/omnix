from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.advisory.candidates import advisory_candidate_summary


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _candidate_id(candidate: Dict[str, Any]) -> str:
    return _safe_str(_safe_dict(candidate).get("candidate_id"))


def deferred_advisory_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    state = runtime_state.setdefault("deferred_advisory", {})
    state.setdefault("candidates", [])
    state.setdefault("accepted", [])
    state.setdefault("rejected", [])
    state.setdefault("ingest_log", [])
    state.setdefault("promotion_log", [])
    state.setdefault("summary", {})
    return state


def ingest_deferred_advisory_candidates(
    *,
    runtime_state: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    turn_index: int,
    source: str,
    max_pending: int = 200,
) -> Dict[str, Any]:
    """Persist background advisory candidates into runtime_state.

    This stores candidates only. It does not promote them and does not mutate
    authoritative RPG facts.
    """
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    advisory_state = deferred_advisory_state(runtime_state)
    existing = _safe_list(advisory_state.get("candidates"))
    existing_ids = {_candidate_id(item) for item in existing if isinstance(item, dict)}

    added = 0
    duplicates = 0
    normalized_candidates: List[Dict[str, Any]] = []
    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        candidate_copy = deepcopy(candidate)
        cid = _candidate_id(candidate_copy)
        if not cid:
            continue
        if cid in existing_ids:
            duplicates += 1
            continue
        existing_ids.add(cid)
        candidate_copy.setdefault("status", "pending")
        candidate_copy.setdefault("source", source or "deferred_advisory")
        normalized_candidates.append(candidate_copy)
        added += 1

    merged = existing + normalized_candidates
    if len(merged) > max_pending:
        merged = merged[-max_pending:]

    advisory_state["candidates"] = merged
    advisory_state["ingest_log"].append(
        {
            "turn_index": turn_index,
            "source": source,
            "added": added,
            "duplicates": duplicates,
            "pending_total": len(merged),
        }
    )
    advisory_state["summary"] = {
        "candidates": advisory_candidate_summary(merged),
        "accepted_count": len(_safe_list(advisory_state.get("accepted"))),
        "rejected_count": len(_safe_list(advisory_state.get("rejected"))),
        "ingest_count": len(_safe_list(advisory_state.get("ingest_log"))),
        "promotion_count": len(_safe_list(advisory_state.get("promotion_log"))),
    }
    return {
        "ok": True,
        "turn_index": turn_index,
        "source": source,
        "added": added,
        "duplicates": duplicates,
        "pending_total": len(merged),
        "summary": advisory_state["summary"],
    }


def compact_deferred_advisory_runtime_summary(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    advisory_state = _safe_dict(_safe_dict(runtime_state).get("deferred_advisory"))
    candidates = _safe_list(advisory_state.get("candidates"))
    accepted = _safe_list(advisory_state.get("accepted"))
    rejected = _safe_list(advisory_state.get("rejected"))
    return {
        "pending_total": sum(1 for item in candidates if _safe_dict(item).get("status") == "pending"),
        "candidate_total": len(candidates),
        "accepted_total": len(accepted),
        "rejected_total": len(rejected),
        "latest_ingest": (_safe_list(advisory_state.get("ingest_log")) or [])[-3:],
        "latest_promotions": (_safe_list(advisory_state.get("promotion_log")) or [])[-3:],
        "summary": _safe_dict(advisory_state.get("summary")),
    }