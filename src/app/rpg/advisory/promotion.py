from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from app.rpg.advisory.candidates import advisory_candidate_summary


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _npc_exists_or_is_present(simulation_state: Dict[str, Any], target: str) -> bool:
    if not target:
        return False
    target_norm = target.lower()
    npcs = _safe_dict(simulation_state.get("npcs"))
    if target in npcs or target_norm in {str(k).lower() for k in npcs.keys()}:
        return True
    present = _safe_list(simulation_state.get("present_npcs")) or _safe_list(simulation_state.get("nearby_npcs"))
    return any(str(npc).lower() == target_norm for npc in present)


def _is_backed_by_turn(candidate: Dict[str, Any]) -> bool:
    backing = _safe_dict(candidate.get("backing"))
    action = _safe_str(backing.get("turn_contract_action"))
    return bool(action.strip())


def _candidate_rejection_reason(
    candidate: Dict[str, Any],
    simulation_state: Dict[str, Any],
    current_turn: int,
) -> str:
    promotion = _safe_dict(candidate.get("promotion"))
    eligible_from = int(promotion.get("eligible_from_turn") or 0)
    if current_turn < eligible_from:
        return "not_eligible_until_future_turn"
    if _safe_dict(candidate.get("safety")).get("contains_forbidden_authoritative_claim"):
        return "contains_forbidden_authoritative_claim"
    if not _is_backed_by_turn(candidate):
        return "not_backed_by_turn_contract"

    kind = _safe_str(candidate.get("kind"))
    payload = _safe_dict(candidate.get("payload"))

    if kind == "relationship_delta":
        target = _safe_str(payload.get("target") or payload.get("npc") or payload.get("npc_id"))
        if not _npc_exists_or_is_present(simulation_state, target):
            return "relationship_target_not_present_or_unknown"
        try:
            delta = int(payload.get("delta") or 0)
        except Exception:
            return "relationship_delta_not_integer"
        if delta < -2 or delta > 2:
            return "relationship_delta_out_of_bounds"

    if kind == "memory":
        owner = _safe_str(payload.get("owner") or payload.get("npc") or payload.get("npc_id"))
        summary = _safe_str(payload.get("summary"))
        if not owner:
            return "memory_owner_missing"
        if not summary:
            return "memory_summary_missing"

    if kind == "world_signal":
        summary = _safe_str(payload.get("summary"))
        if not summary:
            return "world_signal_summary_missing"

    if kind == "future_hook":
        summary = _safe_str(payload.get("summary"))
        if not summary:
            return "future_hook_summary_missing"

    return ""


def _accepted_projection(candidate: Dict[str, Any]) -> Dict[str, Any]:
    kind = _safe_str(candidate.get("kind"))
    payload = deepcopy(_safe_dict(candidate.get("payload")))
    return {
        "candidate_id": candidate.get("candidate_id"),
        "kind": kind,
        "payload": payload,
        "source": "deferred_advisory_promotion",
    }


def promote_advisory_candidates(
    *,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    current_turn: int,
    max_promotions_per_turn: int = 5,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Promote advisory candidates deterministically.

    Advisory candidates do not mutate authoritative RPG facts directly.
    This gate only creates bounded accepted projections that later deterministic
    systems can inspect.
    """
    runtime_state = deepcopy(runtime_state if isinstance(runtime_state, dict) else {})
    advisory_state = runtime_state.setdefault("deferred_advisory", {})
    candidates = _safe_list(advisory_state.get("candidates"))
    accepted = _safe_list(advisory_state.get("accepted"))
    rejected = _safe_list(advisory_state.get("rejected"))

    accepted_ids = {str(item.get("candidate_id")) for item in accepted if isinstance(item, dict)}
    rejected_ids = {str(item.get("candidate_id")) for item in rejected if isinstance(item, dict)}

    promoted_this_turn = 0
    decisions: List[Dict[str, Any]] = []
    updated_candidates: List[Dict[str, Any]] = []

    for candidate_raw in candidates:
        if not isinstance(candidate_raw, dict):
            continue
        candidate = deepcopy(candidate_raw)
        cid = str(candidate.get("candidate_id") or "")
        if not cid:
            updated_candidates.append(candidate)
            continue
        if cid in accepted_ids or cid in rejected_ids:
            updated_candidates.append(candidate)
            continue
        if promoted_this_turn >= max_promotions_per_turn:
            updated_candidates.append(candidate)
            continue

        reason = _candidate_rejection_reason(candidate, simulation_state, current_turn)
        if reason:
            candidate["status"] = "rejected"
            candidate.setdefault("promotion", {})["rejected"] = True
            candidate.setdefault("promotion", {})["reason"] = reason
            rejected.append(
                {
                    "candidate_id": cid,
                    "turn_index": candidate.get("turn_index"),
                    "kind": candidate.get("kind"),
                    "reason": reason,
                    "rejected_at_turn": current_turn,
                }
            )
            decisions.append({"candidate_id": cid, "status": "rejected", "reason": reason})
        else:
            candidate["status"] = "accepted"
            candidate.setdefault("promotion", {})["accepted"] = True
            candidate.setdefault("promotion", {})["reason"] = "accepted_by_deterministic_gate"
            candidate.setdefault("promotion", {})["promoted_at_turn"] = current_turn
            projection = _accepted_projection(candidate)
            accepted.append(
                {
                    "candidate_id": cid,
                    "turn_index": candidate.get("turn_index"),
                    "kind": candidate.get("kind"),
                    "projection": projection,
                    "accepted_at_turn": current_turn,
                    "reason": "accepted_by_deterministic_gate",
                }
            )
            decisions.append(
                {
                    "candidate_id": cid,
                    "status": "accepted",
                    "reason": "accepted_by_deterministic_gate",
                }
            )
            promoted_this_turn += 1
        updated_candidates.append(candidate)

    advisory_state["candidates"] = updated_candidates
    advisory_state["accepted"] = accepted
    advisory_state["rejected"] = rejected
    advisory_state["summary"] = {
        "candidates": advisory_candidate_summary(updated_candidates),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }

    result = {
        "ok": True,
        "current_turn": current_turn,
        "promoted_this_turn": promoted_this_turn,
        "decisions": decisions,
        "summary": advisory_state["summary"],
    }
    return runtime_state, result