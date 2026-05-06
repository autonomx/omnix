from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.advisory.promotion import promote_advisory_candidates
from app.rpg.advisory.runtime_store import compact_deferred_advisory_runtime_summary


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _simulation_state_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("simulation_state", "final_turn_state", "state_snapshot", "state"):
        value = _safe_dict(row.get(key))
        if value:
            return value
    turn_result = _safe_dict(row.get("turn_result"))
    session = _safe_dict(turn_result.get("session"))
    for key in ("simulation_state", "state"):
        value = _safe_dict(session.get(key))
        if value:
            return value
    return {}


def _runtime_state_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(row.get("runtime_state"))
    if value:
        return value
    turn_result = _safe_dict(row.get("turn_result"))
    session = _safe_dict(turn_result.get("session"))
    return _safe_dict(session.get("runtime_state"))


def _candidate_id(candidate: Dict[str, Any]) -> str:
    return str(_safe_dict(candidate).get("candidate_id") or "")


def _merge_deferred_advisory_state(
    carried_runtime_state: Dict[str, Any],
    row_runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge carried deferred advisory state with current-row ingested candidates."""
    merged = deepcopy(carried_runtime_state if isinstance(carried_runtime_state, dict) else {})
    row_runtime_state = deepcopy(row_runtime_state if isinstance(row_runtime_state, dict) else {})

    carried_adv = _safe_dict(merged.get("deferred_advisory"))
    row_adv = _safe_dict(row_runtime_state.get("deferred_advisory"))

    merged.update(row_runtime_state)

    if not carried_adv and not row_adv:
        return merged

    out_adv = deepcopy(carried_adv)
    out_adv.setdefault("candidates", [])
    out_adv.setdefault("accepted", [])
    out_adv.setdefault("rejected", [])
    out_adv.setdefault("ingest_log", [])
    out_adv.setdefault("promotion_log", [])

    def merge_list(key: str) -> None:
        existing = _safe_list(out_adv.get(key))
        seen = {
            _candidate_id(item) or str(item)
            for item in existing
            if isinstance(item, dict)
        }
        for item in _safe_list(row_adv.get(key)):
            if not isinstance(item, dict):
                continue
            marker = _candidate_id(item) or str(item)
            if marker in seen:
                continue
            seen.add(marker)
            existing.append(deepcopy(item))
        out_adv[key] = existing

    merge_list("candidates")
    merge_list("accepted")
    merge_list("rejected")

    out_adv["ingest_log"] = _safe_list(carried_adv.get("ingest_log")) + _safe_list(row_adv.get("ingest_log"))
    out_adv["promotion_log"] = _safe_list(carried_adv.get("promotion_log")) + _safe_list(row_adv.get("promotion_log"))
    if row_adv.get("summary"):
        out_adv["summary"] = row_adv.get("summary")
    elif carried_adv.get("summary"):
        out_adv["summary"] = carried_adv.get("summary")

    merged["deferred_advisory"] = out_adv
    return merged


def run_deferred_advisory_promotions_for_transcript(
    *,
    transcript: List[Dict[str, Any]],
    max_promotions_per_turn: int = 5,
) -> Dict[str, Any]:
    """Run promotion gate over transcript in turn order.

    This simulates next-turn/idle-tick promotion for autoplay artifacts.
    It does not mutate authoritative state; it mutates row-local runtime_state
    mirrors and records decisions for report/debug.
    """
    if not isinstance(transcript, list):
        return {"ok": False, "error": "transcript_not_list"}

    promotion_results: List[Dict[str, Any]] = []
    accepted = 0
    rejected = 0
    pending = 0

    # Carry advisory runtime state forward across rows so turn N candidates can
    # be promoted on turn N+1.
    carried_runtime_state: Dict[str, Any] = {}

    for row in transcript:
        if not isinstance(row, dict):
            continue
        turn_index = int(row.get("turn_index") or 0)
        runtime_state = _merge_deferred_advisory_state(
            carried_runtime_state,
            _runtime_state_from_row(row),
        )

        # Ingest result may have already placed current-turn candidates into this
        # row's runtime_state. They are not eligible until turn_index + 1, so this
        # call will reject/preserve same-turn candidates as not eligible.
        simulation_state_before = _simulation_state_from_row(row)
        simulation_state_after_probe = deepcopy(simulation_state_before)

        updated_runtime_state, result = promote_advisory_candidates(
            simulation_state=simulation_state_after_probe,
            runtime_state=runtime_state,
            current_turn=turn_index,
            max_promotions_per_turn=max_promotions_per_turn,
        )

        # Safety: promotion must not mutate simulation_state.
        mutated_authoritative_state = simulation_state_after_probe != simulation_state_before
        result["mutated_authoritative_state"] = mutated_authoritative_state

        decisions = _safe_list(result.get("decisions"))
        accepted += sum(1 for decision in decisions if _safe_dict(decision).get("status") == "accepted")
        rejected += sum(1 for decision in decisions if _safe_dict(decision).get("status") == "rejected")
        pending += sum(1 for decision in decisions if _safe_dict(decision).get("status") == "pending")

        updated_runtime_state.setdefault("deferred_advisory", {}).setdefault("promotion_log", []).append(
            {
                "turn_index": turn_index,
                "result": result,
            }
        )
        row["runtime_state"] = updated_runtime_state
        row["deferred_advisory_promotion_result"] = result
        row["deferred_advisory_runtime_summary"] = compact_deferred_advisory_runtime_summary(updated_runtime_state)
        carried_runtime_state = updated_runtime_state
        promotion_results.append(
            {
                "turn_index": turn_index,
                "promoted_this_turn": result.get("promoted_this_turn"),
                "decision_count": len(decisions),
                "mutated_authoritative_state": mutated_authoritative_state,
            }
        )

    return {
        "ok": True,
        "turns": len([row for row in transcript if isinstance(row, dict)]),
        "accepted": accepted,
        "rejected": rejected,
        "pending": pending,
        "results": promotion_results,
        "mutated_authoritative_state": any(item.get("mutated_authoritative_state") for item in promotion_results),
    }