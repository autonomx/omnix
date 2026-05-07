from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.advisory.promotion import promote_advisory_candidates
from app.rpg.advisory.runtime_store import compact_deferred_advisory_runtime_summary
from app.rpg.npc_evolution.consumer import consume_accepted_advisory_projections
from app.rpg.npc_evolution.profile_store import persist_npc_evolution_profiles
from tests.rpg.autoplay.npc_profile_runtime_loader import load_profiles_into_row_runtime


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _bounded_list_tail(value: Any, limit: int) -> List[Any]:
    items = list(value) if isinstance(value, list) else []
    if int(limit or 0) <= 0:
        return items
    return items[-int(limit or 0):]


def _compact_deferred_advisory_state(
    runtime_state: Dict[str, Any],
    *,
    candidate_limit: int = 50,
    pending_limit: int = 50,
    accepted_limit: int = 100,
    rejected_limit: int = 100,
) -> Dict[str, Any]:
    """Return a small carry-state safe for pre-turn incremental promotion.

    The full runtime mirror can become very large because every promotion pass
    carries candidates, accepted/rejected history, evolution projections, and
    profile summaries forward. Pre-turn promotion only needs recent deterministic
    context, not the full report history.
    """
    runtime_state = deepcopy(runtime_state) if isinstance(runtime_state, dict) else {}
    advisory = runtime_state.get("deferred_advisory")
    if not isinstance(advisory, dict):
        return runtime_state

    advisory["candidates"] = _bounded_list_tail(
        advisory.get("candidates"),
        int(candidate_limit or 50),
    )
    advisory["pending"] = _bounded_list_tail(
        advisory.get("pending"),
        int(pending_limit or 50),
    )
    advisory["accepted"] = _bounded_list_tail(
        advisory.get("accepted"),
        int(accepted_limit or 100),
    )
    advisory["rejected"] = _bounded_list_tail(
        advisory.get("rejected"),
        int(rejected_limit or 100),
    )
    runtime_state["deferred_advisory"] = advisory
    return runtime_state


def _row_has_unpromoted_pre_turn_background_result(row: Dict[str, Any]) -> bool:
    row = row if isinstance(row, dict) else {}
    if bool(row.get("pre_turn_advisory_promoted")):
        return False
    attach = row.get("combined_background_llm_attach")
    if isinstance(attach, dict) and str(attach.get("phase") or "") == "pre_turn":
        return bool(row.get("combined_background_llm_result"))
    # Defensive fallback for older rows where attach metadata was not stored.
    return bool(row.get("combined_background_llm_result")) and not bool(
        row.get("pre_turn_advisory_promoted")
    )


def _simulation_state_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("simulation_state", "final_turn_state", "before_state", "state_snapshot", "state"):
        value = _safe_dict(row.get(key))
        if value:
            value = deepcopy(value)
            value.setdefault("turn_contract", _safe_dict(row.get("turn_contract")))
            return value
    turn_result = _safe_dict(row.get("turn_result"))
    value = _safe_dict(turn_result.get("simulation_state"))
    if value:
        value = deepcopy(value)
        value.setdefault("turn_contract", _safe_dict(row.get("turn_contract") or turn_result.get("turn_contract")))
        return value
    session = _safe_dict(turn_result.get("session"))
    for key in ("simulation_state", "state"):
        value = _safe_dict(session.get(key))
        if value:
            value = deepcopy(value)
            value.setdefault("turn_contract", _safe_dict(row.get("turn_contract") or turn_result.get("turn_contract")))
            return value
    raw_result = _safe_dict(row.get("raw_result")) or _safe_dict(turn_result.get("raw_result"))
    raw_session = _safe_dict(raw_result.get("session"))
    for key in ("simulation_state", "state"):
        value = _safe_dict(raw_session.get(key))
        if value:
            value = deepcopy(value)
            value.setdefault("turn_contract", _safe_dict(row.get("turn_contract") or turn_result.get("turn_contract")))
            return value
    result_session = _safe_dict(_safe_dict(turn_result.get("result")).get("session"))
    for key in ("simulation_state", "state"):
        value = _safe_dict(result_session.get(key))
        if value:
            value = deepcopy(value)
            value.setdefault("turn_contract", _safe_dict(row.get("turn_contract") or turn_result.get("turn_contract")))
            return value
    story_hook_state = _safe_dict(_safe_dict(row.get("story_hook_result")).get("simulation_state"))
    if story_hook_state:
        story_hook_state = deepcopy(story_hook_state)
        story_hook_state.setdefault("turn_contract", _safe_dict(row.get("turn_contract") or turn_result.get("turn_contract")))
        return story_hook_state
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


