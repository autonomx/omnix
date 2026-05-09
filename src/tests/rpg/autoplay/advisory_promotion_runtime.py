from __future__ import annotations

from copy import deepcopy
from time import perf_counter
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


def _elapsed_ms(start: float) -> int:
    return int(round((perf_counter() - start) * 1000))


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


def _compact_pre_turn_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the namespaces needed by pre-turn advisory promotion.

    Full runtime_state can include profile stores, journal history, report state,
    large quest/event mirrors, and evolution projections. Pre-turn promotion
    only needs enough state to validate/accept recent advisory candidates.
    """
    runtime_state = _safe_dict(runtime_state)
    keep_keys = (
        "deferred_advisory",
        "quest_progress",
        "quest_log_state",
        "settings",
        "ui_state",
        "current_location",
        "current_location_name",
        "scene",
        "dialogue_state",
        "autoplay_story_hook_state",
        "objective_progression_log",
        "quest_reconciliation_log",
        "quest_handoff_log",
    )
    compact: Dict[str, Any] = {}
    for key in keep_keys:
        if key in runtime_state:
            compact[key] = deepcopy(runtime_state[key])
    return compact


def _compact_pre_turn_simulation_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Small simulation-state view for deterministic promotion validation."""
    simulation_state = _safe_dict(simulation_state)
    keep_keys = (
        "turn_contract",
        "npcs",
        "present_npcs",
        "nearby_npcs",
        "visible_npcs",
        "scene",
        "current_location",
        "current_location_name",
        "quest_progress",
        "quest_log_state",
        "npc_progression_state",
        "npc_profile_state",
    )
    compact: Dict[str, Any] = {}
    for key in keep_keys:
        if key in simulation_state:
            compact[key] = deepcopy(simulation_state[key])
    return compact


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
    fast_pre_turn: bool = False,
    skip_profile_load_for_pre_turn: bool = True,
    skip_evolution_for_pre_turn: bool = True,
    skip_mutation_compare_for_pre_turn: bool = True,
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
    timing_breakdown: Dict[str, int] = {
        "row_total_ms": 0,
        "merge_runtime_ms": 0,
        "simulation_state_ms": 0,
        "profile_load_ms": 0,
        "promotion_ms": 0,
        "evolution_consume_ms": 0,
        "profile_persist_ms": 0,
    }
    fast_path_used = bool(incremental_pre_turn and fast_pre_turn)

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
            if fast_path_used:
                carried_runtime_state = _compact_pre_turn_runtime_state(carried_runtime_state)
        else:
            carried_runtime_state = deepcopy(previous_runtime_state)

    for row in rows:
        if not isinstance(row, dict):
            continue
        if not isinstance(row, dict):
            continue
        turn_index = int(row.get("turn_index") or 0)
        row_start = perf_counter()

        merge_start = perf_counter()
        row_runtime_state = _runtime_state_from_row(row)
        if fast_path_used:
            row_runtime_state = _compact_pre_turn_runtime_state(row_runtime_state)
        runtime_state = _merge_deferred_advisory_state(
            carried_runtime_state,
            row_runtime_state,
        )
        if fast_path_used:
            runtime_state = _compact_deferred_advisory_state(
                _compact_pre_turn_runtime_state(runtime_state),
                candidate_limit=int(carry_candidate_limit or 50),
                pending_limit=int(carry_pending_limit or 50),
                accepted_limit=int(carry_accepted_limit or 100),
                rejected_limit=int(carry_rejected_limit or 100),
            )
        timing_breakdown["merge_runtime_ms"] += _elapsed_ms(merge_start)

        sim_start = perf_counter()
        simulation_state_before = _simulation_state_from_row(row)
        if fast_path_used:
            simulation_state_before = _compact_pre_turn_simulation_state(simulation_state_before)
        timing_breakdown["simulation_state_ms"] += _elapsed_ms(sim_start)

        # Important for full/final promotion: profile loading enriches merged
        # runtime state. For pre-turn fast path, skip disk/profile work.
        row["runtime_state"] = runtime_state
        profile_load_start = perf_counter()
        if fast_path_used and skip_profile_load_for_pre_turn:
            profile_load_summary = {
                "ok": True,
                "skipped": True,
                "reason": "fast_pre_turn_skip_profile_load",
            }
        else:
            profile_load_summary = load_profiles_into_row_runtime(
                row=row,
                simulation_state=simulation_state_before,
            )
            runtime_state = _safe_dict(row.get("runtime_state")) or runtime_state
        timing_breakdown["profile_load_ms"] += _elapsed_ms(profile_load_start)

        promotion_start = perf_counter()
        if fast_path_used and skip_mutation_compare_for_pre_turn:
            simulation_state_after_probe = simulation_state_before
        else:
            simulation_state_after_probe = deepcopy(simulation_state_before)

        updated_runtime_state, result = promote_advisory_candidates(
            simulation_state=simulation_state_after_probe,
            runtime_state=runtime_state,
            current_turn=turn_index,
            max_promotions_per_turn=max_promotions_per_turn,
        )
        timing_breakdown["promotion_ms"] += _elapsed_ms(promotion_start)

        # Safety: full/final promotion checks simulation mutation. Fast pre-turn
        # promotion skips expensive deep comparison and remains non-authoritative.
        if fast_path_used and skip_mutation_compare_for_pre_turn:
            mutated_authoritative_state = False
            result["mutation_compare_skipped"] = True
            result["mutation_compare_skip_reason"] = "fast_pre_turn"
        else:
            mutated_authoritative_state = simulation_state_after_probe != simulation_state_before
        result["mutated_authoritative_state"] = mutated_authoritative_state
        result["fast_pre_turn"] = bool(fast_path_used)

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
        evolution_start = perf_counter()
        if fast_path_used and skip_evolution_for_pre_turn:
            evolution_result = {
                "ok": True,
                "skipped": True,
                "reason": "fast_pre_turn_skip_evolution_consumption",
                "signals_created": 0,
                "signals_consumed": 0,
                "summary": {},
            }
        else:
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
        timing_breakdown["evolution_consume_ms"] += _elapsed_ms(evolution_start)
        row["runtime_state"] = updated_runtime_state
        row["npc_evolution_consumption_result"] = evolution_result
        row["npc_evolution_summary"] = evolution_result.get("summary") or {}
        persist_start = perf_counter()
        if persist_profiles:
            profile_persist_result = persist_npc_evolution_profiles(runtime_state=updated_runtime_state)
        else:
            profile_persist_result = {
                "ok": True,
                "skipped": True,
                "reason": "pre_turn_promotion_no_disk_persist",
            }
        timing_breakdown["profile_persist_ms"] += _elapsed_ms(persist_start)
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
        evolution_signals_created += int(_safe_dict(evolution_result).get("signals_created") or 0)
        evolution_signals_consumed += int(_safe_dict(evolution_result).get("signals_consumed") or 0)
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
                "row_elapsed_ms": _elapsed_ms(row_start),
                "fast_pre_turn": bool(fast_path_used),
            }
        )
        timing_breakdown["row_total_ms"] += _elapsed_ms(row_start)

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
        "timing_breakdown": timing_breakdown,
        "fast_pre_turn": bool(fast_path_used),
        "skip_profile_load_for_pre_turn": bool(skip_profile_load_for_pre_turn),
        "skip_evolution_for_pre_turn": bool(skip_evolution_for_pre_turn),
        "skip_mutation_compare_for_pre_turn": bool(skip_mutation_compare_for_pre_turn),
        "results": promotion_results,
        "mutated_authoritative_state": any(item.get("mutated_authoritative_state") for item in promotion_results),
    }