def _merge_unique_dict_list(left: List[Any], right: List[Any], *, key: str) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for item in list(left or []) + list(right or []):
        if not isinstance(item, dict):
            continue
        marker = str(_safe_dict(item).get(key) or item)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(deepcopy(item))
    return out


def _merge_campaign_calendar(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left = _safe_dict(left)
    right = _safe_dict(right)
    if not left:
        return deepcopy(right)
    if not right:
        return deepcopy(left)
    merged = deepcopy(left)
    merged.update(deepcopy(right))
    history = _merge_unique_dict_list(
        _safe_list(left.get("history")),
        _safe_list(right.get("history")),
        key="turn_index",
    )
    history.sort(key=lambda item: int(_safe_dict(item).get("turn_index") or 0))
    merged["history"] = history[-500:]
    if history:
        merged["current"] = history[-1]
    return merged


def _merge_player_journal(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left = _safe_dict(left)
    right = _safe_dict(right)
    if not left:
        return deepcopy(right)
    if not right:
        return deepcopy(left)
    merged = deepcopy(left)
    merged.update(deepcopy(right))
    merged["entries"] = _merge_unique_dict_list(
        _safe_list(left.get("entries")),
        _safe_list(right.get("entries")),
        key="entry_id",
    )[-100:]
    merged["pending_actions"] = deepcopy(_safe_list(right.get("pending_actions")))
    merged["pending_results"] = deepcopy(_safe_list(right.get("pending_results")))
    return merged


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

    merged["campaign_calendar"] = _merge_campaign_calendar(
        _safe_dict(carried_runtime_state.get("campaign_calendar")),
        _safe_dict(row_runtime_state.get("campaign_calendar")),
    )
    merged["player_journal"] = _merge_player_journal(
        _safe_dict(carried_runtime_state.get("player_journal")),
        _safe_dict(row_runtime_state.get("player_journal")),
    )
    for key in ("quest_progress", "settings", "ui_state"):
        if key in row_runtime_state:
            merged[key] = deepcopy(row_runtime_state[key])
        elif key in carried_runtime_state and key not in merged:
            merged[key] = deepcopy(carried_runtime_state[key])

    return merged


def run_deferred_advisory_promotions_for_transcript(
    *,
    transcript: List[Dict[str, Any]],
    max_promotions_per_turn: int = 5,
    max_rows: int = 0,
    persist_profiles: bool = True,
    incremental_pre_turn: bool = False,
    mark_pre_turn_promoted: bool = False,
    current_turn: int = 0,
    carry_candidate_limit: int = 50,
    carry_pending_limit: int = 50,
    carry_accepted_limit: int = 100,
    carry_rejected_limit: int = 100,
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
    evolution_signals_created = 0
    evolution_signals_consumed = 0
    latest_profile_persist_result: Dict[str, Any] = {}

    all_rows = [row for row in transcript if isinstance(row, dict)]
    source_transcript_turns = len(all_rows)
    window_start_index = 0
    rows = all_rows

    if incremental_pre_turn:
        # Only process rows that received a pre-turn background result and have
        # not already had deterministic pre-turn advisory promotion applied.
        candidate_rows = [
            row for row in all_rows
            if _row_has_unpromoted_pre_turn_background_result(row)
        ]
        if int(max_rows or 0) > 0:
            candidate_rows = candidate_rows[-int(max_rows or 0):]
        rows = candidate_rows
        if rows:
            first_row = rows[0]
            try:
                window_start_index = all_rows.index(first_row)
            except ValueError:
                window_start_index = 0
    elif int(max_rows or 0) > 0 and len(all_rows) > int(max_rows or 0):
        window_start_index = len(all_rows) - int(max_rows or 0)
        rows = all_rows[window_start_index:]

    # Carry advisory runtime state forward across rows so turn N candidates can
    # be promoted on turn N+1.
    #
    # For incremental pre-turn promotion, seed only a compact carry-state from
    # the row immediately before the window. Do not copy the full historical
    # advisory backlog into pre-turn work.
    carried_runtime_state: Dict[str, Any] = {}
    if window_start_index > 0:
        previous_runtime_state = _runtime_state_from_row(all_rows[window_start_index - 1])
        if incremental_pre_turn:
            carried_runtime_state = _compact_deferred_advisory_state(
                previous_runtime_state,
                candidate_limit=int(carry_candidate_limit or 50),
                pending_limit=int(carry_pending_limit or 50),
                accepted_limit=int(carry_accepted_limit or 100),
                rejected_limit=int(carry_rejected_limit or 100),
            )
        else:
            carried_runtime_state = deepcopy(previous_runtime_state)

    for row in rows:
        if not isinstance(row, dict):
            continue
        if not isinstance(row, dict):
            continue
        turn_index = int(row.get("turn_index") or 0)
        runtime_state = _merge_deferred_advisory_state(
            carried_runtime_state,
            _runtime_state_from_row(row),
        )

        simulation_state_before = _simulation_state_from_row(row)
        # Important: profile loading must enrich the already-merged runtime
        # state. If it reads only the row-local runtime_state, it can drop
        # carried deferred_advisory candidates from previous turns, causing all
        # candidates to remain same-turn pending forever.
        row["runtime_state"] = runtime_state
        profile_load_summary = load_profiles_into_row_runtime(
            row=row,
            simulation_state=simulation_state_before,
        )
        runtime_state = _safe_dict(row.get("runtime_state")) or runtime_state
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
        updated_runtime_state, evolution_result = consume_accepted_advisory_projections(
            runtime_state=updated_runtime_state,
            simulation_state=simulation_state_before,
            turn_index=turn_index,
        )
        evolution_result["simulation_state_keys"] = sorted(list(simulation_state_before.keys()))[:80]
        npc_progression_state = _safe_dict(simulation_state_before.get("npc_progression_state"))
        scene = _safe_dict(simulation_state_before.get("scene"))
        contract = _safe_dict(simulation_state_before.get("turn_contract"))
        resolved_action_location = _safe_dict(
            _safe_dict(_safe_dict(contract.get("resolved_action")).get("location_state")).get("current_location")
        )
        evolution_result["simulation_npc_count"] = len(
            _safe_dict(simulation_state_before.get("npcs"))
            or _safe_dict(npc_progression_state.get("npcs"))
        )
        evolution_result["simulation_present_npc_count"] = len(
            _safe_list(simulation_state_before.get("present_npcs"))
            or _safe_list(simulation_state_before.get("nearby_npcs"))
            or _safe_list(scene.get("nearby_npcs"))
            or _safe_list(resolved_action_location.get("present_npcs"))
        )
        row["runtime_state"] = updated_runtime_state
        row["npc_evolution_consumption_result"] = evolution_result
        row["npc_evolution_summary"] = evolution_result.get("summary") or {}
        if persist_profiles:
            profile_persist_result = persist_npc_evolution_profiles(runtime_state=updated_runtime_state)
        else:
            profile_persist_result = {
                "ok": True,
                "skipped": True,
                "reason": "pre_turn_promotion_no_disk_persist",
            }
        row["npc_evolution_profile_persist_result"] = profile_persist_result
        latest_profile_persist_result = profile_persist_result

        if incremental_pre_turn and mark_pre_turn_promoted:
            row["pre_turn_advisory_promoted"] = True
            row["pre_turn_advisory_promoted_at_turn"] = int(current_turn or 0)
            row["pre_turn_advisory_promotion_summary"] = {
                "ok": True,
                "current_turn": int(current_turn or 0),
                "incremental_pre_turn": True,
                "persist_profiles": bool(persist_profiles),
                "max_rows": int(max_rows or 0),
            }
        evolution_signals_created += int(evolution_result.get("signals_created") or 0)
        evolution_signals_consumed += int(evolution_result.get("signals_consumed") or 0)
        carried_runtime_state = updated_runtime_state
        promotion_results.append(
            {
                "turn_index": turn_index,
                "promoted_this_turn": result.get("promoted_this_turn"),
                "decision_count": len(decisions),
                "mutated_authoritative_state": mutated_authoritative_state,
                "evolution_signals_created": evolution_result.get("signals_created"),
                "evolution_signals_consumed": evolution_result.get("signals_consumed"),
                "npc_evolution_summary": evolution_result.get("summary") or {},
                "profile_persist_result": profile_persist_result,
                "profile_load_summary": profile_load_summary,
            }
        )

    return {
        "ok": True,
        "turns": len(rows),
        "source_transcript_turns": source_transcript_turns,
        "window_start_index": window_start_index,
        "max_rows": int(max_rows or 0),
        "persist_profiles": bool(persist_profiles),
        "incremental_pre_turn": bool(incremental_pre_turn),
        "mark_pre_turn_promoted": bool(mark_pre_turn_promoted),
        "current_turn": int(current_turn or 0),
        "carry_candidate_limit": int(carry_candidate_limit or 0),
        "carry_pending_limit": int(carry_pending_limit or 0),
        "carry_accepted_limit": int(carry_accepted_limit or 0),
        "carry_rejected_limit": int(carry_rejected_limit or 0),
        "accepted": accepted,
        "rejected": rejected,
        "pending": pending,
        "evolution_signals_created": evolution_signals_created,
        "evolution_signals_consumed": evolution_signals_consumed,
        "profile_persist_result": latest_profile_persist_result,
        "results": promotion_results,
        "mutated_authoritative_state": any(item.get("mutated_authoritative_state") for item in promotion_results),
    }