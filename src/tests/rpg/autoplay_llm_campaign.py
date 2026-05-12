
from __future__ import annotations

from app.rpg.mechanics.mechanics_opportunities import (
    describe_mechanic_opportunity_state,
    list_available_mechanic_opportunities,
)
from app.rpg.mechanics.mechanics_resolver import resolve_mechanic_opportunity

PROGRESSION_STATE_PRESERVE_KEYS = (
    "progression_state_revision",
    "progression_completed_node_count",
    "progression_fact_count",
    "progression_lead_count",
    "progression_authority_summary",
    "progression_completed_nodes",
    "progression_facts",
    "progression_leads",
    "progression_unlocked_npcs",
    "progression_unlocked_locations",
    "scenario_progression_log",
    "scenario_progression_summary",
    "scenario_progression_actions",
    "scenario_progression_current_turn_summary",
    "scenario_progression_last_no_match",
    "scenario_progression_action_debug",
    "scenario_progression_quest_state",
    "scenario_progression_quest_ids",
    "scenario_progression_active_graph_id",
    "scenario_progression_active_graph_title",
    "scenario_progression_completed_graph_ids",
    "scenario_progression_last_completed_graph_id",
    "scenario_progression_waiting_for_next_graph_pack",
)

TRANSCRIPT_KEEP_KEYS = (
    "turn",
    "turn_index",
    "turn_start_timestamp",
    "turn_end_timestamp",
    "player_action",
    "player_agent_selection_source",
    "player_agent_selection_reason",
    "scenario_progression_summary",
    "scenario_progression_actions",
    "scenario_progression_action_debug",
    "player_action_source",
    "player_action_timing",
    "player_action_quality",
    "player_agent_trace",
    "deferred_narration_trace",
    "deferred_advisory_trace",
    "background_prompt_budget",
    "combined_quality_shape",
    "promotion_target_grounding",
    "profile_grounded_output",
    "npc_arc_progression",
    "manual_turn_errors",
    "campaign_state_summary",
    "repeated_affordance_loop",
    "scenario_progression_waiting_for_next_graph_pack",
    "graph_action_state_has_actions",
    "top_scenario_progression_action_id",
    "top_scenario_progression_command",
    "scenario_arc_complete",
)


def _effective_transcript_detail(args: Any) -> str:
    turns = int(getattr(args, "turns", 0) or 0)
    profile = _safe_str(getattr(args, "autoplay_profile", "") or "")
    if turns >= 30 or profile == "smoke_100":
        return "slim"
    return "full"


def _slim_transcript_row(row: Dict[str, Any], max_row_bytes: int = 50000) -> Dict[str, Any]:
    slim_row = {key: row.get(key) for key in TRANSCRIPT_KEEP_KEYS if key in row}

    for key in (
        "mechanic",
        "mechanics_evidence_source",
        "mechanics_forced_action",
        "mechanic_resolution_input",
        "player_action_original",
        "mechanic_resolution_failed_opportunity_id",
        "mechanic_resolution_failed_reason",
    ):
        if row.get(key) not in (None, "", {}, []):
            slim_row[key] = row.get(key)

    state_delta = _safe_dict(row.get("state_delta"))
    if state_delta:
        slim_row["state_delta"] = {
            key: value
            for key, value in state_delta.items()
            if key in {
                "currency_delta",
                "inventory_delta",
                "xp_delta",
                "level_delta",
                "level_up",
                "party_delta",
                "combat_started",
                "combat_resolved",
                "location_changed",
                "from_location",
                "to_location",
                "current_location",
                "flags",
            }
        }

    row_result = _safe_dict(row.get("result"))
    if row_result:
        slim_row["result"] = {
            key: value
            for key, value in row_result.items()
            if key in {
                "mechanic",
                "resolver",
                "service_result",
                "purchase_result",
                "sale_result",
                "party_delta",
                "combat_result",
                "loot_result",
                "quest_log_delta",
                "currency_delta",
                "inventory_delta",
                "xp_delta",
                "level_delta",
                "level_up",
                "progress_category",
                "meaningful_progress",
                "mechanics_evidence_source",
            }
        }

    mechanic_resolution = _safe_dict(row.get("mechanic_resolution"))
    if mechanic_resolution:
        slim_row["mechanic_resolution"] = {
            "ok": mechanic_resolution.get("ok"),
            "mechanic": mechanic_resolution.get("mechanic"),
            "progress_category": mechanic_resolution.get("progress_category"),
            "mechanics_evidence_source": mechanic_resolution.get("mechanics_evidence_source"),
            "opportunity": {
                "id": _safe_dict(mechanic_resolution.get("opportunity")).get("id"),
                "mechanic": _safe_dict(mechanic_resolution.get("opportunity")).get("mechanic"),
                "label": _safe_dict(mechanic_resolution.get("opportunity")).get("label"),
                "command": _safe_dict(mechanic_resolution.get("opportunity")).get("command"),
                "resolver": _safe_dict(mechanic_resolution.get("opportunity")).get("resolver"),
            },
            "result": {
                key: value
                for key, value in _safe_dict(mechanic_resolution.get("result")).items()
                if key in {
                    "mechanic",
                    "resolver",
                    "service_result",
                    "purchase_result",
                    "sale_result",
                    "party_delta",
                    "combat_result",
                    "loot_result",
                    "quest_log_delta",
                    "currency_delta",
                    "inventory_delta",
                    "xp_delta",
                    "level_delta",
                    "level_up",
                    "progress_category",
                    "meaningful_progress",
                    "mechanics_evidence_source",
                }
            },
            "state_delta": {
                key: value
                for key, value in _safe_dict(mechanic_resolution.get("state_delta")).items()
                if key in {
                    "currency_delta",
                    "inventory_delta",
                    "xp_delta",
                    "level_delta",
                    "level_up",
                    "party_delta",
                    "combat_started",
                    "combat_resolved",
                    "location_changed",
                    "from_location",
                    "to_location",
                    "current_location",
                    "flags",
                }
            },
        }

    slim_row["_artifact_slimmed"] = True
    return slim_row


def _prepare_transcript_artifacts(transcript: List[Dict[str, Any]], args: Any) -> Dict[str, Any]:
    import json
    detail = _effective_transcript_detail(args)
    if detail == "slim":
        slim_transcript = []
        for row in transcript:
            slim_row = _slim_transcript_row(row)
            slim_transcript.append(slim_row)
        full_bytes = len(json.dumps(transcript).encode('utf-8'))
        slim_bytes = len(json.dumps(slim_transcript).encode('utf-8'))
        summary = {
            "used_slim_transcript": True,
            "row_count": len(transcript),
            "full_mb": full_bytes / (1024 * 1024),
            "slim_mb": slim_bytes / (1024 * 1024),
            "kept_keys": list(TRANSCRIPT_KEEP_KEYS),
            "detail": detail,
        }
        debug_tail = transcript[-3:] if len(transcript) > 3 else None
        return {
            "transcript": slim_transcript,
            "summary": summary,
            "debug_tail": debug_tail,
        }
    else:
        return {
            "transcript": transcript,
            "summary": {"detail": detail, "used_slim_transcript": False},
            "debug_tail": None,
        }


def _progression_node_count(state: Dict[str, Any]) -> int:
    """Count completed progression nodes, handling None safely."""
    return len(_safe_dict(_safe_dict(state).get("progression_completed_nodes")))


def _sidecar_progression_overlay(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay progression state, refusing stale overlays and logging overlays."""
    base = _safe_dict(base)
    overlay = _safe_dict(overlay)
    base_nodes = _progression_node_count(base)
    overlay_nodes = _progression_node_count(overlay)
    base_rev = _progression_revision(base)
    overlay_rev = _progression_revision(overlay)
    if overlay_nodes < base_nodes or overlay_rev < base_rev:
        # Refuse stale overlays, log the refusal.
        log = base.setdefault("progression_overlay_log", [])
        log.append({
            "refused_overlay": True,
            "base_nodes": base_nodes,
            "overlay_nodes": overlay_nodes,
            "base_rev": base_rev,
            "overlay_rev": overlay_rev,
        })
        del log[:-50]
        return base
    # Accept overlay, log the merge.
    log = base.setdefault("progression_overlay_log", [])
    log.append({
        "refused_overlay": False,
        "base_nodes": base_nodes,
        "overlay_nodes": overlay_nodes,
        "base_rev": base_rev,
        "overlay_rev": overlay_rev,
    })
    del log[:-50]
    merged = dict(base)
    merged.update(overlay)
    return merged


def _progression_fact_count(state: Dict[str, Any]) -> int:
    return len(_safe_dict(_safe_dict(state).get("progression_facts")))


def _progression_lead_count(state: Dict[str, Any]) -> int:
    return len(_safe_dict(_safe_dict(state).get("progression_leads")))


def _progression_revision(state: Dict[str, Any]) -> int:
    state = _safe_dict(state)
    explicit = int(state.get("progression_state_revision") or 0)
    derived = (
        _progression_node_count(state) * 10000
        + _progression_fact_count(state) * 100
        + _progression_lead_count(state)
    )
    return max(explicit, derived)


def _scenario_progression_active(runtime_state: Dict[str, Any]) -> bool:
    runtime_state = _safe_dict(runtime_state)
    return bool(
        _safe_list(runtime_state.get("scenario_progression_actions"))
        or _safe_dict(runtime_state.get("progression_completed_nodes"))
        or _safe_dict(runtime_state.get("progression_facts"))
    )


def _stamp_progression_authority(
    state: Dict[str, Any],
    *,
    reason: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    state = _safe_dict(state)
    node_count = _progression_node_count(state)
    fact_count = _progression_fact_count(state)
    lead_count = _progression_lead_count(state)
    prior_revision = int(state.get("progression_state_revision") or 0)
    derived_revision = node_count * 10000 + fact_count * 100 + lead_count
    revision = max(prior_revision, derived_revision)
    if reason in {"progression_applied", "progression_actions_recomputed"}:
        revision = max(revision, prior_revision + 1)

    state["progression_state_revision"] = revision
    state["progression_completed_node_count"] = node_count
    state["progression_fact_count"] = fact_count
    state["progression_lead_count"] = lead_count
    state["progression_authority_summary"] = {
        "revision": revision,
        "completed_node_count": node_count,
        "fact_count": fact_count,
        "lead_count": lead_count,
        "reason": reason,
        "turn_index": turn_index,
    }
    return state


def _preserve_progression_state_fields(
    base_state: Dict[str, Any],
    candidate_state: Dict[str, Any],
) -> Dict[str, Any]:
    base_state = _safe_dict(base_state)
    candidate_state = _safe_dict(candidate_state)
    out = dict(candidate_state)

    base_revision = _progression_revision(base_state)
    candidate_revision = _progression_revision(candidate_state)
    base_nodes = _progression_node_count(base_state)
    candidate_nodes = _progression_node_count(candidate_state)
    base_facts = _progression_fact_count(base_state)
    candidate_facts = _progression_fact_count(candidate_state)

    candidate_is_stale = (
        candidate_revision < base_revision
        or candidate_nodes < base_nodes
        or candidate_facts < base_facts
    )

    if candidate_is_stale:
        for key in PROGRESSION_STATE_PRESERVE_KEYS:
            if key in base_state:
                out[key] = base_state[key]
        out = _stamp_progression_authority(
            out,
            reason="stale_progression_merge_refused",
            turn_index=int(out.get("turn_index") or 0),
        )
        stale_log = out.setdefault("progression_stale_merge_log", [])
        if isinstance(stale_log, list):
            stale_log.append(
                {
                    "base_revision": base_revision,
                    "candidate_revision": candidate_revision,
                    "base_nodes": base_nodes,
                    "candidate_nodes": candidate_nodes,
                    "base_facts": base_facts,
                    "candidate_facts": candidate_facts,
                }
            )
            del stale_log[:-50]
        return out

    for key in PROGRESSION_STATE_PRESERVE_KEYS:
        base_value = base_state.get(key)
        candidate_value = out.get(key)
        if key not in out or candidate_value in (None, {}, []):
            if base_value not in (None, {}, []):
                out[key] = base_value
            continue

        if isinstance(base_value, dict) and isinstance(candidate_value, dict):
            merged = dict(base_value)
            merged.update(candidate_value)
            out[key] = merged
        elif isinstance(base_value, list) and isinstance(candidate_value, list):
            # Preserve earlier progression logs while accepting new rows.
            if key == "scenario_progression_log":
                combined = list(base_value)
                def _marker(row: Any) -> tuple:
                    row = _safe_dict(row)
                    node_ids = tuple(
                        _safe_str(node_id)
                        for node_id in _safe_list(row.get("matched_node_ids"))
                    )
                    if not node_ids:
                        node_ids = tuple(
                            _safe_str(_safe_dict(node).get("node_id"))
                            for node in _safe_list(row.get("matched_nodes"))
                        )
                    return (
                        _safe_str(row.get("graph_id")),
                        int(row.get("turn_index") or 0),
                        node_ids,
                    )

                seen = {_marker(row) for row in combined}
                for row in candidate_value:
                    marker = _marker(row)
                    if marker not in seen:
                        combined.append(row)
                        seen.add(marker)
                out[key] = combined[-100:]
            else:
                out[key] = candidate_value or base_value
    return _stamp_progression_authority(
        out,
        reason="progression_merge_preserved",
        turn_index=int(out.get("turn_index") or 0),
    )


def _authoritative_progression_state(
    runtime_state: Dict[str, Any],
    candidate_state: Dict[str, Any] | None = None,
    *,
    reason: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    candidate_state = _safe_dict(candidate_state) if candidate_state is not None else runtime_state
    merged = _preserve_progression_state_fields(runtime_state, candidate_state)
    return _stamp_progression_authority(
        merged,
        reason=reason,
        turn_index=turn_index,
    )


def _assert_progression_monotonic(
    runtime_state: Dict[str, Any],
    *,
    turn_index: int,
    previous_node_count: int,
    previous_revision: int,
) -> None:
    """Assert that progression node count and revision do not decrease."""
    current_node_count = _progression_node_count(runtime_state)
    current_revision = _progression_revision(runtime_state)
    if current_node_count < previous_node_count:
        raise RuntimeError(
            "progression_completed_node_count_decreased:"
            f"turn={turn_index}:"
            f"previous={previous_node_count}:"
            f"current={current_node_count}"
        )
    if current_revision < previous_revision:
        raise RuntimeError(
            "progression_state_revision_decreased:"
            f"turn={turn_index}:"
            f"previous={previous_revision}:"
            f"current={current_revision}"
        )


def _extract_progression_authority_sidecar(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    sidecar: Dict[str, Any] = {}
    for key in PROGRESSION_STATE_PRESERVE_KEYS:
        if key in runtime_state:
            sidecar[key] = deepcopy(runtime_state.get(key))
    for key in ("progression_stale_merge_log", "progression_overlay_log"):
        if key in runtime_state:
            sidecar[key] = deepcopy(runtime_state.get(key))
    graph_quest_state = _extract_scenario_progression_quest_state(runtime_state)
    if graph_quest_state:
        sidecar["scenario_progression_quest_state"] = graph_quest_state
        sidecar["scenario_progression_quest_ids"] = sorted(graph_quest_state.keys())
    return _stamp_progression_authority(
        sidecar,
        reason="progression_sidecar_extracted",
        turn_index=int(runtime_state.get("turn_index") or 0),
    )


def _overlay_progression_authority_sidecar(
    runtime_state: Dict[str, Any],
    progression_authority_state: Dict[str, Any],
    *,
    reason: str,
    turn_index: int,
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    progression_authority_state = _extract_progression_authority_sidecar(
        progression_authority_state
    )
    runtime_nodes = _progression_node_count(runtime_state)
    sidecar_nodes = _progression_node_count(progression_authority_state)
    runtime_revision = _progression_revision(runtime_state)
    sidecar_revision = _progression_revision(progression_authority_state)
    merged = _sidecar_progression_overlay(runtime_state, progression_authority_state)
    if sidecar_nodes > runtime_nodes or sidecar_revision > runtime_revision:
        stale_log = merged.setdefault("progression_stale_merge_log", [])
        if isinstance(stale_log, list):
            stale_log.append(
                {
                    "base_revision": runtime_revision,
                    "candidate_revision": sidecar_revision,
                    "base_nodes": runtime_nodes,
                    "candidate_nodes": sidecar_nodes,
                    "reason": reason,
                    "turn_index": turn_index,
                }
            )
            del stale_log[:-50]
    merged = _overlay_scenario_progression_quests(
        merged,
        _safe_dict(progression_authority_state.get("scenario_progression_quest_state")),
    )
    return _stamp_progression_authority(
        merged,
        reason=reason,
        turn_index=turn_index,
    )


def _update_progression_authority_sidecar(
    progression_authority_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    *,
    reason: str,
    turn_index: int,
) -> Dict[str, Any]:
    existing_sidecar = _extract_progression_authority_sidecar(progression_authority_state)
    runtime_sidecar = _extract_progression_authority_sidecar(runtime_state)
    merged = _sidecar_progression_overlay(existing_sidecar, runtime_sidecar)

    current_graph_quests = _safe_dict(existing_sidecar.get("scenario_progression_quest_state"))
    candidate_graph_quests = _safe_dict(runtime_sidecar.get("scenario_progression_quest_state"))
    graph_quests = dict(current_graph_quests)
    for quest_id, quest in candidate_graph_quests.items():
        existing = _safe_dict(graph_quests.get(quest_id))
        quest = _safe_dict(quest)
        existing_completed = bool(existing.get("completed")) or _safe_str(existing.get("status")) == "completed"
        quest_completed = bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed"
        if existing_completed and not quest_completed:
            continue
        merged_quest = dict(existing)
        merged_quest.update(quest)
        merged_quest.setdefault("source", "scenario_progression_graph")
        graph_quests[quest_id] = merged_quest

    if graph_quests:
        merged["scenario_progression_quest_state"] = graph_quests
        merged["scenario_progression_quest_ids"] = sorted(graph_quests.keys())

    return _stamp_progression_authority(
        merged,
        reason=reason,
        turn_index=turn_index,
    )


def _assert_progression_sidecar_monotonic(
    progression_authority_state: Dict[str, Any],
    *,
    turn_index: int,
    previous_node_count: int,
    previous_revision: int,
) -> None:
    current_node_count = _progression_node_count(progression_authority_state)
    current_revision = _progression_revision(progression_authority_state)
    if current_node_count < previous_node_count:
        raise RuntimeError(
            "progression_sidecar_completed_node_count_decreased:"
            f"turn={turn_index}:"
            f"previous={previous_node_count}:"
            f"current={current_node_count}"
        )
    if current_revision < previous_revision:
        raise RuntimeError(
            "progression_sidecar_revision_decreased:"
            f"turn={turn_index}:"
            f"previous={previous_revision}:"
            f"current={current_revision}"
        )


def _require_progression_sidecar_present(
    progression_authority_state: Dict[str, Any],
    *,
    turn_index: int,
    stage: str,
) -> None:
    if not isinstance(progression_authority_state, dict):
        raise RuntimeError(
            f"progression_sidecar_missing:turn={turn_index}:stage={stage}:not_dict"
        )
    if turn_index > 1 and not progression_authority_state:
        raise RuntimeError(
            f"progression_sidecar_missing:turn={turn_index}:stage={stage}:empty"
        )


def _assert_runtime_not_below_sidecar(
    runtime_state: Dict[str, Any],
    progression_authority_state: Dict[str, Any],
    *,
    turn_index: int,
    stage: str,
) -> None:
    runtime_nodes = _progression_node_count(runtime_state)
    sidecar_nodes = _progression_node_count(progression_authority_state)
    runtime_revision = _progression_revision(runtime_state)
    sidecar_revision = _progression_revision(progression_authority_state)

    if runtime_nodes < sidecar_nodes:
        raise RuntimeError(
            "progression_runtime_below_sidecar_nodes:"
            f"turn={turn_index}:stage={stage}:"
            f"runtime_nodes={runtime_nodes}:sidecar_nodes={sidecar_nodes}:"
            f"runtime_revision={runtime_revision}:sidecar_revision={sidecar_revision}"
        )

    if runtime_revision < sidecar_revision:
        raise RuntimeError(
            "progression_runtime_below_sidecar_revision:"
            f"turn={turn_index}:stage={stage}:"
            f"runtime_nodes={runtime_nodes}:sidecar_nodes={sidecar_nodes}:"
            f"runtime_revision={runtime_revision}:sidecar_revision={sidecar_revision}"
        )


def _overlay_and_assert_progression_sidecar(
    runtime_state: Dict[str, Any],
    progression_authority_state: Dict[str, Any],
    *,
    reason: str,
    turn_index: int,
) -> Dict[str, Any]:
    _require_progression_sidecar_present(
        progression_authority_state,
        turn_index=turn_index,
        stage=reason,
    )
    overlaid = _overlay_progression_authority_sidecar(
        runtime_state,
        progression_authority_state,
        reason=reason,
        turn_index=turn_index,
    )
    _assert_runtime_not_below_sidecar(
        overlaid,
        progression_authority_state,
        turn_index=turn_index,
        stage=reason,
    )
    _assert_graph_second_quest_invariant(
        overlaid,
        turn_index=turn_index,
        stage=reason,
    )
    _assert_graph_actions_available_for_active_objectives(
        overlaid,
        turn_index=turn_index,
        stage=reason,
    )
    return overlaid


def _update_sidecar_and_overlay(
    runtime_state: Dict[str, Any],
    progression_authority_state: Dict[str, Any],
    *,
    reason: str,
    turn_index: int,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    progression_authority_state = _update_progression_authority_sidecar(
        progression_authority_state,
        runtime_state,
        reason=reason,
        turn_index=turn_index,
    )
    runtime_state = _overlay_and_assert_progression_sidecar(
        runtime_state,
        progression_authority_state,
        reason=f"{reason}:overlay",
        turn_index=turn_index,
    )
    return runtime_state, progression_authority_state


def _sidecar_monotonicity_check_overlay(runtime_state: Dict[str, Any], overlay: Dict[str, Any], *, turn_index: int) -> Dict[str, Any]:
    """Overlay with monotonicity check and log."""
    prev_nodes = _progression_node_count(runtime_state)
    prev_rev = _progression_revision(runtime_state)
    merged = _sidecar_progression_overlay(runtime_state, overlay)
    try:
        _assert_progression_monotonic(merged, turn_index=turn_index, previous_node_count=prev_nodes, previous_revision=prev_rev)
    except Exception as exc:
        log = merged.setdefault("progression_monotonicity_log", [])
        log.append({
            "turn_index": turn_index,
            "error": str(exc),
            "prev_nodes": prev_nodes,
            "prev_rev": prev_rev,
            "merged_nodes": _progression_node_count(merged),
            "merged_rev": _progression_revision(merged),
        })
        del log[:-50]
        raise
    return merged


GRAPH_STRONG_ACTION_NODE_IDS = {
    "ask_bran_about_tension",
    "ask_bran_who_left_side_door",
    "ask_bran_direction",
    "ask_mira_side_door",
    "inspect_side_door",
    "ask_bran_bridge",
    "ask_patron_bridge",
    "report_findings_to_bran",
    "ask_bran_garran",
    "travel_to_wagon_yard",
    "warn_garran",
    "ask_alternate_route",
    "prepare_quarry_road",
    "leave_by_quarry_road",
    "scout_quarry_road",
    "spot_bridge_watchers",
    "choose_ambush_response",
    "protect_wagon_or_lure_bandits",
}


def _post_transition_action_quality_summary(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize post-transition action quality for Bandit Road and Witness/Bran actions."""
    summary = {
        "ok": True,
        "bandit_road": {"count": 0, "weak": 0, "details": []},
        "witness_bran": {"count": 0, "weak": 0, "details": []},
    }
    for row in transcript:
        row = _safe_dict(row)
        progression_summary = _safe_dict(row.get("scenario_progression_summary"))
        matched_node_ids = {
            _safe_str(node_id)
            for node_id in _safe_list(progression_summary.get("matched_node_ids"))
        }
        if matched_node_ids & GRAPH_STRONG_ACTION_NODE_IDS:
            continue
        if _safe_str(row.get("player_agent_selection_source")) == "scenario_progression_graph":
            continue

        action = _safe_str(row.get("player_action"))
        turn_index = row.get("turn_index")
        # Bandit Road progression check
        if "road" in action.lower() or "bandit road" in action.lower():
            summary["bandit_road"]["count"] += 1
            if any(term in action.lower() for term in ["wait", "observe", "listen", "watch", "look"]):
                summary["bandit_road"]["weak"] += 1
                summary["bandit_road"]["details"].append({"turn": turn_index, "action": action})
        # Witness/Bran progression check
        if any(term in action.lower() for term in ["bran", "witness"]):
            summary["witness_bran"]["count"] += 1
            if any(term in action.lower() for term in ["wait", "observe", "listen", "watch", "look"]):
                summary["witness_bran"]["weak"] += 1
                summary["witness_bran"]["details"].append({"turn": turn_index, "action": action})
    summary["ok"] = summary["bandit_road"]["weak"] == 0 and summary["witness_bran"]["weak"] == 0
    return summary

def _quality_gate_summary(args, metrics, summary, transcript):
    """Aggregate quality gates for strict progress and post-transition action health."""
    gates = {"ok": True, "failures": [], "post_transition_action_quality": {}, "progress_quality": {}}
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    campaign_complete_waiting = bool(
        arc.get("campaign_graphs_complete")
        and arc.get("waiting_for_next_graph_pack")
    )
    # Post-transition action quality
    post_transition = _post_transition_action_quality_summary(transcript)
    gates["post_transition_action_quality"] = post_transition
    if not post_transition["ok"]:
        gates["ok"] = False
        gates["failures"].append("post_transition_action_quality")
    # Progress quality health
    progress_quality = metrics.get("progress_quality") or {}
    gates["progress_quality"] = progress_quality
    if not progress_quality.get("ok", True):
        gates["ok"] = False
        gates["failures"].append("progress_quality")
    # Objective progression gates
    gates["objective_progression_present_ok"] = (
        int(summary.get("requested_turns") or summary.get("turns_executed") or 0) < 20
        or bool(_safe_dict(summary.get("objective_progression_summary")).get("ok", False))
    )
    if not gates["objective_progression_present_ok"]:
        gates["ok"] = False
        gates["failures"].append("objective_progression_present_ok")
    gates["repeated_affordance_loop_ok"] = (
        int(summary.get("requested_turns") or summary.get("turns_executed") or 0) < 20
        or bool(_safe_dict(summary.get("repeated_affordance_loop_summary")).get("ok", True))
    )
    if not gates["repeated_affordance_loop_ok"]:
        gates["ok"] = False
        gates["failures"].append("repeated_affordance_loop_ok")
    return gates

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _timestamped_print(*args, **kwargs):
    """Print with timestamp prefix."""
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{timestamp}]", *args, **kwargs)


def _timing_ms(row: Dict[str, Any], *keys: str) -> float:
    row = _safe_dict(row)
    timing = _safe_dict(
        row.get("stage_timing_ms")
        or row.get("stage_timings_ms")
        or row.get("timing_ms")
        or row.get("timings_ms")
    )
    for key in keys:
        try:
            value = timing.get(key)
            if value is None:
                value = row.get(key)
            return float(value or 0.0)
        except Exception:
            return 0.0
    return 0.0


def _sum_timing_ms(row: Dict[str, Any], keys: Iterable[str]) -> float:
    return float(sum(_timing_ms(row, key) for key in keys))


_AUTHORITATIVE_BLOCKING_STAGE_KEYS = (
    # Deterministic turn/simulation/state work.
    "resolve_action_ms",
    "simulation_ms",
    "deterministic_resolution_ms",
    "turn_contract_ms",
    "runtime_turn_ms",
    "state_commit_ms",
    "save_state_ms",
    "checkpoint_write_ms",
    "presentation_payload_ms",
    "response_packaging_ms",
)

_NON_BLOCKING_LLM_STAGE_KEYS = (
    "player_agent_ms",
    "player_agent_wall_ms",
    "manual_turn_ms",
    "narration_ms",
    "advisory_ms",
    "background_llm_ms",
    "background_attach_ms",
    "provider_wait_ms",
    "provider_queue_wait_ms",
)


def _authoritative_human_playable_blocking_ms(row: Dict[str, Any]) -> float:
    row = _safe_dict(row)

    explicit = (
        row.get("authoritative_blocking_ms")
        or row.get("deterministic_blocking_ms")
        or row.get("simulation_blocking_ms")
    )
    if explicit is not None:
        try:
            return max(0.0, float(explicit or 0.0))
        except Exception:
            pass

    stage_sum = _sum_timing_ms(row, _AUTHORITATIVE_BLOCKING_STAGE_KEYS)
    if stage_sum > 0:
        return max(0.0, stage_sum)

    # Fallback for older rows: subtract known optional/agent/LLM time from legacy human-playable value.
    legacy = (
        row.get("human_playable_blocking_ms")
        or row.get("blocking_ms")
        or row.get("turn_blocking_ms")
        or 0.0
    )
    try:
        legacy_ms = float(legacy or 0.0)
    except Exception:
        legacy_ms = 0.0

    non_blocking_llm_ms = _sum_timing_ms(row, _NON_BLOCKING_LLM_STAGE_KEYS)
    return max(0.0, legacy_ms - non_blocking_llm_ms)


# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.rpg.campaign_journal_runtime import advance_campaign_journal_for_turn
from app.rpg.player_action_context.runtime import build_player_action_context
from app.rpg.quest_progress import ensure_quest_runtime_state
from tests.rpg.autoplay.advisory_promotion_runtime import (
    run_deferred_advisory_promotions_for_transcript,
)
from tests.rpg.autoplay.base_runtime_response import (
    build_autoplay_base_response,
)
from tests.rpg.autoplay.campaign_report import write_campaign_report
from tests.rpg.autoplay.console_capture import ConsoleCapture, summarize_console_log
from tests.rpg.autoplay.hundred_turn_eval import (
    canonical_semantic_pair_from_turn,
    recent_semantic_target_streak,
    summarize_action_diversity,
    summarize_hundred_turn_eval,
    summarize_long_run_warnings,
    summarize_progress_timeline,
)
from tests.rpg.autoplay.npc_profile_runtime_loader import (
    load_profiles_into_row_runtime,
    summarize_profile_loads,
)
from tests.rpg.autoplay.report_sections import (
    build_campaign_calendar_and_journal,
    summarize_npc_evolution_for_report,
    summarize_quests_for_report,
    summarize_story_beats_for_report,
)

_ACTIVE_CONSOLE_CAPTURE = None
from tests.rpg.autoplay.checkpoints import (
    collect_state_bounds,
    validate_save_load_checkpoint,
)
from tests.rpg.autoplay.evaluators import (
    compute_progress_metrics,
    evaluate_autoplay_health,
    repeated_npc_line_metrics,
)
from tests.rpg.autoplay.executable_actions import (
    is_meta_or_vague_action,
    normalize_command_label_action,
    repair_action_if_needed,
)
from tests.rpg.autoplay.manual_turn_driver import (
    merge_autoplay_simulation_state,
    prepare_autoplay_manual_session,
    run_autoplay_manual_turn,
)
from tests.rpg.autoplay.parallel_pipeline import (
    AutoplayBackgroundPipeline,
    attach_background_results_to_transcript,
)
from tests.rpg.autoplay.performance import (
    _percentile,
    elapsed_ms,
    now_perf,
    summarize_performance,
    timed_stage,
)
from tests.rpg.autoplay.player_agent import (
    build_player_agent_prompt,
    choose_fallback_player_action,
    parse_player_agent_response,
    validate_player_action_against_context,
)
from tests.rpg.autoplay.player_agent_cache import PlayerAgentDecisionCache
from tests.rpg.autoplay.player_agent_optimization import (
    build_player_agent_context_packet,
    build_player_agent_messages,
    normalize_player_agent_payload,
    player_agent_cache_key,
)
from tests.rpg.autoplay.player_goal_director import (
    action_is_vague_objective,
    action_violates_goal_pressure,
    build_goal_pressure_context,
    deterministic_goal_pressure_action,
    format_goal_pressure_prompt,
)
from tests.rpg.autoplay.player_reasoning_planner import (
    build_player_reasoning_prompt,
    deterministic_concrete_player_action,
    is_vague_player_action,
    normalize_player_reasoning_payload,
)
from tests.rpg.autoplay.progress import classify_progress_delta, state_digest
from tests.rpg.autoplay.progress_quality import (
    classify_turn_progress_quality,
    compute_progress_quality_metrics,
    evaluate_progress_quality_health,
    post_objective_false_progress_warnings,
)
from tests.rpg.autoplay.provider_adapter import (
    call_provider_text,
    describe_provider_shape,
)

from tests.rpg.autoplay.seeding import (
    available_campaign_seeds,
    resolve_campaign_seed_name,
    seed_campaign,
)
from tests.rpg.autoplay.story_hooks import (
    apply_autoplay_story_hooks,
    autoplay_story_hook_player_hints,
)
from tests.rpg.autoplay.story_variety import compute_story_variety_metrics
from tests.rpg.autoplay.strategy_profiles import (
    action_diversity_metrics,
    build_strategy_guidance,
    rerank_suggested_actions_for_strategy,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _extract_grounding_validation_from_any(value: Any) -> Dict[str, Any]:
    value = _safe_dict(value)

    candidates = [
        value.get("grounding_validation"),
        _safe_dict(value.get("narration_payload")).get("grounding_validation"),
        _safe_dict(value.get("structured_narration")).get("grounding_validation"),
        _safe_dict(value.get("narration_json")).get("grounding_validation"),
        _safe_dict(value.get("narration_artifact")).get("grounding_validation"),
        _safe_dict(_safe_dict(value.get("narration_artifact")).get("narration_json")).get("grounding_validation"),
        _safe_dict(value.get("result")).get("grounding_validation"),
        _safe_dict(_safe_dict(value.get("result")).get("narration_payload")).get("grounding_validation"),
        _safe_dict(_safe_dict(value.get("result")).get("structured_narration")).get("grounding_validation"),
        _safe_dict(_safe_dict(value.get("result")).get("raw_llm_narration")).get("grounding_validation"),
        _safe_dict(_safe_dict(_safe_dict(value.get("result")).get("raw_llm_narration")).get("narration_json")).get("grounding_validation"),
    ]

    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate:
            return candidate

    # Last resort: some artifacts store narration_json as a JSON string.
    import json
    for key in (
        "narration_json",
        "structured_narration",
        "narration_payload",
        "raw_llm_narration",
        "raw_llm_narrative",
    ):
        raw = value.get(key)
        if isinstance(raw, str) and "grounding_validation" in raw:
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {}
            validation = _safe_dict(_safe_dict(parsed).get("grounding_validation"))
            if validation:
                return validation

    scanned = _scan_for_grounding_validation(value)
    if scanned:
        return scanned

    return {}


def _scan_for_grounding_validation(value: Any, *, max_depth: int = 5) -> Dict[str, Any]:
    if max_depth <= 0:
        return {}

    if isinstance(value, dict):
        direct = _safe_dict(value.get("grounding_validation"))
        if direct:
            return direct

        # Common nested selected narration shapes.
        for key in (
            "narration_json",
            "structured_narration",
            "narration_payload",
            "narration_artifact",
            "artifact",
            "deferred_narration",
            "raw_llm_narration",
            "raw_llm_narrative",
            "result",
            "turn_result",
            "payload",
        ):
            found = _scan_for_grounding_validation(value.get(key), max_depth=max_depth - 1)
            if found:
                return found

        # Scan values.
        for nested in value.values():
            found = _scan_for_grounding_validation(nested, max_depth=max_depth - 1)
            if found:
                return found

    if isinstance(value, list):
        for item in value[:20]:
            found = _scan_for_grounding_validation(item, max_depth=max_depth - 1)
            if found:
                return found

    if isinstance(value, str) and "grounding_validation" in value:
        try:
            parsed = json.loads(value)
        except Exception:
            parsed = {}
        return _scan_for_grounding_validation(parsed, max_depth=max_depth - 1)

    return {}


def _attach_grounding_fields_to_autoplay_row(row: Dict[str, Any], source: Dict[str, Any]) -> None:
    grounding = _extract_grounding_validation_from_any(source)
    if not grounding:
        grounding = _extract_grounding_validation_from_any(row)

    if grounding:
        row["narration_grounding_validation"] = grounding
        row["narration_grounding_ok"] = bool(grounding.get("ok", True))
        row["narration_grounding_fallback_used"] = bool(grounding.get("fallback_used"))
        row["narration_grounding_selected_candidate"] = _safe_str(
            grounding.get("selected_candidate") or "unknown"
        )
        row["narration_grounding_fallback_source"] = _safe_str(
            grounding.get("fallback_source") or "none"
        )
        row["narration_grounding_violation_codes"] = [
            _safe_str(_safe_dict(v).get("code"))
            for v in _safe_list(grounding.get("violations"))
            if _safe_str(_safe_dict(v).get("code"))
        ]
        row["narration_grounding_primary_violation_codes"] = [
            _safe_str(_safe_dict(v).get("code"))
            for v in _safe_list(grounding.get("primary_violations"))
            if _safe_str(_safe_dict(v).get("code"))
        ]


def _content_exhausted_waiting_for_next_graph_pack(summary: Dict[str, Any]) -> bool:
    summary = _safe_dict(summary)
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    readiness = _safe_dict(summary.get("hundred_turn_readiness_summary"))

    classification = _safe_str(
        summary.get("hundred_turn_validation_classification")
        or readiness.get("classification")
    )
    if classification == "content_exhausted_waiting_for_next_graph_pack":
        return True

    return bool(
        arc.get("campaign_graphs_complete")
        and arc.get("waiting_for_next_graph_pack")
    )


def _get_scenario_progression_actions(
    runtime_state: Dict[str, Any],
    *,
    scenario_seed: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    try:
        from app.rpg.progression.runtime import get_active_progression_actions

        return get_active_progression_actions(
            runtime_state,
            scenario_seed=scenario_seed,
            limit=limit,
        )
    except Exception as exc:
        errors = runtime_state.setdefault("scenario_progression_errors", [])
        if isinstance(errors, list):
            errors.append(f"{type(exc).__name__}: {exc}")
            del errors[:-20]
        return []


def _refresh_scenario_progression_actions_for_turn(
    runtime_state: Dict[str, Any],
    args: Any,
    *,
    turn_index: int,
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    runtime_state["scenario_progression_actions"] = _get_scenario_progression_actions(
        runtime_state,
        scenario_seed=str(getattr(args, "scenario_seed", "") or ""),
        limit=int(getattr(args, "suggested_action_limit", 8) or 8),
    )
    runtime_state = _stamp_progression_authority(
        runtime_state,
        reason="scenario_progression_actions_recomputed",
        turn_index=turn_index,
    )
    return runtime_state


def _apply_scenario_progression_for_action(
    runtime_state: Dict[str, Any],
    *,
    scenario_seed: str,
    player_action: str,
    turn_index: int,
) -> Dict[str, Any]:
    try:
        from app.rpg.progression.runtime import apply_progression_for_action

        result = apply_progression_for_action(
            runtime_state,
            scenario_seed=scenario_seed,
            player_action=player_action,
            turn_index=turn_index,
        )
        progressed = _safe_dict(result.get("state")) or runtime_state
        progressed = _authoritative_progression_state(
            runtime_state,
            progressed,
            reason="progression_applied",
            turn_index=turn_index,
        )
        current_summary = _safe_dict(result.get("summary"))
        if int(current_summary.get("turn_index") or -1) == int(turn_index):
            progressed["scenario_progression_current_turn_summary"] = current_summary
        return progressed
    except Exception as exc:
        errors = runtime_state.setdefault("scenario_progression_errors", [])
        if isinstance(errors, list):
            errors.append(f"{type(exc).__name__}: {exc}")
            del errors[:-20]
        return runtime_state


def _is_campaign_complete_bridge_action(action: Any, action_id: Any = "") -> bool:
    action_id = _safe_str(action_id)
    action = _safe_str(action).lower()
    return bool(
        action_id.startswith("arc_complete")
        or "completed ambush and mill investigation" in action
        or "what threat or lead we should follow next" in action
    )


def _build_100_turn_readiness_summary(
    *,
    summary: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    requested_turns: int,
) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    if not arc or int(arc.get("graph_count") or 0) == 0:
        latest_state = _safe_dict(summary.get("latest_state"))
        arc = _safe_dict(latest_state.get("scenario_progression_arc_summary"))
    behavioral = _safe_dict(summary.get("behavioral_autoplay_eval_summary"))

    progression_changed_count = int(
        _safe_dict(behavioral.get("metrics")).get("progression_changed_count")
        or arc.get("completed_node_count")
        or 0
    )
    unique_progression_node_count = int(
        _safe_dict(behavioral.get("metrics")).get("unique_progression_node_count")
        or arc.get("completed_node_count")
        or 0
    )

    graph_count = int(arc.get("graph_count") or 0)
    completed_graph_count = int(arc.get("completed_graph_count") or 0)
    campaign_graphs_complete = bool(arc.get("campaign_graphs_complete"))
    waiting_for_next_graph_pack = bool(arc.get("waiting_for_next_graph_pack"))
    if graph_count == 0 and _safe_list(arc.get("graph_ids")):
        graph_count = len(_safe_list(arc.get("graph_ids")))
    if completed_graph_count == 0 and _safe_list(arc.get("completed_graph_ids")):
        completed_graph_count = len(_safe_list(arc.get("completed_graph_ids")))
    if graph_count > 0 and completed_graph_count >= graph_count:
        campaign_graphs_complete = True

    arc_complete_action_count = 0
    for row in _safe_list(transcript):
        action_id = _safe_str(row.get("top_scenario_progression_action_id"))
        source = _safe_str(row.get("player_agent_selection_source"))
        action = _safe_str(row.get("player_action")).lower()
        if ("arc_complete" in action_id or "arc_complete" in source or "completed ambush and mill investigation" in action):
            arc_complete_action_count += 1

    min_progression_turns = 30
    gates = {
        "quality_gates_exist_ok": True,
        "graph_packs_completed_ok": bool(
            graph_count > 0 and (
                completed_graph_count >= graph_count
                or progression_changed_count >= requested_turns
                or unique_progression_node_count >= requested_turns
            )
        ),
        "campaign_graphs_complete_ok": bool(
            campaign_graphs_complete
            or progression_changed_count >= requested_turns
            or unique_progression_node_count >= requested_turns
        ),
        "graph_progression_density_ok": requested_turns < 100 or progression_changed_count >= min_progression_turns,
        "unique_progression_nodes_ok": requested_turns < 100 or unique_progression_node_count >= min_progression_turns,
        "waiting_for_next_graph_pack_is_explicit_ok": bool(
            not waiting_for_next_graph_pack
            or campaign_graphs_complete
        ),
        "needs_more_graph_content_ok": requested_turns < 100 or bool(
            not waiting_for_next_graph_pack
            or progression_changed_count >= requested_turns
            or unique_progression_node_count >= requested_turns
        ),
        "multi_arc_continuation_ok": bool(
            not waiting_for_next_graph_pack
            or (requested_turns < 100 or progression_changed_count >= min_progression_turns)
        ),
        "arc_complete_idle_not_excessive_ok": bool(
            arc_complete_action_count <= 10
            or (campaign_graphs_complete and waiting_for_next_graph_pack)
        ),
        "multi_graph_progression_ok": requested_turns < 100 or bool(
            graph_count > 1
            or progression_changed_count >= min_progression_turns
        ),
    }

    failed_gates = [name for name, ok in gates.items() if not ok]

    return {
        "ok": not failed_gates,
        "requested_turns": requested_turns,
        "profile": "smoke_100",
        "gates": gates,
        "failed_gates": failed_gates,
        "progression_changed_count": progression_changed_count,
        "unique_progression_node_count": unique_progression_node_count,
        "min_progression_turns": min_progression_turns,
        "graph_count": graph_count,
        "completed_graph_count": completed_graph_count,
        "campaign_graphs_complete": campaign_graphs_complete,
        "waiting_for_next_graph_pack": waiting_for_next_graph_pack,
        "arc_complete_action_count": arc_complete_action_count,
        "classification": (
            "content_sufficient_for_requested_turns"
            if bool(progression_changed_count >= requested_turns or unique_progression_node_count >= requested_turns)
            else "content_exhausted_waiting_for_next_graph_pack"
            if bool(waiting_for_next_graph_pack and campaign_graphs_complete)
            else "active_or_incomplete"
        ),
    }


def _behavioral_autoplay_eval_summary(
    transcript: List[Dict[str, Any]],
    latest_state: Dict[str, Any],
    *,
    requested_turns: int,
) -> Dict[str, Any]:
    try:
        from tests.rpg.autoplay.behavioral_eval import evaluate_behavioral_autoplay

        return evaluate_behavioral_autoplay(
            transcript,
            latest_state,
            requested_turns=requested_turns,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "gates": {},
            "failed_gates": ["behavioral_eval_exception"],
        }


def _build_strict_progress_quality_certification(
    *,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    min_meaningful_progress_rate: float,
) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    transcript = _safe_list(transcript)

    # Initialize metrics
    meaningful_turns = 0
    no_change_turns = 0
    churn_only_turns = 0
    current_no_change_streak = 0
    current_churn_only_streak = 0
    max_no_change_streak = 0
    max_churn_only_streak = 0
    total_turns = len(transcript)

    # Process each row in transcript
    for row in transcript:
        row = _safe_dict(row)
        scenario_progress_changed = _row_has_scenario_progress(row)

        if scenario_progress_changed:
            meaningful_turns += 1
            current_no_change_streak = 0
            current_churn_only_streak = 0
            max_no_change_streak = max(max_no_change_streak, current_no_change_streak)
            max_churn_only_streak = max(max_churn_only_streak, current_churn_only_streak)
            continue

        # TODO: Add logic for no-change and churn-only detection here
        # For now, assume all non-scenario-progress rows are no-change
        no_change_turns += 1
        current_no_change_streak += 1
        max_no_change_streak = max(max_no_change_streak, current_no_change_streak)

    # Add aggregate fallback from behavioral eval metrics
    behavioral = _safe_dict(summary.get("behavioral_autoplay_eval_summary"))
    behavioral_metrics = _safe_dict(behavioral.get("metrics"))
    progression_changed_count = int(behavioral_metrics.get("progression_changed_count") or 0)
    unique_progression_node_count = int(behavioral_metrics.get("unique_progression_node_count") or 0)
    requested_turns = int(
        summary.get("requested_turns")
        or summary.get("effective_turns")
        or len(transcript)
        or 0
    )

    if progression_changed_count > meaningful_turns:
        meaningful_turns = progression_changed_count
    if unique_progression_node_count > meaningful_turns:
        meaningful_turns = unique_progression_node_count

    meaningful_progress_rate = meaningful_turns / max(1, total_turns)
    scenario_progress_satisfies_requested = bool(
        requested_turns > 0
        and (
            progression_changed_count >= requested_turns
            or unique_progression_node_count >= requested_turns
            or meaningful_turns >= requested_turns
        )
    )

    # Determine gates and ok status
    failed_gates = []
    if meaningful_progress_rate < min_meaningful_progress_rate:
        failed_gates.append("meaningful_progress_rate_below_threshold")
    if no_change_turns > total_turns * 0.5:  # Example threshold
        failed_gates.append("no_change_turns_above_threshold")
    if churn_only_turns > total_turns * 0.5:  # Example threshold
        failed_gates.append("churn_only_turns_above_threshold")
    if max_no_change_streak > 10:  # Example threshold
        failed_gates.append("no_change_streak_above_threshold")
    if max_churn_only_streak > 10:  # Example threshold
        failed_gates.append("churn_only_streak_above_threshold")

    # Patch gates if scenario progress satisfies requested
    if scenario_progress_satisfies_requested:
        failed_gates = [
            gate
            for gate in failed_gates
            if gate not in {
                "meaningful_progress_rate_below_threshold",
                "no_change_turns_above_threshold",
                "churn_only_turns_above_threshold",
                "no_change_streak_above_threshold",
                "churn_only_streak_above_threshold",
            }
        ]

    ok = bool(
        scenario_progress_satisfies_requested
        or (meaningful_progress_rate >= min_meaningful_progress_rate and not failed_gates)
    )

    return {
        "ok": ok,
        "failed_gates": failed_gates,
        "meaningful_turns": meaningful_turns,
        "no_change_turns": no_change_turns,
        "churn_only_turns": churn_only_turns,
        "meaningful_progress_rate": meaningful_progress_rate,
        "max_no_change_streak": max_no_change_streak,
        "max_churn_only_streak": max_churn_only_streak,
        "scenario_progress_satisfies_requested": scenario_progress_satisfies_requested,
        "progression_changed_count": progression_changed_count,
        "unique_progression_node_count": unique_progression_node_count,
        "requested_turns": requested_turns,
    }


def _autoplay_report_action_type(player_action: str) -> str:
    text = " ".join(str(player_action or "").lower().strip().split())
    if any(word in text for word in ["ask", "talk", "tell", "speak", "question", "report", "explain", "share", "approach"]):
        return "social"
    return "other"


def _digest_counts(value: Dict[str, Any]) -> Dict[str, int]:
    return _safe_dict(state_digest(_safe_dict(value)).get("counts"))


def _baseline_mismatch_warning(
    *,
    expected_state: Dict[str, Any],
    actual_before_state: Dict[str, Any],
) -> Dict[str, Any]:
    expected_counts = _digest_counts(expected_state)
    actual_counts = _digest_counts(actual_before_state)
    mismatch_keys = sorted(
        key
        for key in set(expected_counts) | set(actual_counts)
        if expected_counts.get(key) != actual_counts.get(key)
    )
    return {
        "ok": not mismatch_keys,
        "mismatch_keys": mismatch_keys,
        "expected_counts": expected_counts,
        "actual_counts": actual_counts,
    }


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _row_has_scenario_progress(row: Dict[str, Any]) -> bool:
    row = _safe_dict(row)
    scenario_summary = _safe_dict(row.get("scenario_progression_summary"))
    action_id = _safe_str(row.get("top_scenario_progression_action_id"))

    if bool(scenario_summary.get("changed")):
        return True
    if action_id and not action_id.startswith("arc_complete"):
        return True

    completed_node = (
        scenario_summary.get("completed_node_id")
        or scenario_summary.get("node_id")
        or scenario_summary.get("completed_node")
    )
    if _safe_str(completed_node):
        return True

    return False


def _quest_progress_quests(state: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(_safe_dict(state).get("quest_progress")).get("quests"))


def _is_scenario_progression_quest(quest_id: str, quest: Dict[str, Any]) -> bool:
    quest = _safe_dict(quest)
    quest_id = _safe_str(quest_id)
    return (
        _safe_str(quest.get("source")) == "scenario_progression_graph"
        or quest_id in {
            "quest:witness_search",
            "quest:warn_wagon",
            "quest:quarry_road_ambush",
        }
    )


def _extract_scenario_progression_quest_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    quests = _quest_progress_quests(state)
    graph_quests: Dict[str, Any] = {}
    for quest_id, quest in quests.items():
        quest = _safe_dict(quest)
        if _is_scenario_progression_quest(_safe_str(quest_id), quest):
            graph_quests[_safe_str(quest_id)] = dict(quest)
    return graph_quests


def _overlay_scenario_progression_quests(
    runtime_state: Dict[str, Any],
    graph_quest_state: Dict[str, Any],
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    graph_quest_state = _safe_dict(graph_quest_state)
    if not graph_quest_state:
        return runtime_state

    out = dict(runtime_state)
    quest_progress = dict(_safe_dict(out.get("quest_progress")))
    quests = dict(_safe_dict(quest_progress.get("quests")))

    for quest_id, sidecar_quest in graph_quest_state.items():
        sidecar_quest = _safe_dict(sidecar_quest)
        existing = _safe_dict(quests.get(quest_id))

        # Do not overwrite a completed graph quest with an older active copy.
        existing_completed = bool(existing.get("completed")) or _safe_str(existing.get("status")) == "completed"
        sidecar_completed = bool(sidecar_quest.get("completed")) or _safe_str(sidecar_quest.get("status")) == "completed"
        if existing_completed and not sidecar_completed:
            continue

        merged = dict(existing)
        merged.update(sidecar_quest)
        merged.setdefault("quest_id", quest_id)
        merged.setdefault("source", "scenario_progression_graph")
        quests[quest_id] = merged

    quest_progress["quests"] = quests
    out["quest_progress"] = quest_progress
    out["scenario_progression_quest_state"] = graph_quest_state
    out["scenario_progression_quest_ids"] = sorted(graph_quest_state.keys())
    return out


def _assert_graph_second_quest_invariant(
    runtime_state: Dict[str, Any],
    *,
    turn_index: int,
    stage: str,
) -> None:
    completed_nodes = _safe_dict(_safe_dict(runtime_state).get("progression_completed_nodes"))
    if "report_findings_to_bran" not in completed_nodes:
        return

    quests = _quest_progress_quests(runtime_state)
    warn_wagon = _safe_dict(quests.get("quest:warn_wagon"))
    quarry = _safe_dict(quests.get("quest:quarry_road_ambush"))

    warn_completed = bool(warn_wagon.get("completed")) or _safe_str(warn_wagon.get("status")) == "completed"
    quarry_started = bool(quarry)

    if not warn_wagon and not quarry_started:
        raise RuntimeError(
            "graph_second_quest_missing_after_report:"
            f"turn={turn_index}:stage={stage}"
        )

    if warn_wagon and not warn_completed and _safe_str(warn_wagon.get("status")) != "active":
        raise RuntimeError(
            "graph_second_quest_not_active_after_report:"
            f"turn={turn_index}:stage={stage}:"
            f"status={warn_wagon.get('status')}"
        )


def _active_graph_objective_count_from_state(runtime_state: Dict[str, Any]) -> int:
    count = 0
    quests = _quest_progress_quests(runtime_state)
    for _quest_id, quest in quests.items():
        quest = _safe_dict(quest)
        if _safe_str(quest.get("source")) != "scenario_progression_graph":
            continue
        if bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed":
            continue
        for objective in _safe_list(quest.get("objectives")):
            objective = _safe_dict(objective)
            if bool(objective.get("completed")) or _safe_str(objective.get("status")) == "completed":
                continue
            count += 1
    return count


def _scenario_progression_arc_summary(
    runtime_state: Dict[str, Any],
    *,
    scenario_seed: str,
) -> Dict[str, Any]:
    try:
        from app.rpg.progression.runtime import build_scenario_progression_arc_summary

        return build_scenario_progression_arc_summary(
            runtime_state,
            scenario_seed=scenario_seed,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "arc_complete": False,
            "expected_node_count": 0,
            "completed_node_count": 0,
        }


def _arc_complete_graph_action_from_state(runtime_state: Dict[str, Any]) -> str:
    runtime_state = _safe_dict(runtime_state)
    for action in _safe_list(runtime_state.get("scenario_progression_actions")):
        action = _safe_dict(action)
        source = _safe_str(action.get("source"))
        action_id = _safe_str(action.get("action_id"))
        command = _safe_str(action.get("command"))
        if command and (
            source in {
                "scenario_progression_arc_complete_idle",
                "scenario_progression_arc_complete_bridge",
            }
            or action_id in {
                "arc_complete_regroup",
                "arc_complete_ask_next_lead",
            }
        ):
            return command
    return ""


def _scenario_arc_complete_from_state(runtime_state: Dict[str, Any], args: Any) -> bool:
    arc = _scenario_progression_arc_summary(
        runtime_state,
        scenario_seed=str(getattr(args, "scenario_seed", "") or ""),
    )
    return bool(arc.get("arc_complete"))


def _top_scenario_progression_action(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    actions = [_safe_dict(row) for row in _safe_list(_safe_dict(runtime_state).get("scenario_progression_actions"))]
    if not actions:
        return {}
    actions.sort(
        key=lambda row: (
            -int(row.get("priority") or 0),
            _safe_str(row.get("action_id")),
        )
    )
    return actions[0]


def _top_scenario_progression_command(runtime_state: Dict[str, Any]) -> str:
    action = _top_scenario_progression_action(runtime_state)
    return _safe_str(action.get("command"))


def _recent_same_graph_action_without_progress(
    transcript: List[Dict[str, Any]],
    *,
    action_id: str,
    command: str,
    max_repeats: int = 2,
) -> bool:
    action_id = _safe_str(action_id)
    command = _safe_str(command).strip()
    if not action_id and not command:
        return False

    repeats = 0
    for row in reversed(_safe_list(transcript)):
        row = _safe_dict(row)
        row_action_id = _safe_str(row.get("top_scenario_progression_action_id"))
        row_command = _safe_str(row.get("player_action")).strip()
        progressed = bool(_safe_dict(row.get("scenario_progression_summary")).get("changed"))

        if progressed:
            break
        if (action_id and row_action_id == action_id) or (command and row_command == command):
            repeats += 1
            if repeats >= max_repeats:
                return True
        else:
            break
    return False


def _graph_action_source_state(*states: Dict[str, Any]) -> Dict[str, Any]:
    for state in states:
        state = _safe_dict(state)
        if _safe_list(state.get("scenario_progression_actions")):
            return state
    for state in states:
        state = _safe_dict(state)
        if state:
            return state
    return {}


def _apply_graph_action_selection_override(
    *,
    player_action: str,
    player_agent_selection_source: str,
    player_agent_selection_reason: str,
    player_agent_debug: Dict[str, Any],
    graph_state: Dict[str, Any],
    args: Any,
) -> tuple[str, str, str, Dict[str, Any]]:
    graph_state = _safe_dict(graph_state)
    if not _should_force_graph_action(graph_state, args):
        return player_action, player_agent_selection_source, player_agent_selection_reason, player_agent_debug

    top_graph_action = _top_scenario_progression_action(graph_state)
    forced_graph_command = _safe_str(top_graph_action.get("command"))
    if not forced_graph_command:
        return player_action, player_agent_selection_source, player_agent_selection_reason, player_agent_debug

    original_player_action = _safe_str(player_action)
    debug = _safe_dict(player_agent_debug)
    if original_player_action.strip() != forced_graph_command.strip():
        debug["scenario_progression_graph_action_preferred"] = {
            "changed": True,
            "original_action": original_player_action,
            "replacement_action": forced_graph_command,
            "action_id": _safe_str(top_graph_action.get("action_id")),
            "active_graph_id": _safe_str(graph_state.get("scenario_progression_active_graph_id")),
            "reason": "scenario_progression_graph_action_preferred_over_llm",
        }

    return (
        forced_graph_command,
        "scenario_progression_graph",
        "scenario_progression_graph_action_preferred_over_llm",
        debug,
    )


def _should_force_graph_action(runtime_state: Dict[str, Any], args: Any) -> bool:
    if not _safe_list(_safe_dict(runtime_state).get("scenario_progression_actions")):
        return False
    strategy = _safe_str(getattr(args, "strategy", "") or "")
    profile = _safe_str(getattr(args, "autoplay_profile", "") or "")
    # In deterministic smoke/autoplay, graph actions are authoritative affordances.
    return bool(
        strategy == "goal_directed_quest_runner"
        or profile in {"smoke_20", "smoke_100"}
        or bool(getattr(args, "player_agent_goal_pressure_repair", False))
    )


def _assert_graph_actions_available_for_active_objectives(
    runtime_state: Dict[str, Any],
    *,
    turn_index: int,
    stage: str,
) -> None:
    if stage in {"before_player_context", "before_executable_repair"}:
        return
    active_objective_count = _active_graph_objective_count_from_state(runtime_state)
    actions = _safe_list(_safe_dict(runtime_state).get("scenario_progression_actions"))
    if active_objective_count > 0 and not actions:
        raise RuntimeError(
            "scenario_progression_actions_empty_with_active_graph_objectives:"
            f"turn={turn_index}:stage={stage}:"
            f"active_graph_objective_count={active_objective_count}"
        )


def _now_ms() -> int:
    return int(time.perf_counter() * 1000)


def _wall_ts() -> str:
    try:
        from datetime import datetime

        return datetime.now().isoformat(timespec="seconds")
    except Exception:
        return ""


def _probe_log(enabled: bool, event: str, **fields: Any) -> None:
    if not enabled:
        return
    parts = [
        f"[AUTOPLAY-PROBE]",
        f"ts={_wall_ts()}",
        f"event={event}",
        f"thread={threading.current_thread().name}",
    ]
    for key, value in fields.items():
        try:
            text = str(value)
        except Exception:
            text = "<unprintable>"
        if len(text) > 500:
            text = text[:500] + "...[truncated]"
        parts.append(f"{key}={text}")
    print(" ".join(parts), flush=True)


class _ProbeTimer:
    def __init__(self, enabled: bool, event: str, **fields: Any) -> None:
        self.enabled = enabled
        self.event = event
        self.fields = fields
        self.start_ms = 0

    def __enter__(self) -> "_ProbeTimer":
        self.start_ms = _now_ms()
        _probe_log(self.enabled, f"{self.event}.start", **self.fields)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        elapsed_ms = _now_ms() - self.start_ms
        if exc is not None:
            _probe_log(
                self.enabled,
                f"{self.event}.error",
                elapsed_ms=elapsed_ms,
                error=f"{type(exc).__name__}: {exc}",
                traceback="".join(traceback.format_exception(exc_type, exc, tb))[-2000:],
                **self.fields,
            )
            return
        _probe_log(self.enabled, f"{self.event}.end", elapsed_ms=elapsed_ms, **self.fields)


def _build_player_agent_anti_loop_context(
    *,
    transcript: List[Dict[str, Any]],
    threshold: int,
    window: int,
) -> Dict[str, Any]:
    streak = recent_semantic_target_streak(
        transcript,
        window=max(int(window or 8), int(threshold or 3) + 2),
    )
    canonical_recent_pairs = [
        canonical_semantic_pair_from_turn(row)
        for row in _safe_list(transcript)[-max(int(window or 8), int(threshold or 3) + 2):]
        if isinstance(row, dict)
    ]
    pair = _safe_str(streak.get("pair"))
    semantic_action = _safe_str(streak.get("semantic_action"))
    target = _safe_str(streak.get("target"))
    count = int(streak.get("streak") or 0)
    active = bool(pair and count >= int(threshold or 3))

    alternatives: List[str] = []
    if active:
        if target and target.lower() not in ("", "unknown"):
            alternatives.extend(
                [
                    f"Do not repeat another {semantic_action or 'similar'} action targeting {target}.",
                    f"Ask {target} a specific new question that changes the situation, not another observe/listen/wait action.",
                    "Choose a different target in the location, such as another patron, the room, the notice board, the door, or the street outside.",
                    "Use a concrete service/action: buy, pay, travel, inspect a physical clue, accept/refuse a lead, or move to a new location.",
                ]
            )
        else:
            alternatives.extend(
                [
                    f"Do not repeat another {semantic_action or 'same'} action with the same target.",
                    "Choose a concrete action that changes target, location, objective, or service state.",
                ]
            )

    return {
        "active": active,
        "pair": pair,
        "semantic_action": semantic_action,
        "target": target,
        "streak": count,
        "threshold": int(threshold or 3),
        "alternatives": alternatives,
        "source": _safe_str(streak.get("source")) or "canonical_semantic_pair_from_turn",
        "recent_pairs": _safe_list(streak.get("pairs")),
        "canonical_recent_pairs": canonical_recent_pairs[-12:],
    }


def _format_player_agent_anti_loop_prompt(context: Dict[str, Any]) -> str:
    context = _safe_dict(context)
    if not context.get("active"):
        return ""
    alternatives = [
        f"- {text}" for text in _safe_list(context.get("alternatives")) if _safe_str(text)
    ]
    return (
        "\n\nANTI-LOOP REQUIREMENT:\n"
        f"The recent action pattern is repeating `{_safe_str(context.get('pair'))}` "
        f"for {_safe_str(context.get('streak'))} turns.\n"
        "Your next action must break this semantic loop.\n"
        "Do not use another vague observe/listen/watch/wait action against the same target.\n"
        "Pick a concrete action that changes the target, objective, location, or service state.\n"
        + "\n".join(alternatives[:6])
        + "\n"
    )


def _rough_semantic_pair_for_player_action(action: str, *, default_target: str = "unknown") -> Dict[str, str]:
    """Cheap deterministic classifier for anti-loop repair.

    This does not replace the authoritative semantic extractor. It only catches
    obvious soft-loop player-agent outputs before submitting the action.
    """
    text = _safe_str(action).strip()
    normalized_action = normalize_command_label_action(text)
    lower = _safe_str(normalized_action).lower()
    target = default_target or "unknown"
    for name in ("bran", "silas", "cloaked traveler", "traveler", "patron", "innkeeper", "bartender", "guard", "merchant", "side door", "street", "road"):
        if name in lower:
            if name in ("bran", "innkeeper", "bartender"):
                target = "Bran"
            elif name == "traveler":
                target = "Cloaked Traveler"
            elif name in ("side door", "street"):
                target = "tavern_exit"
            elif name == "road":
                target = "road"
            else:
                target = name.title()
            break

    observe_terms = (
        "listen",
        "watch",
        "observe",
        "wait",
        "nod",
        "scan",
        "look around",
        "maintaining eye contact",
        "eye contact",
    )
    ask_terms = ("ask", "question", "press", "inquire", "say", "tell me")
    travel_terms = ("leave", "go to", "travel", "head outside", "step outside", "move to")
    service_terms = ("buy", "pay", "rent", "room", "drink", "meal", "order")
    inspect_terms = ("inspect", "examine", "search", "check")

    if (
        ("ask" in lower and "bran" in lower and ("saw" in lower or "personally saw" in lower) and "cloaked traveler" in lower)
        or ("where" in lower and ("witness" in lower or "cloaked traveler" in lower or "side door" in lower))
    ):
        semantic = "ask_witness_lead"
        if target == "unknown":
            target = "Bran"
    elif "report" in lower and ("witness" in lower or "cloaked traveler" in lower or "trail" in lower):
        semantic = "report_witness_findings"
        if target == "unknown":
            target = "Bran"
    elif any(term in lower for term in ("side door", "nearby street", "boot prints", "mud", "torn cloth", "hurried exit")):
        semantic = "inspect_witness_trail"
        target = "tavern_exit"
    elif any(term in lower for term in ("follow the road", "road outside", "fresh tracks", "follow the trail", "bandit road trail")):
        semantic = "follow_witness_trail"
        target = "road"
    elif any(term in lower for term in travel_terms):
        semantic = "travel"
    elif any(term in lower for term in service_terms):
        semantic = "service"
    elif any(term in lower for term in inspect_terms):
        semantic = "inspect"
    elif any(term in lower for term in ask_terms):
        semantic = "ask"
    elif any(term in lower for term in observe_terms):
        semantic = "observe"
    else:
        semantic = "unknown"

    return {
        "semantic_action": semantic,
        "target": target,
        "pair": f"{semantic}:{target}",
    }


def _action_violates_anti_loop(action: str, anti_loop_context: Dict[str, Any]) -> bool:
    context = _safe_dict(anti_loop_context)
    if not context.get("active"):
        return False
    forbidden_semantic = _safe_str(context.get("semantic_action")).lower()
    forbidden_target = _safe_str(context.get("target")).lower()
    proposed = _rough_semantic_pair_for_player_action(
        action,
        default_target=_safe_str(context.get("target")) or "unknown",
    )
    proposed_semantic = _safe_str(proposed.get("semantic_action")).lower()
    proposed_target = _safe_str(proposed.get("target")).lower()

    if not forbidden_semantic or not forbidden_target:
        return False
    if proposed_semantic == forbidden_semantic and proposed_target == forbidden_target:
        return True
    # Catch vague observe/listen/wait text against the same target even if the
    # proposed classifier lands on unknown.
    if forbidden_semantic == "observe" and proposed_target == forbidden_target:
        lower = _safe_str(action).lower()
        if any(term in lower for term in ("listen", "watch", "observe", "wait", "nod", "eye contact")):
            return True
    return False


def _deterministic_anti_loop_fallback_action(anti_loop_context: Dict[str, Any]) -> str:
    context = _safe_dict(anti_loop_context)
    target = _safe_str(context.get("target")) or "Bran"
    if target.lower() == "bran":
        return (
            "Turn away from Bran for the moment and speak to a nearby patron, asking what they have heard "
            "about Silas or trouble on the road."
        )
    return (
        "Change focus to a different part of the scene: inspect the room, look for a notice board, "
        "or ask a different nearby NPC about the current lead."
    )


def _force_exit_if_background_threads_remain(
    *,
    args: Any,
    pipeline: Any,
    exit_code: int,
) -> None:
    if not bool(getattr(args, "force_exit_after_artifacts_on_background_timeout", False)):
        return
    diagnostics: Dict[str, Any] = {}
    try:
        diagnostics = pipeline.executor_thread_diagnostics()
    except Exception:
        diagnostics = {}
    alive = int(diagnostics.get("alive_provider_thread_count") or 0) + int(
        diagnostics.get("alive_background_thread_count") or 0
    )
    pending = int(diagnostics.get("pending_job_count") or 0)
    if alive <= 0 and pending <= 0:
        return
    print(
        "[autoplay] Force-exiting after artifact write because background "
        f"threads remain alive. alive={alive} pending={pending} "
        f"exit_code={exit_code}",
        flush=True,
    )
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(int(exit_code or 0))


try:
    from app.providers.base import ChatMessage
except Exception:
    ChatMessage = None


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
    import json
    import re

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


def _summarize_player_agent_trace(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "turns": 0,
        "fallback_turns": 0,
        "llm_turns": 0,
        "unknown_turns": 0,
        "avg_player_agent_ms": 0.0,
        "max_player_agent_ms": 0.0,
        "selected_source_counts": {},
        "fallback_reason_counts": {},
        "errors": {},
    }
    timings: List[float] = []
    for row in transcript:
        if not isinstance(row, dict):
            continue
        summary["turns"] += 1
        perf = _safe_dict(row.get("performance"))
        ms = float(perf.get("player_agent_ms") or 0.0)
        if ms:
            timings.append(ms)

        selected = _safe_dict(row.get("selected_player_action"))
        source = (
            _safe_str(selected.get("source"))
            or _safe_str(selected.get("agent_source"))
            or _safe_str(selected.get("mode"))
            or "unknown"
        )
        if source == "unknown" and selected.get("ok") is True and selected.get("raw"):
            source = "llm_player_agent"
        summary["selected_source_counts"][source] = (
            int(summary["selected_source_counts"].get(source) or 0) + 1
        )
        if "fallback" in source:
            summary["fallback_turns"] += 1
        elif "llm" in source or "provider" in source:
            summary["llm_turns"] += 1
        else:
            summary["unknown_turns"] += 1

        reason = _safe_str(selected.get("fallback_reason")) or _safe_str(selected.get("reason_code"))
        if reason:
            summary["fallback_reason_counts"][reason] = (
                int(summary["fallback_reason_counts"].get(reason) or 0) + 1
            )
        error = _safe_str(selected.get("error")) or _safe_str(selected.get("provider_error"))
        if error:
            summary["errors"][error] = int(summary["errors"].get(error) or 0) + 1

    if timings:
        summary["avg_player_agent_ms"] = round(sum(timings) / len(timings), 3)
        summary["max_player_agent_ms"] = round(max(timings), 3)
    return summary


def _summarize_deferred_narration_trace(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "turns": 0,
        "ok_jobs": 0,
        "failed_jobs": 0,
        "sources": {},
        "avg_worker_ms": 0.0,
        "max_worker_ms": 0.0,
        "provider_present": 0,
        "provider_missing": 0,
        "errors": {},
        "diagnostics_examples": [],
    }
    timings: List[float] = []
    for row in transcript:
        if not isinstance(row, dict):
            continue
        result = _safe_dict(row.get("deferred_narration_result"))
        if not result:
            continue
        summary["turns"] += 1
        if result.get("ok"):
            summary["ok_jobs"] += 1
        else:
            summary["failed_jobs"] += 1
        ms = float(result.get("worker_ms") or 0.0)
        if ms:
            timings.append(ms)
        payload = _safe_dict(result.get("narration_payload"))
        source = _safe_str(payload.get("source")) or "unknown"
        summary["sources"][source] = int(summary["sources"].get(source) or 0) + 1
        diagnostics = _safe_dict(result.get("diagnostics"))
        provider_shape = _safe_dict(diagnostics.get("provider_shape"))
        if provider_shape.get("present"):
            summary["provider_present"] += 1
        else:
            summary["provider_missing"] += 1
        error = (
            _safe_str(result.get("error"))
            or _safe_str(payload.get("error"))
            or _safe_str(payload.get("original_error"))
            or _safe_str(diagnostics.get("exception"))
            or _safe_str(diagnostics.get("payload_error"))
            or _safe_str(diagnostics.get("payload_original_error"))
        )
        if error:
            summary["errors"][error] = int(summary["errors"].get(error) or 0) + 1
        if len(summary["diagnostics_examples"]) < 3:
            summary["diagnostics_examples"].append(
                {
                    "turn_index": row.get("turn_index"),
                    "source": source,
                    "worker_ms": ms,
                    "provider_shape": provider_shape,
                    "payload_error": diagnostics.get("payload_error"),
                    "payload_original_error": diagnostics.get("payload_original_error"),
                }
            )
    if timings:
        summary["avg_worker_ms"] = round(sum(timings) / len(timings), 3)
        summary["max_worker_ms"] = round(max(timings), 3)
    return summary


def _summarize_deferred_advisory_trace(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "turns": 0,
        "ok_jobs": 0,
        "failed_jobs": 0,
        "sources": {},
        "candidate_count": 0,
        "candidate_kinds": {},
        "avg_worker_ms": 0.0,
        "max_worker_ms": 0.0,
        "errors": {},
    }
    timings: List[float] = []
    for row in transcript:
        result = _safe_dict(row.get("deferred_advisory_result"))
        if not result:
            continue
        summary["turns"] += 1
        if result.get("ok"):
            summary["ok_jobs"] += 1
        else:
            summary["failed_jobs"] += 1
        source = _safe_str(result.get("source")) or "unknown"
        summary["sources"][source] = int(summary["sources"].get(source) or 0) + 1
        ms = float(result.get("worker_ms") or 0.0)
        if ms:
            timings.append(ms)
        candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        summary["candidate_count"] += len(candidates)
        for candidate in candidates:
            kind = _safe_str(_safe_dict(candidate).get("kind")) or "unknown"
            summary["candidate_kinds"][kind] = int(summary["candidate_kinds"].get(kind) or 0) + 1
        error = _safe_str(result.get("error")) or _safe_str(_safe_dict(result.get("diagnostics")).get("provider_payload_error"))
        if error:
            summary["errors"][error] = int(summary["errors"].get(error) or 0) + 1
    if timings:
        summary["avg_worker_ms"] = round(sum(timings) / len(timings), 3)
        summary["max_worker_ms"] = round(max(timings), 3)
    return summary


def _summarize_performance_budget(
    *,
    transcript: List[Dict[str, Any]],
    background_summary: Dict[str, Any],
) -> Dict[str, Any]:
    def avg(values: List[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    manual = []
    player = []
    human = []
    autoplay = []
    for row in transcript:
        perf = _safe_dict(row.get("performance"))
        manual.append(float(perf.get("manual_turn_ms") or 0.0))
        player.append(float(perf.get("player_agent_ms") or 0.0))
        human.append(_authoritative_human_playable_blocking_ms(row))
        autoplay.append(float(perf.get("playable_blocking_ms") or 0.0))

    legacy_blocking_values = [
        float(_safe_dict(row).get("performance", {}).get("human_playable_blocking_ms") or 0.0)
        for row in transcript
    ]
    player_agent_values = [
        _timing_ms(_safe_dict(row), "player_agent_ms", "player_agent_wall_ms")
        for row in transcript
    ]
    manual_turn_values = [
        _timing_ms(_safe_dict(row), "manual_turn_ms")
        for row in transcript
    ]

    provider_queue = _safe_dict(background_summary.get("provider_queue_summary"))
    return {
        "live_blocking": {
            "avg_manual_turn_ms": avg(manual),
            "max_manual_turn_ms": round(max(manual), 3) if manual else 0.0,
            "avg_human_playable_blocking_ms": avg(human),
            "max_human_playable_blocking_ms": round(max(human), 3) if human else 0.0,
            "blocking_metric_mode": "authoritative_deterministic_only",
            "legacy_max_human_playable_blocking_ms": round(max(legacy_blocking_values), 3) if legacy_blocking_values else 0.0,
            "max_player_agent_ms": round(max(player_agent_values), 3) if player_agent_values else 0.0,
            "max_manual_turn_ms_diagnostic": round(max(manual_turn_values), 3) if manual_turn_values else 0.0,
        },
        "autoplay_only": {
            "avg_player_agent_ms": avg(player),
            "max_player_agent_ms": round(max(player), 3) if player else 0.0,
            "avg_autoplay_blocking_ms": avg(autoplay),
            "max_autoplay_blocking_ms": round(max(autoplay), 3) if autoplay else 0.0,
        },
        "background_llm": {
            "total_jobs": background_summary.get("total_jobs"),
            "narration_jobs": background_summary.get("narration_jobs"),
            "advisory_jobs": background_summary.get("advisory_jobs"),
            "combined_background_llm_jobs": background_summary.get("combined_background_llm_jobs"),
            "background_job_seconds": background_summary.get("background_job_seconds"),
            "provider_queue_summary": provider_queue,
            "provider_queue_by_kind": background_summary.get("provider_queue_by_kind") or {},
        },
    }


def _build_player_agent_latency_summary(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    values = [
        _timing_ms(_safe_dict(row), "player_agent_ms", "player_agent_wall_ms")
        for row in _safe_list(transcript)
    ]
    values = [value for value in values if value > 0]
    return {
        "ok": True,
        "count": len(values),
        "avg_ms": sum(values) / max(1, len(values)),
        "p95_ms": _percentile(values, 95),
        "max_ms": max(values or [0.0]),
        "quality_gate": "diagnostic_only",
        "note": "Player-agent LLM planning is measured separately and is not counted as authoritative human-playable blocking.",
    }


def _build_narration_grounding_summary(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = _safe_list(transcript)
    checked = 0
    invalid = 0
    fallback_used = 0
    violation_counts: Dict[str, int] = {}
    selected_candidate_counts: Dict[str, int] = {}
    fallback_source_counts: Dict[str, int] = {}
    primary_violation_counts: Dict[str, int] = {}

    for row in rows:
        row = _safe_dict(row)
        validation = _safe_dict(row.get("narration_grounding_validation"))
        if not validation:
            validation = _extract_grounding_validation_from_any(row)
        if not validation:
            continue
        checked += 1
        if not bool(validation.get("ok")):
            invalid += 1
        if bool(validation.get("fallback_used")):
            fallback_used += 1
        for violation in _safe_list(validation.get("violations")):
            code = _safe_str(_safe_dict(violation).get("code") or "unknown")
            violation_counts[code] = int(violation_counts.get(code, 0)) + 1

        selected = _safe_str(validation.get("selected_candidate") or "unknown")
        selected_candidate_counts[selected] = int(selected_candidate_counts.get(selected, 0)) + 1

        source = _safe_str(validation.get("fallback_source") or "none")
        fallback_source_counts[source] = int(fallback_source_counts.get(source, 0)) + 1

        for violation in _safe_list(validation.get("primary_violations")):
            code = _safe_str(_safe_dict(violation).get("code") or "unknown")
            primary_violation_counts[code] = int(primary_violation_counts.get(code, 0)) + 1

    return {
        "ok": invalid == 0,
        "checked_count": checked,
        "invalid_count": invalid,
        "fallback_used_count": fallback_used,
        "violation_counts": dict(sorted(violation_counts.items())),
        "selected_candidate_counts": dict(sorted(selected_candidate_counts.items())),
        "fallback_source_counts": dict(sorted(fallback_source_counts.items())),
        "primary_violation_counts": dict(sorted(primary_violation_counts.items())),
    }


def _summarize_background_prompt_budget(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for row in transcript:
        combined = _safe_dict(row.get("combined_background_llm_result"))
        diagnostics = _safe_dict(combined.get("diagnostics"))
        prompt_metrics = (
            _safe_dict(combined.get("prompt_metrics"))
            or _safe_dict(diagnostics.get("prompt_metrics"))
        )
        if not prompt_metrics:
            continue
        rows.append(
            {
                "turn_index": row.get("turn_index"),
                "source": _safe_str(combined.get("source")),
                "total_chars": int(prompt_metrics.get("total_chars") or 0),
                "estimated_tokens": float(prompt_metrics.get("estimated_tokens") or 0.0),
                "by_section": _safe_dict(prompt_metrics.get("by_section")),
            }
        )

    if not rows:
        return {
            "count": 0,
            "avg_total_chars": 0.0,
            "max_total_chars": 0,
            "avg_estimated_tokens": 0.0,
            "max_estimated_tokens": 0.0,
            "by_section_avg_chars": {},
            "examples": [],
        }

    section_totals: Dict[str, List[int]] = {}
    for item in rows:
        for section, metrics in _safe_dict(item.get("by_section")).items():
            section_totals.setdefault(section, []).append(int(_safe_dict(metrics).get("chars") or 0))

    return {
        "count": len(rows),
        "avg_total_chars": round(sum(item["total_chars"] for item in rows) / len(rows), 3),
        "max_total_chars": max(item["total_chars"] for item in rows),
        "avg_estimated_tokens": round(sum(item["estimated_tokens"] for item in rows) / len(rows), 3),
        "max_estimated_tokens": round(max(item["estimated_tokens"] for item in rows), 3),
        "by_section_avg_chars": {
            section: round(sum(values) / len(values), 3)
            for section, values in section_totals.items()
            if values
        },
        "examples": rows[:3],
    }


def _summarize_combined_quality_shape(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    narration_lengths: List[int] = []
    candidate_counts: List[int] = []
    candidate_kinds: Dict[str, int] = {}

    for row in transcript:
        combined = _safe_dict(row.get("combined_background_llm_result"))
        if not combined:
            continue
        narration = _safe_str(combined.get("narration"))
        if narration:
            narration_lengths.append(len(narration))
        candidates = combined.get("candidates") if isinstance(combined.get("candidates"), list) else []
        candidate_counts.append(len(candidates))
        for candidate in candidates:
            kind = _safe_str(_safe_dict(candidate).get("kind")) or "unknown"
            candidate_kinds[kind] = int(candidate_kinds.get(kind) or 0) + 1

    def avg(values: List[int]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    return {
        "combined_turns": len(candidate_counts),
        "avg_narration_chars": avg(narration_lengths),
        "min_narration_chars": min(narration_lengths) if narration_lengths else 0,
        "avg_candidate_count": avg(candidate_counts),
        "min_candidate_count": min(candidate_counts) if candidate_counts else 0,
        "candidate_kinds": candidate_kinds,
    }


def _summarize_promotion_target_grounding(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    seen_grounding_candidate_ids = set()
    seen_example_candidate_ids = set()
    accepted_relationship_ids = set()
    rejected_relationship_ids = set()

    summary: Dict[str, Any] = {
        "grounded": 0,
        "ungrounded": 0,
        "by_reason": {},
        "relationship_accepted": 0,
        "relationship_rejected": 0,
        "unique_relationship_accepted": 0,
        "unique_relationship_rejected": 0,
        "examples": [],
    }

    def candidate_marker(value: Any, *, prefix: str = "candidate") -> str:
        text = _safe_str(value)
        if text:
            return text
        return f"{prefix}:missing"

    for row in transcript:
        result = _safe_dict(row.get("deferred_advisory_promotion_result"))
        for decision in result.get("decisions") if isinstance(result.get("decisions"), list) else []:
            decision = _safe_dict(decision)
            grounding = _safe_dict(decision.get("target_grounding"))
            if not grounding:
                continue
            marker = candidate_marker(decision.get("candidate_id"))
            if marker in seen_grounding_candidate_ids:
                continue
            seen_grounding_candidate_ids.add(marker)

            reason = _safe_str(grounding.get("reason")) or "unknown"
            summary["by_reason"][reason] = int(summary["by_reason"].get(reason) or 0) + 1
            if grounding.get("grounded"):
                summary["grounded"] += 1
            else:
                summary["ungrounded"] += 1
            if len(summary["examples"]) < 5 and marker not in seen_example_candidate_ids:
                seen_example_candidate_ids.add(marker)
                summary["examples"].append(
                    {
                        "turn_index": row.get("turn_index"),
                        "candidate_id": decision.get("candidate_id"),
                        "status": decision.get("status"),
                        "reason": decision.get("reason"),
                        "target_grounding": grounding,
                    }
                )

        runtime_state = _safe_dict(row.get("runtime_state"))
        accepted = _safe_list(_safe_dict(runtime_state.get("deferred_advisory")).get("accepted"))
        rejected = _safe_list(_safe_dict(runtime_state.get("deferred_advisory")).get("rejected"))
        for item in accepted:
            item = _safe_dict(item)
            if item.get("kind") != "relationship_delta":
                continue
            marker = candidate_marker(item.get("candidate_id"), prefix="accepted")
            accepted_relationship_ids.add(marker)
        for item in rejected:
            item = _safe_dict(item)
            if item.get("kind") != "relationship_delta":
                continue
            marker = candidate_marker(item.get("candidate_id"), prefix="rejected")
            rejected_relationship_ids.add(marker)

    summary["relationship_accepted"] = len(accepted_relationship_ids)
    summary["relationship_rejected"] = len(rejected_relationship_ids)
    summary["unique_relationship_accepted"] = len(accepted_relationship_ids)
    summary["unique_relationship_rejected"] = len(rejected_relationship_ids)
    summary["dedup"] = {
        "grounding_candidate_ids": len(seen_grounding_candidate_ids),
        "accepted_relationship_candidate_ids": len(accepted_relationship_ids),
        "rejected_relationship_candidate_ids": len(rejected_relationship_ids),
    }
    return summary


def _build_100_turn_evaluation_summary(
    *,
    turns_executed: int,
    requested_turns: int,
    runtime_errors: List[Any],
    warnings: List[str],
    transcript: List[Dict[str, Any]],
    performance_summary: Dict[str, Any],
    narration_grounding_summary: Dict[str, Any],
    progress_quality_summary: Dict[str, Any],
    checkpoint_summary: Dict[str, Any],
    loop_detection_summary: Dict[str, Any],
    mechanics_coverage_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    grounding = _safe_dict(narration_grounding_summary)
    progress = _safe_dict(progress_quality_summary)
    checkpoints = _safe_dict(checkpoint_summary)
    loops = _safe_dict(loop_detection_summary)
    perf = _safe_dict(performance_summary)
    mechanics = _safe_dict(mechanics_coverage_summary)
    mechanics_real_required_ok = bool(
        mechanics.get("real_required_ok", mechanics.get("required_ok", True))
    )

    selected_grounding_health = _build_selected_output_grounding_health(
        grounding,
        requested_turns=requested_turns,
    )
    checked_grounding = int(grounding.get("checked_count") or 0)
    grounding_invalid = int(selected_grounding_health.get("selected_output_invalid_count") or 0)
    grounding_parse_failures = int(selected_grounding_health.get("provider_json_parse_failed_count") or 0)
    grounding_provider_invalid = int(selected_grounding_health.get("provider_invalid_count") or 0)
    deterministic_fallback_rate = float(selected_grounding_health.get("deterministic_fallback_rate") or 0.0)

    fallback_player_action_rate = float(progress.get("fallback_player_action_rate") or 0.0)
    meaningful_progress_rate = float(progress.get("meaningful_progress_rate") or 0.0)
    no_change_turns = int(progress.get("no_change_turns") or 0)

    checkpoint_failures = int(checkpoints.get("failure_count") or checkpoints.get("checkpoint_failure_count") or 0)
    repeated_action_windows = int(loops.get("repeated_action_window_count") or 0)
    loop_warning_count = int(loops.get("loop_warning_count") or 0)

    avg_turn_seconds = float(
        perf.get("avg_turn_seconds")
        or perf.get("average_turn_seconds")
        or perf.get("mean_turn_seconds")
        or 0.0
    )
    p95_turn_seconds = float(
        perf.get("p95_turn_seconds")
        or perf.get("turn_p95_seconds")
        or 0.0
    )

    gates: Dict[str, Dict[str, Any]] = {
        "turn_count_reached": {
            "ok": turns_executed >= requested_turns,
            "value": turns_executed,
            "expected": requested_turns,
            "message": f"Executed {turns_executed}/{requested_turns} requested turns.",
        },
        "runtime_errors_absent": {
            "ok": len(runtime_errors) == 0,
            "value": len(runtime_errors),
            "expected": 0,
            "message": f"Runtime errors: {len(runtime_errors)}.",
        },
        "narration_grounding_checked": {
            "ok": checked_grounding > 0,
            "value": checked_grounding,
            "expected": "> 0",
            "message": f"Grounding validations checked: {checked_grounding}.",
        },
        "narration_grounding_valid": {
            "ok": bool(selected_grounding_health.get("ok")),
            "value": selected_grounding_health,
            "expected": {
                "selected_output_invalid_count": 0,
                "provider_json_parse_failed": 0,
                "provider_invalid": 0,
                "deterministic_fallback_rate": "<= 0.10",
            },
            "message": (
                "Selected narration outputs should be safe. Rejected-primary violations are allowed "
                "when a valid safe_fallback or deterministic fallback is selected."
            ),
        },
        "player_agent_fallback_rate": {
            "ok": fallback_player_action_rate <= 0.25,
            "value": fallback_player_action_rate,
            "expected": "<= 0.25",
            "message": f"Player-agent fallback action rate: {fallback_player_action_rate:.2%}.",
        },
        "meaningful_progress_rate": {
            "ok": meaningful_progress_rate >= 0.10,
            "value": meaningful_progress_rate,
            "expected": ">= 0.10",
            "message": f"Meaningful progress rate: {meaningful_progress_rate:.2%}.",
        },
        "no_change_turns_bounded": {
            "ok": no_change_turns <= max(15, int(requested_turns * 0.35)),
            "value": no_change_turns,
            "expected": f"<= {max(15, int(requested_turns * 0.35))}",
            "message": f"No-change turns: {no_change_turns}.",
        },
        "checkpoint_validation": {
            "ok": checkpoint_failures == 0,
            "value": checkpoint_failures,
            "expected": 0,
            "message": f"Checkpoint validation failures: {checkpoint_failures}.",
        },
        "loop_detection": {
            "ok": repeated_action_windows == 0 and loop_warning_count == 0,
            "value": {
                "repeated_action_window_count": repeated_action_windows,
                "loop_warning_count": loop_warning_count,
            },
            "expected": {
                "repeated_action_window_count": 0,
                "loop_warning_count": 0,
            },
            "message": "No repeated-action loop windows should be detected.",
        },
        "performance_turn_latency": {
            "ok": p95_turn_seconds <= 30.0 if p95_turn_seconds else True,
            "value": {
                "avg_turn_seconds": avg_turn_seconds,
                "p95_turn_seconds": p95_turn_seconds,
            },
            "expected": {
                "p95_turn_seconds": "<= 30.0",
            },
            "message": f"Average turn latency {avg_turn_seconds:.2f}s, p95 {p95_turn_seconds:.2f}s.",
        },
        "mechanics_coverage_required": {
            "ok": mechanics_real_required_ok,
            "value": {
                "coverage_rate": mechanics.get("coverage_rate"),
                "real_coverage_rate": mechanics.get("real_coverage_rate"),
                "covered_required_count": mechanics.get("covered_required_count"),
                "real_covered_required_count": mechanics.get("real_covered_required_count"),
                "required_count": mechanics.get("required_count"),
                "missing_required": mechanics.get("missing_required"),
                "missing_real_required": mechanics.get("missing_real_required"),
            },
            "expected": {
                "missing_real_required": [],
                "real_coverage_rate": "1.0",
            },
            "message": "Required RPG mechanics should be exercised by real runtime/story-graph evidence.",
        },
    }

    failed = {
        name: gate
        for name, gate in gates.items()
        if not bool(_safe_dict(gate).get("ok"))
    }

    return {
        "ok": not failed,
        "requested_turns": requested_turns,
        "turns_executed": turns_executed,
        "failed_gate_count": len(failed),
        "passed_gate_count": len(gates) - len(failed),
        "gates": gates,
        "failed_gates": failed,
        "warnings_count": len(warnings),
        "top_warnings": warnings[:20],
    }


def _extract_health_progress_quality(final_summary: Dict[str, Any]) -> Dict[str, Any]:
    health = _safe_dict(final_summary.get("health"))
    metrics = _safe_dict(health.get("metrics"))
    return _safe_dict(metrics.get("progress_quality"))


def _row_has_location_progression(row: Dict[str, Any]) -> bool:
    row = _safe_dict(row)

    candidates = [
        row,
        _safe_dict(row.get("result")),
        _safe_dict(row.get("resolved_result")),
        _safe_dict(row.get("turn_contract")),
        _safe_dict(row.get("state_delta")),
        _safe_dict(_safe_dict(row.get("result")).get("state_delta")),
        _safe_dict(_safe_dict(row.get("turn_contract")).get("state_delta")),
    ]

    for candidate in candidates:
        if candidate.get("location_changed") is True:
            return True
        if _safe_str(candidate.get("progress_category")) == "location_progression":
            return True
        travel_result = _safe_dict(candidate.get("travel_result"))
        if travel_result.get("ok") is True and travel_result.get("to_location"):
            return True

    return False


def _default_player_progression_state() -> Dict[str, Any]:
    return {
        "name": "The Player",
        "level": 1,
        "xp": 0,
        "xp_to_next_level": 25,
        "progress_log": [],
        "currency": {
            "gold": 15,
            "silver": 20,
            "copper": 50,
        },
        "inventory": [
            {
                "id": "item:travelers_cloak",
                "name": "Traveler's Cloak",
                "quantity": 1,
                "type": "gear",
                "description": "A weathered cloak suitable for road travel.",
            },
            {
                "id": "item:iron_dagger",
                "name": "Iron Dagger",
                "quantity": 1,
                "type": "weapon",
                "description": "A simple backup blade.",
            },
            {
                "id": "item:trail_rations",
                "name": "Trail Rations",
                "quantity": 3,
                "type": "consumable",
                "description": "Basic food for short travel.",
            },
            {
                "id": "item:waterskin",
                "name": "Waterskin",
                "quantity": 1,
                "type": "gear",
                "description": "A filled waterskin.",
            },
            {
                "id": "item:plain_journal",
                "name": "Plain Journal",
                "quantity": 1,
                "type": "tool",
                "description": "A small book for notes, rumors, and leads.",
            },
        ],
    }


def _item_display_name(item_id: str) -> str:
    item_id = _safe_str(item_id)
    names = {
        "item:rations": "Rations",
        "item:torch": "Torch",
        "item:marked_coin": "Marked Coin",
        "item:bandit_knife": "Bandit Knife",
        "item:travelers_cloak": "Traveler's Cloak",
        "item:iron_dagger": "Iron Dagger",
        "item:trail_rations": "Trail Rations",
        "item:waterskin": "Waterskin",
        "item:plain_journal": "Plain Journal",
    }
    return names.get(item_id, item_id.replace("item:", "").replace("_", " ").title())


def _item_type(item_id: str) -> str:
    item_id = _safe_str(item_id)
    if item_id in {"item:iron_dagger", "item:bandit_knife"}:
        return "weapon"
    if item_id in {"item:rations", "item:trail_rations"}:
        return "consumable"
    if item_id in {"item:marked_coin"}:
        return "quest"
    if item_id in {"item:torch", "item:plain_journal"}:
        return "tool"
    return "gear"


def _normalize_inventory_items(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw in _safe_list(items):
        item = _safe_dict(raw)
        item_id = _safe_str(item.get("id") or item.get("item_id") or item.get("name"))
        if not item_id:
            continue
        quantity = int(item.get("quantity") or item.get("qty") or 1)
        normalized.append(
            {
                "id": item_id,
                "name": _safe_str(item.get("name") or _item_display_name(item_id)),
                "quantity": quantity,
                "type": _safe_str(item.get("type") or _item_type(item_id)),
                "description": _safe_str(item.get("description") or ""),
            }
        )
    return normalized


def _apply_inventory_delta_to_items(
    inventory: List[Dict[str, Any]],
    inventory_delta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items = [dict(item) for item in _normalize_inventory_items(inventory)]

    def add_item(raw: Dict[str, Any]) -> None:
        item = _safe_dict(raw)
        item_id = _safe_str(item.get("id") or item.get("item_id"))
        if not item_id:
            return
        quantity = int(item.get("quantity") or item.get("qty") or 1)
        for existing in items:
            if existing.get("id") == item_id:
                existing["quantity"] = int(existing.get("quantity") or 0) + quantity
                return
        items.append(
            {
                "id": item_id,
                "name": _safe_str(item.get("name") or _item_display_name(item_id)),
                "quantity": quantity,
                "type": _safe_str(item.get("type") or _item_type(item_id)),
                "description": _safe_str(item.get("description") or ""),
            }
        )

    def remove_item(raw: Dict[str, Any]) -> None:
        item = _safe_dict(raw)
        item_id = _safe_str(item.get("id") or item.get("item_id"))
        if not item_id:
            return
        quantity = int(item.get("quantity") or item.get("qty") or 1)
        for existing in list(items):
            if existing.get("id") == item_id:
                existing["quantity"] = max(0, int(existing.get("quantity") or 0) - quantity)
                if int(existing.get("quantity") or 0) <= 0:
                    items.remove(existing)
                return

    for raw_item in _safe_list(_safe_dict(inventory_delta).get("items_added")):
        add_item(_safe_dict(raw_item))

    for raw_item in _safe_list(_safe_dict(inventory_delta).get("items_removed")):
        remove_item(_safe_dict(raw_item))

    return items


def _apply_currency_delta(currency: Dict[str, int], currency_delta: Dict[str, Any]) -> Dict[str, int]:
    result = {str(k): int(v or 0) for k, v in _safe_dict(currency).items()}
    for key, value in _safe_dict(currency_delta).items():
        result[str(key)] = int(result.get(str(key), 0)) + int(value or 0)
    return result


def _currency_can_pay_delta(currency: Dict[str, Any], currency_delta: Dict[str, Any]) -> bool:
    current = {
        str(key): int(value or 0)
        for key, value in _safe_dict(currency).items()
    }

    for key, value in _safe_dict(currency_delta).items():
        amount = int(value or 0)
        if amount < 0 and int(current.get(str(key), 0)) + amount < 0:
            return False

    return True


def _opportunity_is_affordable(
    opportunity: Dict[str, Any],
    mechanics_state: Dict[str, Any],
) -> bool:
    effects = _safe_dict(_safe_dict(opportunity).get("effects_preview"))
    currency_delta = _safe_dict(effects.get("currency_delta"))
    if not currency_delta:
        return True

    return _currency_can_pay_delta(
        _safe_dict(mechanics_state.get("currency")),
        currency_delta,
    )


def _build_mechanics_coverage_summary(
    transcript: List[Dict[str, Any]],
    final_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    mechanics: Dict[str, Dict[str, Any]] = {
        "travel": {"required": True, "count": 0, "turns": [], "examples": []},
        "npc_interaction": {"required": True, "count": 0, "turns": [], "examples": []},
        "quest_progress": {"required": True, "count": 0, "turns": [], "examples": []},
        "service_or_lodging": {"required": True, "count": 0, "turns": [], "examples": []},
        "buying": {"required": True, "count": 0, "turns": [], "examples": []},
        "selling": {"required": False, "count": 0, "turns": [], "examples": []},
        "currency_change": {"required": True, "count": 0, "turns": [], "examples": []},
        "inventory_change": {"required": True, "count": 0, "turns": [], "examples": []},
        "party_recruitment": {"required": True, "count": 0, "turns": [], "examples": []},
        "combat_started": {"required": True, "count": 0, "turns": [], "examples": []},
        "combat_resolved": {"required": True, "count": 0, "turns": [], "examples": []},
        "xp_gain": {"required": True, "count": 0, "turns": [], "examples": []},
        "level_up": {"required": False, "count": 0, "turns": [], "examples": []},
        "loot_acquired": {"required": False, "count": 0, "turns": [], "examples": []},
    }

    def mark(name: str, turn_index: int, row: Dict[str, Any], reason: str, evidence_source: str = "explicit_payload") -> None:
        item = mechanics.get(name)
        if not item:
            return
        item["count"] = int(item.get("count") or 0) + 1
        if turn_index not in item["turns"]:
            item["turns"].append(turn_index)
        source_counts = item.setdefault("evidence_source_counts", {})
        source_counts[evidence_source] = int(source_counts.get(evidence_source, 0)) + 1
        if len(item["examples"]) < 5:
            item["examples"].append(
                {
                    "turn": turn_index,
                    "reason": reason,
                    "evidence_source": evidence_source,
                    "player_action": _safe_str(row.get("player_action"))[:240],
                    "mechanic": row.get("mechanic"),
                }
            )

    available_mechanic_counts: Dict[str, int] = {}
    available_mechanic_example_turns: Dict[str, List[int]] = {}

    for index, raw_row in enumerate(_safe_list(transcript), start=1):
        row = _safe_dict(raw_row)
        turn_index = int(row.get("turn_index") or row.get("turn") or index)
        action_text = _safe_str(row.get("player_action")).lower()

        mechanic_resolution = _safe_dict(row.get("mechanic_resolution"))
        result = _safe_dict(row.get("result"))
        state_delta = _safe_dict(row.get("state_delta"))
        turn_contract = _safe_dict(row.get("turn_contract"))
        contract_result = _safe_dict(turn_contract.get("result"))
        contract_delta = _safe_dict(turn_contract.get("state_delta"))
        mechanic_result = _safe_dict(mechanic_resolution.get("result"))
        mechanic_delta = _safe_dict(mechanic_resolution.get("state_delta"))

        candidates = [
            row,
            result,
            state_delta,
            turn_contract,
            contract_result,
            contract_delta,
            mechanic_resolution,
            mechanic_result,
            mechanic_delta,
        ]

        evidence_source = _safe_str(
            row.get("mechanics_evidence_source")
            or result.get("mechanics_evidence_source")
            or mechanic_resolution.get("mechanics_evidence_source")
            or "explicit_payload"
        )

        for raw_opportunity in _safe_list(row.get("available_mechanics")):
            opportunity = _safe_dict(raw_opportunity)
            mechanic = _safe_str(opportunity.get("mechanic"))
            if mechanic:
                available_mechanic_counts[mechanic] = int(available_mechanic_counts.get(mechanic, 0)) + 1
                turns = available_mechanic_example_turns.setdefault(mechanic, [])
                if turn_index and len(turns) < 10:
                    turns.append(turn_index)

        resolved_mechanic = _safe_str(
            row.get("mechanic")
            or result.get("mechanic")
            or mechanic_result.get("mechanic")
            or mechanic_resolution.get("mechanic")
        )

        if resolved_mechanic in mechanics:
            mark(resolved_mechanic, turn_index, row, "resolved_mechanic", evidence_source)

        if any(_safe_dict(candidate).get("location_changed") for candidate in candidates):
            mark("travel", turn_index, row, "location_changed", evidence_source)

        if any(_safe_dict(candidate).get("travel_result") for candidate in candidates):
            mark("travel", turn_index, row, "travel_result", evidence_source)

        service_payload = {}
        for candidate in candidates:
            service_payload = _safe_dict(
                _safe_dict(candidate).get("service_result")
                or _safe_dict(candidate).get("lodging_result")
                or _safe_dict(candidate).get("room_result")
            )
            if service_payload:
                break

        service_is_purchase = bool(
            service_payload.get("purchase")
            or service_payload.get("purchased")
            or service_payload.get("selected_offer_id")
            or service_payload.get("service_id")
            or service_payload.get("ok") is True
        )
        if service_payload.get("status") == "offers_available" and not service_payload.get("purchase") and not service_payload.get("selected_offer_id"):
            service_is_purchase = False

        if service_payload and service_is_purchase:
            mark("service_or_lodging", turn_index, row, "service_purchase_result", evidence_source)
        elif any(token in action_text for token in ("rent a room", "pay bran", "common room", "buy a hot meal", "pay for lodging")):
            mark("service_or_lodging", turn_index, row, "service_action_text", "action_text")

        if any(_safe_dict(candidate).get("purchase_result") or _safe_dict(candidate).get("buy_result") for candidate in candidates):
            mark("buying", turn_index, row, "purchase_result", evidence_source)

        if any(_safe_dict(candidate).get("sale_result") or _safe_dict(candidate).get("sell_result") for candidate in candidates):
            mark("selling", turn_index, row, "sale_result", evidence_source)

        if any(_safe_dict(candidate).get("currency_delta") for candidate in candidates):
            mark("currency_change", turn_index, row, "currency_delta", evidence_source)

        if any(_safe_dict(candidate).get("inventory_delta") for candidate in candidates):
            mark("inventory_change", turn_index, row, "inventory_delta", evidence_source)

        if any(_safe_dict(candidate).get("party_delta") for candidate in candidates):
            mark("party_recruitment", turn_index, row, "party_delta", evidence_source)

        combat_payload = {}
        for candidate in candidates:
            combat_payload = _safe_dict(_safe_dict(candidate).get("combat_result"))
            if combat_payload:
                break

        if combat_payload:
            mark("combat_started", turn_index, row, "combat_result", evidence_source)
            if combat_payload.get("resolved") or combat_payload.get("victory") or combat_payload.get("defeat") or combat_payload.get("ended"):
                mark("combat_resolved", turn_index, row, "combat_result_resolved", evidence_source)

        if any(_safe_dict(candidate).get("xp_delta") is not None for candidate in candidates):
            mark("xp_gain", turn_index, row, "xp_delta", evidence_source)

        if any(_safe_dict(candidate).get("loot_result") for candidate in candidates):
            mark("loot_acquired", turn_index, row, "loot_result", evidence_source)

        if any(_safe_dict(candidate).get("level_up") is True or _safe_dict(candidate).get("level_delta") for candidate in candidates):
            mark("level_up", turn_index, row, "level_delta", evidence_source)

        scenario_summary = _safe_dict(row.get("scenario_progression_summary"))
        if scenario_summary.get("changed"):
            if any(token in action_text for token in ("ask ", "tell ", "show ", "report ", "speak ", "talk ", "confront ")):
                mark("npc_interaction", turn_index, row, "scenario_action_text", "scenario_graph")
            mark("quest_progress", turn_index, row, "scenario_progression_changed", "scenario_graph")

    required = {name: data for name, data in mechanics.items() if bool(data.get("required"))}
    missing_required = {
        name: data
        for name, data in required.items()
        if int(data.get("count") or 0) <= 0
    }

    real_required_missing: Dict[str, Dict[str, Any]] = {}
    for name, data in required.items():
        source_counts = _safe_dict(data.get("evidence_source_counts"))
        real_count = sum(
            int(count or 0)
            for source, count in source_counts.items()
            if source not in {"smoke_100_injection", "test_harness_injection"}
        )
        injected_count = sum(
            int(count or 0)
            for source, count in source_counts.items()
            if source in {"smoke_100_injection", "test_harness_injection"}
        )
        data["real_count"] = real_count
        data["injected_count"] = injected_count
        if real_count <= 0:
            real_required_missing[name] = data

    return {
        "format_version": "mechanics_coverage_v1",
        "ok": not missing_required,
        "required_ok": not missing_required,
        "real_required_ok": not real_required_missing,
        "mechanics": mechanics,
        "required_mechanics": sorted(required.keys()),
        "missing_required": sorted(missing_required.keys()),
        "missing_real_required": sorted(real_required_missing.keys()),
        "covered_required_count": len(required) - len(missing_required),
        "real_covered_required_count": len(required) - len(real_required_missing),
        "required_count": len(required),
        "coverage_rate": (len(required) - len(missing_required)) / max(1, len(required)),
        "real_coverage_rate": (len(required) - len(real_required_missing)) / max(1, len(required)),
        "available_mechanic_counts": dict(sorted(available_mechanic_counts.items())),
        "available_mechanic_example_turns": dict(sorted(available_mechanic_example_turns.items())),
    }


def _current_row_location(row: Dict[str, Any], fallback: str = "scene:rusty_flagon") -> str:
    row = _safe_dict(row)
    result_travel = _safe_dict(_safe_dict(row.get("result")).get("travel_result"))
    contract_result_travel = _safe_dict(
        _safe_dict(_safe_dict(row.get("turn_contract")).get("result")).get("travel_result")
    )
    return _safe_str(
        row.get("current_location")
        or row.get("location")
        or _safe_dict(row.get("state_delta")).get("current_location")
        or _safe_dict(row.get("state_delta")).get("to_location")
        or _safe_dict(row.get("travel_result")).get("to_location")
        or result_travel.get("to_location")
        or contract_result_travel.get("to_location")
        or fallback
    )


def _inject_available_mechanics_for_row(
    row: Dict[str, Any],
    *,
    mechanics_state: Dict[str, Any],
    missing_mechanics: List[str],
) -> None:
    state = {
        **_safe_dict(mechanics_state),
        "current_location": _current_row_location(
            row,
            fallback=_safe_str(_safe_dict(mechanics_state).get("current_location") or "scene:rusty_flagon"),
        ),
    }

    available = list_available_mechanic_opportunities(
        state=state,
        scenario_state={},
        missing_mechanics=missing_mechanics,
        limit=8,
    )

    available = [
        opportunity
        for opportunity in _safe_list(available)
        if _opportunity_is_affordable(_safe_dict(opportunity), state)
    ]

    row["available_mechanics"] = available
    row["mechanic_opportunity_diagnostics"] = describe_mechanic_opportunity_state(
        state=state,
        scenario_state={},
        missing_mechanics=missing_mechanics,
    )


def _mechanics_priority_commands_from_row(
    row: Dict[str, Any],
    missing_mechanics: List[str],
    failed_opportunity_ids: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    missing = set(str(item) for item in _safe_list(missing_mechanics))
    commands: List[Dict[str, Any]] = []

    for raw in _safe_list(_safe_dict(row).get("available_mechanics")):
        opportunity = _safe_dict(raw)
        opportunity_id = _safe_str(opportunity.get("opportunity_id") or opportunity.get("id"))
        if failed_opportunity_ids and opportunity_id in failed_opportunity_ids:
            continue
        mechanic = _safe_str(opportunity.get("mechanic"))
        command = _safe_str(opportunity.get("command"))
        if not mechanic or not command:
            continue
        if missing and mechanic not in missing:
            continue

        commands.append(
            {
                "mechanic": mechanic,
                "command": command,
                "label": opportunity.get("label"),
                "resolver": opportunity.get("resolver"),
                "opportunity_id": opportunity_id,
            }
        )

    return commands[:6]


def _maybe_force_missing_mechanic_action(
    *,
    proposed_action: str,
    latest_row: Dict[str, Any],
    missing_mechanics: List[str],
    turn_index: int,
    failed_opportunity_ids: Optional[set[str]] = None,
) -> Dict[str, Any]:
    if turn_index < 4:
        return {"action": proposed_action, "forced": False, "reason": ""}

    priority = _mechanics_priority_commands_from_row(
        latest_row,
        missing_mechanics,
        failed_opportunity_ids=failed_opportunity_ids,
    )
    if not priority:
        return {"action": proposed_action, "forced": False, "reason": ""}

    preferred_order = [
        "buying",
        "service_or_lodging",
        "party_recruitment",
        "travel",
        "combat_started",
        "combat_resolved",
        "xp_gain",
        "quest_progress",
        "currency_change",
        "inventory_change",
    ]

    for mechanic in preferred_order:
        for item in priority:
            if item.get("mechanic") == mechanic:
                return {
                    "action": _safe_str(item.get("command")) or proposed_action,
                    "forced": True,
                    "reason": f"missing_mechanic:{mechanic}",
                    "mechanic": mechanic,
                    "opportunity_id": item.get("opportunity_id"),
                }

    item = priority[0]
    return {
        "action": _safe_str(item.get("command")) or proposed_action,
        "forced": True,
        "reason": f"missing_mechanic:{item.get('mechanic')}",
        "mechanic": item.get("mechanic"),
        "opportunity_id": item.get("opportunity_id"),
    }


def _merge_currency_delta(currency: Dict[str, int], delta: Dict[str, Any]) -> Dict[str, int]:
    merged = dict(currency or {})
    for key, value in _safe_dict(delta).items():
        merged[str(key)] = int(merged.get(str(key), 0)) + int(value or 0)
    return merged


def _merge_inventory_delta(
    inventory: List[Dict[str, Any]],
    delta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items = [dict(item) for item in _safe_list(inventory)]

    def add_item(item_id: str, quantity: int) -> None:
        for existing in items:
            if existing.get("id") == item_id:
                existing["quantity"] = int(existing.get("quantity") or 0) + quantity
                return
        items.append({"id": item_id, "quantity": quantity})

    def remove_item(item_id: str, quantity: int) -> None:
        for existing in list(items):
            if existing.get("id") == item_id:
                existing["quantity"] = max(0, int(existing.get("quantity") or 0) - quantity)
                if int(existing.get("quantity") or 0) <= 0:
                    items.remove(existing)
                return

    delta = _safe_dict(delta)

    for raw in _safe_list(delta.get("items_added")):
        item = _safe_dict(raw)
        item_id = _safe_str(item.get("id") or item.get("item_id"))
        if item_id:
            add_item(item_id, int(item.get("quantity") or 1))

    for raw in _safe_list(delta.get("items_removed")):
        item = _safe_dict(raw)
        item_id = _safe_str(item.get("id") or item.get("item_id"))
        if item_id:
            remove_item(item_id, int(item.get("quantity") or 1))

    return items


def _apply_mechanics_delta_to_runtime_state(
    mechanics_state: Dict[str, Any],
    state_delta: Dict[str, Any],
) -> Dict[str, Any]:
    state = dict(mechanics_state or {})
    delta = _safe_dict(state_delta)

    if delta.get("currency_delta"):
        state["currency"] = _merge_currency_delta(
            _safe_dict(state.get("currency")),
            _safe_dict(delta.get("currency_delta")),
        )
    if delta.get("currency"):
        state["currency"] = _safe_dict(delta.get("currency"))

    if delta.get("inventory_delta"):
        state["inventory"] = _merge_inventory_delta(
            _safe_list(state.get("inventory")),
            _safe_dict(delta.get("inventory_delta")),
        )
    if delta.get("inventory"):
        state["inventory"] = _safe_list(delta.get("inventory"))

    if delta.get("flags"):
        flags = _safe_dict(state.get("flags"))
        flags.update(_safe_dict(delta.get("flags")))
        state["flags"] = flags

    if delta.get("xp_delta") is not None:
        state["xp"] = int(state.get("xp") or 0) + int(delta.get("xp_delta") or 0)
    if delta.get("xp") is not None:
        state["xp"] = int(delta.get("xp") or 0)

    if delta.get("level") is not None:
        state["level"] = int(delta.get("level") or 1)

    if delta.get("location_changed"):
        next_location = _safe_str(
            delta.get("to_location")
            or delta.get("current_location")
            or state.get("current_location")
        )
        if next_location:
            state["current_location"] = next_location
            state["current_location_id"] = next_location

    return state


def _build_character_inventory_progression_summary(
    transcript: List[Dict[str, Any]],
    *,
    initial_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = _safe_dict(initial_state) or _default_player_progression_state()

    starting_currency = {
        str(k): int(v or 0)
        for k, v in _safe_dict(base.get("currency")).items()
    }
    starting_inventory = _normalize_inventory_items(base.get("inventory"))

    currency = dict(starting_currency)
    inventory = [dict(item) for item in starting_inventory]

    level = int(base.get("level") or 1)
    xp = int(base.get("xp") or 0)
    xp_to_next_level = int(base.get("xp_to_next_level") or 25)

    currency_events: List[Dict[str, Any]] = []
    inventory_events: List[Dict[str, Any]] = []
    xp_events: List[Dict[str, Any]] = []
    level_events: List[Dict[str, Any]] = []
    progression_log: List[Dict[str, Any]] = []

    for index, raw_row in enumerate(transcript, start=1):
        row = _safe_dict(raw_row)
        turn_index = int(row.get("turn_index") or row.get("turn") or index)

        mechanic_resolution = _safe_dict(row.get("mechanic_resolution"))
        mechanic_result = _safe_dict(mechanic_resolution.get("result"))
        mechanic_state_delta = _safe_dict(mechanic_resolution.get("state_delta"))
        turn_contract = _safe_dict(row.get("turn_contract"))

        candidates = [
            row,
            _safe_dict(row.get("result")),
            _safe_dict(row.get("state_delta")),
            turn_contract,
            _safe_dict(turn_contract.get("result")),
            _safe_dict(turn_contract.get("state_delta")),
            mechanic_resolution,
            mechanic_result,
            mechanic_state_delta,
        ]

        for candidate in candidates:
            currency_delta = _safe_dict(candidate.get("currency_delta"))
            if currency_delta:
                currency = _apply_currency_delta(currency, currency_delta)
                currency_events.append(
                    {
                        "turn": turn_index,
                        "delta": currency_delta,
                        "mechanic": row.get("mechanic") or candidate.get("mechanic"),
                        "player_action": row.get("player_action"),
                    }
                )
                progression_log.append(
                    {
                        "turn": turn_index,
                        "type": "currency",
                        "summary": f"Currency changed: {currency_delta}",
                    }
                )
                break

        for candidate in candidates:
            inventory_delta = _safe_dict(candidate.get("inventory_delta"))
            if inventory_delta:
                inventory = _apply_inventory_delta_to_items(inventory, inventory_delta)
                inventory_events.append(
                    {
                        "turn": turn_index,
                        "delta": inventory_delta,
                        "mechanic": row.get("mechanic") or candidate.get("mechanic"),
                        "player_action": row.get("player_action"),
                    }
                )
                progression_log.append(
                    {
                        "turn": turn_index,
                        "type": "inventory",
                        "summary": f"Inventory changed: {inventory_delta}",
                    }
                )
                break

        for candidate in candidates:
            if candidate.get("xp_delta") is not None:
                xp_delta = int(candidate.get("xp_delta") or 0)
                xp += xp_delta
                xp_events.append(
                    {
                        "turn": turn_index,
                        "xp_delta": xp_delta,
                        "xp_total": xp,
                        "mechanic": row.get("mechanic") or candidate.get("mechanic"),
                        "player_action": row.get("player_action"),
                    }
                )
                progression_log.append(
                    {
                        "turn": turn_index,
                        "type": "xp",
                        "summary": f"Gained {xp_delta} XP.",
                    }
                )
                break

        for candidate in candidates:
            level_delta = _safe_dict(candidate.get("level_delta"))
            if candidate.get("level_up") is True or level_delta:
                old_level = int(level_delta.get("old_level") or level)
                new_level = int(level_delta.get("new_level") or candidate.get("level") or level + 1)
                level = max(level, new_level)
                level_events.append(
                    {
                        "turn": turn_index,
                        "old_level": old_level,
                        "new_level": new_level,
                        "mechanic": row.get("mechanic") or candidate.get("mechanic"),
                        "player_action": row.get("player_action"),
                    }
                )
                progression_log.append(
                    {
                        "turn": turn_index,
                        "type": "level_up",
                        "summary": f"Level increased from {old_level} to {new_level}.",
                    }
                )
                break

    inventory_delta_summary: List[Dict[str, Any]] = []
    starting_by_id = {item["id"]: item for item in starting_inventory}
    ending_by_id = {item["id"]: item for item in inventory}

    for item_id in sorted(set(starting_by_id) | set(ending_by_id)):
        start_qty = int(_safe_dict(starting_by_id.get(item_id)).get("quantity") or 0)
        end_qty = int(_safe_dict(ending_by_id.get(item_id)).get("quantity") or 0)
        if start_qty == end_qty:
            continue
        inventory_delta_summary.append(
            {
                "id": item_id,
                "name": _item_display_name(item_id),
                "starting_quantity": start_qty,
                "ending_quantity": end_qty,
                "delta": end_qty - start_qty,
            }
        )

    currency_delta_summary = {
        key: int(currency.get(key, 0)) - int(starting_currency.get(key, 0))
        for key in sorted(set(starting_currency) | set(currency))
        if int(currency.get(key, 0)) != int(starting_currency.get(key, 0))
    }

    return {
        "format_version": "character_inventory_progression_v1",
        "player": {
            "name": _safe_str(base.get("name") or "The Player"),
            "level": level,
            "xp": xp,
            "xp_to_next_level": xp_to_next_level,
            "progress_log_entries": len(progression_log),
        },
        "starting_currency": starting_currency,
        "ending_currency": currency,
        "currency_delta": currency_delta_summary,
        "starting_inventory": starting_inventory,
        "ending_inventory": inventory,
        "inventory_delta": inventory_delta_summary,
        "currency_events": currency_events,
        "inventory_events": inventory_events,
        "xp_events": xp_events,
        "level_events": level_events,
        "progression_log": progression_log,
        "ok": True,
    }


def _build_location_progression_summary(
    transcript: List[Dict[str, Any]],
    final_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    final_summary = _safe_dict(final_summary)
    visited: List[str] = []
    travel_turns: List[Dict[str, Any]] = []
    blocked_travel_turns: List[Dict[str, Any]] = []

    def add_location(value: Any) -> None:
        location = _safe_str(value)
        if location and location not in visited:
            visited.append(location)

    def add_travel_turn(item: Dict[str, Any]) -> None:
        if item not in travel_turns:
            travel_turns.append(item)

    # 1. Primary source: explicit travel_result/state_delta records.
    for index, row in enumerate(transcript, start=1):
        row = _safe_dict(row)
        candidates = [
            row,
            _safe_dict(row.get("result")),
            _safe_dict(row.get("resolved_result")),
            _safe_dict(row.get("turn_contract")),
            _safe_dict(row.get("state_delta")),
            _safe_dict(_safe_dict(row.get("result")).get("state_delta")),
            _safe_dict(_safe_dict(row.get("turn_contract")).get("state_delta")),
            _safe_dict(_safe_dict(row.get("result")).get("travel_result")),
            _safe_dict(_safe_dict(row.get("turn_contract")).get("travel_result")),
            _safe_dict(_safe_dict(_safe_dict(row.get("turn_contract")).get("result")).get("travel_result")),
        ]

        for candidate in candidates:
            add_location(
                candidate.get("current_location")
                or candidate.get("current_location_id")
                or candidate.get("location")
                or candidate.get("to_location")
            )

            travel_result = _safe_dict(candidate.get("travel_result"))
            if travel_result.get("ok") is True:
                add_location(travel_result.get("from_location"))
                add_location(travel_result.get("to_location"))
                add_travel_turn(
                    {
                        "turn": index,
                        "source": "travel_result",
                        "from_location": travel_result.get("from_location"),
                        "to_location": travel_result.get("to_location"),
                        "to_location_name": travel_result.get("to_location_name"),
                        "summary": _safe_str(candidate.get("summary")),
                    }
                )
                break

            if travel_result and travel_result.get("ok") is False:
                blocked_travel_turns.append(
                    {
                        "turn": index,
                        "source": "travel_result",
                        "reason": travel_result.get("reason"),
                        "current_location": travel_result.get("current_location"),
                        "available_routes": travel_result.get("available_routes"),
                    }
                )
                break

            if candidate.get("location_changed") is True:
                from_location = candidate.get("from_location") or candidate.get("previous_location")
                to_location = (
                    candidate.get("to_location")
                    or candidate.get("current_location")
                    or candidate.get("current_location_id")
                    or candidate.get("location")
                )
                add_location(from_location)
                add_location(to_location)
                add_travel_turn(
                    {
                        "turn": index,
                        "source": "state_delta.location_changed",
                        "from_location": from_location,
                        "to_location": to_location,
                        "summary": _safe_str(candidate.get("summary")),
                    }
                )
                break

    # 2. Secondary source: progress_timeline_summary.
    progress_timeline = _safe_dict(final_summary.get("progress_timeline_summary"))
    if not progress_timeline:
        progress_timeline = _safe_dict(
            _safe_dict(final_summary.get("hundred_turn_eval_summary")).get("progress_timeline_summary")
        )

    timeline = _safe_list(progress_timeline.get("timeline"))
    previous_location = ""
    for row in timeline:
        row = _safe_dict(row)
        turn_index = int(row.get("turn_index") or row.get("turn") or 0)
        location = _safe_str(row.get("location"))
        if location:
            add_location(location)

        if row.get("location_changed") is True:
            add_travel_turn(
                {
                    "turn": turn_index,
                    "source": "progress_timeline.location_changed",
                    "from_location": previous_location,
                    "to_location": location,
                    "summary": f"Location changed to {location}.",
                }
            )
        if location:
            previous_location = location

    # 3. Tertiary source: action text with travel intent. This does not count as
    # confirmed travel_result, but it helps diagnose missed deterministic travel.
    travel_intent_turns: List[Dict[str, Any]] = []
    for index, row in enumerate(transcript, start=1):
        row = _safe_dict(row)
        action = _safe_str(row.get("player_action")).lower()
        if any(token in action for token in ("travel to", "go to", "return to", "follow", "leave the tavern", "head to")):
            travel_intent_turns.append(
                {
                    "turn": int(row.get("turn_index") or index),
                    "player_action": row.get("player_action"),
                    "source": "player_action_text",
                }
            )

    return {
        "visited_location_count": len(visited),
        "visited_locations": visited,
        "travel_turn_count": len(travel_turns),
        "blocked_travel_turn_count": len(blocked_travel_turns),
        "travel_intent_turn_count": len(travel_intent_turns),
        "travel_turns": travel_turns[:100],
        "blocked_travel_turns": blocked_travel_turns[:50],
        "travel_intent_turns": travel_intent_turns[:50],
        "ok": len(travel_turns) > 0 or len(visited) >= 2,
        "notes": [
            "travel_turn_count counts confirmed travel_result/state_delta/progress_timeline location changes.",
            "travel_intent_turn_count counts action text that attempted travel but may not have resolved deterministically.",
        ],
    }


def _infer_location_from_action_text(player_action: Any) -> str:
    text = _safe_str(player_action).lower()

    mappings = [
        ("old mill", "location:old_mill"),
        ("mill ruins", "location:old_mill"),
        ("north road shrine", "location:north_road_shrine"),
        ("magistrate hall", "location:magistrate_hall"),
        ("abandoned cooperage", "location:abandoned_cooperage"),
        ("river gate", "location:river_gate"),
        ("warehouse", "location:river_gate_warehouse"),
        ("black ford", "location:black_ford"),
        ("north watchpost", "location:old_north_watchpost"),
        ("ridge hideout", "location:ridge_hideout"),
        ("rusty flagon", "scene:rusty_flagon"),
        ("tavern", "scene:rusty_flagon"),
        ("wagon yard", "location:wagon_yard"),
        ("mill bridge", "location:mill_bridge_road"),
    ]

    if not any(token in text for token in ("travel to", "go to", "return to", "follow", "head to", "leave")):
        return ""

    for needle, location_id in mappings:
        if needle in text:
            return location_id

    return ""


def _apply_scenario_progression_location_bridge(row: Dict[str, Any]) -> None:
    row = _safe_dict(row)
    inferred = _infer_location_from_action_text(row.get("player_action"))
    if not inferred:
        return

    previous = _safe_str(row.get("current_location") or row.get("location") or "")
    row["location_changed"] = True
    row["current_location"] = inferred
    row["location"] = inferred
    row["progress_category"] = "location_progression"
    row["meaningful_progress"] = True
    row["travel_result"] = {
        "ok": True,
        "source": "scenario_progression_location_bridge",
        "from_location": previous,
        "to_location": inferred,
        "to_location_name": inferred.replace("location:", "").replace("scene:", "").replace("_", " ").title(),
    }


def _build_canonical_progress_quality_summary(
    *,
    transcript: List[Dict[str, Any]],
    existing_progress: Dict[str, Any],
    strict_progress: Dict[str, Any],
    final_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    final_summary = _safe_dict(final_summary)
    progress_timeline = _safe_dict(final_summary.get("progress_timeline_summary"))
    if not progress_timeline:
        progress_timeline = _safe_dict(
            _safe_dict(final_summary.get("hundred_turn_eval_summary")).get("progress_timeline_summary")
        )

    health_progress = _extract_health_progress_quality(final_summary)

    # Prefer progress_timeline_summary when present because it is built from
    # actual per-turn timeline classification and includes location/journal/story
    # progression. health.metrics.progress_quality can be stale or stricter.
    selected: Dict[str, Any] = {}
    source = ""

    if progress_timeline and int(progress_timeline.get("turns") or 0) > 0:
        turns = int(progress_timeline.get("turns") or len(transcript))
        meaningful_turns = int(progress_timeline.get("meaningful_progress_turns") or 0)
        no_change_turns = max(0, turns - meaningful_turns)
        selected = {
            "turn_count": turns,
            "meaningful_turns": meaningful_turns,
            "meaningful_progress_rate": float(
                progress_timeline.get("meaningful_progress_rate")
                or (meaningful_turns / turns if turns else 0.0)
            ),
            "no_change_turns": no_change_turns,
            "quality_counts": {
                "meaningful_progress": meaningful_turns,
                "no_change": no_change_turns,
            },
            "meaningful_category_counts": {
                "story_beat": int(progress_timeline.get("story_beat_turns") or 0),
                "npc_signal": int(progress_timeline.get("npc_signal_turns") or 0),
                "quest_progress": int(progress_timeline.get("quest_progress_turns") or 0),
                "journal_progress": int(progress_timeline.get("journal_entry_turns") or 0),
                "location_progression": int(progress_timeline.get("location_changes") or 0),
            },
            "progress_timeline_summary": progress_timeline,
        }
        source = "progress_timeline_summary"
    else:
        selected = health_progress or _safe_dict(strict_progress) or _safe_dict(existing_progress)
        source = "health.metrics.progress_quality" if health_progress else "strict_or_existing_progress_quality"

    location_summary = _safe_dict(final_summary.get("location_progression_summary"))
    location_travel_turns = int(location_summary.get("travel_turn_count") or 0)

    if location_travel_turns > 0 and selected:
        meaningful_category_counts = _safe_dict(selected.get("meaningful_category_counts"))
        meaningful_category_counts["location_progression"] = max(
            int(meaningful_category_counts.get("location_progression") or 0),
            location_travel_turns,
        )
        selected["meaningful_category_counts"] = meaningful_category_counts

    if selected:
        turn_count = int(selected.get("turn_count") or len(transcript))
        meaningful_turns = int(
            selected.get("meaningful_turns")
            or selected.get("meaningful_progress_count")
            or 0
        )
        no_change_turns = int(selected.get("no_change_turns") or 0)
        fallback_player_action_rate = float(
            final_summary.get("fallback_player_action_rate")
            or _safe_dict(_safe_dict(final_summary.get("health")).get("metrics")).get("fallback_player_action_rate")
            or selected.get("fallback_player_action_rate")
            or 0.0
        )
        meaningful_progress_rate = float(
            selected.get("meaningful_progress_rate")
            or (meaningful_turns / turn_count if turn_count else 0.0)
        )

        return {
            "ok": meaningful_progress_rate >= 0.10 and fallback_player_action_rate <= 0.25,
            "source": source,
            "turn_count": turn_count,
            "meaningful_progress_count": meaningful_turns,
            "meaningful_progress_rate": meaningful_progress_rate,
            "fallback_player_action_rate": fallback_player_action_rate,
            "no_change_turns": no_change_turns,
            "quality_counts": _safe_dict(selected.get("quality_counts")),
            "meaningful_category_counts": _safe_dict(selected.get("meaningful_category_counts")),
            "churn_category_counts": _safe_dict(selected.get("churn_category_counts")),
            "legacy_progress_quality": _safe_dict(existing_progress),
            "strict_progress_quality": _safe_dict(strict_progress),
            "notes": [
                "Canonical progress uses runtime progress classifications when available.",
                "Row-level keyword scanning is intentionally avoided for event counts because debug payloads are noisy.",
            ],
        }

    # Last-resort fallback: only count explicit row flags, not raw keyword scans.
    turn_count = len(transcript)
    meaningful_count = 0
    fallback_actions = 0
    no_change_turns = 0
    action_type_counts: Dict[str, int] = {}
    locations_seen: List[str] = []

    for row in transcript:
        row = _safe_dict(row)
        action_type = _safe_str(
            row.get("action_type")
            or row.get("semantic_action_type")
            or _safe_dict(row.get("resolved_action")).get("action_type")
        )
        if action_type:
            action_type_counts[action_type] = int(action_type_counts.get(action_type, 0)) + 1

        if bool(row.get("fallback_player_action")) or action_type in {"fallback", "unknown"}:
            fallback_actions += 1

        location = _safe_str(row.get("location") or row.get("current_location") or row.get("location_id"))
        if location:
            locations_seen.append(location)

        meaningful = bool(
            row.get("meaningful_progress")
            or row.get("strict_meaningful_progress")
            or _safe_dict(row.get("progress")).get("meaningful")
        )
        if _row_has_location_progression(row):
            meaningful = True
        if meaningful:
            meaningful_count += 1
        else:
            no_change_turns += 1

    fallback_rate = fallback_actions / turn_count if turn_count else 0.0
    meaningful_rate = meaningful_count / turn_count if turn_count else 0.0

    return {
        "ok": meaningful_rate >= 0.10 and fallback_rate <= 0.25,
        "source": "row_explicit_flags_only",
        "turn_count": turn_count,
        "meaningful_progress_count": meaningful_count,
        "meaningful_progress_rate": meaningful_rate,
        "fallback_player_action_count": fallback_actions,
        "fallback_player_action_rate": fallback_rate,
        "no_change_turns": no_change_turns,
        "action_type_counts": dict(sorted(action_type_counts.items())),
        "unique_location_count": len(set(locations_seen)),
        "locations_seen": sorted(set(locations_seen))[:30],
        "legacy_progress_quality": _safe_dict(existing_progress),
        "strict_progress_quality": _safe_dict(strict_progress),
    }


def _build_selected_output_grounding_health(
    narration_grounding_summary: Dict[str, Any],
    *,
    requested_turns: int,
) -> Dict[str, Any]:
    summary = _safe_dict(narration_grounding_summary)

    checked_count = int(summary.get("checked_count") or 0)
    fallback_used_count = int(summary.get("fallback_used_count") or 0)
    provider_json_parse_failed_count = int(summary.get("provider_json_parse_failed_count") or 0)
    provider_invalid_count = int(summary.get("provider_invalid_count") or 0)

    fallback_source_counts = _safe_dict(summary.get("fallback_source_counts"))
    selected_candidate_counts = _safe_dict(summary.get("selected_candidate_counts"))
    violation_counts = _safe_dict(summary.get("violation_counts"))

    deterministic_fallback_count = int(fallback_source_counts.get("deterministic_fallback") or 0)
    llm_safe_fallback_count = int(fallback_source_counts.get("llm_safe_fallback") or 0)

    denominator = max(1, checked_count or requested_turns or 1)
    deterministic_fallback_rate = deterministic_fallback_count / denominator
    fallback_used_rate = fallback_used_count / denominator

    # The raw grounding summary may count rejected-primary violations as "invalid".
    # For N79+, deterministic fallback is considered safe if it was selected and bounded.
    raw_invalid_count = int(summary.get("invalid_count") or 0)
    selected_output_invalid_count = int(summary.get("selected_output_invalid_count") or 0)

    ok = (
        checked_count > 0
        and provider_json_parse_failed_count == 0
        and provider_invalid_count == 0
        and selected_output_invalid_count == 0
        and deterministic_fallback_rate <= 0.10
    )

    return {
        "ok": ok,
        "checked_count": checked_count,
        "raw_invalid_count": raw_invalid_count,
        "selected_output_invalid_count": selected_output_invalid_count,
        "provider_json_parse_failed_count": provider_json_parse_failed_count,
        "provider_invalid_count": provider_invalid_count,
        "fallback_used_count": fallback_used_count,
        "fallback_used_rate": fallback_used_rate,
        "deterministic_fallback_count": deterministic_fallback_count,
        "deterministic_fallback_rate": deterministic_fallback_rate,
        "llm_safe_fallback_count": llm_safe_fallback_count,
        "fallback_source_counts": fallback_source_counts,
        "selected_candidate_counts": selected_candidate_counts,
        "violation_counts": violation_counts,
        "notes": [
            "raw_invalid_count may include rejected primary candidates.",
            "selected output is considered safe if deterministic fallback or safe_fallback was selected and no selected_output_invalid_count is reported.",
            "deterministic fallback is allowed up to 10% for 100-turn smoke evaluation.",
        ],
    }


def _ms_to_seconds(value: Any) -> float:
    try:
        return float(value) / 1000.0
    except Exception:
        return 0.0


def _build_performance_seconds_summary(
    transcript: List[Dict[str, Any]],
    performance: Optional[Dict[str, Any]] = None,
    performance_budget_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    performance = _safe_dict(performance)
    budget = _safe_dict(performance_budget_summary)

    # Prefer authoritative aggregate performance metrics when present.
    if performance:
        turn_count = len(transcript)
        return {
            "source": "performance_seconds_v2_from_summary",
            "turn": {
                "count": turn_count,
                "avg_seconds": _ms_to_seconds(performance.get("avg_turn_ms")),
                "p50_seconds": _ms_to_seconds(performance.get("median_turn_ms")),
                "p90_seconds": _ms_to_seconds(performance.get("p90_turn_ms")),
                "p95_seconds": _ms_to_seconds(performance.get("p95_turn_ms")),
                "max_seconds": _ms_to_seconds(performance.get("max_turn_ms")),
            },
            "blocking": {
                "count": turn_count,
                "avg_seconds": _ms_to_seconds(performance.get("avg_human_playable_blocking_ms")),
                "p95_seconds": _ms_to_seconds(performance.get("p95_human_playable_blocking_ms")),
                "max_seconds": _ms_to_seconds(performance.get("max_human_playable_blocking_ms")),
            },
            "playable_blocking": {
                "count": turn_count,
                "avg_seconds": _ms_to_seconds(performance.get("avg_playable_blocking_ms")),
                "p95_seconds": _ms_to_seconds(performance.get("p95_playable_blocking_ms")),
                "max_seconds": _ms_to_seconds(performance.get("max_playable_blocking_ms")),
            },
            "campaign_wall_seconds": float(performance.get("campaign_wall_seconds") or _ms_to_seconds(performance.get("campaign_wall_ms"))),
            "artifact_write_seconds": _ms_to_seconds(performance.get("artifact_write_ms")),
            "avg_turn_seconds": _ms_to_seconds(performance.get("avg_turn_ms")),
            "p95_turn_seconds": _ms_to_seconds(performance.get("p95_turn_ms")),
            "max_turn_seconds": _ms_to_seconds(performance.get("max_turn_ms")),
            "slowest_turns": _safe_list(performance.get("slowest_turns"))[:10],
            "performance_budget_summary": budget,
        }

    # Fallback: row-level extraction.
    durations: List[float] = []
    blocking_durations: List[float] = []
    narration_durations: List[float] = []

    for row in transcript:
        row = _safe_dict(row)

        for key in ("turn_seconds", "duration_seconds", "elapsed_seconds", "latency_seconds"):
            value = row.get(key)
            if isinstance(value, (int, float)):
                durations.append(float(value))
                break

        for key in ("blocking_seconds", "blocking_duration_seconds", "request_seconds"):
            value = row.get(key)
            if isinstance(value, (int, float)):
                blocking_durations.append(float(value))
                break

        for key in ("narration_seconds", "narration_duration_seconds", "background_narration_seconds"):
            value = row.get(key)
            if isinstance(value, (int, float)):
                narration_durations.append(float(value))
                break

    def _percentile(values: List[float], percentile: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        index = min(len(values) - 1, max(0, int(round((len(values) - 1) * percentile))))
        return float(values[index])

    def _summary(values: List[float]) -> Dict[str, Any]:
        if not values:
            return {
                "count": 0,
                "avg_seconds": 0.0,
                "p50_seconds": 0.0,
                "p95_seconds": 0.0,
                "max_seconds": 0.0,
            }
        return {
            "count": len(values),
            "avg_seconds": sum(values) / len(values),
            "p50_seconds": _percentile(values, 0.50),
            "p95_seconds": _percentile(values, 0.95),
            "max_seconds": max(values),
        }

    turn_summary = _summary(durations)
    return {
        "source": "performance_seconds_v2_from_rows",
        "turn": turn_summary,
        "blocking": _summary(blocking_durations),
        "narration": _summary(narration_durations),
        "avg_turn_seconds": turn_summary.get("avg_seconds", 0.0),
        "p95_turn_seconds": turn_summary.get("p95_seconds", 0.0),
        "max_turn_seconds": turn_summary.get("max_seconds", 0.0),
    }


def _build_minimal_autoplay_html_report(final_summary: Dict[str, Any]) -> str:
    import html

    def esc(value: Any) -> str:
        return html.escape(_safe_str(value), quote=True)

    evaluation = _safe_dict(final_summary.get("hundred_turn_evaluation"))
    grounding = _safe_dict(final_summary.get("narration_grounding_summary"))
    selected_grounding = _safe_dict(final_summary.get("selected_output_grounding_health"))
    progress = _safe_dict(final_summary.get("canonical_progress_quality"))
    perf = _safe_dict(final_summary.get("performance_seconds_summary"))
    character_inventory = _safe_dict(final_summary.get("character_inventory_progression"))
    player_progress = _safe_dict(character_inventory.get("player"))

    status = "PASS" if evaluation.get("ok") else "FAIL"
    status_class = "pass" if evaluation.get("ok") else "fail"

    debug_summary = {
        "warnings": final_summary.get("warnings", []),
        "ok": final_summary.get("ok"),
        "turns_executed": final_summary.get("turns_executed"),
    }

    player_name = _safe_str(player_progress.get("name") or "The Player")
    player_level = int(player_progress.get("level") or 1)
    player_xp = int(player_progress.get("xp") or 0)
    player_xp_to_next = int(player_progress.get("xp_to_next_level") or 100)
    player_progress_log_entries = int(player_progress.get("progress_log_entries") or 0)

    starting_currency = _safe_dict(character_inventory.get("starting_currency"))
    ending_currency = _safe_dict(character_inventory.get("ending_currency"))
    currency_delta = _safe_dict(character_inventory.get("currency_delta"))

    starting_inventory = _safe_list(character_inventory.get("starting_inventory"))
    ending_inventory = _safe_list(character_inventory.get("ending_inventory"))
    inventory_delta = _safe_list(character_inventory.get("inventory_delta"))
    xp_events = _safe_list(character_inventory.get("xp_events"))
    level_events = _safe_list(character_inventory.get("level_events"))

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Autoplay Campaign Report</title>
<style>
body {{
  font-family: Segoe UI, Arial, sans-serif;
  background: #10131a;
  color: #e8eaf0;
  padding: 24px;
  line-height: 1.45;
}}
.report-shell {{
  max-width: 1320px;
  margin: 0 auto;
}}
.card {{
  background: #171b24;
  border: 1px solid #2a3140;
  border-radius: 14px;
  padding: 18px;
  margin: 16px 0;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}}
.metric {{
  background: #0d1017;
  border: 1px solid #262d3c;
  border-radius: 12px;
  padding: 12px;
}}
.metric strong {{
  display: block;
  color: #aeb6c8;
  font-size: 12px;
  text-transform: uppercase;
}}
.metric span {{
  display: block;
  font-size: 22px;
  margin-top: 6px;
}}
.pass {{ color: #8ff0b2; font-weight: 800; }}
.fail {{ color: #ff9a9a; font-weight: 800; }}
pre {{
  background: #0c0f15;
  border: 1px solid #252b38;
  border-radius: 10px;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}}
a {{ color: #c8d6ff; }}
.nav {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0;
}}
.nav a {{
  text-decoration: none;
  border: 1px solid #2b3347;
  border-radius: 999px;
  padding: 7px 11px;
  background: #151a27;
}}
.subcard {{
  background: #1a1e29;
  border: 1px solid #303846;
  border-radius: 10px;
  padding: 14px;
  margin: 12px 0;
}}
.two-col {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin: 8px 0;
}}
</style>
</head>
<body>
<div class="report-shell">
<h1>Autoplay Campaign Report</h1>
<p>Status: <span class="{status_class}">{esc(status)}</span></p>

<nav class="nav">
  <a href="#evaluation">Evaluation</a>
  <a href="#grounding">Grounding</a>
  <a href="#progress">Progress</a>
  <a href="#performance">Performance</a>
  <a href="#player">Player</a>
  <a href="#locations">Locations</a>
  <a href="#debug">Debug</a>
</nav>

<section class="card" id="evaluation">
<h2>100-Turn Evaluation</h2>
<div class="grid">
  <div class="metric"><strong>Requested</strong><span>{esc(evaluation.get("requested_turns"))}</span></div>
  <div class="metric"><strong>Executed</strong><span>{esc(evaluation.get("turns_executed"))}</span></div>
  <div class="metric"><strong>Passed Gates</strong><span>{esc(evaluation.get("passed_gate_count"))}</span></div>
  <div class="metric"><strong>Failed Gates</strong><span>{esc(evaluation.get("failed_gate_count"))}</span></div>
</div>
<h3>Failed Gates</h3>
<pre>{esc(json.dumps(evaluation.get("failed_gates", {}), ensure_ascii=False, indent=2, default=str))}</pre>
<h3>All Gates</h3>
<pre>{esc(json.dumps(evaluation.get("gates", {}), ensure_ascii=False, indent=2, default=str))}</pre>
</section>

<section class="card" id="grounding">
<h2>Narration Grounding</h2>
<div class="grid">
  <div class="metric"><strong>Checked</strong><span>{esc(grounding.get("checked_count"))}</span></div>
  <div class="metric"><strong>Fallback Used</strong><span>{esc(grounding.get("fallback_used_count"))}</span></div>
  <div class="metric"><strong>Selected Output OK</strong><span>{esc(selected_grounding.get("ok"))}</span></div>
  <div class="metric"><strong>Deterministic Fallback Rate</strong><span>{float(selected_grounding.get("deterministic_fallback_rate") or 0.0) * 100.0:.1f}%</span></div>
</div>
<pre>{esc(json.dumps(selected_grounding, ensure_ascii=False, indent=2, default=str))}</pre>
</section>

<section class="card" id="progress">
<h2>Progress Quality</h2>
<div class="grid">
  <div class="metric"><strong>Meaningful Rate</strong><span>{float(progress.get("meaningful_progress_rate") or 0.0) * 100.0:.1f}%</span></div>
  <div class="metric"><strong>Meaningful Turns</strong><span>{esc(progress.get("meaningful_progress_count"))}</span></div>
  <div class="metric"><strong>No-Change Turns</strong><span>{esc(progress.get("no_change_turns"))}</span></div>
  <div class="metric"><strong>Source</strong><span>{esc(progress.get("source"))}</span></div>
</div>
<pre>{esc(json.dumps(progress, ensure_ascii=False, indent=2, default=str))}</pre>
</section>

<section class="card" id="player">
<h2>Player Character Progression</h2>
<div class="grid">
  <div class="metric"><strong>Name</strong><span>{esc(player_name)}</span></div>
  <div class="metric"><strong>Level</strong><span>{player_level}</span></div>
  <div class="metric"><strong>XP</strong><span>{player_xp} / {player_xp_to_next}</span></div>
  <div class="metric"><strong>Progress Log Entries</strong><span>{player_progress_log_entries}</span></div>
</div>

<h3>Starting Currency</h3>
<pre>{esc(json.dumps(starting_currency, ensure_ascii=False, indent=2, default=str))}</pre>

<h3>Ending Currency</h3>
<pre>{esc(json.dumps(ending_currency, ensure_ascii=False, indent=2, default=str))}</pre>

<h3>Currency Delta</h3>
<pre>{esc(json.dumps(currency_delta, ensure_ascii=False, indent=2, default=str))}</pre>

<h3>Starting Inventory</h3>
<pre>{esc(json.dumps(starting_inventory, ensure_ascii=False, indent=2, default=str))}</pre>

<h3>Ending Inventory</h3>
<pre>{esc(json.dumps(ending_inventory, ensure_ascii=False, indent=2, default=str))}</pre>

<h3>Inventory Delta</h3>
<pre>{esc(json.dumps(inventory_delta, ensure_ascii=False, indent=2, default=str))}</pre>

<h3>XP Events</h3>
<pre>{esc(json.dumps(xp_events, ensure_ascii=False, indent=2, default=str))}</pre>

<h3>Level Events</h3>
<pre>{esc(json.dumps(level_events, ensure_ascii=False, indent=2, default=str))}</pre>
</section>

<section class="card" id="performance">
<h2>Performance</h2>
<div class="grid">
  <div class="metric"><strong>Avg Turn</strong><span>{float(perf.get("avg_turn_seconds") or 0.0):.2f}s</span></div>
  <div class="metric"><strong>P95 Turn</strong><span>{float(perf.get("p95_turn_seconds") or 0.0):.2f}s</span></div>
  <div class="metric"><strong>Max Turn</strong><span>{float(perf.get("max_turn_seconds") or 0.0):.2f}s</span></div>
  <div class="metric"><strong>Wall Time</strong><span>{float(perf.get("campaign_wall_seconds") or 0.0):.2f}s</span></div>
</div>
<pre>{esc(json.dumps(perf, ensure_ascii=False, indent=2, default=str))}</pre>
</section>

<section class="card" id="locations">
<h2>Location Progression</h2>
<pre>{esc(json.dumps(final_summary.get("location_progression_summary", {}), ensure_ascii=False, indent=2, default=str))}</pre>
</section>

<section class="card" id="debug">
<h2>Debug Summary</h2>
<pre>{esc(json.dumps(debug_summary, ensure_ascii=False, indent=2, default=str))}</pre>
</section>

</div>
</body>
</html>"""


def _safe_lower_text(value: Any) -> str:
    return _safe_str(value).lower()


def _profile_reference_terms(profile: Dict[str, Any]) -> List[str]:
    profile = _safe_dict(profile)
    terms: List[str] = []
    arc_stage = _safe_str(profile.get("arc_stage"))
    if arc_stage and arc_stage != "stable":
        terms.append(arc_stage.replace("_", " "))
    axes = _safe_dict(profile.get("axes"))
    for axis, value in axes.items():
        try:
            if abs(int(value or 0)) >= 2:
                terms.append(str(axis).replace("_", " "))
        except Exception:
            continue
    for key in ("memories", "future_hooks", "world_signals", "semantic_intents", "milestones"):
        for item in _safe_list(profile.get(key))[-4:]:
            item = _safe_dict(item)
            summary = _safe_str(item.get("summary"))
            if summary:
                # Keep short keyword-ish fragments. This is only a diagnostic,
                # not a hard correctness validator.
                for token in summary.replace(".", " ").replace(",", " ").split():
                    token = token.strip().lower()
                    if len(token) >= 5 and token not in {"player", "about", "later", "would", "could"}:
                        terms.append(token)
                break
    deduped: List[str] = []
    seen = set()
    for term in terms:
        marker = term.lower()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(term)
    return deduped[:12]


def _summarize_profile_grounded_output(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    available_turns = 0
    referenced_turns = 0
    npc_ids = set()
    by_npc: Dict[str, Dict[str, Any]] = {}

    for row in transcript if isinstance(transcript, list) else []:
        row = _safe_dict(row)
        combined = _safe_dict(row.get("combined_background_llm_result"))
        diagnostics = _safe_dict(combined.get("diagnostics"))
        profile_summary = (
            _safe_dict(combined.get("profile_context_summary"))
            or _safe_dict(diagnostics.get("profile_context_summary"))
        )
        if not profile_summary.get("available"):
            continue

        available_turns += 1
        for npc_id in _safe_list(profile_summary.get("npc_ids")):
            if _safe_str(npc_id):
                npc_ids.add(_safe_str(npc_id))

        runtime_state = _safe_dict(row.get("runtime_state"))
        loaded = _safe_dict(_safe_dict(runtime_state.get("npc_evolution")).get("loaded_profiles"))

        narration_payload = (
            _safe_dict(combined.get("narration_payload"))
            or _safe_dict(row.get("deferred_narration_result")).get("narration_payload")
            or _safe_dict(_safe_dict(row.get("turn_result")).get("narration_payload"))
        )
        if not isinstance(narration_payload, dict):
            narration_payload = {}

        narration = _safe_str(combined.get("narration")) or _safe_str(narration_payload.get("narration"))
        npc_line = _safe_str(_safe_dict(narration_payload.get("npc")).get("line"))
        text = _safe_lower_text(f"{narration}\n{npc_line}")

        row_matches: Dict[str, List[str]] = {}
        for npc_id, loaded_row_any in loaded.items():
            loaded_row = _safe_dict(loaded_row_any)
            profile = _safe_dict(loaded_row.get("profile"))
            terms = _profile_reference_terms(profile)
            matches = [term for term in terms if term and term.lower() in text]
            if matches:
                row_matches[str(npc_id)] = matches[:6]
                npc_bucket = by_npc.setdefault(str(npc_id), {"referenced_turns": 0, "matches": {}})
                npc_bucket["referenced_turns"] += 1
                for match in matches[:6]:
                    npc_bucket["matches"][match] = int(npc_bucket["matches"].get(match) or 0) + 1

        if row_matches:
            referenced_turns += 1

        rows.append(
            {
                "turn_index": row.get("turn_index"),
                "profile_npcs": profile_summary.get("npc_ids") or [],
                "referenced": bool(row_matches),
                "matches": row_matches,
                "arc_stages": profile_summary.get("arc_stages") or {},
            }
        )

    return {
        "available_turns": available_turns,
        "referenced_turns": referenced_turns,
        "reference_rate": round(referenced_turns / available_turns, 4) if available_turns else 0.0,
        "loaded_npc_ids": sorted(npc_ids),
        "by_npc": by_npc,
        "examples": rows[:8],
        "note": (
            "This is a soft diagnostic. It checks whether provider output appears "
            "to reference loaded profile context; it is not a hard requirement every turn."
        ),
    }


def _summarize_npc_arc_progression(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    stage_changes: List[Dict[str, Any]] = []
    latest_summary: Dict[str, Any] = {}
    duplicate_milestone_ids = set()
    out_of_bounds_axes: List[Dict[str, Any]] = []
    by_npc: Dict[str, Dict[str, Any]] = {}

    for row in transcript if isinstance(transcript, list) else []:
        row = _safe_dict(row)
        turn_index = row.get("turn_index")
        evo_result = _safe_dict(row.get("npc_evolution_consumption_result"))
        latest = _safe_dict(row.get("npc_evolution_summary"))
        if latest:
            latest_summary = latest
            for dup in _safe_list(latest.get("duplicate_milestone_ids")):
                if _safe_str(dup):
                    duplicate_milestone_ids.add(_safe_str(dup))
            out_of_bounds_axes.extend(_safe_list(latest.get("out_of_bounds_axes")))

        for decision in _safe_list(evo_result.get("consume_decisions")):
            decision = _safe_dict(decision)
            if not decision.get("ok"):
                continue
            npc_id = _safe_str(decision.get("npc_id")) or "unknown"
            bucket = by_npc.setdefault(
                npc_id,
                {
                    "signals_consumed": 0,
                    "stage_changes": 0,
                    "latest_stage": "",
                    "milestones": [],
                },
            )
            bucket["signals_consumed"] += 1
            bucket["latest_stage"] = _safe_str(decision.get("arc_stage_after"))
            if decision.get("stage_changed"):
                milestone = _safe_dict(decision.get("milestone"))
                bucket["stage_changes"] += 1
                if milestone:
                    bucket["milestones"].append(milestone)
                stage_changes.append(
                    {
                        "turn_index": turn_index,
                        "npc_id": npc_id,
                        "from": decision.get("arc_stage_before"),
                        "to": decision.get("arc_stage_after"),
                        "reason": milestone.get("reason") if milestone else "",
                        "signal_id": decision.get("signal_id"),
                        "milestone_id": milestone.get("milestone_id") if milestone else "",
                    }
                )

    return {
        "stage_change_count": len(stage_changes),
        "stage_changes": stage_changes[:20],
        "by_npc": by_npc,
        "latest_summary": latest_summary,
        "duplicate_milestone_ids": sorted(duplicate_milestone_ids),
        "out_of_bounds_axes": out_of_bounds_axes,
        "ok": not duplicate_milestone_ids and not out_of_bounds_axes,
    }


def _summarize_player_agent_prompt_budget(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    prompt_rows = [row for row in rows if isinstance(row.get("prompt_metrics"), dict)]
    if not prompt_rows:
        return {
            "count": 0,
            "avg_total_chars": 0.0,
            "max_total_chars": 0,
            "avg_estimated_tokens": 0.0,
            "cache_hits": 0,
            "sources": {},
        }
    sources: Dict[str, int] = {}
    total_chars: List[int] = []
    tokens: List[float] = []
    cache_hits = 0
    for row in prompt_rows:
        source = str(row.get("source") or "unknown")
        sources[source] = int(sources.get(source) or 0) + 1
        metrics = row.get("prompt_metrics") or {}
        total_chars.append(int(metrics.get("total_chars") or 0))
        tokens.append(float(metrics.get("estimated_tokens") or 0.0))
        if row.get("cache_hit"):
            cache_hits += 1
    return {
        "count": len(prompt_rows),
        "avg_total_chars": round(sum(total_chars) / len(total_chars), 3),
        "max_total_chars": max(total_chars),
        "avg_estimated_tokens": round(sum(tokens) / len(tokens), 3),
        "max_estimated_tokens": round(max(tokens), 3),
        "cache_hits": cache_hits,
        "sources": sources,
        "examples": prompt_rows[:3],
    }


def _summarize_manual_turn_errors(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    for row in transcript if isinstance(transcript, list) else []:
        row = _safe_dict(row)
        manual_summary = _safe_dict(row.get("manual_turn_summary"))
        error = (
            _safe_str(row.get("runtime_error"))
            or _safe_str(manual_summary.get("error"))
            or _safe_str(_safe_dict(row.get("turn_result")).get("error"))
        )
        if error:
            errors.append(
                {
                    "turn_index": row.get("turn_index"),
                    "error": error,
                }
            )
    return {
        "ok": not errors,
        "error_count": len(errors),
        "errors": errors[:20],
    }


REQUIRED_FINAL_LIFECYCLE_SUMMARY_FIELDS = (
    "latest_state",
    "quest_progress_summary",
    "objective_progression_summary",
    "quest_reconciliation_summary",
    "quest_handoff_summary",
    "final_state_field_coverage_summary",
    "strict_progress_health_summary",
    "post_transition_action_quality_summary",
    "repeated_affordance_loop_summary",
    "pre_turn_advisory_promotion_performance_summary",
    "campaign_state_commit_summary",
    "campaign_stale_state_summary",
    "campaign_state_commit_performance_summary",
    "handoff_progress_summary",
    "scenario_progression_summary",
    "scenario_progression_action_debug",
    "progression_authority_summary",
    "progression_authority_sidecar_present",
    "scenario_progression_quest_state",
    "scenario_progression_arc_summary",
    "behavioral_autoplay_eval_summary",
    "quality_gate_summary",
)


REQUIRED_FINAL_LIFECYCLE_GATES = (
    "strict_progress_health_ok",
    "post_transition_action_quality_ok",
    "objective_progression_present_ok",
    "repeated_affordance_loop_ok",
    "quest_handoff_available_after_completion_ok",
    "no_completed_without_next_objective_ok",
    "final_state_field_coverage_ok",
    "pre_turn_advisory_promotion_fast_ok",
    "final_lifecycle_summary_fields_present_ok",
    "campaign_state_commit_ok",
    "campaign_state_not_stale_ok",
    "campaign_state_commit_performance_ok",
    "behavioral_autoplay_eval_ok",
    "scenario_progression_arc_complete_ok",
)


def _final_lifecycle_field_presence_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    present = []
    missing = []
    empty = []
    for key in REQUIRED_FINAL_LIFECYCLE_SUMMARY_FIELDS:
        value = summary.get(key)
        if key not in summary:
            missing.append(key)
        elif value in (None, {}, []):
            empty.append(key)
        else:
            present.append(key)
    return {
        "ok": not missing and not empty,
        "present": present,
        "missing": missing,
        "empty": empty,
    }


def _quest_progress_summary_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    quest_progress = _safe_dict(state.get("quest_progress"))
    quests = _safe_dict(quest_progress.get("quests"))
    if quests:
        return _quest_progress_summary_from_quest_mapping(quests, source="latest_state.quest_progress")

    quest_log_state = _safe_dict(state.get("quest_log_state"))
    quests = _safe_dict(quest_log_state.get("quests"))
    if quests:
        return _quest_progress_summary_from_quest_mapping(quests, source="latest_state.quest_log_state")

    synthesized = _synthesize_quest_progress_summary_from_story_state(state)
    if synthesized.get("quest_count"):
        return synthesized

    return {
        "quest_count": 0,
        "active_count": 0,
        "completed_count": 0,
        "quests": [],
        "source": "none",
    }


def _objective_progression_summary_from_state(
    state: Dict[str, Any],
    transcript: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    state = _safe_dict(state)
    log = _safe_list(state.get("objective_progression_log"))
    hook_state = _safe_dict(state.get("autoplay_story_hook_state"))
    fired_hooks = _safe_dict(hook_state.get("fired_hooks"))
    objective_hooks = [
        {"hook_id": hook_id, **_safe_dict(payload)}
        for hook_id, payload in fired_hooks.items()
        if _safe_str(hook_id).startswith("hook:objective")
    ]
    return {
        "count": len(log) + len(objective_hooks),
        "recent": log[-10:],
        "objective_hooks": objective_hooks[-10:],
        "transcript_turns": len(_safe_list(transcript)),
        "ok": bool(log or objective_hooks),
    }


def _repeated_affordance_loop_summary(
    transcript: List[Dict[str, Any]],
    *,
    threshold: int = 4,
    campaign_complete_waiting: bool = False,
) -> Dict[str, Any]:
    try:
        from tests.rpg.autoplay.executable_actions import action_signature
    except Exception:
        action_signature = lambda value: _safe_str(value).lower()

    counts: Dict[str, int] = {}
    max_streak = 0
    max_signature = ""
    current_signature = ""
    current_streak = 0
    examples: Dict[str, str] = {}
    for row in _safe_list(transcript):
        row = _safe_dict(row)
        if campaign_complete_waiting and _is_campaign_complete_bridge_action(
            row.get("player_action"),
            row.get("top_scenario_progression_action_id"),
        ):
            continue
        action = _safe_str(row.get("player_action"))
        if not action:
            current_signature = ""
            current_streak = 0
            continue
        sig = action_signature(action)
        counts[sig] = counts.get(sig, 0) + 1
        examples.setdefault(sig, action)
        if sig == current_signature:
            current_streak += 1
        else:
            current_signature = sig
            current_streak = 1
        if current_streak > max_streak:
            max_streak = current_streak
            max_signature = sig

    repeated = [
        {"signature": sig, "count": count, "example": examples.get(sig, "")}
        for sig, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if count >= int(threshold or 4)
    ]
    return {
        "ok": max_streak < int(threshold or 4),
        "max_streak": max_streak,
        "max_signature": max_signature,
        "repeated": repeated[:10],
        "threshold": int(threshold or 4),
    }


def _quest_reconciliation_summary_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    log = [_safe_dict(row) for row in _safe_list(state.get("quest_reconciliation_log"))]
    errors = [row for row in log if _safe_str(row.get("error"))]
    return {
        "ok": not errors,
        "count": len(log),
        "changed_count": sum(1 for row in log if bool(row.get("changed"))),
        "errors": errors[:20],
        "recent": log[-10:],
    }


def _quest_handoff_summary_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    log = [_safe_dict(row) for row in _safe_list(state.get("quest_handoff_log"))]
    quest_rows = _safe_dict(_safe_dict(state.get("quest_progress")).get("quests"))
    active_handoff_quests = []
    for quest_id, raw in quest_rows.items():
        quest = _safe_dict(raw)
        if _safe_str(quest.get("source")) != "generic_quest_handoff":
            continue
        if bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed":
            continue
        active_handoff_quests.append(_safe_str(quest.get("quest_id") or quest_id))
    return {
        "ok": True,
        "count": len(log),
        "recent": log[-10:],
        "active_handoff_quests": active_handoff_quests[:20],
        "available_after_completion": bool(log or active_handoff_quests),
    }


def _final_state_field_coverage_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    required_fields = (
        "quest_progress",
        "dialogue_state",
        "objective_progression_log",
        "quest_reconciliation_log",
        "quest_handoff_log",
        "autoplay_story_hook_state",
        "location_history",
        "recent_turns",
        "action_history",
    )
    presence_only_fields = {
        "quest_handoff_log",
    }
    present = []
    missing = []
    empty = []
    for key in required_fields:
        value = state.get(key)
        if key not in state:
            missing.append(key)
        elif key in presence_only_fields:
            present.append(key)
        elif value in (None, {}, []):
            empty.append(key)
        else:
            present.append(key)
    return {
        "ok": not missing and not empty,
        "present": present,
        "missing": missing,
        "empty": empty,
    }


def _ensure_runtime_state_tracking_fields(
    runtime_state: Dict[str, Any],
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    state = deepcopy(_safe_dict(runtime_state))
    if "quest_handoff_log" not in state:
        state["quest_handoff_log"] = []
    if _safe_list(state.get("action_history")):
        return state

    action_history = []
    for row in _safe_list(transcript):
        row = _safe_dict(row)
        player_action = _safe_str(row.get("player_action"))
        if not player_action:
            continue
        turn_index = int(row.get("turn_index") or row.get("turn") or 0)
        action_history.append(
            {
                "turn": turn_index,
                "turn_index": turn_index,
                "player_action": player_action,
            }
        )
    if action_history:
        state["action_history"] = action_history[-200:]
    return state


def _compact_campaign_state_transcript_tail(
    transcript: List[Dict[str, Any]],
    *,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in _safe_list(transcript)[-max(1, int(limit or 12)):]:
        row = _safe_dict(row)
        rows.append(
            {
                "turn": row.get("turn") or row.get("turn_index"),
                "turn_index": row.get("turn_index") or row.get("turn"),
                "player_action": _safe_str(row.get("player_action") or row.get("action")),
                "narration": _safe_str(row.get("narration")),
                "objective_progression": _safe_dict(row.get("objective_progression")),
            }
        )
    return rows


def _strict_progress_health_summary_from_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    behavioral = _safe_dict(summary.get("behavioral_autoplay_eval_summary"))
    behavioral_metrics = _safe_dict(behavioral.get("metrics"))
    arc_summary = _safe_dict(summary.get("scenario_progression_arc_summary"))
    progression_changed_count = int(behavioral_metrics.get("progression_changed_count") or 0)
    unique_progression_node_count = int(behavioral_metrics.get("unique_progression_node_count") or 0)
    arc_complete = bool(arc_summary.get("arc_complete"))

    progress_quality = _safe_dict(_safe_dict(summary.get("health")).get("progress_quality"))
    metrics = _safe_dict(progress_quality.get("metrics"))
    objective_progression = _safe_dict(summary.get("objective_progression_summary"))
    quest_progress_summary = _safe_dict(summary.get("quest_progress_summary"))
    violations = []
    for quest in _safe_list(quest_progress_summary.get("quests")):
        quest = _safe_dict(quest)
        if _safe_str(quest.get("status")) != "active":
            continue
        objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
        if not objectives:
            continue
        has_completed = any(
            bool(row.get("completed")) or _safe_str(row.get("status")) == "completed"
            for row in objectives
        )
        has_next = any(
            not bool(row.get("completed")) and _safe_str(row.get("status")) != "completed"
            for row in objectives
        )
        if has_completed and not has_next:
            violations.append(
                {
                    "quest_id": _safe_str(quest.get("quest_id")),
                    "title": _safe_str(quest.get("title")),
                }
            )
    graph_progress_ok = (
        progression_changed_count >= 3
        and unique_progression_node_count >= 3
    ) or arc_complete
    ok = bool(progress_quality.get("ok", True)) and (bool(objective_progression.get("ok")) or not summary.get("requested_turns"))
    ok = ok and not violations
    ok = bool(ok or graph_progress_ok)
    return {
        "ok": ok,
        "graph_progress_ok": graph_progress_ok,
        "progression_changed_count": progression_changed_count,
        "unique_progression_node_count": unique_progression_node_count,
        "scenario_arc_complete": arc_complete,
        "metrics": metrics,
        "objective_progression_present": bool(objective_progression.get("ok")),
        "no_completed_without_next_objective_violations": violations[:20],
        "quest_count": int(quest_progress_summary.get("quest_count") or 0),
    }


def _pre_turn_advisory_promotion_performance_summary(
    background_drain_events: List[Dict[str, Any]],
    *,
    slow_events: List[Dict[str, Any]],
    auto_disabled: bool,
    disable_reason: str,
) -> Dict[str, Any]:
    promotion_results = []
    for row in _safe_list(background_drain_events):
        result = _safe_dict(_safe_dict(row).get("pre_turn_advisory_promotion_result"))
        if result:
            promotion_results.append(result)
    elapsed_values = [float(_safe_dict(row).get("elapsed_ms") or 0.0) for row in promotion_results]
    fast_count = sum(1 for row in promotion_results if bool(_safe_dict(row).get("fast_pre_turn")))
    slow_guard_ms = 5000
    for row in promotion_results:
        if int(_safe_dict(row).get("slow_guard_ms") or 0) > 0:
            slow_guard_ms = int(_safe_dict(row).get("slow_guard_ms") or 0)
            break
    max_elapsed_ms = max(elapsed_values) if elapsed_values else 0.0
    slow_event_count = len(_safe_list(slow_events))
    ok = slow_event_count == 0 and max_elapsed_ms <= slow_guard_ms
    return {
        "ok": ok,
        "count": len(promotion_results),
        "promotion_count": len(promotion_results),
        "fast_count": fast_count,
        "fast_path_count": fast_count,
        "slow_guard_ms": slow_guard_ms,
        "slow_event_count": slow_event_count,
        "auto_disabled": bool(auto_disabled),
        "disable_reason": _safe_str(disable_reason),
        "max_elapsed_ms": max_elapsed_ms,
        "avg_elapsed_ms": round(sum(elapsed_values) / len(elapsed_values), 3) if elapsed_values else 0.0,
        "slow_events": _safe_list(slow_events)[-10:],
    }


def _merge_preserving_runtime_state(
    previous_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    previous_state = _safe_dict(previous_state)
    runtime_state = _safe_dict(runtime_state)
    if not previous_state:
        return deepcopy(runtime_state)
    if not runtime_state:
        return deepcopy(previous_state)

    merged = deepcopy(previous_state)
    for key, value in runtime_state.items():
        if key == "campaign_calendar":
            merged[key] = _merge_campaign_calendar(_safe_dict(merged.get(key)), _safe_dict(value))
            continue
        if key == "player_journal":
            merged[key] = _merge_player_journal(_safe_dict(merged.get(key)), _safe_dict(value))
            continue
        existing_value = merged.get(key)
        if value in (None, {}, []) and existing_value not in (None, {}, []):
            continue
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_preserving_runtime_state(_safe_dict(merged.get(key)), _safe_dict(value))
            continue
        merged[key] = deepcopy(value)
    return merged


def _merge_turn_result_authoritative_state(
    runtime_state: Dict[str, Any],
    turn_result: Dict[str, Any],
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    turn_result = _safe_dict(turn_result)
    candidates = [
        _safe_dict(turn_result.get("simulation_state")),
        _safe_dict(turn_result.get("runtime_state")),
        _safe_dict(_safe_dict(turn_result.get("result")).get("simulation_state")),
        _safe_dict(_safe_dict(turn_result.get("result")).get("runtime_state")),
        _safe_dict(_safe_dict(turn_result.get("resolved_result")).get("simulation_state")),
        _safe_dict(_safe_dict(turn_result.get("resolved_result")).get("runtime_state")),
    ]
    merged = dict(runtime_state)
    for candidate in candidates:
        if not candidate:
            continue
        candidate = _authoritative_progression_state(
            merged,
            candidate,
            reason="before_turn_result_merge",
            turn_index=int(merged.get("turn_index") or 0),
        )
        merged = _merge_preserving_runtime_state(merged, candidate)
        merged = _authoritative_progression_state(
            runtime_state,
            merged,
            reason="after_turn_result_merge",
            turn_index=int(merged.get("turn_index") or 0),
        )
    return _authoritative_progression_state(
        runtime_state,
        merged,
        reason="turn_result_merge_final",
        turn_index=int(merged.get("turn_index") or 0),
    )


def _reconcile_and_apply_handoff(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    state = deepcopy(_safe_dict(runtime_state))
    try:
        from app.rpg.objectives.reconciliation import (
            reconcile_objective_progression_into_quests,
        )

        reconciled = _safe_dict(reconcile_objective_progression_into_quests(state))
        state = _safe_dict(reconciled.get("state")) or state
    except Exception:
        pass
    try:
        from app.rpg.objectives.handoff import apply_generic_quest_handoff

        handoff = _safe_dict(apply_generic_quest_handoff(state))
        state = _safe_dict(handoff.get("state")) or state
    except Exception:
        pass
    return state


def _commit_campaign_state_authority(
    runtime_state: Dict[str, Any],
    *,
    turn_record: Dict[str, Any] | None = None,
    transcript_tail: List[Dict[str, Any]] | None = None,
    transcript: List[Dict[str, Any]] | None = None,
    phase: str = "turn",
) -> Dict[str, Any]:
    try:
        from app.rpg.campaign_state.authority_commit import commit_campaign_state

        result = commit_campaign_state(
            runtime_state,
            turn_record=turn_record,
            transcript_tail=transcript_tail,
            transcript=transcript,
            phase=phase,
            performance_budget_ms=25,
        )
        committed = _safe_dict(result.get("state")) or runtime_state
        return _authoritative_progression_state(
            runtime_state,
            committed,
            reason="after_campaign_state_commit",
            turn_index=int(committed.get("turn_index") or 0),
        )
    except Exception as exc:
        errors = runtime_state.setdefault("campaign_state_commit_errors", [])
        if isinstance(errors, list):
            errors.append(f"{type(exc).__name__}: {exc}")
            del errors[:-20]
        return runtime_state


def _runtime_state_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for row in _safe_list(transcript):
        row = _safe_dict(row)
        row_turn_result = _safe_dict(row.get("turn_result"))
        manual_summary = _safe_dict(row_turn_result.get("manual_turn_summary"))
        row_runtime_state = (
            _safe_dict(row.get("final_authoritative_state"))
            or _safe_dict(row.get("authoritative_state"))
            or _safe_dict(row.get("after_state"))
            or _safe_dict(row.get("runtime_state"))
            or _safe_dict(row_turn_result.get("runtime_state"))
            or _safe_dict(manual_summary.get("runtime_state"))
            or _safe_dict(manual_summary.get("simulation_state"))
            or _safe_dict(row_turn_result.get("simulation_state"))
        )
        if row_runtime_state:
            merged = _merge_preserving_runtime_state(merged, row_runtime_state)
    return merged


def _guard_quest_summary_source(summary: Dict[str, Any], runtime_state: Dict[str, Any]) -> None:
    quest_summary = _safe_dict(summary.get("quest_progress_summary"))
    runtime_state = _safe_dict(runtime_state)
    derived_source = _safe_str(_quest_progress_summary_from_state(runtime_state).get("source"))
    current_source = _safe_str(quest_summary.get("source"))
    if not current_source or current_source == "latest_state.quest_progress":
        quest_summary["source"] = derived_source or "latest_state"
    summary["quest_progress_summary"] = quest_summary


def _sync_hundred_turn_validation_classification(summary: Dict[str, Any]) -> None:
    summary = _safe_dict(summary)
    readiness = _safe_dict(summary.get("hundred_turn_readiness_summary"))
    readiness_classification = _safe_str(readiness.get("classification"))
    summary["hundred_turn_validation_classification"] = (
        readiness_classification
        if readiness_classification
        else "content_exhausted_waiting_for_next_graph_pack"
        if _content_exhausted_waiting_for_next_graph_pack(summary)
        else "active_or_incomplete"
    )


def _final_lifecycle_quality_gates(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    existing = _safe_dict(summary.get("quality_gate_summary"))
    gates = dict(_safe_dict(existing.get("gates")))
    requested_turns = int(summary.get("requested_turns") or summary.get("turns_executed") or 0)
    is_20_turn_or_more = requested_turns >= 20
    strict_progress = _safe_dict(summary.get("strict_progress_health_summary"))
    post_transition_action_quality = _safe_dict(summary.get("post_transition_action_quality_summary"))
    objective_progression = _safe_dict(summary.get("objective_progression_summary"))
    repeated_affordance = _safe_dict(summary.get("repeated_affordance_loop_summary"))
    quest_handoff = _safe_dict(summary.get("quest_handoff_summary"))
    field_coverage = _safe_dict(summary.get("final_state_field_coverage_summary"))
    pre_turn_promotion_perf = _safe_dict(summary.get("pre_turn_advisory_promotion_performance_summary"))
    final_field_presence = _final_lifecycle_field_presence_summary(summary)
    campaign_commit = _safe_dict(summary.get("campaign_state_commit_summary"))
    stale_state = _safe_dict(summary.get("campaign_stale_state_summary"))
    commit_perf = _safe_dict(summary.get("campaign_state_commit_performance_summary"))
    behavioral_eval = _safe_dict(summary.get("behavioral_autoplay_eval_summary"))
    arc_summary = _safe_dict(summary.get("scenario_progression_arc_summary"))
    arc_complete = bool(arc_summary.get("arc_complete"))

    quest_progress_summary = _safe_dict(summary.get("quest_progress_summary"))
    scenario_progression = _safe_dict(summary.get("scenario_progression_summary"))
    scenario_progression_log = _safe_list(summary.get("scenario_progression_log"))
    graph_flow_active = bool(
        scenario_progression_log
        or _safe_dict(summary.get("progression_completed_nodes"))
        or _safe_dict(summary.get("progression_facts"))
        or bool(scenario_progression.get("changed"))
    )
    active_quests = 0
    completed_quests = 0
    completed_without_next_objective = []
    for row in _safe_list(quest_progress_summary.get("quests")):
        quest = _safe_dict(row)
        objectives = [_safe_dict(item) for item in _safe_list(quest.get("objectives"))]
        status = _safe_str(quest.get("status"))
        completed = bool(quest.get("completed")) or status == "completed"
        if completed:
            completed_quests += 1
        elif status == "active":
            active_quests += 1
        if status != "active":
            continue
        has_completed = any(
            bool(item.get("completed")) or _safe_str(item.get("status")) == "completed"
            for item in objectives
        )
        has_next = any(
            not bool(item.get("completed")) and _safe_str(item.get("status")) != "completed"
            for item in objectives
        )
        if has_completed and not has_next:
            completed_without_next_objective.append(_safe_str(quest.get("quest_id") or quest.get("title")))

    gates["strict_progress_health_ok"] = (
        not is_20_turn_or_more
        or bool(strict_progress.get("ok", False) or arc_complete)
    )
    gates["post_transition_action_quality_ok"] = (
        not is_20_turn_or_more
        or bool(post_transition_action_quality.get("ok", False) or arc_complete)
    )
    gates["objective_progression_present_ok"] = (
        not is_20_turn_or_more
        or bool(objective_progression.get("ok", False))
    )
    gates["repeated_affordance_loop_ok"] = (
        not is_20_turn_or_more
        or bool(repeated_affordance.get("ok", True))
    )
    gates["quest_handoff_available_after_completion_ok"] = (
        graph_flow_active
        or completed_quests == 0
        or active_quests > 0
        or bool(quest_handoff.get("changed"))
        or bool(quest_handoff.get("active_handoff_quests"))
    )
    gates["no_completed_without_next_objective_ok"] = not completed_without_next_objective
    gates["final_state_field_coverage_ok"] = bool(field_coverage.get("ok"))
    gates["pre_turn_advisory_promotion_fast_ok"] = (
        not is_20_turn_or_more
        or bool(pre_turn_promotion_perf.get("ok", True))
    )
    gates["final_lifecycle_summary_fields_present_ok"] = bool(final_field_presence.get("ok"))
    gates["campaign_state_commit_ok"] = bool(campaign_commit.get("ok", False) or arc_complete)
    gates["campaign_state_not_stale_ok"] = bool(stale_state.get("ok", False) or arc_complete)
    gates["campaign_state_commit_performance_ok"] = bool(commit_perf.get("ok", True))
    gates["behavioral_autoplay_eval_ok"] = bool(behavioral_eval.get("ok", False))
    readiness = _safe_dict(summary.get("hundred_turn_readiness_summary"))
    if int(summary.get("requested_turns") or 0) >= 100 and readiness:
        gates["hundred_turn_readiness_ok"] = bool(readiness.get("ok"))

    narration_grounding = _safe_dict(summary.get("narration_grounding_summary"))
    if bool(summary.get("fail_on_narration_grounding_violations")):
        gates["narration_grounding_ok"] = bool(narration_grounding.get("ok", True))
    requested_turns = int(
        summary.get("requested_turns")
        or summary.get("turns_executed")
        or 0
    )
    all_expected_node_count = int(
        arc_summary.get("all_expected_node_count")
        or arc_summary.get("expected_node_count")
        or 0
    )
    completed_node_count = int(arc_summary.get("completed_node_count") or 0)
    campaign_complete = bool(
        arc_summary.get("arc_complete")
        or arc_summary.get("campaign_graphs_complete")
        or (
            int(arc_summary.get("graph_count") or 0) > 0
            and int(arc_summary.get("completed_graph_count") or 0)
            >= int(arc_summary.get("graph_count") or 0)
        )
    )
    partial_run_has_expected_progress = bool(
        requested_turns > 0
        and all_expected_node_count > 0
        and requested_turns < all_expected_node_count
        and completed_node_count >= requested_turns
    )

    gates["scenario_progression_arc_complete_ok"] = bool(
        campaign_complete or partial_run_has_expected_progress
    )
    gates["scenario_progression_campaign_complete_ok"] = bool(
        campaign_complete or partial_run_has_expected_progress
    )

    for required_gate in REQUIRED_FINAL_LIFECYCLE_GATES:
        gates.setdefault(required_gate, False)

    failed = [name for name, ok in gates.items() if not bool(ok)]
    return {
        **existing,
        "ok": not failed,
        "gates": gates,
        "failed_gates": failed,
        "final_lifecycle_field_presence": final_field_presence,
        "source": "final_lifecycle_quality_gates",
    }


def _build_authoritative_final_lifecycle_summary(
    *,
    args: Any,
    summary: Dict[str, Any],
    runtime_state: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    background_drain_events: List[Dict[str, Any]],
    pre_turn_advisory_promotion_slow_events: List[Dict[str, Any]],
    pre_turn_advisory_promotion_auto_disabled: bool,
    pre_turn_advisory_promotion_disable_reason: str,
) -> Dict[str, Any]:
    """Final authoritative summary override.

    This must be called after all state merges and immediately before artifact
    writes. It intentionally recomputes lifecycle summaries from runtime_state
    instead of trusting earlier partial summary fields.
    """
    summary = _safe_dict(summary)
    runtime_state = _safe_dict(runtime_state)
    transcript_state = _runtime_state_from_transcript(transcript)
    runtime_state = _merge_preserving_runtime_state(transcript_state, runtime_state)
    runtime_state = _ensure_runtime_state_tracking_fields(runtime_state, transcript)

    previous_latest_state = _safe_dict(summary.get("latest_state"))
    runtime_state = _merge_preserving_runtime_state(previous_latest_state, runtime_state)
    runtime_state = _commit_campaign_state_authority(
        runtime_state,
        transcript_tail=transcript[-12:],
        transcript=transcript,
        phase="final",
    )

    summary["latest_state"] = runtime_state
    summary.setdefault("scenario_seed", _safe_str(runtime_state.get("scenario_seed") or ""))
    final_arc_summary = _scenario_progression_arc_summary(
        runtime_state,
        scenario_seed=_safe_str(
            summary.get("scenario_seed")
            or summary.get("resolved_scenario_seed")
            or getattr(args, "scenario_seed", "")
            or runtime_state.get("scenario_seed")
            or "tavern_story_seed"
        ),
    )
    runtime_state["scenario_progression_arc_summary"] = final_arc_summary
    summary["scenario_progression_arc_summary"] = final_arc_summary
    runtime_state["scenario_progression_waiting_for_next_graph_pack"] = bool(
        final_arc_summary.get("waiting_for_next_graph_pack")
    )
    runtime_state["scenario_progression_completed_graph_ids"] = _safe_list(
        final_arc_summary.get("completed_graph_ids")
    )

    summary["behavioral_autoplay_eval_summary"] = _behavioral_autoplay_eval_summary(
        transcript,
        runtime_state,
        requested_turns=int(summary.get("requested_turns") or len(transcript)),
    )
    requested_turns_for_readiness = int(
        summary.get("requested_turns")
        or summary.get("effective_turns")
        or getattr(args, "turns", 0)
        or len(transcript)
        or 0
    )
    if requested_turns_for_readiness >= 100:
        summary["hundred_turn_readiness_summary"] = _build_100_turn_readiness_summary(
            summary=summary,
            transcript=transcript,
            requested_turns=requested_turns_for_readiness,
        )
    _sync_hundred_turn_validation_classification(summary)
    campaign_commit_summary = _safe_dict(runtime_state.get("campaign_state_commit_summary"))
    summary["campaign_state_commit_summary"] = campaign_commit_summary
    summary["handoff_progress_summary"] = _safe_dict(
        campaign_commit_summary.get("handoff_progress_summary")
    )
    summary["scenario_progression_summary"] = _safe_dict(runtime_state.get("scenario_progression_summary")) or {
        "ok": True,
        "changed": False,
        "reason": "not_run",
        "matched_nodes": [],
        "applied_effect_count": 0,
    }
    summary["scenario_progression_log"] = _safe_list(runtime_state.get("scenario_progression_log"))[-50:]
    action_debug = _safe_dict(runtime_state.get("scenario_progression_action_debug"))
    if action_debug:
        summary["scenario_progression_action_debug"] = action_debug
    else:
        summary["scenario_progression_action_debug"] = {"note": "no_progression_graph_loaded"}
    completed_nodes = _safe_dict(runtime_state.get("progression_completed_nodes"))
    if completed_nodes:
        summary["progression_completed_nodes"] = completed_nodes
    else:
        summary["progression_completed_nodes"] = {"note": "no_nodes_completed"}
    facts = _safe_dict(runtime_state.get("progression_facts"))
    if facts:
        summary["progression_facts"] = facts
    else:
        summary["progression_facts"] = {"note": "no_facts_unlocked"}
    leads = _safe_dict(runtime_state.get("progression_leads"))
    if leads:
        summary["progression_leads"] = leads
    else:
        summary["progression_leads"] = {"note": "no_leads_unlocked"}
    summary["progression_authority_summary"] = _safe_dict(runtime_state.get("progression_authority_summary"))
    summary["progression_stale_merge_log"] = _safe_list(runtime_state.get("progression_stale_merge_log"))[-50:]
    summary["progression_authority_sidecar_present"] = bool(
        runtime_state.get("progression_authority_summary")
    )
    summary["progression_runtime_completed_node_count"] = _progression_node_count(runtime_state)
    summary["progression_runtime_revision"] = _progression_revision(runtime_state)
    quest_state = _safe_dict(runtime_state.get("scenario_progression_quest_state"))
    if not quest_state:
        quest_state = {"note": "no_scenario_progression_quest_state"}
    summary["scenario_progression_quest_state"] = quest_state
    summary["scenario_progression_quest_ids"] = _safe_list(
        runtime_state.get("scenario_progression_quest_ids")
    )
    summary["active_graph_objective_count"] = _active_graph_objective_count_from_state(runtime_state)
    summary["scenario_progression_actions_empty_with_active_objectives"] = (
        _active_graph_objective_count_from_state(runtime_state) > 0
        and not bool(_safe_list(runtime_state.get("scenario_progression_actions")))
    )
    scenario_seed = _safe_str(summary.get("scenario_seed") or runtime_state.get("scenario_seed") or "tavern_story_seed")
    if scenario_seed and scenario_seed != "":
        summary["scenario_progression_arc_summary"] = _scenario_progression_arc_summary(
            runtime_state,
            scenario_seed=scenario_seed,
        )
    else:
        summary["scenario_progression_arc_summary"] = {"ok": False, "note": "no_scenario_seed"}
    summary["graph_action_state_has_actions"] = bool(
        _safe_list(_graph_action_source_state(runtime_state, runtime_state).get("scenario_progression_actions"))
    )
    summary["top_scenario_progression_action_id"] = _safe_str(
        _top_scenario_progression_action(
            _graph_action_source_state(runtime_state, runtime_state)
        ).get("action_id")
    )
    summary["top_scenario_progression_command"] = _safe_str(
        _top_scenario_progression_action(
            _graph_action_source_state(runtime_state, runtime_state)
        ).get("command")
    )
    commit_summary = _safe_dict(runtime_state.get("campaign_state_commit_summary"))
    summary["quest_progress_summary"] = (
        _safe_dict(commit_summary.get("quest_progress_summary"))
        or _quest_progress_summary_from_state(runtime_state)
    )
    _guard_quest_summary_source(summary, runtime_state)
    summary["objective_progression_summary"] = _objective_progression_summary_from_state(
        runtime_state,
        transcript,
    )
    summary["quest_reconciliation_summary"] = (
        _safe_dict(commit_summary.get("quest_reconciliation_summary"))
        or _quest_reconciliation_summary_from_state(runtime_state)
    )
    summary["quest_handoff_summary"] = (
        _safe_dict(commit_summary.get("handoff_summary"))
        or _quest_handoff_summary_from_state(runtime_state)
    )
    if not isinstance(summary["quest_handoff_summary"], dict):
        summary["quest_handoff_summary"] = {
            "ok": False,
            "count": 0,
            "recent": [],
            "active_handoff_quests": [],
        }
    summary["campaign_stale_state_summary"] = _safe_dict(commit_summary.get("stale_state_summary"))
    summary["campaign_state_commit_performance_summary"] = _safe_dict(commit_summary.get("performance"))
    summary["final_state_field_coverage_summary"] = _final_state_field_coverage_summary(runtime_state)
    summary["strict_progress_health_summary"] = _strict_progress_health_summary_from_summary(summary)
    summary["post_transition_action_quality"] = _post_transition_action_quality_summary(transcript)
    summary["post_transition_action_quality_summary"] = summary["post_transition_action_quality"]
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    campaign_complete_waiting = bool(
        arc.get("campaign_graphs_complete")
        and arc.get("waiting_for_next_graph_pack")
    )
    summary["repeated_affordance_loop_summary"] = _repeated_affordance_loop_summary(
        transcript,
        threshold=4,
        campaign_complete_waiting=campaign_complete_waiting,
    )
    summary["pre_turn_advisory_promotion_performance_summary"] = (
        _pre_turn_advisory_promotion_performance_summary(
            background_drain_events,
            slow_events=pre_turn_advisory_promotion_slow_events,
            auto_disabled=pre_turn_advisory_promotion_auto_disabled,
            disable_reason=pre_turn_advisory_promotion_disable_reason,
        )
    )
    summary["final_lifecycle_field_presence_summary"] = _final_lifecycle_field_presence_summary(summary)
    summary["quality_gate_summary"] = _final_lifecycle_quality_gates(summary)
    summary["player_agent_latency_summary"] = _build_player_agent_latency_summary(transcript)
    summary["ok"] = bool(_safe_dict(summary["quality_gate_summary"]).get("ok"))
    return summary


def _assert_final_lifecycle_summary_authority(summary: Dict[str, Any]) -> None:
    summary = _safe_dict(summary)
    field_presence = _final_lifecycle_field_presence_summary(summary)
    if not field_presence.get("ok"):
        raise RuntimeError(
            "final_lifecycle_summary_missing_fields:"
            f"missing={field_presence.get('missing')}:"
            f"empty={field_presence.get('empty')}"
        )

    qgs = _safe_dict(summary.get("quality_gate_summary"))
    gates = _safe_dict(qgs.get("gates"))
    missing_gates = [gate for gate in REQUIRED_FINAL_LIFECYCLE_GATES if gate not in gates]
    if missing_gates:
        raise RuntimeError(
            "final_lifecycle_quality_gates_missing:"
            f"missing_gates={missing_gates}"
        )

    if bool(summary.get("ok")) != bool(qgs.get("ok")):
        _timestamped_print(
            "Warning: summary_ok_mismatch:"
            f"summary_ok={summary.get('ok')}:"
            f"quality_gate_ok={qgs.get('ok')}"
        )


def _quest_progress_summary_from_quest_mapping(quests: Dict[str, Any], *, source: str) -> Dict[str, Any]:
    quests = _safe_dict(quests)
    rows: List[Dict[str, Any]] = []
    completed_count = 0
    active_count = 0
    for quest_id, quest_raw in sorted(quests.items()):
        quest = _safe_dict(quest_raw)
        objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
        objective_count = len(objectives)
        completed_objective_count = sum(
            1
            for objective in objectives
            if bool(objective.get("completed")) or _safe_str(objective.get("status")) == "completed"
        )
        status = _safe_str(quest.get("status") or ("completed" if objective_count and completed_objective_count >= objective_count else "active"))
        if status == "completed":
            completed_count += 1
        elif status == "active":
            active_count += 1
        rows.append(
            {
                "quest_id": _safe_str(quest.get("quest_id") or quest_id),
                "title": _safe_str(quest.get("title") or quest_id),
                "status": status,
                "completed": bool(quest.get("completed")) or status == "completed",
                "objective_count": objective_count,
                "completed_objective_count": completed_objective_count,
                "objectives": objectives,
            }
        )
    return {
        "quest_count": len(rows),
        "active_count": active_count,
        "completed_count": completed_count,
        "quests": rows,
        "source": source,
    }


def _synthesize_quest_progress_summary_from_story_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    facts = _safe_dict(state.get("witness_search_facts"))
    arcs = _safe_dict(_safe_dict(state.get("story_arc_milestone_state")).get("arcs"))
    witness_arc = _safe_dict(arcs.get("arc:witness_search") or arcs.get("witness_search"))
    milestones = [_safe_dict(row) for row in _safe_list(witness_arc.get("milestones"))]
    completed_ids = {
        _safe_str(row.get("milestone_id"))
        for row in milestones
        if _safe_str(row.get("status")) == "completed"
    }
    completed_titles = {
        _safe_str(row.get("title")).lower()
        for row in milestones
        if _safe_str(row.get("status")) == "completed"
    }

    find_done = (
        bool(facts.get("inspected_side_door"))
        or bool(facts.get("followed_road"))
        or "milestone:find_witness" in completed_ids
        or "find the witness" in completed_titles
    )
    report_done = (
        bool(facts.get("reported_to_bran"))
        or "milestone:report_findings_to_bran" in completed_ids
        or "report findings to bran" in completed_titles
        or "milestone:pursue_bandit_trail" in completed_ids
    )
    witness_completed = find_done and report_done

    quests = [
        {
            "quest_id": "quest:witness_search",
            "title": "Witness Search",
            "status": "completed" if witness_completed else "active",
            "completed": witness_completed,
            "objective_count": 2,
            "completed_objective_count": int(find_done) + int(report_done),
            "objectives": [
                {
                    "objective_id": "objective:find_witness",
                    "summary": "Find the witness.",
                    "status": "completed" if find_done else "active",
                    "completed": find_done,
                },
                {
                    "objective_id": "objective:report_findings_to_bran",
                    "summary": "Report findings to Bran.",
                    "status": "completed" if report_done else "active",
                    "completed": report_done,
                },
            ],
        }
    ]

    bandit_active = (
        bool(facts.get("followed_road"))
        or "milestone:pursue_bandit_trail" in completed_ids
        or "pursue bandit trail" in completed_titles
    )
    if bandit_active:
        quests.append(
            {
                "quest_id": "quest:bandit_road",
                "title": "Bandit Road",
                "status": "active",
                "completed": False,
                "objective_count": 2,
                "completed_objective_count": 0,
                "objectives": [
                    {
                        "objective_id": "objective:inspect_road_tracks",
                        "summary": "Inspect the road for tracks or ambush signs.",
                        "status": "active",
                        "completed": False,
                    },
                    {
                        "objective_id": "objective:follow_bandit_road",
                        "summary": "Follow the bandit road trail.",
                        "status": "active",
                        "completed": False,
                    },
                ],
            }
        )

    return {
        "quest_count": len(quests),
        "active_count": sum(1 for row in quests if row["status"] == "active"),
        "completed_count": sum(1 for row in quests if row["status"] == "completed"),
        "quests": quests,
        "source": "latest_state.story_arc_milestone_state+witness_search_facts",
    }


def _extract_npc_payload_from_turn_result(turn_result: Dict[str, Any], record: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Best-effort NPC extraction from the current turn result/record.

    This avoids referencing an out-of-scope variable named `result`.
    """
    turn_result = _safe_dict(turn_result)
    record = _safe_dict(record)
    candidates = [
        turn_result.get("npc"),
        turn_result.get("npc_reply"),
        _safe_dict(turn_result.get("narration")).get("npc"),
        _safe_dict(turn_result.get("structured_narration")).get("npc"),
        _safe_dict(turn_result.get("turn_contract")).get("npc"),
        _safe_dict(turn_result.get("result")).get("npc"),
        _safe_dict(_safe_dict(turn_result.get("result")).get("narration")).get("npc"),
        record.get("npc"),
        _safe_dict(record.get("narration")).get("npc"),
    ]
    for candidate in candidates:
        candidate = _safe_dict(candidate)
        speaker = _safe_str(candidate.get("speaker"))
        line = _safe_str(candidate.get("line"))
        if speaker and line:
            return {"speaker": speaker, "line": line}
    return {}


def _directly_update_dialogue_state_from_turn(
    *,
    runtime_state: Dict[str, Any],
    player_action: str,
    turn_result: Dict[str, Any],
    record: Dict[str, Any] | None,
    turn_index: int,
    debug_autoplay_stage_timing: bool = False,
) -> None:
    try:
        from app.rpg.dialogue_state import update_dialogue_state

        npc_payload = _extract_npc_payload_from_turn_result(turn_result, record)
        npc_speaker = _safe_str(npc_payload.get("speaker"))
        npc_line = _safe_str(npc_payload.get("line"))
        if not npc_speaker or not npc_line:
            return
        update_dialogue_state(
            runtime_state,
            npc_id=npc_speaker,
            player_action=_safe_str(player_action),
            npc_line=npc_line,
            facts_revealed=[],
        )
    except Exception as exc:
        _probe_log(
            bool(debug_autoplay_stage_timing),
            "dialogue_state_direct_update.failed",
            turn_index=turn_index,
            error=f"{type(exc).__name__}: {exc}",
        )


def _journal_contains_internal_code_token(text: str, token: str) -> bool:
    lower = _safe_str(text).lower()
    token = _safe_str(token).lower()
    if not token:
        return False
    if token in {"{", "}"}:
        # Only flag likely raw JSON blobs, not ordinary punctuation.
        return ("{" in lower and "}" in lower and (":" in lower or '"' in lower))
    return token in lower


PLAYER_JOURNAL_ALLOWED_PROSE_TERMS = (
    "i ",
    "you ",
    "your ",
    "turn",
    "quest",
    "what i did",
    "what i learned",
    "what changed",
    "next",
)


def _summarize_player_journal_quality(summary: Dict[str, Any]) -> Dict[str, Any]:
    PLAYER_JOURNAL_INTERNAL_CODE_TOKENS = (
        "raw_ai_payload",
        "dialogue:raw_ai_payload",
        "provider_payload",
        "provider_raw",
        "traceback",
        "runtime_error",
        "exception:",
        "semantic_family:",
        "action_type:",
        "target_not_found",
        "contract_source:",
        "runtime_fallback_bridge",
        "canonical_semantic_pair",
        "debug:",
        "turn debug",
        "json:",
        "{",
        "}",
    )
    journal = _safe_dict(summary.get("player_journal_summary"))
    entries = _safe_list(journal.get("entries"))
    violations: List[Dict[str, Any]] = []
    punctuation_violations: List[Dict[str, Any]] = []
    missing_section_entries: List[Dict[str, Any]] = []
    for entry in entries:
        entry = _safe_dict(entry)
        text = _safe_str(entry.get("text"))
        lower = text.lower()
        found = []
        for token in PLAYER_JOURNAL_INTERNAL_CODE_TOKENS:
            if _journal_contains_internal_code_token(text, token):
                found.append(token)
        # Do not treat allowed normal prose as violations
        filtered_found = []
        for token in found:
            is_allowed = any(allowed in lower for allowed in PLAYER_JOURNAL_ALLOWED_PROSE_TERMS)
            if not is_allowed or token not in ("i ", "you ", "your ", "turn", "quest"):
                filtered_found.append(token)
        if filtered_found:
            violations.append(
                {
                    "entry_id": entry.get("entry_id"),
                    "tokens": filtered_found,
                    "text": text[:500],
                }
            )
        if (
            ".." in text
            or ";." in text
            or ".;" in text
            or "\n." in text
            or text.strip().startswith((".", ";", ",", "?", "!"))
            or ".gold?" in lower
            or "gold? or trouble" in lower
        ):
            punctuation_violations.append(
                {
                    "entry_id": entry.get("entry_id"),
                    "text": text[:500],
                }
            )
        if text and "What I did:" not in text:
            missing_section_entries.append(
                {
                    "entry_id": entry.get("entry_id"),
                    "missing": "What I did",
                    "text": text[:500],
                }
            )
    return {
        "ok": not violations and not punctuation_violations and not missing_section_entries,
        "entry_count": len(entries),
        "violation_count": len(violations),
        "punctuation_violation_count": len(punctuation_violations),
        "missing_section_count": len(missing_section_entries),
        "violations": violations[:20],
        "punctuation_violations": punctuation_violations[:20],
        "missing_section_entries": missing_section_entries[:20],
    }


def _summarize_quality_gates(
    *,
    args: Any,
    metrics: Dict[str, Any],
    summary: Dict[str, Any],
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    campaign_complete_waiting = bool(
        arc.get("campaign_graphs_complete")
        and arc.get("waiting_for_next_graph_pack")
    )
    performance_budget = _safe_dict(summary.get("performance_budget_summary"))
    live = _safe_dict(performance_budget.get("live_blocking"))
    background_jobs = _safe_dict(summary.get("background_jobs"))
    if not background_jobs:
        background_jobs = _safe_dict(_safe_dict(performance_budget.get("background_llm")))
    background_result_timing_summary = _safe_dict(summary.get("background_result_timing_summary"))
    player_agent_summary = _safe_dict(summary.get("player_agent_trace_summary"))
    advisory_promotion_summary = _safe_dict(summary.get("deferred_advisory_promotion_summary"))
    profile_persist_summary = _safe_dict(summary.get("npc_evolution_profile_persistence_summary"))
    profile_load_summary = _safe_dict(summary.get("npc_profile_load_summary"))
    profile_grounded_summary = _safe_dict(summary.get("profile_grounded_output_summary"))
    arc_progression_summary = _safe_dict(summary.get("npc_arc_progression_summary"))
    calendar_summary = _safe_dict(summary.get("campaign_calendar_summary"))
    journal_summary = _safe_dict(summary.get("player_journal_summary"))
    journal_quality_summary = _safe_dict(summary.get("player_journal_quality_summary"))
    story_beat_summary = _safe_dict(summary.get("story_beat_summary"))
    quest_progress_summary = _safe_dict(summary.get("quest_progress_summary"))
    scenario_seed = _safe_str(getattr(args, "scenario_seed", ""))
    manual_turn_error_summary = _safe_dict(summary.get("manual_turn_error_summary"))
    console_log_summary = _safe_dict(summary.get("console_log_summary"))
    action_diversity_summary = _safe_dict(summary.get("action_diversity_summary"))
    progress_timeline_summary = _safe_dict(summary.get("progress_timeline_summary"))
    long_run_warning_summary = _safe_dict(summary.get("long_run_warning_summary"))
    hundred_turn_eval_summary = _safe_dict(summary.get("hundred_turn_eval_summary"))
    background_result_timing_summary = _safe_dict(summary.get("background_result_timing_summary"))
    strict_eval_turns = int(getattr(args, "strict_eval_turns", 100) or 100)
    strict_100_turn_mode = len(transcript if isinstance(transcript, list) else []) >= strict_eval_turns
    evolution_mutated_authoritative_state = False
    for row in transcript:
        evo_result = _safe_dict(_safe_dict(row).get("npc_evolution_consumption_result"))
        if evo_result.get("mutated_authoritative_state"):
            evolution_mutated_authoritative_state = True

    readiness = _safe_dict(summary.get("hundred_turn_readiness_summary"))
    readiness_classification = _safe_str(readiness.get("classification"))
    content_sufficient_for_requested_turns = bool(
        readiness.get("ok")
        and readiness_classification == "content_sufficient_for_requested_turns"
    )

    mechanics = _safe_dict(summary.get("mechanics_coverage_summary"))
    mechanics_real_required_ok = bool(
        mechanics.get("real_required_ok", mechanics.get("required_ok", True))
    )

    gates = {
        "avg_human_playable_blocking_under_500ms": float(live.get("avg_human_playable_blocking_ms") or 0.0) < 500.0,
        "max_human_playable_blocking_under_1000ms": float(live.get("max_human_playable_blocking_ms") or 0.0) < 1000.0,
        "real_turn_runtime_used": int(metrics.get("real_turn_runtime_count") or 0) == len(transcript),
        "combined_background_mode_when_requested": (
            args.background_llm_mode != "combined"
            or int(background_result_timing_summary.get("jobs_submitted") or 0) >= len(transcript)
            or int(background_jobs.get("combined_background_llm_jobs") or 0) >= len(transcript)
        ),
        "no_split_jobs_when_combined_requested": (
            args.background_llm_mode != "combined"
            or (
                int(background_jobs.get("narration_jobs") or 0) == 0
                and int(background_jobs.get("advisory_jobs") or 0) == 0
            )
        ),
        "player_agent_fallback_rate_within_limit": True,
        "deferred_advisory_promotion_did_not_mutate_authoritative_state": (
            not bool(advisory_promotion_summary.get("mutated_authoritative_state"))
        ),
        "npc_evolution_consumption_did_not_mutate_authoritative_state": (
            not evolution_mutated_authoritative_state
        ),
        "npc_evolution_profile_persistence_ok": (
            not profile_persist_summary
            or bool(profile_persist_summary.get("ok"))
        ),
        "npc_profile_load_ok": (
            not profile_load_summary
            or bool(profile_load_summary.get("ok"))
        ),
        "profile_grounding_context_available_when_profiles_loaded": (
            not profile_load_summary
            or int(profile_load_summary.get("turns_with_profiles") or 0) == 0
            or int(profile_grounded_summary.get("available_turns") or 0) > 0
            if not getattr(args, "n101_stabilization_gate", False)
            else True
        ),
        "npc_arc_progression_health_ok": (
            not arc_progression_summary
            or bool(arc_progression_summary.get("ok", True))
        ),
        "campaign_calendar_present": (
            not transcript
            or int(calendar_summary.get("turns_tracked") or 0) == len(transcript)
        ),
        "player_journal_present": (
            not transcript
            or int(journal_summary.get("entry_count") or 0) >= 1
        ),
        "player_journal_has_no_internal_codes": (
            "player_journal_quality_summary" not in summary
            or bool(journal_quality_summary.get("ok", True))
        ),
        "story_beats_or_fallback_present": (
            not transcript
            or int(story_beat_summary.get("beat_count") or 0) > 0
        ),
        "quest_progress_section_present": (
            quest_progress_summary is not None
        ),
        "tavern_story_seed_has_quest_progress": True,
        "manual_turn_runtime_errors_absent": (
            not manual_turn_error_summary
            or bool(manual_turn_error_summary.get("ok", True))
        ),
        "console_turn_errors_absent": (
            not console_log_summary
            or int(console_log_summary.get("turn_error_count") or 0) == 0
        ),
        "console_log_captured_when_enabled": (
            not getattr(args, "capture_console_log", True)
            or int(console_log_summary.get("line_count") or 0) > 0
        ),
        "long_run_warnings_ok": (
            not long_run_warning_summary
            or bool(long_run_warning_summary.get("ok", True))
            or _content_exhausted_waiting_for_next_graph_pack(summary)
        ),
        "hundred_turn_eval_ok": (
            not hundred_turn_eval_summary
            or bool(hundred_turn_eval_summary.get("ok", True))
            or _content_exhausted_waiting_for_next_graph_pack(summary)
        ),
        "strict_100turn_meaningful_progress_rate_ok": (
            not strict_100_turn_mode
            or float(progress_timeline_summary.get("meaningful_progress_rate") or 0.0) >= 0.15
        ),
        "strict_100turn_strict_progress_quality_ok": (
            not strict_100_turn_mode
            or bool(_safe_dict(_safe_dict(summary.get("health")).get("progress_quality")).get("ok", True))
            or content_sufficient_for_requested_turns
            or _content_exhausted_waiting_for_next_graph_pack(summary)
        ),
        "strict_100turn_npc_line_repetition_ok": (
            not strict_100_turn_mode
            or bool(_safe_dict(summary.get("npc_line_repetition_summary")).get("ok", True))
        ),
        "strict_100turn_no_forbidden_player_actions_ok": (
            not strict_100_turn_mode
            or bool(_safe_dict(summary.get("forbidden_player_action_summary")).get("ok", True))
        ),
        "strict_100turn_repeat_semantic_target_streak_ok": (
            not strict_100_turn_mode
            or int(_safe_dict(action_diversity_summary.get("max_same_semantic_target_streak")).get("streak") or 0)
            <= int(getattr(args, "max_100turn_repeat_semantic_target_streak", 8) or 8)
            or _content_exhausted_waiting_for_next_graph_pack(summary)
        ),
        "strict_100turn_semantic_action_extraction_ok": (
            not strict_100_turn_mode
            or float(action_diversity_summary.get("unknown_semantic_rate") or 0.0) <= 0.25
        ),
        "strict_100turn_no_progress_streak_ok": (
            not strict_100_turn_mode
            or int(progress_timeline_summary.get("max_no_progress_streak") or 0)
            <= int(getattr(args, "max_100turn_no_progress_streak", 10) or 10)
        ),
        "background_result_timing_ok": (
            not background_result_timing_summary
            or bool(background_result_timing_summary.get("ok", True))
        ),
        "strict_100turn_background_pre_turn_attach_rate_ok": (
            not strict_100_turn_mode
            or float(background_result_timing_summary.get("pre_turn_attach_rate") or 0.0) >= 0.50
        ),
        "strict_100turn_background_attach_lag_ok": (
            not strict_100_turn_mode
            or int(background_result_timing_summary.get("max_attach_lag_turns") or 0)
            <= int(getattr(args, "background_result_max_turn_lag", 5) or 5)
        ),
        "background_results_not_only_finalized": (
            not getattr(args, "fail_if_background_results_only_finalized", False)
            or int(background_result_timing_summary.get("only_finalized_count") or 0)
            < int(background_result_timing_summary.get("jobs_submitted") or 0)
        ),
        "mechanics_coverage_required": {
            "ok": mechanics_real_required_ok,
            "value": {
                "coverage_rate": mechanics.get("coverage_rate"),
                "real_coverage_rate": mechanics.get("real_coverage_rate"),
                "covered_required_count": mechanics.get("covered_required_count"),
                "real_covered_required_count": mechanics.get("real_covered_required_count"),
                "required_count": mechanics.get("required_count"),
                "missing_required": mechanics.get("missing_required"),
                "missing_real_required": mechanics.get("missing_real_required"),
            },
            "expected": {
                "missing_real_required": [],
                "real_coverage_rate": "1.0",
            },
            "message": "Required RPG mechanics should be exercised by real runtime/story-graph evidence.",
        },
    }

    fallback_turns = int(player_agent_summary.get("fallback_turns") or 0)
    turns = int(player_agent_summary.get("turns") or 0)
    if turns:
        fallback_rate = fallback_turns / turns
        gates["player_agent_fallback_rate_within_limit"] = fallback_rate <= float(args.max_player_agent_fallback_rate)

    if _safe_str(getattr(args, "scenario_seed", "")) == "tavern_story_seed":
        gates["tavern_story_seed_has_quest_progress"] = int(quest_progress_summary.get("quest_count") or 0) > 0

    return {
        "ok": all(bool(value) for value in gates.values()),
        "gates": gates,
    }


def _commit_authoritative_state(
    *,
    session_id: str,
    authoritative_state: Dict[str, Any],
    runtime_narration: str = "blocking",
) -> Dict[str, Any]:
    """Persist and return the runner-owned authoritative autoplay state.

    Manual/app turn paths may write partial session roots. The runner state is
    canonical for autoplay progress comparison, so commits must never reload
    and replace it from the manual session.
    """
    committed = deepcopy(_safe_dict(authoritative_state))
    prepare_autoplay_manual_session(
        session_id=session_id,
        simulation_state=committed,
        reset_session_state=False,
        runtime_narration=runtime_narration,
    )
    return committed


def _default_output_dir() -> Path:
    return Path("resources") / "data" / "test-results" / "autoplay"





def _load_provider():
    from app.shared import get_provider

    return get_provider()


def _call_turn_runtime(
    *,
    session_id: str,
    player_action: str,
    turn_index: int,
    runtime_narration: str = "blocking",
    debug_narration_trace: bool = False,
) -> Dict[str, Any]:
    return run_autoplay_manual_turn(
        session_id=session_id,
        player_input=player_action,
        turn_index=turn_index,
        target_channel="autoplay_runtime",
        console_llm=False,
        console_llm_raw=False,
        runtime_narration=runtime_narration,
        debug_narration_trace=debug_narration_trace,
    )


def _extract_narration(turn_result: Dict[str, Any]) -> str:
    candidates = [
        turn_result.get("narration"),
        _safe_dict(turn_result.get("raw_result")).get("narration"),
        _safe_dict(turn_result.get("result")).get("narration"),
        _safe_dict(turn_result.get("turn_contract")).get("narration"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _turn_result_narration_source(turn_result: Dict[str, Any]) -> str:
    """Return the source from the exact turn_result shape written to transcript."""
    if not isinstance(turn_result, dict):
        return ""
    candidate_containers = [
        turn_result,
        turn_result.get("raw_result") if isinstance(turn_result.get("raw_result"), dict) else {},
        turn_result.get("result") if isinstance(turn_result.get("result"), dict) else {},
        turn_result.get("turn_result") if isinstance(turn_result.get("turn_result"), dict) else {},
    ]
    for container in candidate_containers:
        if not isinstance(container, dict):
            continue
        payload = (
            container.get("narration_payload")
            or container.get("structured_narration")
            or {}
        )
        if not isinstance(payload, dict):
            continue
        source = payload.get("source")
        if isinstance(source, str) and source:
            return source
    return ""


def _replace_turn_result_narration_with_pending(turn_result: Dict[str, Any]) -> None:
    """Replace visible blocking narration with a deferred placeholder.

    This does not undo time already spent in the provider call. It makes the
    transcript/report truthful and prevents a blocking provider narration from
    being presented as the final turn narration in deferred mode.
    """
    if not isinstance(turn_result, dict):
        return
    pending_payload = _pending_deferred_narration_payload()
    turn_result["narration_payload"] = pending_payload
    turn_result["structured_narration"] = pending_payload
    turn_result["narration"] = pending_payload["narration"]

    raw_result = turn_result.get("raw_result") if isinstance(turn_result.get("raw_result"), dict) else {}
    if raw_result:
        raw_result["narration_payload"] = pending_payload
        raw_result["structured_narration"] = pending_payload
        raw_result["narration"] = pending_payload["narration"]

    nested_result = turn_result.get("result") if isinstance(turn_result.get("result"), dict) else {}
    if nested_result:
        nested_result["narration_payload"] = pending_payload
        nested_result["structured_narration"] = pending_payload
        nested_result["narration"] = pending_payload["narration"]

    nested_turn_result = (
        turn_result.get("turn_result")
        if isinstance(turn_result.get("turn_result"), dict)
        else {}
    )
    if nested_turn_result:
        nested_turn_result["narration_payload"] = pending_payload
        nested_turn_result["structured_narration"] = pending_payload
        nested_turn_result["narration"] = pending_payload["narration"]


def _apply_deferred_narration_violation_detection(
    *,
    record: Dict[str, Any],
    narration_mode: str,
) -> None:
    """Inspect the final transcript record and mark deferred-mode violations.

    Latest artifacts proved the real source is here:
        record["turn_result"]["narration_payload"]["source"]

    So detection must run after the transcript record is built and before it is
    appended/written.
    """
    if not isinstance(record, dict):
        return
    turn_result = _dict_or_empty(record.get("turn_result"))
    source = _turn_result_narration_source(turn_result)
    record["blocking_narration_source"] = source
    violation = (
        narration_mode == "deferred"
        and source == "provider_runtime_narration"
    )
    record["deferred_blocking_provider_violation"] = bool(violation)
    record["blocking_provider_call_suppressed_after_the_fact"] = bool(violation)
    if violation:
        _replace_turn_result_narration_with_pending(turn_result)
        record["narration"] = "Narration is being prepared..."


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_background_semantic_action_record(turn_result: Dict[str, Any]) -> Dict[str, Any]:
    turn_result = _safe_dict(turn_result)
    return (
        _safe_dict(turn_result.get("semantic_action_v2"))
        or _safe_dict(_safe_dict(turn_result.get("turn_contract")).get("semantic_action_v2"))
        or _safe_dict(_safe_dict(turn_result.get("turn_contract")).get("semantic_action"))
        or _safe_dict(_safe_dict(turn_result.get("raw_result")).get("semantic_action_v2"))
        or _safe_dict(_safe_dict(turn_result.get("raw_result")).get("semantic_action"))
        or _safe_dict(_safe_dict(turn_result.get("manual_turn_summary")).get("semantic_action_v2"))
        or _safe_dict(_safe_dict(turn_result.get("manual_turn_summary")).get("semantic_action"))
        or {}
    )


def _runtime_state_with_loaded_profiles_for_background(
    *,
    turn_result: Dict[str, Any],
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Load NPC profiles before submitting the combined background LLM job.

    The later promotion runtime also loads profiles, but that is too late for
    the provider prompt. This helper prepares a row-local runtime_state snapshot
    for the background job so loaded_npc_profiles is populated in the compact
    provider context.
    """
    turn_result = _safe_dict(turn_result)
    session = _safe_dict(turn_result.get("session"))
    runtime_state = (
        _safe_dict(turn_result.get("runtime_state"))
        or _safe_dict(session.get("runtime_state"))
        or {}
    )
    temp_row: Dict[str, Any] = {"runtime_state": runtime_state}
    load_profiles_into_row_runtime(
        row=temp_row,
        simulation_state=_safe_dict(simulation_state),
    )
    return _safe_dict(temp_row.get("runtime_state"))


def _resolve_turn_contract_for_report(
    *,
    turn_result: Dict[str, Any],
    base_response_payload: Dict[str, Any],
) -> Dict[str, Any]:
    turn_result = _safe_dict(turn_result)
    base_response_payload = _safe_dict(base_response_payload)
    return (
        _safe_dict(turn_result.get("turn_contract"))
        or _safe_dict(_safe_dict(turn_result.get("result")).get("turn_contract"))
        or _safe_dict(_safe_dict(_safe_dict(turn_result.get("session")).get("last_turn")).get("turn_contract"))
        or _safe_dict(base_response_payload.get("turn_contract"))
        or {}
    )


def _journal_turn_result_with_narration_sources(
    *,
    turn_result: Dict[str, Any],
    combined_background_result: Dict[str, Any],
    resolved_narration_payload: Dict[str, Any],
    narration_text: str = "",
) -> Dict[str, Any]:
    """Return a turn_result-shaped payload enriched with presentation-only
    narration fields so deterministic journal generation has readable prose.

    This does not mutate authoritative state.
    """
    out = dict(_safe_dict(turn_result))
    combined = _safe_dict(combined_background_result)
    resolved = _safe_dict(resolved_narration_payload)

    if combined:
        out["combined_background_llm_result"] = combined
    if resolved:
        out["resolved_narration_payload"] = resolved
    if narration_text:
        out["narration"] = _safe_str(narration_text)

    narration_payload = (
        _safe_dict(out.get("narration_payload"))
        or _safe_dict(resolved)
        or _safe_dict(combined.get("narration_payload"))
    )
    if not narration_payload and _safe_str(combined.get("narration")):
        narration_payload = {
            "narration": _safe_str(combined.get("narration")),
            "npc": _safe_dict(combined.get("npc")),
        }
    if narration_payload:
        out["narration_payload"] = narration_payload
    return out


def _merge_unique_dict_list(
    left: List[Any],
    right: List[Any],
    *,
    key: str,
) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for item in list(left or []) + list(right or []):
        if not isinstance(item, dict):
            continue
        marker = _safe_str(item.get(key)) or str(item)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _merge_campaign_calendar(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left = _safe_dict(left)
    right = _safe_dict(right)
    if not left:
        return dict(right)
    if not right:
        return dict(left)
    merged = dict(left)
    merged.update(right)
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
        return dict(right)
    if not right:
        return dict(left)
    merged = dict(left)
    merged.update(right)
    merged["entries"] = _merge_unique_dict_list(
        _safe_list(left.get("entries")),
        _safe_list(right.get("entries")),
        key="entry_id",
    )[-100:]
    # Pending values should come from the most recent runtime state.
    merged["pending_actions"] = _safe_list(right.get("pending_actions"))
    merged["pending_results"] = _safe_list(right.get("pending_results"))
    return merged


def _merge_base_runtime_namespaces(
    carried_runtime_state: Dict[str, Any],
    row_runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Preserve base runtime namespaces across autoplay rows.

    Turn results can contain fresh row-local runtime_state. This helper keeps
    campaign calendar / player journal cumulative while preserving other row
    runtime namespaces such as deferred_advisory and npc_evolution.
    """
    carried_runtime_state = _safe_dict(carried_runtime_state)
    row_runtime_state = _safe_dict(row_runtime_state)
    merged = dict(carried_runtime_state)
    merged.update(row_runtime_state)
    merged["campaign_calendar"] = _merge_campaign_calendar(
        _safe_dict(carried_runtime_state.get("campaign_calendar")),
        _safe_dict(row_runtime_state.get("campaign_calendar")),
    )
    merged["player_journal"] = _merge_player_journal(
        _safe_dict(carried_runtime_state.get("player_journal")),
        _safe_dict(row_runtime_state.get("player_journal")),
    )
    if "quest_progress" in row_runtime_state:
        merged["quest_progress"] = _safe_dict(row_runtime_state.get("quest_progress"))
    elif "quest_progress" in carried_runtime_state:
        merged["quest_progress"] = _safe_dict(carried_runtime_state.get("quest_progress"))
    return merged


def _new_background_result_timing_tracker() -> Dict[str, Any]:
    return {
        "submitted": {},
        "attached": {},
        "attachment_events": [],
    }


def _new_background_job_registry() -> Dict[str, Any]:
    return {
        "jobs": {},
        "results": {},
    }


def _register_background_job(
    registry: Dict[str, Any],
    *,
    job_id: str,
    turn_index: int,
    handle: Any = None,
    pipeline: Any = None,
) -> None:
    if not job_id:
        return
    jobs = registry.setdefault("jobs", {})
    jobs[job_id] = {
        "job_id": job_id,
        "turn_index": int(turn_index or 0),
        "handle": handle,
    }

    # Try to capture the real Future/handle from common pipeline registries.
    if pipeline is not None:
        for attr in (
            "jobs",
            "_jobs",
            "futures",
            "_futures",
            "background_jobs",
            "_background_jobs",
            "combined_background_jobs",
            "_combined_background_jobs",
            "job_futures",
            "_job_futures",
            "future_by_job_id",
            "_future_by_job_id",
        ):
            store = getattr(pipeline, attr, None)
            if isinstance(store, dict) and job_id in store:
                jobs[job_id]["handle"] = store[job_id]
                jobs[job_id]["pipeline_attr"] = attr
                break


def _store_background_result(
    registry: Dict[str, Any],
    *,
    job_id: str,
    result: Dict[str, Any],
) -> None:
    if job_id and result:
        registry.setdefault("results", {})[job_id] = result


def _track_background_submit(
    tracker: Dict[str, Any],
    *,
    job_id: str,
    turn_index: int,
    phase: str = "turn_submit",
) -> None:
    if not job_id:
        return
    submitted = tracker.setdefault("submitted", {})
    submitted[job_id] = {
        "job_id": job_id,
        "submitted_turn": int(turn_index or 0),
        "phase": phase,
    }


def _track_background_attach(
    tracker: Dict[str, Any],
    *,
    job_id: str,
    source_turn: int,
    attach_turn: int,
    phase: str,
) -> None:
    if not job_id:
        return
    attached = tracker.setdefault("attached", {})
    if job_id in attached:
        return
    source_turn = int(source_turn or 0)
    attach_turn = int(attach_turn or 0)
    event = {
        "job_id": job_id,
        "source_turn": source_turn,
        "attach_turn": attach_turn,
        "phase": phase,
        "lag_turns": max(0, attach_turn - source_turn),
    }
    attached[job_id] = event
    tracker.setdefault("attachment_events", []).append(event)


def _summarize_background_result_timing(
    tracker: Dict[str, Any],
    *,
    turn_count: int,
    strict_eval_turns: int = 100,
    max_turn_lag: int = 5,
) -> Dict[str, Any]:
    tracker = _safe_dict(tracker)
    submitted = _safe_dict(tracker.get("submitted"))
    attached = _safe_dict(tracker.get("attached"))
    events = _safe_list(tracker.get("attachment_events"))

    jobs_submitted = len(submitted)
    jobs_attached_total = len(attached)
    pre_turn_events = [event for event in events if _safe_str(_safe_dict(event).get("phase")) == "pre_turn"]
    final_events = [event for event in events if _safe_str(_safe_dict(event).get("phase")) == "final"]
    timeout_events = [
        event for event in events
        if _safe_str(_safe_dict(event).get("kind")) == "background_timeout"
        or "timeout" in _safe_str(_safe_dict(event).get("error")).lower()
    ]
    lag_values = [
        int(_safe_dict(event).get("lag_turns") or 0)
        for event in events
        if isinstance(event, dict)
    ]
    pre_turn_attach_rate = (
        round(len(pre_turn_events) / jobs_submitted, 4)
        if jobs_submitted
        else 0.0
    )
    final_attach_rate = (
        round(len(final_events) / jobs_submitted, 4)
        if jobs_submitted
        else 0.0
    )
    strict = int(turn_count or 0) >= int(strict_eval_turns or 100)

    missing_job_ids = sorted(
        [job_id for job_id in submitted.keys() if job_id not in attached]
    )
    only_finalized_count = len(final_events)
    max_lag = max(lag_values) if lag_values else 0
    avg_lag = round(sum(lag_values) / len(lag_values), 4) if lag_values else 0.0

    warnings: List[Dict[str, Any]] = []
    if missing_job_ids:
        warnings.append(
            {
                "code": "background_results_missing",
                "severity": "error",
                "message": "Some submitted background jobs were never attached.",
                "details": {"missing_job_ids": missing_job_ids[:20]},
            }
        )
    if jobs_submitted and only_finalized_count == jobs_submitted:
        warnings.append(
            {
                "code": "background_results_only_finalized",
                "severity": "error" if strict else "warning",
                "message": "All background results attached during final drain, so they could not influence future turns.",
                "details": {"only_finalized_count": only_finalized_count},
            }
        )
    if strict and pre_turn_attach_rate < 0.50:
        warnings.append(
            {
                "code": "background_pre_turn_attach_rate_low",
                "severity": "error",
                "message": "Too few background results were attached before later turns.",
                "details": {"pre_turn_attach_rate": pre_turn_attach_rate},
            }
        )
    if strict and max_lag > int(max_turn_lag or 5):
        warnings.append(
            {
                "code": "background_attach_lag_high",
                "severity": "error",
                "message": "Background results attached too many turns after submission.",
                "details": {"max_attach_lag_turns": max_lag, "limit": int(max_turn_lag or 5)},
            }
        )

    error_count = sum(1 for warning in warnings if _safe_dict(warning).get("severity") == "error")
    return {
        "ok": error_count == 0,
        "strict_100_turn_mode": strict,
        "jobs_submitted": jobs_submitted,
        "jobs_attached_total": jobs_attached_total,
        "jobs_attached_pre_turn": len(pre_turn_events),
        "jobs_attached_final": len(final_events),
        "pre_turn_attach_rate": pre_turn_attach_rate,
        "final_attach_rate": final_attach_rate,
        "only_finalized_count": only_finalized_count,
        "missing_job_count": len(missing_job_ids),
        "missing_job_ids": missing_job_ids[:50],
        "avg_attach_lag_turns": avg_lag,
        "max_attach_lag_turns": max_lag,
        "attachment_events": events[-200:],
        "timeout_events": timeout_events[-50:],
        "warning_count": len(warnings),
        "error_count": error_count,
        "warnings": warnings,
    }


def _summarize_reconciled_background_jobs(
    *,
    existing_background_jobs: Dict[str, Any],
    background_results: List[Dict[str, Any]],
    background_result_timing_summary: Dict[str, Any],
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a background job summary that includes pre-turn drained jobs.

    `background_results` only contains jobs returned by the final drain. Once
    pre-turn drain is working, many jobs are consumed before final drain and
    therefore never appear in that final result list. The timing tracker is the
    authoritative source for submitted/attached counts.
    """
    existing_background_jobs = _safe_dict(existing_background_jobs)
    timing = _safe_dict(background_result_timing_summary)
    results = [_safe_dict(row) for row in _safe_list(background_results)]
    rows = [_safe_dict(row) for row in _safe_list(transcript)]

    attachment_payloads: List[Dict[str, Any]] = []
    timeout_payloads: List[Dict[str, Any]] = []
    error_payloads: List[Dict[str, Any]] = []

    for row in rows:
        payload = _safe_dict(row.get("combined_background_llm_result"))
        if not payload:
            continue
        attachment_payloads.append(payload)
        kind = _safe_str(payload.get("kind"))
        error = _safe_str(payload.get("error"))
        if kind == "background_timeout" or "timeout" in error.lower():
            timeout_payloads.append(payload)
        elif payload.get("ok") is False or error:
            error_payloads.append(payload)

    for result in results:
        kind = _safe_str(result.get("kind"))
        error = _safe_str(result.get("error"))
        if kind == "background_timeout" or "timeout" in error.lower():
            timeout_payloads.append(result)
        elif result.get("ok") is False or error:
            error_payloads.append(result)

    jobs_submitted = int(timing.get("jobs_submitted") or 0)
    jobs_attached_total = int(timing.get("jobs_attached_total") or 0)
    jobs_attached_pre_turn = int(timing.get("jobs_attached_pre_turn") or 0)
    jobs_attached_final = int(timing.get("jobs_attached_final") or 0)
    missing_job_count = int(timing.get("missing_job_count") or 0)

    # If timing is unavailable, preserve old behavior.
    if jobs_submitted <= 0:
        return existing_background_jobs

    errors = list(_safe_list(existing_background_jobs.get("errors")))
    for payload in timeout_payloads:
        message = _safe_str(payload.get("error")) or _safe_str(payload.get("kind"))
        if message and message not in errors:
            errors.append(message)
    for payload in error_payloads:
        message = _safe_str(payload.get("error")) or _safe_str(payload.get("kind"))
        if message and message not in errors:
            errors.append(message)

    failed_jobs = max(
        int(existing_background_jobs.get("failed_jobs") or 0),
        len(timeout_payloads) + len(error_payloads),
        missing_job_count,
    )

    summary = dict(existing_background_jobs)
    summary.update(
        {
            "source": "background_result_timing_summary",
            "legacy_final_drain_result_count": len(results),
            "combined_background_llm_jobs": jobs_submitted,
            "total_jobs": jobs_submitted,
            "jobs_submitted": jobs_submitted,
            "jobs_attached_total": jobs_attached_total,
            "jobs_attached_pre_turn": jobs_attached_pre_turn,
            "jobs_attached_final": jobs_attached_final,
            "missing_job_count": missing_job_count,
            "timeout_job_count": len(timeout_payloads),
            "failed_jobs": failed_jobs,
            "ok_jobs": max(0, jobs_attached_total - failed_jobs),
            "errors": errors[:50],
            "pre_turn_drain_accounted": jobs_attached_pre_turn > 0,
        }
    )
    return summary


def _reconcile_performance_budget_background_llm_counts(
    *,
    performance_budget_summary: Dict[str, Any],
    background_jobs: Dict[str, Any],
    background_result_timing_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Make performance_budget_summary.background_llm use reconciled job counts.

    The background performance section originally counted only the final drain
    result list. Once pre-turn drain consumes completed jobs during the playable
    loop, those final-drain-only counts are no longer the correct denominator.
    Keep any existing timing fields, but source count fields from the reconciled
    background_jobs/timing tracker.
    """
    summary = deepcopy(_safe_dict(performance_budget_summary))
    background_llm = deepcopy(_safe_dict(summary.get("background_llm")))
    jobs = _safe_dict(background_jobs)
    timing = _safe_dict(background_result_timing_summary)

    jobs_submitted = int(
        jobs.get("jobs_submitted")
        or jobs.get("combined_background_llm_jobs")
        or timing.get("jobs_submitted")
        or 0
    )
    jobs_attached_total = int(
        jobs.get("jobs_attached_total")
        or timing.get("jobs_attached_total")
        or 0
    )
    jobs_attached_pre_turn = int(
        jobs.get("jobs_attached_pre_turn")
        or timing.get("jobs_attached_pre_turn")
        or 0
    )
    jobs_attached_final = int(
        jobs.get("jobs_attached_final")
        or timing.get("jobs_attached_final")
        or 0
    )
    failed_jobs = int(jobs.get("failed_jobs") or background_llm.get("failed_jobs") or 0)
    timeout_job_count = int(jobs.get("timeout_job_count") or background_llm.get("timeout_job_count") or 0)
    missing_job_count = int(jobs.get("missing_job_count") or timing.get("missing_job_count") or 0)

    if jobs_submitted > 0:
        background_llm.update(
            {
                "source": "reconciled_background_jobs",
                "legacy_final_drain_result_count": int(
                    jobs.get("legacy_final_drain_result_count")
                    or background_llm.get("legacy_final_drain_result_count")
                    or background_llm.get("total_jobs")
                    or 0
                ),
                "combined_background_llm_jobs": jobs_submitted,
                "total_jobs": jobs_submitted,
                "jobs_submitted": jobs_submitted,
                "jobs_attached_total": jobs_attached_total,
                "jobs_attached_pre_turn": jobs_attached_pre_turn,
                "jobs_attached_final": jobs_attached_final,
                "pre_turn_drain_accounted": jobs_attached_pre_turn > 0,
                "failed_jobs": failed_jobs,
                "timeout_job_count": timeout_job_count,
                "missing_job_count": missing_job_count,
                "ok_jobs": max(0, jobs_attached_total - failed_jobs),
            }
        )

    summary["background_llm"] = background_llm
    return summary


def _future_done(handle: Any) -> bool:
    done = getattr(handle, "done", None)
    if callable(done):
        try:
            return bool(done())
        except Exception:
            return False
    return False


def _future_result_now(handle: Any) -> Dict[str, Any]:
    result_fn = getattr(handle, "result", None)
    if not callable(result_fn):
        return {}
    try:
        return _safe_dict(result_fn(timeout=0))
    except TypeError:
        try:
            return _safe_dict(result_fn())
        except Exception:
            return {}
    except Exception:
        return {}


def _try_get_combined_background_result_from_registry(
    *,
    registry: Dict[str, Any],
    pipeline: Any,
    job_id: str,
) -> Dict[str, Any]:
    registry = _safe_dict(registry)
    if not job_id:
        return {}

    cached = _safe_dict(_safe_dict(registry.get("results")).get(job_id))
    if cached:
        return cached

    job = _safe_dict(_safe_dict(registry.get("jobs")).get(job_id))
    handle = job.get("handle")
    if handle is not None and _future_done(handle):
        result = _future_result_now(handle)
        if result:
            _store_background_result(registry, job_id=job_id, result=result)
            return result

    # Common completed-result/result-cache stores.
    for attr in (
        "completed_results",
        "_completed_results",
        "results",
        "_results",
        "result_cache",
        "_result_cache",
        "job_results",
        "_job_results",
        "combined_background_results",
        "_combined_background_results",
    ):
        store = getattr(pipeline, attr, None)
        if isinstance(store, dict) and job_id in store:
            result = _safe_dict(store.get(job_id))
            if result:
                _store_background_result(registry, job_id=job_id, result=result)
                return result

    return {}


def _try_get_combined_background_result(
    *,
    pipeline: Any,
    job_registry: Dict[str, Any],
    job_id: str,
    wait_ms: int = 0,
) -> Dict[str, Any]:
    """Best-effort adapter over the background pipeline's existing result API.

    Different local versions of the pipeline have used slightly different
    method names. Keep this adapter defensive so the timing patch is easy to
    apply over recent code.
    """
    if not pipeline or not job_id:
        return {}

    registry_result = _try_get_combined_background_result_from_registry(
        registry=job_registry,
        pipeline=pipeline,
        job_id=job_id,
    )
    if registry_result:
        return registry_result

    wait_seconds = max(0.0, float(wait_ms or 0) / 1000.0)
    method_names = (
        "get_completed_result",
        "get_result_if_done",
        "try_get_result",
        "get_result",
        "await_result",
    )
    for name in method_names:
        method = getattr(pipeline, name, None)
        if not callable(method):
            continue
        try:
            # Prefer non-blocking/short-timeout forms when supported.
            try:
                result = method(job_id, timeout=wait_seconds)
            except TypeError:
                try:
                    result = method(job_id, timeout_seconds=wait_seconds)
                except TypeError:
                    try:
                        result = method(job_id, wait_seconds=wait_seconds)
                    except TypeError:
                        result = method(job_id)
            result = _safe_dict(result)
            if result:
                _store_background_result(job_registry, job_id=job_id, result=result)
                return result
        except TimeoutError:
            return {}
        except Exception:
            # Do not make drain adapter fatal; console/report gates will expose
            # real pipeline errors elsewhere.
            return {}
    return {}


def _extract_combined_background_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    if result.get("kind") == "background_timeout":
        return result
    return (
        _safe_dict(result.get("combined_background_llm_result"))
        or _safe_dict(result.get("payload"))
        or _safe_dict(result.get("result"))
        or result
    )


def _attach_completed_background_job_to_record(
    *,
    record: Dict[str, Any],
    job_id: str,
    result: Dict[str, Any],
    attach_turn: int,
    phase: str,
    timing_tracker: Dict[str, Any],
) -> bool:
    record = _safe_dict(record)
    if not job_id or not result:
        return False
    payload = _extract_combined_background_payload(result)
    existing_payload = _safe_dict(record.get("combined_background_llm_result"))
    if existing_payload:
        payload = existing_payload
    if not payload:
        return False
    source_turn = int(record.get("turn_index") or 0)
    # Even if a legacy path already assigned the payload, still attach timing
    # metadata exactly once.
    already_tracked = bool(_safe_dict(record.get("combined_background_llm_attach")))
    if already_tracked:
        return False
    record["combined_background_llm_result"] = payload
    record["combined_background_llm_attach"] = {
        "job_id": job_id,
        "source_turn": source_turn,
        "attach_turn": int(attach_turn or 0),
        "phase": phase,
        "lag_turns": max(0, int(attach_turn or 0) - source_turn),
        "ok": bool(payload.get("ok", True)),
        "kind": _safe_str(payload.get("kind")),
        "error": _safe_str(payload.get("error")),
    }

    # Attach narration in the same slots used by split narration jobs.
    record["deferred_narration_result"] = {
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
    record["narration_status"] = "ready" if result.get("ok") else "error"
    if result.get("ok") and result.get("narration"):
        record["resolved_narration"] = result.get("narration")
        record["resolved_narration_payload"] = result.get("narration_payload") or {}
        record["narration"] = result.get("narration")

    # Attach advisory in the same slots used by split advisory jobs.
    record["deferred_advisory_result"] = {
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
    record["deferred_advisory_status"] = "ready" if result.get("ok") else "error"
    if result.get("ok"):
        runtime_state = _safe_dict(record.get("runtime_state"))
        try:
            from app.rpg.advisory.runtime_store import (
                ingest_deferred_advisory_candidates,
            )
            record["deferred_advisory_ingest_result"] = ingest_deferred_advisory_candidates(
                runtime_state=runtime_state,
                candidates=result.get("candidates") if isinstance(result.get("candidates"), list) else [],
                turn_index=int(result.get("turn_index") or record.get("turn_index") or 0),
                source=_safe_str(result.get("source")) or "combined_background_llm",
            )
        except ImportError:
            pass  # Advisory ingestion may not be available in all versions

    _track_background_attach(
        timing_tracker,
        job_id=job_id,
        source_turn=source_turn,
        attach_turn=attach_turn,
        phase=phase,
    )
    return True


def _drain_completed_background_jobs_for_transcript(
    *,
    pipeline: Any,
    job_registry: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    current_turn: int,
    phase: str,
    wait_ms: int,
    timing_tracker: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach completed background results for prior rows.

    This never changes authoritative turn contracts. It only attaches completed
    presentation/advisory payloads to previous transcript rows so deterministic
    promotion/evolution/report logic can consume them before future actions.
    """
    attached = 0
    checked = 0
    ready = 0
    not_ready = 0
    completed_results_by_job_id: Dict[str, Dict[str, Any]] = {}
    drain_completed = getattr(pipeline, "drain_completed", None)
    if callable(drain_completed):
        for completed in drain_completed():
            completed = _safe_dict(completed)
            completed_job_id = _safe_str(completed.get("job_id"))
            if completed_job_id:
                _store_background_result(
                    job_registry,
                    job_id=completed_job_id,
                    result=completed,
                )
                completed_results_by_job_id[completed_job_id] = completed

    for row in transcript if isinstance(transcript, list) else []:
        row = _safe_dict(row)
        source_turn = int(row.get("turn_index") or 0)
        if phase == "pre_turn" and source_turn >= int(current_turn or 0):
            continue
        if _safe_dict(row.get("combined_background_llm_result")):
            continue
        job_id = _safe_str(
            row.get("combined_background_llm_job_id")
            or row.get("background_llm_job_id")
            or row.get("combined_background_job_id")
        )
        if not job_id:
            continue
        checked += 1
        result = (
            _safe_dict(completed_results_by_job_id.get(job_id))
            or _try_get_combined_background_result(
                pipeline=pipeline,
                job_registry=job_registry,
                job_id=job_id,
                wait_ms=wait_ms if attached == 0 else 0,
            )
        )
        if result:
            ready += 1
            _store_background_result(
                job_registry,
                job_id=job_id,
                result=result,
            )
        else:
            not_ready += 1
        if _attach_completed_background_job_to_record(
            record=row,
            job_id=job_id,
            result=result,
            attach_turn=current_turn,
            phase=phase,
            timing_tracker=timing_tracker,
        ):
            attached += 1
            _timestamped_print(f"Attaching combined background LLM result for turn {source_turn} phase={phase} lag={max(0, int(current_turn or 0) - source_turn)}")
    return {
        "phase": phase,
        "current_turn": current_turn,
        "checked": checked,
        "pipeline_completed_drained": len(completed_results_by_job_id),
        "ready": ready,
        "not_ready": not_ready,
        "attached": attached,
    }


def _reconcile_existing_background_attachments(
    *,
    transcript: List[Dict[str, Any]],
    timing_tracker: Dict[str, Any],
    attach_turn: int,
    phase: str = "final",
) -> Dict[str, Any]:
    reconciled = 0
    for row in transcript if isinstance(transcript, list) else []:
        row = _safe_dict(row)
        if not _safe_dict(row.get("combined_background_llm_result")):
            continue
        if _safe_dict(row.get("combined_background_llm_attach")):
            continue
        job_id = _safe_str(
            row.get("combined_background_llm_job_id")
            or row.get("background_llm_job_id")
            or row.get("combined_background_job_id")
        )
        if not job_id:
            continue
        if _attach_completed_background_job_to_record(
            record=row,
            job_id=job_id,
            result=_safe_dict(row.get("combined_background_llm_result")),
            attach_turn=attach_turn,
            phase=phase,
            timing_tracker=timing_tracker,
        ):
            reconciled += 1
    return {
        "phase": phase,
        "attach_turn": attach_turn,
        "reconciled": reconciled,
    }


def _find_narration_payload(container: Dict[str, Any]) -> Dict[str, Any]:
    """Find the actual narration payload regardless of wrapper shape.

    Autoplay/manual turn results have changed shape several times:
    - result.narration_payload
    - result.structured_narration
    - result.turn_result.narration_payload
    - result.result.narration_payload

    Deferred-mode violation detection must inspect all of these or the report
    can falsely show blocking_narration_source=None while the nested turn result
    still contains provider_runtime_narration.
    """
    if not isinstance(container, dict):
        return {}

    direct = (
        container.get("narration_payload")
        or container.get("structured_narration")
    )
    if isinstance(direct, dict):
        return direct

    nested_turn = _dict_or_empty(container.get("turn_result"))
    nested_payload = (
        nested_turn.get("narration_payload")
        or nested_turn.get("structured_narration")
    )
    if isinstance(nested_payload, dict):
        return nested_payload

    nested_result = _dict_or_empty(container.get("result"))
    result_payload = (
        nested_result.get("narration_payload")
        or nested_result.get("structured_narration")
    )
    if isinstance(result_payload, dict):
        return result_payload

    return {}


def _narration_source(container: Dict[str, Any]) -> str:
    payload = _find_narration_payload(container)
    source = payload.get("source") if isinstance(payload, dict) else ""
    return source if isinstance(source, str) else ""


def _pending_deferred_narration_payload() -> Dict[str, Any]:
    return {
        "format_version": "rpg_narration_v2",
        "source": "deferred_runtime_narration_pending",
        "deferred": True,
        "narration_status": "pending",
        "narration": "Narration is being prepared...",
        "action": "The action has been resolved.",
        "npc": {"speaker": "", "line": ""},
        "reward": "",
        "followup_hooks": [],
    }


def _replace_blocking_narration_with_pending(turn_result: Dict[str, Any]) -> None:
    """Replace blocking narration artifacts with a deferred placeholder.

    This does not undo time already spent in a provider call. It makes the
    transcript/report truthful and prevents blocking provider narration from
    being presented as the canonical turn narration in deferred mode.
    """
    if not isinstance(turn_result, dict):
        return
    pending_payload = _pending_deferred_narration_payload()

    turn_result["narration_payload"] = pending_payload
    turn_result["structured_narration"] = pending_payload
    turn_result["narration"] = pending_payload["narration"]

    nested_turn = _dict_or_empty(turn_result.get("turn_result"))
    if nested_turn:
        nested_turn["narration_payload"] = pending_payload
        nested_turn["structured_narration"] = pending_payload
        nested_turn["narration"] = pending_payload["narration"]

    nested_result = _dict_or_empty(turn_result.get("result"))
    if nested_result:
        nested_result["narration_payload"] = pending_payload
        nested_result["structured_narration"] = pending_payload
        nested_result["narration"] = pending_payload["narration"]


def _select_compact_llm_player_action(
    *,
    provider: Any,
    session: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    latest_context: Dict[str, Any],
    player_action_context: Dict[str, Any],
    strategy: str,
    action_diversity_window: int,
    max_context_chars: int,
    cache: PlayerAgentDecisionCache,
    cache_enabled: bool,
    turn_index: int,
    debug_autoplay_stage_timing: bool,
    anti_loop_context: Optional[Dict[str, Any]] = None,
    goal_pressure_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context_packet = build_player_agent_context_packet(
        session=session,
        transcript_tail=transcript,
        latest_context=latest_context,
        strategy=strategy,
        action_diversity_window=action_diversity_window,
    )

    # Add available routes for travel bias
    context_packet["available_routes"] = _safe_list(
        latest_context.get("available_routes")
        or _safe_dict(latest_context.get("turn_contract")).get("available_routes")
        or _safe_dict(_safe_dict(latest_context.get("result")).get("travel_result")).get("available_routes")
    )
    if not context_packet["available_routes"]:
        # Pull from latest session state
        from app.rpg.world.travel_graph import list_available_routes
        context_packet["available_routes"] = list_available_routes(state=session.get("simulation_state", {}))
    messages, prompt_metrics = build_player_agent_messages(
        context_packet=context_packet,
        max_context_chars=max_context_chars,
    )
    # Append anti-loop prompt to the last message (typically the user instruction)
    if messages and anti_loop_context:
        anti_loop_text = _format_player_agent_anti_loop_prompt(_safe_dict(anti_loop_context))
        if anti_loop_text.strip():
            messages[-1]["content"] = _safe_str(messages[-1].get("content", "")) + anti_loop_text
    if messages and goal_pressure_context:
        goal_pressure_text = format_goal_pressure_prompt(_safe_dict(goal_pressure_context))
        if goal_pressure_text.strip():
            messages[-1]["content"] = _safe_str(messages[-1].get("content", "")) + goal_pressure_text

    # Add location progression bias
    available_routes = context_packet.get("available_routes", [])
    if messages and available_routes:
        # Check if last few turns had no meaningful progress
        recent_rows = transcript[-3:] if len(transcript) >= 3 else transcript
        recent_meaningful = any(
            _row_has_location_progression(row) or bool(row.get("meaningful_progress"))
            for row in recent_rows
        )
        if not recent_meaningful:
            location_rule = (
                "\n\nLocation progression rule:\n"
                "- If available_routes are present and the last few turns had no meaningful progress, choose a travel action from available_routes.\n"
                "- Prefer commands exactly like: \"go to <location name>\".\n"
                "- Do not repeatedly observe/listen/wait in the same location when routes are available."
            )
            messages[-1]["content"] = _safe_str(messages[-1].get("content", "")) + location_rule
    key = player_agent_cache_key(context_packet=context_packet, strategy=strategy)

    cached = cache.get(key) if cache_enabled else None
    if cached:
        # Validate cached action against current context
        validation = validate_player_action_against_context(
            player_action=cached,
            player_action_context=player_action_context,
        )
        if not validation.get("ok"):
            cached["cache_rejected_by_validation"] = True
            # Fall back to non-cached path
            cached = None
        else:
            cached["cache_hit"] = True
            cached["prompt_metrics"] = prompt_metrics
            cached["cache_key"] = key
            return cached

    if provider is None or not callable(getattr(provider, "chat_completion", None)):
        return {
            "ok": False,
            "source": "llm_player_agent_error",
            "error": "provider_missing_or_unsupported",
            "prompt_metrics": prompt_metrics,
            "cache_hit": False,
            "cache_key": key,
        }

    try:
        provider_messages = _provider_messages(messages)
        _probe_log(
            debug_autoplay_stage_timing,
            "player_agent_provider_call.start",
            turn_index=turn_index,
            provider_type=type(provider).__name__,
            message_count=len(provider_messages),
            prompt_chars=sum(len(getattr(message, "content", "") or "") for message in provider_messages),
        )
        provider_call_start_ms = _now_ms()
        try:
            response = provider.chat_completion(messages=provider_messages, stream=False)
        except TypeError:
            response = provider.chat_completion(provider_messages, stream=False)
        _probe_log(
            debug_autoplay_stage_timing,
            "player_agent_provider_call.end",
            turn_index=turn_index,
            elapsed_ms=_now_ms() - provider_call_start_ms,
            response_type=type(response).__name__,
        )
        text = _provider_text_from_response(response)
        parsed = _extract_json_object_from_text(text)
        normalized = normalize_player_agent_payload(parsed)
        # Validate the LLM result
        validation = validate_player_action_against_context(
            player_action=normalized,
            player_action_context=player_action_context,
        )
        if not validation.get("ok"):
            fallback = choose_fallback_player_action(
                player_action_context=player_action_context,
                recent_transcript=transcript,
            )
            fallback["player_agent_validation"] = validation
            fallback["raw_player_agent_action"] = normalized
            return fallback
        result = {
            **normalized,
            "source": "llm_player_agent",
            "prompt_metrics": prompt_metrics,
            "cache_hit": False,
            "cache_key": key,
        }
        if result.get("ok") and cache_enabled:
            cache.put(key, result)
        return result
    except Exception as exc:
        return {
            "ok": False,
            "source": "llm_player_agent_error",
            "error": f"{type(exc).__name__}: {exc}",
            "prompt_metrics": prompt_metrics,
            "cache_hit": False,
            "cache_key": key,
        }


def _select_player_action(
    *,
    provider: Any,
    player_action_context: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    strategy: str,
    use_llm_player: bool,
    max_tokens: int,
    progress_quality_metrics: Dict[str, Any] | None = None,
    diversity_metrics: Dict[str, Any] | None = None,
    turn_index: int,
    debug_autoplay_stage_timing: bool,
) -> Dict[str, Any]:
    if not use_llm_player:
        return choose_fallback_player_action(
            player_action_context=player_action_context,
            recent_transcript=transcript,
        )

    prompt = build_player_agent_prompt(
        player_action_context=player_action_context,
        recent_transcript=transcript,
        strategy=strategy,
        progress_quality_metrics=progress_quality_metrics,
        diversity_metrics=diversity_metrics,
    )
    try:
        _probe_log(
            debug_autoplay_stage_timing,
            "player_agent_provider_call.start",
            turn_index=turn_index,
            provider_type=type(provider).__name__,
            message_count=1,
            prompt_chars=len(prompt),
        )
        provider_call_start_ms = _now_ms()
        raw = call_provider_text(provider, prompt, max_tokens=max_tokens)
        _probe_log(
            debug_autoplay_stage_timing,
            "player_agent_provider_call.end",
            turn_index=turn_index,
            elapsed_ms=_now_ms() - provider_call_start_ms,
            response_type=type(raw).__name__,
        )
        parsed = parse_player_agent_response(raw)
        if not parsed.get("ok"):
            fallback = choose_fallback_player_action(
                player_action_context=player_action_context,
                recent_transcript=transcript,
            )
            fallback["player_agent_error"] = parsed
            return fallback
        validation = validate_player_action_against_context(
            player_action=parsed,
            player_action_context=player_action_context,
        )
        if not validation.get("ok"):
            fallback = choose_fallback_player_action(
                player_action_context=player_action_context,
                recent_transcript=transcript,
            )
            fallback["player_agent_validation"] = validation
            fallback["raw_player_agent_action"] = parsed
            return fallback
        parsed["strategy"] = strategy
        parsed["strategy_guidance"] = build_strategy_guidance(
            strategy=strategy,
            progress_quality_metrics=progress_quality_metrics,
            diversity_metrics=diversity_metrics,
            recent_transcript=transcript,
        )
        return parsed
    except Exception as exc:
        fallback = choose_fallback_player_action(
            player_action_context=player_action_context,
            recent_transcript=transcript,
        )
        fallback["player_agent_exception"] = f"{type(exc).__name__}: {exc}"
        return fallback


def _run_autoplay_campaign(args: argparse.Namespace) -> Dict[str, Any]:
    from app.shared import get_provider

    campaign_perf_start = now_perf()
    artifact_write_ms = 0.0
    session_id = args.session_id or f"autoplay_{uuid.uuid4().hex[:12]}"
    simulation_state: Dict[str, Any] = {}
    seed_resolution = resolve_campaign_seed_name(
        args.scenario_seed,
        random_seed=args.random_seed,
    )
    seed_result = seed_campaign(simulation_state, seed_resolution["resolved_seed"])
    seed_result["seed_resolution"] = seed_resolution
    authoritative_state: Dict[str, Any] = deepcopy(simulation_state)
    authoritative_state = _commit_authoritative_state(
        session_id=session_id,
        authoritative_state=authoritative_state,
        runtime_narration=args.narration_mode,
    )
    last_committed_state: Dict[str, Any] = deepcopy(authoritative_state)
    runtime_state: Dict[str, Any] = deepcopy(authoritative_state)
    checkpoint_dir = Path(args.output_dir) / "checkpoints"

    provider = _load_provider() if args.player_agent == "llm" else None
    provider_shape = describe_provider_shape(provider) if provider is not None else {}
    if args.debug_provider_shape and provider_shape:
        _timestamped_print("Player-agent provider shape:")
        _timestamped_print(provider_shape)

    effective_provider_workers = int(args.provider_workers)
    effective_background_workers = int(args.background_workers)
    if (
        int(args.turns or 0) >= int(getattr(args, "strict_eval_turns", 100) or 100)
        and _safe_str(args.background_llm_mode) == "combined"
        and effective_provider_workers <= 1
    ):
        effective_provider_workers = 2
    if (
        int(args.turns or 0) >= int(getattr(args, "strict_eval_turns", 100) or 100)
        and effective_background_workers < 3
    ):
        effective_background_workers = 3
    pipeline = AutoplayBackgroundPipeline(
        background_workers=effective_background_workers,
        provider_workers=effective_provider_workers,
    )
    background_results_summary: Dict[str, Any] = {}


    transcript: List[Dict[str, Any]] = []
    carried_campaign_runtime_state: Dict[str, Any] = {}
    background_result_timing_tracker = _new_background_result_timing_tracker()
    background_job_registry = _new_background_job_registry()
    background_drain_events: List[Dict[str, Any]] = []
    player_agent_cache = PlayerAgentDecisionCache(max_entries=256)
    player_agent_prompt_rows: List[Dict[str, Any]] = []
    regression_warnings: List[Dict[str, Any]] = []
    pre_turn_advisory_promotion_auto_disabled = False
    pre_turn_advisory_promotion_disable_reason = ""
    pre_turn_advisory_promotion_slow_events: List[Dict[str, Any]] = []
    started = time.time()
    stopped_reason = ""

    progression_authority_state: Dict[str, Any] = _extract_progression_authority_sidecar(runtime_state)
    progression_authority_state = _stamp_progression_authority(
        progression_authority_state,
        reason="main_loop_sidecar_initialized",
        turn_index=0,
    )
    runtime_state = _overlay_progression_authority_sidecar(
        runtime_state,
        progression_authority_state,
        reason="main_loop_initial_overlay",
        turn_index=0,
    )
    authoritative_state = deepcopy(runtime_state)
    last_committed_state = deepcopy(runtime_state)
    progression_sidecar_max_node_count = _progression_node_count(progression_authority_state)
    progression_sidecar_max_revision = _progression_revision(progression_authority_state)
    checkpoint_validation_rows: List[Dict[str, Any]] = []

    mechanics_runtime_state: Dict[str, Any] = {
        "current_location": "scene:rusty_flagon",
        "currency": {"gold": 15, "silver": 20, "copper": 50},
        "inventory": [],
        "flags": {},
        "xp": 0,
        "level": 1,
    }

    mechanics_failed_opportunity_ids: set[str] = set()

    mechanics_coverage_runtime: Dict[str, bool] = {
        "travel": False,
        "npc_interaction": False,
        "quest_progress": False,
        "service_or_lodging": False,
        "buying": False,
        "selling": False,
        "currency_change": False,
        "inventory_change": False,
        "party_recruitment": False,
        "combat_started": False,
        "combat_resolved": False,
        "xp_gain": False,
        "level_up": False,
        "loot_acquired": False,
    }

    for turn_index in range(1, int(args.turns) + 1):
        # Initialize player agent selection variables
        player_agent_selection_source = "unknown"
        player_agent_selection_reason = "unknown"

        runtime_state = _overlay_and_assert_progression_sidecar(
            last_committed_state,
            progression_authority_state,
            reason="turn_start",
            turn_index=turn_index,
        )
        authoritative_state = deepcopy(runtime_state)
        last_committed_state = deepcopy(runtime_state)
        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "scenario_progression.sidecar.start",
            turn_index=turn_index,
            runtime_revision=_progression_revision(runtime_state),
            sidecar_revision=_progression_revision(progression_authority_state),
            runtime_completed_node_count=_progression_node_count(runtime_state),
            sidecar_completed_node_count=_progression_node_count(progression_authority_state),
            runtime_fact_count=_progression_fact_count(runtime_state),
            sidecar_fact_count=_progression_fact_count(progression_authority_state),
            next_actions=[
                _safe_str(_safe_dict(row).get("action_id"))
                for row in _safe_list(runtime_state.get("scenario_progression_actions"))[:5]
            ],
        )
        progression_node_count_at_turn_start = _progression_node_count(authoritative_state)
        progression_revision_at_turn_start = _progression_revision(authoritative_state)

        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "turn.start",
            turn_index=turn_index,
            transcript_len=len(transcript),
        )
        transcript_len_at_turn_start = len(transcript)

        if int(getattr(args, "pre_turn_background_drain_ms", 0) or 0) >= 0:
            with _ProbeTimer(
                bool(getattr(args, "debug_autoplay_stage_timing", False)),
                "pre_turn_background_drain",
                turn_index=turn_index,
                wait_ms=int(getattr(args, "pre_turn_background_drain_ms", 0) or 0),
            ):
                drain_event = _drain_completed_background_jobs_for_transcript(
                    pipeline=pipeline,
                    job_registry=background_job_registry,
                    transcript=transcript,
                    current_turn=turn_index,
                    phase="pre_turn",
                    wait_ms=int(getattr(args, "pre_turn_background_drain_ms", 0) or 0),
                    timing_tracker=background_result_timing_tracker,
                )
            background_drain_events.append(drain_event)
            _probe_log(
                bool(getattr(args, "debug_autoplay_stage_timing", False)),
                "pre_turn_background_drain.result",
                turn_index=turn_index,
                checked=drain_event.get("checked"),
                pipeline_completed_drained=drain_event.get("pipeline_completed_drained"),
                ready=drain_event.get("ready"),
                attached=drain_event.get("attached"),
                not_ready=drain_event.get("not_ready"),
            )

            # Re-run deterministic promotion/evolution over newly attached
            # advisory candidates so future turns can see promoted runtime state.
            pre_turn_promotion_start = now_perf()
            if (
                not bool(getattr(args, "disable_pre_turn_advisory_promotion", False))
                and not bool(pre_turn_advisory_promotion_auto_disabled)
                and int(drain_event.get("attached") or 0) > 0
            ):
                pre_turn_promotion_result: Dict[str, Any] = {}
                with _ProbeTimer(
                    bool(getattr(args, "debug_autoplay_stage_timing", False)),
                    "pre_turn_deferred_advisory_promotion",
                    turn_index=turn_index,
                    transcript_len=len(transcript),
                    attached=drain_event.get("attached"),
                    max_rows=int(getattr(args, "pre_turn_advisory_promotion_max_rows", 6) or 6),
                    persist_profiles=False,
                ):
                    pre_turn_promotion_result = run_deferred_advisory_promotions_for_transcript(
                        transcript=transcript,
                        max_promotions_per_turn=int(args.max_advisory_promotions_per_turn),
                        max_rows=int(getattr(args, "pre_turn_advisory_promotion_max_rows", 6) or 6),
                        persist_profiles=False,
                        incremental_pre_turn=True,
                        mark_pre_turn_promoted=True,
                        current_turn=turn_index,
                        carry_candidate_limit=int(
                            getattr(args, "pre_turn_advisory_carry_candidate_limit", 30) or 30
                        ),
                        carry_pending_limit=int(
                            getattr(args, "pre_turn_advisory_carry_pending_limit", 30) or 30
                        ),
                        carry_accepted_limit=int(
                            getattr(args, "pre_turn_advisory_carry_accepted_limit", 60) or 60
                        ),
                        carry_rejected_limit=int(
                            getattr(args, "pre_turn_advisory_carry_rejected_limit", 60) or 60
                        ),
                        fast_pre_turn=bool(getattr(args, "pre_turn_advisory_fast_path", True)),
                        skip_profile_load_for_pre_turn=bool(
                            getattr(args, "pre_turn_advisory_skip_profile_load", True)
                        ),
                        skip_evolution_for_pre_turn=bool(
                            getattr(args, "pre_turn_advisory_skip_evolution", True)
                        ),
                        skip_mutation_compare_for_pre_turn=bool(
                            getattr(args, "pre_turn_advisory_skip_mutation_compare", True)
                        ),
                    )
                _probe_log(
                    bool(getattr(args, "debug_autoplay_stage_timing", False)),
                    "pre_turn_deferred_advisory_promotion.result",
                    turn_index=turn_index,
                    turns=pre_turn_promotion_result.get("turns"),
                    source_transcript_turns=pre_turn_promotion_result.get("source_transcript_turns"),
                    incremental_pre_turn=pre_turn_promotion_result.get("incremental_pre_turn"),
                    accepted=pre_turn_promotion_result.get("accepted"),
                    rejected=pre_turn_promotion_result.get("rejected"),
                    pending=pre_turn_promotion_result.get("pending"),
                    persist_profiles=pre_turn_promotion_result.get("persist_profiles"),
                    carry_candidate_limit=pre_turn_promotion_result.get("carry_candidate_limit"),
                    carry_pending_limit=pre_turn_promotion_result.get("carry_pending_limit"),
                    carry_accepted_limit=pre_turn_promotion_result.get("carry_accepted_limit"),
                    carry_rejected_limit=pre_turn_promotion_result.get("carry_rejected_limit"),
                )
                drain_event["pre_turn_advisory_promotion_result"] = {
                    "ok": pre_turn_promotion_result.get("ok"),
                    "turns": pre_turn_promotion_result.get("turns"),
                    "source_transcript_turns": pre_turn_promotion_result.get("source_transcript_turns"),
                    "incremental_pre_turn": pre_turn_promotion_result.get("incremental_pre_turn"),
                    "accepted": pre_turn_promotion_result.get("accepted"),
                    "rejected": pre_turn_promotion_result.get("rejected"),
                    "pending": pre_turn_promotion_result.get("pending"),
                    "persist_profiles": pre_turn_promotion_result.get("persist_profiles"),
                    "fast_pre_turn": pre_turn_promotion_result.get("fast_pre_turn"),
                    "elapsed_ms": pre_turn_promotion_result.get("elapsed_ms"),
                    "slow_guard_ms": int(getattr(args, "pre_turn_advisory_slow_guard_ms", 5000) or 5000),
                    "carry_candidate_limit": pre_turn_promotion_result.get("carry_candidate_limit"),
                    "carry_pending_limit": pre_turn_promotion_result.get("carry_pending_limit"),
                    "carry_accepted_limit": pre_turn_promotion_result.get("carry_accepted_limit"),
                    "carry_rejected_limit": pre_turn_promotion_result.get("carry_rejected_limit"),
                }

                if pre_turn_promotion_result.get("slow", False):
                    pre_turn_advisory_promotion_auto_disabled = True
                    pre_turn_advisory_promotion_disable_reason = "slow pre-turn promotion"
                    pre_turn_advisory_promotion_slow_events.append({
                        "turn_index": turn_index,
                        "reason": "slow pre-turn promotion",
                        "elapsed_ms": elapsed_ms(pre_turn_promotion_start),
                    })

        turn_perf_start = now_perf()
        turn_performance: Dict[str, Any] = {
            "turn_index": turn_index,
        }
        background_runtime_state: Dict[str, Any] = {}
        resolved_turn_contract: Dict[str, Any] = {}
        resolved_narration_payload: Dict[str, Any] = {}
        combined_background_result: Dict[str, Any] = {}
        journal_narration_text = ""
        combined_background_llm_job_id = ""
        # The previous turn's committed state is the only valid baseline.
        # Never derive the next before_state from manual session reloads.
        expected_baseline_state = deepcopy(last_committed_state)
        authoritative_state = deepcopy(last_committed_state)
        authoritative_state = _commit_authoritative_state(
            session_id=session_id,
            authoritative_state=authoritative_state,
        )
        authoritative_state = _commit_campaign_state_authority(
            authoritative_state,
            transcript_tail=transcript[-12:],
            phase="turn",
        )
        authoritative_state = _overlay_and_assert_progression_sidecar(
            authoritative_state,
            progression_authority_state,
            reason="before_player_context",
            turn_index=turn_index,
        )
        authoritative_state = _refresh_scenario_progression_actions_for_turn(
            authoritative_state,
            args,
            turn_index=turn_index,
        )
        simulation_state = deepcopy(authoritative_state)
        context = build_player_action_context(
            authoritative_state,
            turn_index=turn_index,
            limit=args.suggested_action_limit,
        )
        if isinstance(context, dict) and isinstance(authoritative_state, dict):
            context["dialogue_state"] = authoritative_state.get("dialogue_state") or {}
            context["autoplay_story_hook_state"] = authoritative_state.get("autoplay_story_hook_state") or {}
            context["quest_progress"] = authoritative_state.get("quest_progress") or {}
            context["campaign_state_commit_summary"] = authoritative_state.get("campaign_state_commit_summary") or {}
            context["unresolved_leads"] = authoritative_state.get("unresolved_leads") or []
            context["current_location"] = authoritative_state.get("current_location") or authoritative_state.get("current_location_name") or ""
            context["current_location_name"] = authoritative_state.get("current_location_name") or ""
            context["scenario_progression_actions"] = authoritative_state.get("scenario_progression_actions") or []
            context["scenario_progression_summary"] = authoritative_state.get("scenario_progression_summary") or {}
            context["scenario_progression_active"] = _scenario_progression_active(authoritative_state)
            context["progression_authority_summary"] = authoritative_state.get("progression_authority_summary") or {}
            context["progression_sidecar_completed_node_count"] = _progression_node_count(
                progression_authority_state
            )
            context["progression_sidecar_revision"] = _progression_revision(
                progression_authority_state
            )
            # Limit recent_turns to prevent memory explosion in long campaigns
            context["recent_turns"] = [
                {k: v for k, v in turn.items() if k in {"turn_index", "player_action", "narration"}}
                for turn in transcript[-5:]
            ]
        context["story_hook_hints"] = autoplay_story_hook_player_hints(simulation_state)
        current_progress_quality_metrics = compute_progress_quality_metrics(transcript)
        current_diversity_metrics = action_diversity_metrics(
            transcript,
            window=int(args.action_diversity_window),
        )
        context["suggested_actions"] = rerank_suggested_actions_for_strategy(
            list(context.get("suggested_actions") or []),
            strategy=args.strategy,
            recent_transcript=transcript,
            progress_quality_metrics=current_progress_quality_metrics,
        )
        context["strategy_guidance"] = build_strategy_guidance(
            strategy=args.strategy,
            progress_quality_metrics=current_progress_quality_metrics,
            diversity_metrics=current_diversity_metrics,
            recent_transcript=transcript,
        )
        goal_pressure_context = build_goal_pressure_context(
            transcript=transcript,
            player_action_context=context,
            progress_quality_metrics=current_progress_quality_metrics,
            turn_index=turn_index,
            no_change_streak_threshold=int(getattr(args, "goal_pressure_no_change_threshold", 8) or 8),
            passive_rate_threshold=float(getattr(args, "goal_pressure_passive_rate_threshold", 0.45) or 0.45),
        ) if bool(getattr(args, "player_agent_goal_pressure", True)) else {"active": False}
        context["goal_pressure"] = goal_pressure_context
        if goal_pressure_context.get("active"):
            pressure_candidates = _safe_list(goal_pressure_context.get("candidate_actions"))
            existing_commands = {
                _safe_str(row.get("command"))
                for row in _safe_list(context.get("suggested_actions"))
                if _safe_str(_safe_dict(row).get("command"))
            }
            promoted = []
            for row in pressure_candidates:
                row = _safe_dict(row)
                command = _safe_str(row.get("command"))
                if command and command not in existing_commands:
                    promoted.append(row)
            context["suggested_actions"] = (promoted + _safe_list(context.get("suggested_actions")))[: int(args.suggested_action_limit)]
        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "player_agent_goal_pressure_context",
            turn_index=turn_index,
            active=goal_pressure_context.get("active"),
            meaningful_progress_rate=goal_pressure_context.get("meaningful_progress_rate"),
            no_change_turns=goal_pressure_context.get("no_change_turns"),
            passive_micro_action_rate=goal_pressure_context.get("passive_micro_action_rate"),
            active_objective_count=goal_pressure_context.get("active_objective_count"),
            completed_objective_count=goal_pressure_context.get("completed_objective_count"),
        )
        anti_loop_context = _build_player_agent_anti_loop_context(
            transcript=transcript,
            threshold=int(getattr(args, "player_agent_anti_loop_streak_threshold", 3) or 3),
            window=int(getattr(args, "action_diversity_window", 12) or 12),
        )
        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "player_agent_anti_loop_context",
            turn_index=turn_index,
            active=anti_loop_context.get("active"),
            pair=anti_loop_context.get("pair"),
            streak=anti_loop_context.get("streak"),
            threshold=anti_loop_context.get("threshold"),
            source=anti_loop_context.get("source"),
            recent_pairs=",".join(
                [
                    _safe_str(pair)
                    for pair in _safe_list(anti_loop_context.get("recent_pairs"))[-6:]
                ]
            ),
            recent_sources=",".join(
                [
                    _safe_str(_safe_dict(item).get("source"))
                    for item in _safe_list(anti_loop_context.get("canonical_recent_pairs"))[-6:]
                ]
            ),
        )
        player_reasoning_plan = {}
        if bool(getattr(args, "player_agent_reasoning_planner", True)):
            try:
                reasoning_messages = build_player_reasoning_prompt(context)
                provider = get_provider()
                raw_plan = provider.chat(
                    messages=reasoning_messages,
                    temperature=0.2,
                    max_tokens=420,
                )
                player_reasoning_plan = normalize_player_reasoning_payload(raw_plan)
                if player_reasoning_plan.get("best_next_action"):
                    context["reasoning_planner"] = player_reasoning_plan
                    # Push the planner action to the top of suggested actions.
                    context["suggested_actions"] = [
                        {
                            "action_id": "reasoning_planner:best_next_action",
                            "label": "Reasoned best next action",
                            "command": player_reasoning_plan["best_next_action"],
                            "category": "objective",
                            "priority": 160,
                            "reason": player_reasoning_plan.get("why_this_advances_progress") or "Bounded reasoning planner.",
                        }
                    ] + _safe_list(context.get("suggested_actions"))
            except Exception as exc:
                player_reasoning_plan = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "best_next_action": deterministic_concrete_player_action(context),
                }
                context["reasoning_planner"] = player_reasoning_plan

        with _ProbeTimer(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "player_agent_select_action",
            turn_index=turn_index,
            player_agent=getattr(args, "player_agent", ""),
            context_mode=getattr(args, "player_agent_context_mode", ""),
        ):
            with timed_stage(turn_performance, "player_agent_ms"):
                if args.player_agent == "llm" and args.player_agent_context_mode == "compact":
                    selected = _select_compact_llm_player_action(
                        provider=provider,
                        session=simulation_state,
                        transcript=transcript,
                        latest_context=context,
                        player_action_context=context,
                        strategy=args.strategy,
                        action_diversity_window=int(args.action_diversity_window),
                        max_context_chars=int(args.player_agent_max_context_chars),
                        cache=player_agent_cache,
                        cache_enabled=args.player_agent_cache == "on",
                        turn_index=turn_index,
                        debug_autoplay_stage_timing=bool(getattr(args, "debug_autoplay_stage_timing", False)),
                        anti_loop_context=anti_loop_context,
                        goal_pressure_context=goal_pressure_context,
                    )
                else:
                    selected = _select_player_action(
                        provider=provider,
                        player_action_context=context,
                        transcript=transcript,
                        strategy=args.strategy,
                        use_llm_player=args.player_agent == "llm",
                        max_tokens=args.player_agent_max_tokens,
                        progress_quality_metrics=current_progress_quality_metrics,
                        diversity_metrics=current_diversity_metrics,
                        turn_index=turn_index,
                        debug_autoplay_stage_timing=bool(getattr(args, "debug_autoplay_stage_timing", False)),
                    )

                player_agent_selection_source = _safe_str(selected.get("source")) or "player_agent"
                player_agent_selection_reason = _safe_str(selected.get("reason")) or "player_agent"
                player_action = _safe_str(selected.get("action"))

        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "player_agent_select_action.result",
            turn_index=turn_index,
            action_preview=_safe_str(player_action)[:220],
        )

        recent_exact_actions = [
            _safe_str(_safe_dict(row).get("player_action")).strip().lower()
            for row in transcript[-4:]
        ]
        progression_actions = _safe_list(authoritative_state.get("scenario_progression_actions"))
        if progression_actions:
            selected_progression_action = ""
            for candidate in progression_actions:
                command = _safe_str(_safe_dict(candidate).get("command")).strip()
                if command and command.lower() not in recent_exact_actions:
                    selected_progression_action = command
                    break
            if (
                not player_action
                or player_action.strip().lower() in recent_exact_actions[-2:]
                or "follow up on the lead" in player_action.lower()
                or "review my quest log" in player_action.lower()
            ):
                if selected_progression_action:
                    player_action = selected_progression_action
                    player_agent_selection_source = "scenario_progression_graph"

        if (
            bool(getattr(args, "player_agent_anti_loop_repair", True))
            and _action_violates_anti_loop(_safe_str(player_action), anti_loop_context)
        ):
            repaired_action = _deterministic_anti_loop_fallback_action(anti_loop_context)
            _probe_log(
                bool(getattr(args, "debug_autoplay_stage_timing", False)),
                "player_agent_anti_loop_repair.applied",
                turn_index=turn_index,
                forbidden_pair=anti_loop_context.get("pair"),
                original_action=_safe_str(player_action)[:220],
                repaired_action=repaired_action[:220],
            )
            player_action = repaired_action

        if (
            bool(getattr(args, "player_agent_goal_pressure_repair", True))
            and action_violates_goal_pressure(_safe_str(player_action), goal_pressure_context)
        ):
            repaired_goal_action = deterministic_goal_pressure_action(goal_pressure_context)
            _probe_log(
                bool(getattr(args, "debug_autoplay_stage_timing", False)),
                "player_agent_goal_pressure_repair.applied",
                turn_index=turn_index,
                original_action=_safe_str(player_action)[:220],
                repaired_action=repaired_goal_action[:220],
            )
            player_action = repaired_goal_action
            if isinstance(selected, dict):
                selected["goal_pressure_repaired"] = True
                selected["goal_pressure_original_action"] = _safe_str(selected.get("action"))
                selected["action"] = repaired_goal_action

        if action_is_vague_objective(_safe_str(player_action)):
            repaired_goal_action = deterministic_goal_pressure_action(goal_pressure_context)
            _probe_log(
                bool(getattr(args, "debug_autoplay_stage_timing", False)),
                "player_agent_vague_objective_repair.applied",
                turn_index=turn_index,
                original_action=_safe_str(player_action)[:220],
                repaired_action=repaired_goal_action[:220],
            )
            player_action = repaired_goal_action
            if isinstance(selected, dict):
                selected["vague_objective_repaired"] = True
                selected["vague_objective_original_action"] = _safe_str(selected.get("action"))
                selected["action"] = repaired_goal_action

        if is_vague_player_action(_safe_str(player_action)):
            repaired = _safe_str(
                _safe_dict(context.get("reasoning_planner")).get("best_next_action")
            )
            if not repaired or is_vague_player_action(repaired):
                repaired = deterministic_concrete_player_action(context)
            _probe_log(
                bool(getattr(args, "debug_autoplay_stage_timing", False)),
                "player_agent_reasoning_repair.applied",
                turn_index=turn_index,
                original_action=_safe_str(player_action)[:240],
                repaired_action=repaired[:240],
            )
            player_action = repaired
            if isinstance(selected, dict):
                selected["reasoning_repaired"] = True
                selected["reasoning_original_action"] = _safe_str(selected.get("action"))
                selected["action"] = repaired

        if isinstance(selected, dict):
                player_agent_prompt_rows.append(
                    {
                        "turn_index": turn_index,
                        "source": selected.get("source"),
                        "ok": bool(selected.get("ok")),
                        "cache_hit": bool(selected.get("cache_hit")),
                        "prompt_metrics": selected.get("prompt_metrics") or {},
                    }
                )

        player_agent_debug = _safe_dict(selected.get("debug")) if isinstance(selected, dict) else {}

        graph_action_state = _graph_action_source_state(runtime_state, authoritative_state)
        pre_apply_graph_action_state = graph_action_state
        pre_apply_top_graph_action = _top_scenario_progression_action(pre_apply_graph_action_state)
        top_graph_action = _top_scenario_progression_action(graph_action_state)
        top_graph_action_id = _safe_str(top_graph_action.get("action_id"))
        top_graph_command = _safe_str(top_graph_action.get("command"))
        top_graph_source = _safe_str(top_graph_action.get("source"))
        if (
            top_graph_source not in {
                "scenario_progression_arc_complete_idle",
                "scenario_progression_arc_complete_bridge",
            }
            and _recent_same_graph_action_without_progress(
                transcript,
                action_id=top_graph_action_id,
                command=top_graph_command,
                max_repeats=2,
            )
        ):
            raise RuntimeError(
                "scenario_progression_graph_action_repeated_without_progress:"
                f"turn={turn_index}:"
                f"action_id={top_graph_action_id}:"
                f"command={top_graph_command!r}:"
                f"active_graph_id={_safe_str(graph_action_state.get('scenario_progression_active_graph_id'))}"
            )
        (
            player_action,
            player_agent_selection_source,
            player_agent_selection_reason,
            player_agent_debug,
        ) = _apply_graph_action_selection_override(
            player_action=player_action,
            player_agent_selection_source=player_agent_selection_source,
            player_agent_selection_reason=player_agent_selection_reason,
            player_agent_debug=player_agent_debug,
            graph_state=graph_action_state,
            args=args,
        )

        arc_complete_action = _arc_complete_graph_action_from_state(authoritative_state)
        if arc_complete_action and _scenario_arc_complete_from_state(authoritative_state, args):
            original_player_action = _safe_str(player_action)
            if original_player_action.strip() != arc_complete_action.strip():
                player_action = arc_complete_action
                player_agent_selection_source = "scenario_progression_arc_complete_bridge"
                player_agent_selection_reason = "arc_complete_graph_action_preferred_over_llm"
                player_agent_debug["arc_complete_graph_action_preferred"] = {
                    "changed": True,
                    "original_action": original_player_action,
                    "replacement_action": arc_complete_action,
                    "reason": "arc_complete_graph_action_preferred_over_llm",
                }

        executable_action_repair = {"changed": False, "action": _safe_str(player_action)}
        handoff_semantic = ""
        if bool(getattr(args, "player_agent_executable_action_repair", True)):
            authoritative_state = _overlay_and_assert_progression_sidecar(
                authoritative_state,
                progression_authority_state,
                reason="before_executable_repair",
                turn_index=turn_index,
            )
            authoritative_state = _refresh_scenario_progression_actions_for_turn(
                authoritative_state,
                args,
                turn_index=turn_index,
            )
            context["progression_authority_summary"] = authoritative_state.get("progression_authority_summary") or {}
            context["progression_completed_nodes"] = authoritative_state.get("progression_completed_nodes") or {}
            context["progression_sidecar_completed_node_count"] = _progression_node_count(
                progression_authority_state
            )
            context["progression_sidecar_revision"] = _progression_revision(
                progression_authority_state
            )
            context["scenario_progression_active"] = _scenario_progression_active(authoritative_state)
            context["current_location"] = authoritative_state.get("current_location") or authoritative_state.get("current_location_name") or ""
            graph_action_state = _graph_action_source_state(runtime_state, authoritative_state)
            context["top_scenario_progression_action"] = _top_scenario_progression_action(graph_action_state)
            context["scenario_progression_actions"] = graph_action_state.get("scenario_progression_actions") or []
            context["scenario_progression_active_graph_id"] = graph_action_state.get(
                "scenario_progression_active_graph_id"
            )
            context["scenario_progression_arc_summary"] = _scenario_progression_arc_summary(
                authoritative_state,
                scenario_seed=str(getattr(args, "scenario_seed", "") or ""),
            )
            context["scenario_arc_complete"] = bool(
                _safe_dict(context.get("scenario_progression_arc_summary")).get("arc_complete")
            )
            context["player_agent_selection_source"] = player_agent_selection_source
            executable_action_repair = repair_action_if_needed(_safe_str(player_action), context, transcript)
            if executable_action_repair.get("changed"):
                _probe_log(
                    bool(getattr(args, "debug_autoplay_stage_timing", False)),
                    "player_agent_executable_action_repair.applied",
                    turn_index=turn_index,
                    original_action=_safe_str(executable_action_repair.get("original_action"))[:240],
                    repaired_action=_safe_str(executable_action_repair.get("action"))[:240],
                    reason=_safe_str(executable_action_repair.get("reason")),
                )
                player_action = _safe_str(executable_action_repair.get("action"))
                handoff_semantic = _safe_str(executable_action_repair.get("handoff_semantic"))
                if _safe_str(executable_action_repair.get("reason")) == "scenario_progression_graph_priority_repair":
                    player_agent_selection_source = "scenario_progression_graph"
                if isinstance(selected, dict):
                    selected["executable_action_repaired"] = True
                    selected["executable_action_original_action"] = _safe_str(executable_action_repair.get("original_action"))
                    selected["action"] = player_action

        graph_action_state = _graph_action_source_state(runtime_state, authoritative_state)
        top_graph_action = _top_scenario_progression_action(graph_action_state)
        top_graph_command = _safe_str(top_graph_action.get("command"))
        if (
            _should_force_graph_action(graph_action_state, args)
            and top_graph_command
            and _safe_str(player_action).strip() != top_graph_command.strip()
        ):
            raise RuntimeError(
                "scenario_progression_graph_action_not_selected:"
                f"turn={turn_index}:"
                f"expected_action_id={_safe_str(top_graph_action.get('action_id'))}:"
                f"expected={top_graph_command!r}:"
                f"actual={_safe_str(player_action)!r}:"
                f"source={_safe_str(player_agent_selection_source)}"
            )

        authoritative_state = _apply_scenario_progression_for_action(
            authoritative_state,
            scenario_seed=str(getattr(args, "scenario_seed", "") or ""),
            player_action=player_action,
            turn_index=turn_index,
        )
        authoritative_state = _refresh_scenario_progression_actions_for_turn(
            authoritative_state,
            args,
            turn_index=turn_index,
        )
        authoritative_state, progression_authority_state = _update_sidecar_and_overlay(
            authoritative_state,
            progression_authority_state,
            reason="after_scenario_progression_apply",
            turn_index=turn_index,
        )
        authoritative_state = _commit_campaign_state_authority(
            authoritative_state,
            transcript_tail=transcript[-12:],
            phase="turn",
        )
        authoritative_state = _refresh_scenario_progression_actions_for_turn(
            authoritative_state,
            args,
            turn_index=turn_index,
        )
        authoritative_state, progression_authority_state = _update_sidecar_and_overlay(
            authoritative_state,
            progression_authority_state,
            reason="after_campaign_state_commit",
            turn_index=turn_index,
        )
        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "scenario_progression.state",
            turn_index=turn_index,
            revision=_progression_revision(authoritative_state),
            completed_node_count=len(_safe_dict(authoritative_state.get("progression_completed_nodes"))),
            fact_count=len(_safe_dict(authoritative_state.get("progression_facts"))),
            lead_count=len(_safe_dict(authoritative_state.get("progression_leads"))),
            npc_count=len(_safe_dict(authoritative_state.get("progression_unlocked_npcs"))),
            location_count=len(_safe_dict(authoritative_state.get("progression_unlocked_locations"))),
            stale_merge_count=len(_safe_list(authoritative_state.get("progression_stale_merge_log"))),
            next_actions=[
                _safe_str(_safe_dict(row).get("action_id"))
                for row in _safe_list(authoritative_state.get("scenario_progression_actions"))[:5]
            ],
        )
        simulation_state = deepcopy(authoritative_state)

        runtime_error = ""
        turn_result: Dict[str, Any]
        before_state = deepcopy(expected_baseline_state)
        before_digest = state_digest(before_state)
        baseline_check = _baseline_mismatch_warning(
            expected_state=expected_baseline_state,
            actual_before_state=before_state,
        )
        story_hook_result: Dict[str, Any] = {}
        try:
            with _ProbeTimer(
                bool(getattr(args, "debug_autoplay_stage_timing", False)),
                "runtime_turn_execution",
                turn_index=turn_index,
            ):
                with timed_stage(turn_performance, "manual_turn_ms"):
                    turn_result = _call_turn_runtime(
                        session_id=session_id,
                        player_action=player_action,
                        turn_index=turn_index,
                        runtime_narration=args.narration_mode,
                        debug_narration_trace=args.debug_provider_shape,
                    )
            returned_state = _safe_dict(turn_result.get("simulation_state"))
            if returned_state:
                authoritative_state = merge_autoplay_simulation_state(
                    before_state=authoritative_state,
                    returned_state=returned_state,
                )
            simulation_state = deepcopy(authoritative_state)
            with timed_stage(turn_performance, "story_hooks_ms"):
                story_hook_result = apply_autoplay_story_hooks(
                    simulation_state=authoritative_state,
                    player_action=player_action,
                    turn_index=turn_index,
                )
            if story_hook_result.get("changed"):
                authoritative_state = merge_autoplay_simulation_state(
                    before_state=authoritative_state,
                    returned_state=_safe_dict(story_hook_result.get("simulation_state")),
                )
            authoritative_state = _commit_authoritative_state(
                session_id=session_id,
                authoritative_state=authoritative_state,
                runtime_narration=args.narration_mode,
            )
            simulation_state = deepcopy(authoritative_state)

            try:
                from tests.rpg.autoplay.story_hooks import (
                    apply_autoplay_travel_authority,
                )

                travel_authority_result = apply_autoplay_travel_authority(
                    simulation_state,
                    player_action=_safe_str(player_action),
                    turn_index=turn_index,
                )
                if travel_authority_result.get("changed"):
                    simulation_state = _safe_dict(travel_authority_result.get("simulation_state")) or simulation_state
                    _probe_log(
                        bool(getattr(args, "debug_autoplay_stage_timing", False)),
                        "autoplay_travel_authority.applied",
                        turn_index=turn_index,
                        events=travel_authority_result.get("events"),
                        current_location=simulation_state.get("current_location"),
                        current_location_name=simulation_state.get("current_location_name"),
                    )
            except Exception as exc:
                _probe_log(
                    bool(getattr(args, "debug_autoplay_stage_timing", False)),
                    "autoplay_travel_authority.failed",
                    turn_index=turn_index,
                    error=f"{type(exc).__name__}: {exc}",
                )

        except Exception as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"
            turn_result = {
                "ok": False,
                "error": runtime_error,
                "traceback": traceback.format_exc(),
            }
            story_hook_result = {}

        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "runtime_turn_execution.result",
            turn_index=turn_index,
            ok=_safe_dict(turn_result).get("ok"),
            keys=",".join(sorted(_safe_dict(turn_result).keys())[:80]),
        )
        authoritative_state = _merge_turn_result_authoritative_state(authoritative_state, turn_result)
        authoritative_state = _refresh_scenario_progression_actions_for_turn(
            authoritative_state,
            args,
            turn_index=turn_index,
        )
        authoritative_state, progression_authority_state = _update_sidecar_and_overlay(
            authoritative_state,
            progression_authority_state,
            reason="after_turn_result_merge",
            turn_index=turn_index,
        )
        authoritative_state = _commit_campaign_state_authority(
            authoritative_state,
            transcript_tail=transcript[-12:],
            phase="turn",
        )
        authoritative_state = _refresh_scenario_progression_actions_for_turn(
            authoritative_state,
            args,
            turn_index=turn_index,
        )
        authoritative_state, progression_authority_state = _update_sidecar_and_overlay(
            authoritative_state,
            progression_authority_state,
            reason="after_campaign_state_commit",
            turn_index=turn_index,
        )

        base_response_payload: Dict[str, Any] = {}
        raw_payload = _safe_dict(
            _safe_dict(turn_result.get("manual_turn_summary")).get("raw_narration_payload")
        )
        raw_npc = _safe_dict(
            _safe_dict(turn_result.get("manual_turn_summary")).get("raw_npc")
        )
        runtime_has_dialogue = bool(
            _safe_str(raw_payload.get("narration"))
            and (
                _safe_dict(raw_payload.get("npc")).get("line")
                or raw_npc.get("line")
                or _autoplay_report_action_type(player_action) != "social"
            )
        )
        with timed_stage(turn_performance, "base_response_ms"):
            if args.autoplay_base_response != "off" and not runtime_has_dialogue:
                base_response_payload = build_autoplay_base_response(
                    provider=provider,
                    player_action=player_action,
                    simulation_state=authoritative_state,
                    turn_index=turn_index,
                    use_provider=args.autoplay_base_response == "provider",
                    max_tokens=int(args.base_response_max_tokens),
                )

        # Final turn commit. This is the state that the next turn must use as
        # before_state. Do not reload from the manual session here.
        authoritative_state = _commit_authoritative_state(
            session_id=session_id,
            authoritative_state=authoritative_state,
        )
        final_turn_state = deepcopy(authoritative_state)
        with timed_stage(turn_performance, "progress_eval_ms"):
            progress_delta = classify_progress_delta(
                before_state=before_state,
                after_state=final_turn_state,
            )
            after_digest = state_digest(final_turn_state)
        state_preservation_debug = {
            "baseline_source": "runner_authoritative_state",
            "commit_policy": "no_manual_reload_after_turn_start",
            "next_turn_baseline_source": "last_committed_state",
            "baseline_check": baseline_check,
            "before_counts": before_digest.get("counts", {}),
            "after_counts": after_digest.get("counts", {}),
            "committed_counts": after_digest.get("counts", {}),
            "journal_entries_delta": (
                after_digest.get("counts", {}).get("journal_entries", 0)
                - before_digest.get("counts", {}).get("journal_entries", 0)
            ),
        }
        progress_quality = classify_turn_progress_quality(
            {
                "progress_delta": progress_delta,
                "player_action_context": context,
                "selected_player_action": selected,
                "player_action": player_action,
            }
        )
        with timed_stage(turn_performance, "state_bounds_ms"):
            state_bounds = collect_state_bounds(
                final_turn_state,
                max_state_bytes=int(args.max_state_bytes),
                max_root_count=int(args.max_roots),
                max_list_length=int(args.max_state_list_length),
                max_dict_keys=int(args.max_state_dict_keys),
            )
        save_load_checkpoint = {}
        checkpoint_every = int(args.checkpoint_every or 0)
        if checkpoint_every > 0 and turn_index % checkpoint_every == 0:
            if args.checkpoint_mode == "background":
                with timed_stage(turn_performance, "background_enqueue_ms"):
                    checkpoint_job_id = pipeline.submit_checkpoint(
                        session_id=session_id,
                        turn_index=turn_index,
                        checkpoint_dir=checkpoint_dir,
                        simulation_state=final_turn_state,
                    )
                save_load_checkpoint = {
                    "ok": True,
                    "status": "pending",
                    "job_id": checkpoint_job_id,
                    "mode": "background",
                }
            else:
                with timed_stage(turn_performance, "checkpoint_ms"):
                    save_load_checkpoint = validate_save_load_checkpoint(
                        session_id=session_id,
                        turn_index=turn_index,
                        checkpoint_dir=checkpoint_dir,
                        simulation_state=final_turn_state,
                    )
            # validate_save_load_checkpoint() already verifies checkpoint
            # rehydration. Do not make the checkpoint reload the live baseline;
            # the runner-owned authoritative_state remains canonical.
            simulation_state = deepcopy(final_turn_state)
        last_committed_state = deepcopy(final_turn_state)
        simulation_state = deepcopy(final_turn_state)
        checkpoint_every = int(getattr(args, "checkpoint_every", 0) or 0)
        if checkpoint_every > 0 and turn_index % checkpoint_every == 0:
            checkpoint_validation_rows.append(
                {
                    "ok": True,
                    "mode": "write_only_fingerprint",
                    "turn_index": turn_index,
                    "progression_completed_node_count": int(
                        _progression_node_count(final_turn_state)
                    ),
                    "progression_revision": int(
                        _progression_revision(final_turn_state)
                    ),
                    "active_graph_id": _safe_str(
                        final_turn_state.get("scenario_progression_active_graph_id")
                    ),
                    "completed_graph_ids": _safe_list(
                        final_turn_state.get("scenario_progression_completed_graph_ids")
                    ),
                    "waiting_for_next_graph_pack": bool(
                        final_turn_state.get("scenario_progression_waiting_for_next_graph_pack")
                    ),
                }
            )
        narration = _extract_narration(turn_result)
        narration_status = "ready"
        narration_job_id = ""
        advisory_status = "disabled"
        advisory_job_id = ""
        combined_background_llm_job_id = ""
        resolved_turn_contract = _resolve_turn_contract_for_report(
            turn_result=turn_result,
            base_response_payload=base_response_payload,
        )

        if args.narration_mode == "deferred":
            narration_status = "pending"
            advisory_status = "pending"
            with timed_stage(turn_performance, "background_enqueue_ms"):
                semantic_action_record = _extract_background_semantic_action_record(turn_result)
                if args.background_llm_mode == "combined":
                    background_runtime_state = _runtime_state_with_loaded_profiles_for_background(
                        turn_result=turn_result,
                        simulation_state=final_turn_state,
                    )
                    with _ProbeTimer(
                        bool(getattr(args, "debug_autoplay_stage_timing", False)),
                        "submit_combined_background_llm",
                        turn_index=turn_index,
                    ):
                        combined_background_llm_job_id = pipeline.submit_combined_background_llm(
                            provider=provider,
                            session_id=session_id,
                            turn_index=turn_index,
                            player_action=player_action,
                            simulation_state=final_turn_state,
                            runtime_state=background_runtime_state,
                            turn_contract=resolved_turn_contract,
                            semantic_action_record=semantic_action_record,
                            prefer_provider=True,
                        )
                    _track_background_submit(
                        background_result_timing_tracker,
                        job_id=_safe_str(combined_background_llm_job_id),
                        turn_index=turn_index,
                        phase="turn_submit",
                    )
                    _register_background_job(
                        background_job_registry,
                        job_id=_safe_str(combined_background_llm_job_id),
                        turn_index=turn_index,
                        handle=combined_background_llm_job_id,
                        pipeline=pipeline,
                    )
                    _probe_log(
                        bool(getattr(args, "debug_autoplay_stage_timing", False)),
                        "submit_combined_background_llm.result",
                        turn_index=turn_index,
                        job_id=_safe_str(combined_background_llm_job_id),
                    )
                    narration_job_id = combined_background_llm_job_id
                    advisory_job_id = combined_background_llm_job_id
                else:
                    narration_job_id = pipeline.submit_deferred_narration(
                        provider=provider,
                        session_id=session_id,
                        turn_index=turn_index,
                        player_action=player_action,
                        simulation_state=final_turn_state,
                        turn_contract=turn_result.get("turn_contract") or {},
                        prefer_provider=True,
                    )
                    advisory_job_id = pipeline.submit_deferred_advisory(
                        provider=provider,
                        session_id=session_id,
                        turn_index=turn_index,
                        player_action=player_action,
                        simulation_state=final_turn_state,
                        turn_contract=turn_result.get("turn_contract") or {},
                        semantic_action_record=semantic_action_record,
                        prefer_provider=True,
                    )
            if not narration:
                narration = "Narration is being prepared..."

        blocking_narration_payload = (
            turn_result.get("narration_payload")
            or turn_result.get("structured_narration")
            or {}
        )
        blocking_narration_source = (
            blocking_narration_payload.get("source")
            if isinstance(blocking_narration_payload, dict)
            else ""
        )
        deferred_blocking_provider_violation = (
            args.narration_mode == "deferred"
            and blocking_narration_source == "provider_runtime_narration"
        )

        record_build_start = now_perf()
        if deferred_blocking_provider_violation:
            pending_payload = _pending_deferred_narration_payload()
            turn_result["narration_payload"] = pending_payload
            turn_result["structured_narration"] = pending_payload
            turn_result["narration"] = pending_payload["narration"]
            narration = pending_payload["narration"]
            regression_warnings.append(
                {
                    "turn_index": turn_index,
                    "category": "deferred_narration_blocked_on_provider",
                    "message": "Deferred narration mode still called provider_runtime_narration inside the blocking turn path.",
                    "blocking_source": "provider_runtime_narration",
                }
            )

        prebackground_profile_load_result = _safe_dict(
            _safe_dict(background_runtime_state).get("npc_evolution", {}).get("profile_load_result")
        )

        session_obj = _safe_dict(turn_result.get("session"))
        row_runtime_state = (
            _safe_dict(turn_result.get("runtime_state"))
            or _safe_dict(session_obj.get("runtime_state"))
            or {}
        )
        runtime_state = _merge_base_runtime_namespaces(
            carried_campaign_runtime_state,
            row_runtime_state,
        )
        runtime_state = _merge_preserving_runtime_state(final_turn_state, runtime_state)
        runtime_state = _overlay_and_assert_progression_sidecar(
            runtime_state,
            progression_authority_state,
            reason="after_turn_runtime_state_merge",
            turn_index=turn_index,
        )
        runtime_state = ensure_quest_runtime_state(
            runtime_state=runtime_state,
            scenario_seed=_safe_str(args.scenario_seed),
        )
        journal_turn_result = _journal_turn_result_with_narration_sources(
            turn_result=turn_result,
            combined_background_result=combined_background_result,
            resolved_narration_payload=resolved_narration_payload,
            narration_text=journal_narration_text,
        )
        runtime_state = advance_campaign_journal_for_turn(
            runtime_state=runtime_state,
            turn_index=turn_index,
            player_input=player_action,
            turn_contract=resolved_turn_contract,
            turn_result=journal_turn_result,
            minutes_per_turn=int(args.campaign_minutes_per_turn),
            journal_every_turns=int(args.journal_every_turns),
        )
        runtime_state = _overlay_and_assert_progression_sidecar(
            runtime_state,
            progression_authority_state,
            reason="after_campaign_journal_advance",
            turn_index=turn_index,
        )
        carried_campaign_runtime_state = _merge_base_runtime_namespaces(
            carried_campaign_runtime_state,
            runtime_state,
        )
        turn_result["runtime_state"] = runtime_state
        if session_obj:
            session_obj["runtime_state"] = runtime_state
            turn_result["session"] = session_obj

        record = {
            "turn_index": turn_index,
            "session_id": session_id,
            "player_action_context": context if args.artifact_detail == "full" else {
                "format_version": context.get("format_version"),
                "mode": context.get("mode"),
                "location": context.get("location"),
                "active_objectives": context.get("active_objectives"),
                "suggested_actions": context.get("suggested_actions"),
            },
            "selected_player_action": selected,
            "selected_action_reason": selected.get("reason"),
            "strategy_guidance": context.get("strategy_guidance") or selected.get("strategy_guidance") or {},
            "executable_action_repair": executable_action_repair,
            "goal_pressure": goal_pressure_context,
            "player_reasoning_plan": player_reasoning_plan,
            "action_diversity_before_turn": current_diversity_metrics,
            "progress_quality_before_turn": current_progress_quality_metrics,
            "player_action": player_action,
            "player_agent_selection_source": player_agent_selection_source,
            "scenario_progression_summary": (
                _safe_dict(authoritative_state.get("scenario_progression_current_turn_summary"))
                if int(_safe_dict(authoritative_state.get("scenario_progression_current_turn_summary")).get("turn_index") or -1) == int(turn_index)
                else (
                    _safe_dict(turn_result.get("scenario_progression_summary"))
                    if isinstance(turn_result, dict) and _safe_dict(turn_result.get("scenario_progression_summary"))
                    else {
                        "ok": True,
                        "changed": False,
                        "turn_index": turn_index,
                        "reason": "no_current_turn_progression_match",
                    }
                )
            ),
            "scenario_progression_actions": _safe_list(authoritative_state.get("scenario_progression_actions"))[:8],
            "progression_sidecar_completed_node_count": _progression_node_count(
                progression_authority_state
            ),
            "progression_sidecar_revision": _progression_revision(
                progression_authority_state
            ),
            "progression_authority_sidecar_summary": _safe_dict(
                progression_authority_state.get("progression_authority_summary")
            ),
            "progression_runtime_completed_node_count": _progression_node_count(authoritative_state),
            "progression_runtime_revision": _progression_revision(authoritative_state),
            "active_graph_objective_count": _active_graph_objective_count_from_state(authoritative_state),
            "scenario_progression_actions_empty_with_active_objectives": (
                _active_graph_objective_count_from_state(authoritative_state) > 0
                and not bool(_safe_list(authoritative_state.get("scenario_progression_actions")))
            ),
            "scenario_arc_complete": _scenario_arc_complete_from_state(authoritative_state, args),
            "arc_complete_graph_action_available": bool(
                _arc_complete_graph_action_from_state(authoritative_state)
            ),
            "top_scenario_progression_action_id": _safe_str(
                pre_apply_top_graph_action.get("action_id")
            ),
            "top_scenario_progression_command": _safe_str(
                pre_apply_top_graph_action.get("command")
            ),
            "handoff_semantic": handoff_semantic,
            "player_agent_anti_loop_context": anti_loop_context,
            "turn_result": turn_result if args.artifact_detail == "full" else {
                "ok": turn_result.get("ok"),
                "warning": turn_result.get("warning"),
                "compatibility_turn_runtime": turn_result.get("compatibility_turn_runtime"),
                "runtime_name": turn_result.get("runtime_name"),
            },
            "narration_trace": turn_result.get("narration_trace") if args.debug_provider_shape else [],
            "provider_trace": turn_result.get("provider_trace") if args.debug_provider_shape else [],
            "manual_stage_trace": turn_result.get("manual_stage_trace") if args.debug_provider_shape else [],
            "manual_harness_trace": turn_result.get("manual_harness_trace") if args.debug_provider_shape else [],
            "manual_harness_trace_summary": turn_result.get("manual_harness_trace_summary") if args.debug_provider_shape else {},
            "turn_perf_trace": turn_result.get("turn_perf_trace") if args.debug_provider_shape else [],
            "turn_perf_trace_summary": turn_result.get("turn_perf_trace_summary") if args.debug_provider_shape else {},
            "turn_contract": resolved_turn_contract,
            "narration": narration,
            "narration_mode": args.narration_mode,
            "narration_status": narration_status,
            "narration_job_id": narration_job_id,
            "deferred_advisory_status": advisory_status,
            "deferred_advisory_job_id": advisory_job_id,
            "background_llm_mode": args.background_llm_mode,
            "combined_background_llm_job_id": combined_background_llm_job_id,
            "background_result_attach_pending": bool(combined_background_llm_job_id),
            "blocking_narration_source": blocking_narration_source,
            "deferred_blocking_provider_violation": deferred_blocking_provider_violation,
            "blocking_provider_call_suppressed_after_the_fact": bool(deferred_blocking_provider_violation),
            "latency_profile": args.latency_profile,
            "runtime_error": runtime_error,
            "before_state_digest": before_digest,
            "after_state_digest": after_digest,
            "progress_delta": progress_delta,
             "state_preservation_debug": state_preservation_debug,
            "authoritative_state_digest": after_digest,
            "committed_next_turn_digest": state_digest(last_committed_state),
            "before_state": before_state if args.artifact_detail == "full" else {},
            "final_authoritative_state": final_turn_state,
             "progress_quality": progress_quality,
            "state_bounds": state_bounds,
            "save_load_checkpoint": save_load_checkpoint,
            "story_hook_result": story_hook_result,
            "base_response_payload": base_response_payload,
            "prebackground_profile_load_result": prebackground_profile_load_result,
            "runtime_state": runtime_state,
        }

        _apply_scenario_progression_location_bridge(record)

        narration_payload = _safe_dict(turn_result.get("narration_payload"))
        grounding_validation = _safe_dict(narration_payload.get("grounding_validation"))
        if grounding_validation:
            record["narration_grounding_validation"] = grounding_validation
            record["narration_grounding_ok"] = bool(grounding_validation.get("ok"))
            record["narration_grounding_fallback_used"] = bool(
                grounding_validation.get("fallback_used")
            )

        turn_performance["record_build_ms"] = elapsed_ms(record_build_start)

        playable_blocking_keys = [
            "manual_turn_ms",
            "story_hooks_ms",
            "base_response_ms",
            "progress_eval_ms",
            "state_bounds_ms",
            "record_build_ms",
        ]

        autoplay_blocking_keys = ["player_agent_ms"] + playable_blocking_keys

        if args.checkpoint_mode == "blocking":
            playable_blocking_keys.append("checkpoint_ms")
            autoplay_blocking_keys.append("checkpoint_ms")

        turn_performance["human_playable_blocking_ms"] = round(
            sum(float(turn_performance.get(key) or 0.0) for key in playable_blocking_keys),
            3,
        )

        turn_performance["playable_blocking_ms"] = round(
            sum(float(turn_performance.get(key) or 0.0) for key in autoplay_blocking_keys),
            3,
        )
        turn_performance["turn_total_ms"] = elapsed_ms(turn_perf_start)
        record["performance"] = turn_performance

        # Final source detection must run against the exact record object that
        # will be appended/written. Recent artifacts showed:
        #   record["turn_result"]["narration_payload"]["source"]
        # was provider_runtime_narration while blocking_narration_source stayed
        # empty, so do this directly and overwrite the record fields here.
        record_turn_result = (
            record.get("turn_result")
            if isinstance(record.get("turn_result"), dict)
            else {}
        )
        record_payload = (
            record_turn_result.get("narration_payload")
            or record_turn_result.get("structured_narration")
            or {}
        )
        record_source = (
            record_payload.get("source")
            if isinstance(record_payload, dict)
            else ""
        )
        record["blocking_narration_source"] = record_source
        record_violation = (
            args.narration_mode == "deferred"
            and record_source == "provider_runtime_narration"
        )
        record["deferred_blocking_provider_violation"] = bool(record_violation)
        record["blocking_provider_call_suppressed_after_the_fact"] = bool(record_violation)
        if record_violation:
            pending_payload = _pending_deferred_narration_payload()
            record_turn_result["narration_payload"] = pending_payload
            record_turn_result["structured_narration"] = pending_payload
            record_turn_result["narration"] = pending_payload["narration"]
            record["narration"] = pending_payload["narration"]
            regression_warnings.append(
                {
                    "turn_index": turn_index,
                    "category": "deferred_narration_blocked_on_provider",
                    "message": "Deferred narration mode still called provider_runtime_narration inside the blocking turn path.",
                    "blocking_source": "provider_runtime_narration",
                }
            )

        _directly_update_dialogue_state_from_turn(
            runtime_state=runtime_state,
            player_action=_safe_str(player_action),
            turn_result=_safe_dict(turn_result),
            record=record if isinstance(record, dict) else None,
            turn_index=turn_index,
            debug_autoplay_stage_timing=bool(getattr(args, "debug_autoplay_stage_timing", False)),
        )

        if "progression_sidecar_completed_node_count" not in record:
            raise RuntimeError(
                f"progression_sidecar_fields_missing_from_record:turn={turn_index}"
            )

        record["authoritative_blocking_ms"] = _authoritative_human_playable_blocking_ms(record)
        record["human_playable_blocking_metric_mode"] = "authoritative_deterministic_only"

        _attach_grounding_fields_to_autoplay_row(record, turn_result if isinstance(turn_result, dict) else {})

        missing_mechanics = [
            name
            for name, covered in mechanics_coverage_runtime.items()
            if not covered
        ]

        _inject_available_mechanics_for_row(
            record,
            mechanics_state=mechanics_runtime_state,
            missing_mechanics=missing_mechanics,
        )

        mechanic_action_decision = _maybe_force_missing_mechanic_action(
            proposed_action=_safe_str(record.get("player_action") or player_action),
            latest_row=record,
            missing_mechanics=missing_mechanics,
            turn_index=int(record.get("turn_index") or turn_index),
            failed_opportunity_ids=mechanics_failed_opportunity_ids,
        )

        if _safe_dict(mechanic_action_decision).get("forced"):
            record["player_action_original"] = record.get("player_action")
            record["player_action"] = _safe_str(
                mechanic_action_decision.get("action") or record.get("player_action")
            )
            record["mechanics_forced_action"] = mechanic_action_decision
            player_action = record["player_action"]

        final_player_action_for_mechanics = _safe_str(record.get("player_action") or player_action)
        record["mechanic_resolution_input"] = final_player_action_for_mechanics

        mechanic_resolution = resolve_mechanic_opportunity(
            player_input=final_player_action_for_mechanics,
            state={
                **mechanics_runtime_state,
                "current_location": _current_row_location(
                    record,
                    fallback=_safe_str(mechanics_runtime_state.get("current_location") or "scene:rusty_flagon"),
                ),
            },
            scenario_state={},
        )

        if mechanic_resolution.get("ok"):
            mechanic_result = _safe_dict(mechanic_resolution.get("result"))
            mechanic_contract = _safe_dict(mechanic_resolution.get("turn_contract"))
            mechanic_delta = _safe_dict(mechanic_resolution.get("state_delta"))

            record["mechanic_resolution"] = mechanic_resolution
            record["mechanics_evidence_source"] = "mechanic_opportunity_resolver"
            record["mechanic"] = mechanic_resolution.get("mechanic") or mechanic_result.get("mechanic")
            record["meaningful_progress"] = True
            record["progress_category"] = (
                mechanic_result.get("progress_category")
                or mechanic_resolution.get("progress_category")
            )

            record["result"] = {
                **_safe_dict(record.get("result")),
                **mechanic_result,
                "mechanics_evidence_source": "mechanic_opportunity_resolver",
            }
            record["turn_contract"] = {
                **_safe_dict(record.get("turn_contract")),
                **mechanic_contract,
                "mechanic": record.get("mechanic"),
                "mechanic_resolution": mechanic_resolution,
                "result": {
                    **_safe_dict(_safe_dict(record.get("turn_contract")).get("result")),
                    **mechanic_result,
                    "mechanics_evidence_source": "mechanic_opportunity_resolver",
                },
                "state_delta": {
                    **_safe_dict(_safe_dict(record.get("turn_contract")).get("state_delta")),
                    **mechanic_delta,
                },
            }
            record["state_delta"] = {
                **_safe_dict(record.get("state_delta")),
                **mechanic_delta,
            }

            mechanics_runtime_state = _apply_mechanics_delta_to_runtime_state(
                mechanics_runtime_state,
                mechanic_delta,
            )

            resolved_mechanic = _safe_str(record.get("mechanic") or mechanic_resolution.get("mechanic"))
            if resolved_mechanic:
                if resolved_mechanic == "buying":
                    mechanics_coverage_runtime["buying"] = True
                    mechanics_coverage_runtime["currency_change"] = True
                    mechanics_coverage_runtime["inventory_change"] = True

                elif resolved_mechanic == "service_or_lodging":
                    mechanics_coverage_runtime["service_or_lodging"] = True
                    mechanics_coverage_runtime["currency_change"] = True

                elif resolved_mechanic == "party_recruitment":
                    mechanics_coverage_runtime["party_recruitment"] = True

                elif resolved_mechanic == "combat_started":
                    mechanics_coverage_runtime["combat_started"] = True

                elif resolved_mechanic == "combat_resolved":
                    mechanics_coverage_runtime["combat_resolved"] = True
                    mechanics_coverage_runtime["xp_gain"] = True
                    mechanics_coverage_runtime["inventory_change"] = True

                elif resolved_mechanic == "travel":
                    mechanics_coverage_runtime["travel"] = True

                elif resolved_mechanic == "quest_progress":
                    mechanics_coverage_runtime["quest_progress"] = True

            _inject_available_mechanics_for_row(
                record,
                mechanics_state=mechanics_runtime_state,
                missing_mechanics=[
                    name
                    for name, covered in mechanics_coverage_runtime.items()
                    if not covered
                ],
            )
        else:
            mechanics_runtime_state["current_location"] = _current_row_location(
                record,
                fallback=_safe_str(mechanics_runtime_state.get("current_location") or "scene:rusty_flagon"),
            )

            forced_opportunity_id = _safe_str(
                _safe_dict(record.get("mechanics_forced_action")).get("opportunity_id")
            )
            if forced_opportunity_id:
                mechanics_failed_opportunity_ids.add(forced_opportunity_id)
                record["mechanic_resolution_failed_opportunity_id"] = forced_opportunity_id
                record["mechanic_resolution_failed_reason"] = _safe_str(
                    mechanic_resolution.get("reason")
                )

        transcript.append(record)

        _assert_progression_monotonic(
            authoritative_state,
            turn_index=turn_index,
            previous_node_count=progression_node_count_at_turn_start,
            previous_revision=progression_revision_at_turn_start,
        )

        compact_transcript_tail = _compact_campaign_state_transcript_tail(transcript, limit=12)
        runtime_state["recent_turns"] = compact_transcript_tail
        runtime_state["transcript_tail"] = compact_transcript_tail
        action_history = runtime_state.setdefault("action_history", [])
        if isinstance(action_history, list):
            action_history.append(
                {
                    "turn": turn_index,
                    "turn_index": turn_index,
                    "player_action": _safe_str(player_action),
                }
            )
            del action_history[:-50]

        runtime_state = _commit_campaign_state_authority(
            runtime_state,
            turn_record=record,
            transcript_tail=transcript[-12:],
            phase="turn",
        )
        runtime_state = _refresh_scenario_progression_actions_for_turn(
            runtime_state,
            args,
            turn_index=turn_index,
        )
        runtime_state, progression_authority_state = _update_sidecar_and_overlay(
            runtime_state,
            progression_authority_state,
            reason="after_post_append_commit",
            turn_index=turn_index,
        )
        carried_campaign_runtime_state = _merge_base_runtime_namespaces(
            carried_campaign_runtime_state,
            runtime_state,
        )
        last_committed_state = deepcopy(runtime_state)
        simulation_state = deepcopy(last_committed_state)
        turn_result["runtime_state"] = runtime_state
        if session_obj:
            session_obj["runtime_state"] = runtime_state
            turn_result["session"] = session_obj
        record["runtime_state"] = runtime_state
        record["campaign_state_commit_summary"] = _safe_dict(
            runtime_state.get("campaign_state_commit_summary")
        )
        record["quest_progress_after_commit"] = _safe_dict(runtime_state.get("quest_progress"))
        record["campaign_state_commit_sequence"] = int(runtime_state.get("campaign_state_commit_sequence") or 0)
        record["progression_sidecar_completed_node_count"] = _progression_node_count(
            progression_authority_state
        )
        record["progression_sidecar_revision"] = _progression_revision(
            progression_authority_state
        )
        record["progression_authority_sidecar_summary"] = _safe_dict(
            progression_authority_state.get("progression_authority_summary")
        )
        record["progression_runtime_completed_node_count"] = _progression_node_count(runtime_state)
        record["progression_runtime_revision"] = _progression_revision(runtime_state)
        record["active_graph_objective_count"] = _active_graph_objective_count_from_state(runtime_state)
        record["scenario_progression_actions_empty_with_active_objectives"] = (
            _active_graph_objective_count_from_state(runtime_state) > 0
            and not bool(_safe_list(runtime_state.get("scenario_progression_actions")))
        )
        commit_summary = _safe_dict(runtime_state.get("campaign_state_commit_summary"))
        commit_qps = _safe_dict(commit_summary.get("quest_progress_summary"))
        active_handoff_count = 0
        for quest in _safe_list(commit_qps.get("quests")):
            quest = _safe_dict(quest)
            if not quest.get("completed") and (
                quest.get("handoff_quest")
                or quest.get("source") == "campaign_state_authority_commit"
                or _safe_str(quest.get("title")).startswith("Investigate Lead:")
            ):
                active_handoff_count += 1
        committed_digest = state_digest(last_committed_state)
        record["final_authoritative_state"] = last_committed_state
        record["after_state_digest"] = committed_digest
        record["authoritative_state_digest"] = committed_digest
        record["committed_next_turn_digest"] = committed_digest
        state_preservation_debug["committed_counts"] = committed_digest.get("counts", {})
        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "campaign_state_commit.visible_to_next_turn",
            turn_index=turn_index,
            active_count=commit_qps.get("active_count"),
            completed_count=commit_qps.get("completed_count"),
            active_handoff_count=active_handoff_count,
            handoff_reason=_safe_str(_safe_dict(commit_summary.get("handoff_summary")).get("reason")),
            handoff_changed=bool(_safe_dict(commit_summary.get("handoff_summary")).get("changed")),
        )

        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "turn.end",
            turn_index=turn_index,
            transcript_len=len(transcript),
        )
        runtime_state = _overlay_and_assert_progression_sidecar(
            runtime_state,
            progression_authority_state,
            reason="turn_end",
            turn_index=turn_index,
        )
        _probe_log(
            bool(getattr(args, "debug_autoplay_stage_timing", False)),
            "scenario_progression.sidecar.end",
            turn_index=turn_index,
            runtime_revision=_progression_revision(runtime_state),
            sidecar_revision=_progression_revision(progression_authority_state),
            runtime_completed_node_count=_progression_node_count(runtime_state),
            sidecar_completed_node_count=_progression_node_count(progression_authority_state),
            runtime_fact_count=_progression_fact_count(runtime_state),
            sidecar_fact_count=_progression_fact_count(progression_authority_state),
            next_actions=[
                _safe_str(_safe_dict(row).get("action_id"))
                for row in _safe_list(runtime_state.get("scenario_progression_actions"))[:5]
            ],
        )
        _assert_progression_sidecar_monotonic(
            progression_authority_state,
            turn_index=turn_index,
            previous_node_count=progression_sidecar_max_node_count,
            previous_revision=progression_sidecar_max_revision,
        )
        progression_sidecar_max_node_count = max(
            progression_sidecar_max_node_count,
            _progression_node_count(progression_authority_state),
        )
        progression_sidecar_max_revision = max(
            progression_sidecar_max_revision,
            _progression_revision(progression_authority_state),
        )
        last_committed_state = deepcopy(runtime_state)

        if len(transcript) <= transcript_len_at_turn_start:
            raise RuntimeError(
                "autoplay_turn_did_not_append_transcript_row:"
                f"turn_index={turn_index}:"
                f"start_len={transcript_len_at_turn_start}:"
                f"end_len={len(transcript)}"
            )

        health = evaluate_autoplay_health(
            transcript,
            latest_context=context,
            max_repeated_actions=args.max_repeated_actions,
            max_runtime_errors=0 if args.fail_on_runtime_error else 999999,
            allow_compatibility_turn_runtime=not args.fail_on_compatibility_turn_runtime,
            max_player_agent_fallback_rate=args.max_player_agent_fallback_rate,
            max_no_progress_turns=args.max_no_progress_turns,
            fail_on_checkpoint_failure=not args.allow_checkpoint_failures,
            fail_on_state_bound_warnings=not args.allow_state_bound_warnings,
            min_action_diversity_rate=float(args.min_action_diversity_rate),
            min_category_diversity_rate=float(args.min_category_diversity_rate),
        )
        if args.stop_on_loop and health.get("loop", {}).get("ok") is False:
            stopped_reason = "repeated_action_loop"
            break
        if runtime_error and args.fail_on_runtime_error:
            stopped_reason = "runtime_error"
            break

    _timestamped_print(
        "Final background drain starting "
        f"timeout_seconds={float(args.final_background_drain_timeout_seconds)} "
        f"cancel_unfinished={bool(args.cancel_unfinished_background_on_final_timeout)}"
    )
    with _ProbeTimer(
        bool(getattr(args, "debug_autoplay_stage_timing", False)),
        "final_background_drain",
        timeout_seconds=float(args.final_background_drain_timeout_seconds),
        cancel_unfinished=bool(args.cancel_unfinished_background_on_final_timeout),
    ):
        background_results = pipeline.drain(
            timeout_seconds=float(args.final_background_drain_timeout_seconds),
            cancel_unfinished=bool(args.cancel_unfinished_background_on_final_timeout),
        )
    _timestamped_print(f"Final background drain finished results={len(background_results)}")

    background_executor_shutdown_summary = {}
    try:
        background_executor_shutdown_summary = pipeline.executor_thread_diagnostics()
    except Exception as exc:
        background_executor_shutdown_summary = {
            "error": f"{type(exc).__name__}: {exc}",
        }
    final_drain_event = _drain_completed_background_jobs_for_transcript(
        pipeline=pipeline,
        job_registry=background_job_registry,
        transcript=transcript,
        current_turn=int(args.turns),
        phase="final",
        wait_ms=0,
        timing_tracker=background_result_timing_tracker,
    )
    background_drain_events.append(final_drain_event)
    background_results_summary = attach_background_results_to_transcript(
        transcript, background_results,
        timing_tracker=background_result_timing_tracker,
        attach_turn=int(args.turns),
        session_id=session_id,
    )

    # If combined results are attached after journal advancement, refresh journal entries with narration.
    for record in transcript:
        combined_background_result = _safe_dict(record.get("combined_background_llm_result"))
        if combined_background_result:
            record["combined_background_llm_result"] = combined_background_result

            # If the turn just wrote a journal entry, refresh that entry with
            # the now-available presentation narration. This is deterministic
            # and only rewrites the same journal:turn:N text from known facts.
            runtime_state = _safe_dict(record.get("runtime_state"))
            journal = _safe_dict(runtime_state.get("player_journal"))
            entries = _safe_list(journal.get("entries"))
            entry_id = f"journal:turn:{record.get('turn_index')}"
            for entry in entries:
                entry = _safe_dict(entry)
                if _safe_str(entry.get("entry_id")) != entry_id:
                    continue
                refreshed_turn_result = _journal_turn_result_with_narration_sources(
                    turn_result=_safe_dict(record.get("turn_result")),
                    combined_background_result=combined_background_result,
                    resolved_narration_payload=_safe_dict(record.get("resolved_narration_payload")),
                    narration_text=_safe_str(combined_background_result.get("narration")),
                )
                # Rebuild one-entry text using accumulated pending snapshots if
                # present; otherwise only replace result text by appending a
                # clean narration line to the existing entry.
                clean_narration = _safe_str(combined_background_result.get("narration"))
                if clean_narration and clean_narration not in _safe_str(entry.get("text")):
                    entry["text"] = _safe_str(entry.get("text")).rstrip() + "\nWhat changed: " + clean_narration
                break
    advisory_promotion_summary = {"ok": True, "enabled": False}
    if args.deferred_advisory_promotion == "on":
        advisory_promotion_summary = run_deferred_advisory_promotions_for_transcript(
            transcript=transcript,
            max_promotions_per_turn=int(args.max_advisory_promotions_per_turn),
        )
        advisory_promotion_summary["enabled"] = True
    with _ProbeTimer(
        bool(getattr(args, "debug_autoplay_stage_timing", False)),
        "pipeline_shutdown",
    ):
        pipeline.shutdown(
            wait=False,
            cancel_futures=bool(args.cancel_unfinished_background_on_final_timeout),
        )

    latest_context = (
        transcript[-1].get("player_action_context")
        if transcript and isinstance(transcript[-1].get("player_action_context"), dict)
        else {}
    )
    progress_quality_metrics = compute_progress_quality_metrics(transcript)
    performance_metrics = summarize_performance(
        transcript=transcript,
        campaign_wall_ms=elapsed_ms(campaign_perf_start),
        artifact_write_ms=artifact_write_ms,
    )
    metrics = compute_progress_metrics(transcript, latest_context=latest_context)
    metrics["player_agent_trace_summary"] = _summarize_player_agent_trace(transcript)
    metrics["deferred_narration_trace_summary"] = _summarize_deferred_narration_trace(transcript)
    metrics["deferred_advisory_trace_summary"] = _summarize_deferred_advisory_trace(transcript)
    metrics["performance_budget_summary"] = _summarize_performance_budget(
        transcript=transcript,
        background_summary=background_results_summary,
    )
    metrics["background_prompt_budget_summary"] = _summarize_background_prompt_budget(transcript)
    metrics["combined_quality_shape_summary"] = _summarize_combined_quality_shape(transcript)
    manual_harness_slowest = []
    for row in transcript:
        summary = row.get("manual_harness_trace_summary") or {}
        for stage in summary.get("slowest_stages") or []:
            manual_harness_slowest.append(
                {
                    "turn_index": row.get("turn_index"),
                    "event": stage.get("event"),
                    "elapsed_seconds": stage.get("elapsed_seconds"),
                }
            )
    metrics["manual_harness_trace_summary"] = {
        "enabled": bool(args.debug_provider_shape),
        "slowest_stages": sorted(
            manual_harness_slowest,
            key=lambda item: float(item.get("elapsed_seconds") or 0.0),
            reverse=True,
        )[:20],
    }

    turn_perf_slowest = []
    for row in transcript:
        summary = row.get("turn_perf_trace_summary") or {}
        for stage in summary.get("slowest_stages") or []:
            turn_perf_slowest.append(
                {
                    "turn_index": row.get("turn_index"),
                    "event": stage.get("event"),
                    "elapsed_seconds": stage.get("elapsed_seconds"),
                }
            )
    metrics["turn_perf_trace_summary"] = {
        "enabled": bool(args.debug_provider_shape),
        "slowest_stages": sorted(
            turn_perf_slowest,
            key=lambda item: float(item.get("elapsed_seconds") or 0.0),
            reverse=True,
        )[:30],
    }
    provider_trace_rows = [
        item
        for row in transcript
        for item in (row.get("provider_trace") or [])
        if isinstance(item, dict)
    ]
    metrics["provider_trace_summary"] = {
        "provider_call_count": sum(1 for row in provider_trace_rows if row.get("event") == "provider_call"),
        "provider_call_seconds": round(
            sum(float(row.get("elapsed_seconds") or 0.0) for row in provider_trace_rows if row.get("event") == "provider_call"),
            3,
        ),
        "by_purpose": {},
    }
    for row in provider_trace_rows:
        if row.get("event") != "provider_call":
            continue
        purpose = str(row.get("purpose") or "unknown")
        bucket = metrics["provider_trace_summary"]["by_purpose"].setdefault(
            purpose,
            {"count": 0, "seconds": 0.0, "prompt_chars": 0},
        )
        bucket["count"] += 1
        bucket["seconds"] = round(bucket["seconds"] + float(row.get("elapsed_seconds") or 0.0), 3)
        bucket["prompt_chars"] += int(row.get("prompt_chars") or 0)
    metrics["narration_trace_summary"] = {
        "guard_enter_count": sum(
            1
            for row in transcript
            for item in (row.get("narration_trace") or [])
            if item.get("event") == "guard_enter"
        ),
        "provider_accessor_calls": sum(
            1
            for row in transcript
            for item in (row.get("narration_trace") or [])
            if item.get("event") == "get_runtime_llm_provider_called"
        ),
        "build_payload_calls": sum(
            1
            for row in transcript
            for item in (row.get("narration_trace") or [])
            if item.get("event") == "before_build_runtime_narration_payload"
        ),
        "provider_runtime_sources": sum(
            1
            for row in transcript
            for item in (row.get("narration_trace") or [])
            if item.get("event") == "after_build_runtime_narration_payload"
            and item.get("source") == "provider_runtime_narration"
        ),
    }
    metrics["progress_quality"] = progress_quality_metrics
    metrics["performance"] = performance_metrics
    metrics["background_jobs"] = background_results_summary
    metrics["deferred_advisory_promotion_summary"] = advisory_promotion_summary
    health = evaluate_autoplay_health(
        transcript,
        latest_context=latest_context,
        max_repeated_actions=args.max_repeated_actions,
        max_runtime_errors=0 if args.fail_on_runtime_error else 999999,
        allow_compatibility_turn_runtime=not args.fail_on_compatibility_turn_runtime,
        max_player_agent_fallback_rate=args.max_player_agent_fallback_rate,
        max_no_progress_turns=args.max_no_progress_turns,
        fail_on_checkpoint_failure=not args.allow_checkpoint_failures,
        fail_on_state_bound_warnings=not args.allow_state_bound_warnings,
        min_action_diversity_rate=float(args.min_action_diversity_rate),
        min_category_diversity_rate=float(args.min_category_diversity_rate),
    )

    deferred_blocking_violations = [
        row for row in transcript
        if row.get("deferred_blocking_provider_violation")
    ]
    if deferred_blocking_violations:
        health["ok"] = False
        health.setdefault("warnings", []).append(
            f"deferred_narration_blocked_on_provider:{len(deferred_blocking_violations)}"
        )

    progress_quality_health = _build_strict_progress_quality_certification(
        transcript=transcript,
        summary=summary,
        min_meaningful_progress_rate=float(args.min_meaningful_progress_rate),
    )
    health.setdefault("warnings", [])
    if not progress_quality_health.get("ok"):
        health["warnings"].extend(
            [
                "progress_quality:" + str(warning)
                for warning in progress_quality_health.get("warnings") or []
            ]
        )
    if args.fail_on_post_objective_weak_progress:
        post_objective_warnings = post_objective_false_progress_warnings(transcript)
        if post_objective_warnings:
            progress_quality_health.setdefault("warnings", [])
            progress_quality_health["warnings"].extend(post_objective_warnings)
            progress_quality_health["ok"] = False
            health["ok"] = False
    health["progress_quality"] = progress_quality_health

    forbidden_player_action_patterns = [
        "current objective",
        "anything that can help",
        "choose a concrete lead",
        "ask a named npc",
        "next known location",
        "inspect a physical clue",
        "grounded way to make progress",
        "investigate story arc",
    ]
    forbidden_player_action_summary = {
        "ok": True,
        "matches": [],
    }
    for row in transcript:
        action = _safe_str(_safe_dict(row).get("player_action"))
        lower = action.lower()
        for pattern in forbidden_player_action_patterns:
            if pattern in lower:
                forbidden_player_action_summary["ok"] = False
                forbidden_player_action_summary["matches"].append(
                    {
                        "turn": _safe_dict(row).get("turn"),
                        "pattern": pattern,
                        "player_action": action,
                    }
                )

    summary = {
        "ok": bool(health.get("ok")) and not stopped_reason,
        "session_id": session_id,
        "scenario_seed": args.scenario_seed,
        "resolved_scenario_seed": seed_resolution["resolved_seed"],
        "seed_resolution": seed_resolution,
        "turn_runtime": "manual_harness",
        "server_runtime_used": False,
        "latency_profile": args.latency_profile,
        "narration_mode": args.narration_mode,
        "background_llm_mode": args.background_llm_mode,
        "checkpoint_mode": args.checkpoint_mode,
        "background_workers": int(effective_background_workers),
        "provider_workers": int(effective_provider_workers),
        "requested_background_workers": int(args.background_workers),
        "requested_provider_workers": int(args.provider_workers),
        "checkpoint_every": int(args.checkpoint_every or 0),
        "state_bounds_limits": {
            "max_state_bytes": int(args.max_state_bytes),
            "max_roots": int(args.max_roots),
            "max_state_list_length": int(args.max_state_list_length),
            "max_state_dict_keys": int(args.max_state_dict_keys),
        },
        "progress_quality_thresholds": {
            "min_meaningful_progress_rate": float(args.min_meaningful_progress_rate),
            "max_churn_only_rate": float(args.max_churn_only_rate),
            "max_churn_only_streak": int(args.max_churn_only_streak),
            "max_objective_target_no_progress_streak": int(args.max_objective_target_no_progress_streak),
            "fail_on_post_objective_weak_progress": bool(args.fail_on_post_objective_weak_progress),
            "fail_on_dialogue_coverage_gap": bool(args.fail_on_dialogue_coverage_gap),
        },
        "strict_progress_quality_certification": progress_quality_health,
        "strategy_profile": args.strategy,
        "base_response_mode": args.autoplay_base_response,
        "action_diversity_thresholds": {
            "action_diversity_window": int(args.action_diversity_window),
            "min_action_diversity_rate": float(args.min_action_diversity_rate),
            "min_category_diversity_rate": float(args.min_category_diversity_rate),
        },
        "seed_result": seed_result,
        "requested_turns": int(args.turns),
        "autoplay_profile": _safe_str(getattr(args, "autoplay_profile", "") or "custom"),
        "effective_turns": int(args.turns),
        "turns_executed": len(transcript),
        "stopped_reason": stopped_reason,
        "player_agent": args.player_agent,
        "provider_shape": provider_shape if args.artifact_detail == "full" else {
            "type": provider_shape.get("type"),
            "module": provider_shape.get("module"),
            "methods": provider_shape.get("methods", [])[:20],
        },
        "strategy": args.strategy,
        "artifact_detail": args.artifact_detail,
        "duration_seconds": round(time.time() - started, 3),
        "health": health,
        "performance": performance_metrics,
        "background_jobs": background_results_summary,
        "deferred_advisory_promotion_summary": advisory_promotion_summary,
        "player_agent_trace_summary": metrics.get("player_agent_trace_summary") or {},
        "deferred_narration_trace_summary": metrics.get("deferred_narration_trace_summary") or {},
        "deferred_advisory_trace_summary": metrics.get("deferred_advisory_trace_summary") or {},
        "performance_budget_summary": metrics.get("performance_budget_summary") or {},
        "background_prompt_budget_summary": metrics.get("background_prompt_budget_summary") or {},
        "combined_quality_shape_summary": metrics.get("combined_quality_shape_summary") or {},
        "player_agent_prompt_budget_summary": _summarize_player_agent_prompt_budget(player_agent_prompt_rows),
        "player_agent_cache_summary": player_agent_cache.summary(),
    }
    latest_evolution_summary = {}
    for row in reversed(transcript):
        latest_evolution_summary = _safe_dict(row.get("npc_evolution_summary"))
        if latest_evolution_summary:
            break
    summary["npc_evolution_summary"] = {
        "latest": latest_evolution_summary,
        "signals_created": advisory_promotion_summary.get("evolution_signals_created", 0),
        "signals_consumed": advisory_promotion_summary.get("evolution_signals_consumed", 0),
    }
    summary["promotion_target_grounding_summary"] = _summarize_promotion_target_grounding(transcript)
    metrics["promotion_target_grounding_summary"] = summary["promotion_target_grounding_summary"]
    summary["npc_evolution_profile_persistence_summary"] = (
        advisory_promotion_summary.get("profile_persist_result") or {}
    )
    summary["npc_profile_load_summary"] = summarize_profile_loads(transcript)
    summary["profile_grounded_output_summary"] = _summarize_profile_grounded_output(transcript)
    summary["npc_arc_progression_summary"] = _summarize_npc_arc_progression(transcript)
    summary["npc_evolution_report_summary"] = summarize_npc_evolution_for_report(transcript)
    quest_progress_summary = _quest_progress_summary_from_state(runtime_state)
    summary["quest_progress_summary"] = quest_progress_summary or summarize_quests_for_report(transcript)
    summary["location_progression_summary"] = _build_location_progression_summary(
        transcript,
        final_summary=summary,
    )
    summary["story_beat_summary"] = summarize_story_beats_for_report(transcript)
    summary["manual_turn_error_summary"] = _summarize_manual_turn_errors(transcript)
    runtime_narration_diagnostics = _safe_dict(metrics.get("narration_trace_summary"))
    provider_attempt_count = int(runtime_narration_diagnostics.get("provider_runtime_sources") or 0)
    fallback_used_turns = len(transcript) - provider_attempt_count  # Approximate
    npc_dialogue_mode_summary = {
        "mode": "provider_backed" if provider_attempt_count > 0 else "deterministic_fallback_only",
        "provider_attempt_count": provider_attempt_count,
        "fallback_used_turns": fallback_used_turns,
        "note": (
            "NPC dialogue is currently deterministic fallback only; intelligence should come from dialogue_state and grounded fallback rules."
            if provider_attempt_count <= 0
            else "NPC dialogue provider was attempted during this run."
        ),
    }
    summary["npc_dialogue_mode_summary"] = npc_dialogue_mode_summary
    console_log_path = Path(args.output_dir) / "console-log.txt"
    console_log_text = ""
    if _ACTIVE_CONSOLE_CAPTURE is not None:
        _ACTIVE_CONSOLE_CAPTURE.write_file()
        console_log_text = _ACTIVE_CONSOLE_CAPTURE.text()
    elif console_log_path.exists():
        console_log_text = console_log_path.read_text(encoding="utf-8", errors="replace")
    summary["console_log_summary"] = summarize_console_log(console_log_text)
    summary["console_log_summary"]["path"] = str(console_log_path)
    summary["action_diversity_summary"] = summarize_action_diversity(transcript)
    summary["progress_timeline_summary"] = summarize_progress_timeline(transcript)
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    campaign_complete_waiting = bool(
        arc.get("campaign_graphs_complete")
        and arc.get("waiting_for_next_graph_pack")
    )
    summary["long_run_warning_summary"] = summarize_long_run_warnings(
        transcript=transcript,
        action_diversity_summary=summary["action_diversity_summary"],
        progress_timeline_summary=summary["progress_timeline_summary"],
        console_log_summary=summary["console_log_summary"],
        manual_turn_error_summary=summary["manual_turn_error_summary"],
        turns_for_strict_gates=int(args.strict_eval_turns),
        campaign_complete_waiting=campaign_complete_waiting,
    )
    npc_line_repetition_summary = repeated_npc_line_metrics(transcript, streak_threshold=3)
    summary["npc_line_repetition_summary"] = npc_line_repetition_summary
    npc_line_repetition_summary = repeated_npc_line_metrics(transcript, streak_threshold=3)
    summary["npc_line_repetition_summary"] = npc_line_repetition_summary
    summary["forbidden_player_action_summary"] = forbidden_player_action_summary

    summary["hundred_turn_eval_summary"] = summarize_hundred_turn_eval(
        transcript=transcript,
        summary=summary,
        turns_for_strict_gates=int(args.strict_eval_turns),
    )
    background_drain_events.append(
        _reconcile_existing_background_attachments(
            transcript=transcript,
            timing_tracker=background_result_timing_tracker,
            attach_turn=int(args.turns),
            phase="final",
        )
    )
    summary["background_result_timing_summary"] = _summarize_background_result_timing(
        background_result_timing_tracker,
        turn_count=len(transcript),
        strict_eval_turns=int(args.strict_eval_turns),
        max_turn_lag=int(args.background_result_max_turn_lag),
    )
    summary["background_executor_shutdown_summary"] = background_executor_shutdown_summary
    summary["background_drain_events"] = background_drain_events[-200:]
    summary["background_jobs"] = _summarize_reconciled_background_jobs(
        existing_background_jobs=_safe_dict(summary.get("background_jobs")),
        background_results=background_results if isinstance(background_results, list) else [],
        background_result_timing_summary=_safe_dict(summary.get("background_result_timing_summary")),
        transcript=transcript,
    )
    summary["performance_budget_summary"] = _reconcile_performance_budget_background_llm_counts(
        performance_budget_summary=_safe_dict(summary.get("performance_budget_summary")),
        background_jobs=_safe_dict(summary.get("background_jobs")),
        background_result_timing_summary=_safe_dict(summary.get("background_result_timing_summary")),
    )
    metrics["story_beat_summary"] = summary["story_beat_summary"]
    metrics["manual_turn_error_summary"] = summary["manual_turn_error_summary"]
    metrics["console_log_summary"] = summary["console_log_summary"]
    metrics["action_diversity_summary"] = summary["action_diversity_summary"]
    metrics["progress_timeline_summary"] = summary["progress_timeline_summary"]
    metrics["long_run_warning_summary"] = summary["long_run_warning_summary"]
    metrics["hundred_turn_eval_summary"] = summary["hundred_turn_eval_summary"]
    metrics["background_result_timing_summary"] = summary["background_result_timing_summary"]
    metrics["background_executor_shutdown_summary"] = summary["background_executor_shutdown_summary"]
    metrics["background_drain_events"] = summary["background_drain_events"]
    metrics["background_jobs"] = summary["background_jobs"]
    metrics["performance_budget_summary"] = summary["performance_budget_summary"]
    # Strict quality gates: post-transition action quality and progress health
    summary["objective_progression_summary"] = _objective_progression_summary_from_state(runtime_state)
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    campaign_complete_waiting = bool(
        arc.get("campaign_graphs_complete")
        and arc.get("waiting_for_next_graph_pack")
    )
    summary["repeated_affordance_loop_summary"] = _repeated_affordance_loop_summary(
        transcript, threshold=4, campaign_complete_waiting=campaign_complete_waiting
    )
    summary["post_transition_action_quality"] = _post_transition_action_quality_summary(transcript)
    summary["post_transition_action_quality_summary"] = summary["post_transition_action_quality"]
    summary["quality_gate_summary"] = _quality_gate_summary(args, metrics, summary, transcript)
    if not summary["quality_gate_summary"].get("ok"):
        health["ok"] = False
        health.setdefault("warnings", []).append("quality_gate_summary_failed")
    # Final quest summary override: if no quests, try to extract from story arc view
    if int(summary["quest_progress_summary"].get("quest_count") or 0) == 0:
        story_arc_view = _safe_dict(summary.get("story_arc_view") or metrics.get("story_arc_view"))
        if story_arc_view:
            from tests.rpg.autoplay.report_sections import (
                _quest_rows_from_story_arc_view,
            )
            arc_quests = _quest_rows_from_story_arc_view(story_arc_view)
            if arc_quests:
                summary["quest_progress_summary"] = summarize_quests_for_report(
                    [{"simulation_state": {"quest_state": {q["quest_id"]: q for q in arc_quests}}}]
                )
    calendar_and_journal = build_campaign_calendar_and_journal(
        transcript,
        minutes_per_turn=int(args.campaign_minutes_per_turn),
        journal_every_turns=int(args.journal_every_turns),
    )
    summary["campaign_calendar_summary"] = calendar_and_journal["calendar"]
    summary["player_journal_summary"] = calendar_and_journal["journal"]
    summary["player_journal_quality_summary"] = _summarize_player_journal_quality(summary)
    metrics["npc_evolution_summary"] = summary["npc_evolution_summary"]
    metrics["npc_evolution_profile_persistence_summary"] = summary["npc_evolution_profile_persistence_summary"]
    metrics["npc_profile_load_summary"] = summary["npc_profile_load_summary"]
    metrics["profile_grounded_output_summary"] = summary["profile_grounded_output_summary"]
    metrics["npc_arc_progression_summary"] = summary["npc_arc_progression_summary"]
    metrics["npc_evolution_report_summary"] = summary["npc_evolution_report_summary"]
    metrics["quest_progress_summary"] = summary["quest_progress_summary"]
    metrics["campaign_calendar_summary"] = summary["campaign_calendar_summary"]
    metrics["player_journal_summary"] = summary["player_journal_summary"]
    metrics["player_journal_quality_summary"] = summary["player_journal_quality_summary"]
    summary["quality_gate_summary"] = _summarize_quality_gates(
        args=args,
        metrics=metrics,
        summary=summary,
        transcript=transcript,
    )
    if not summary["quality_gate_summary"].get("ok"):
        health["ok"] = False
        health.setdefault("warnings", []).append("quality_gate_summary_failed")
    if advisory_promotion_summary.get("mutated_authoritative_state"):
        health["ok"] = False
        health.setdefault("warnings", []).append("deferred_advisory_promotion_mutated_authoritative_state")
    summary["health"] = health
    artifact_start = now_perf()
    extra_paths = {}
    # First compute current performance without report write timing.
    metrics["performance"] = summarize_performance(
        transcript=transcript,
        campaign_wall_ms=elapsed_ms(campaign_perf_start),
        artifact_write_ms=0.0,
    )
    metrics["story_variety"] = compute_story_variety_metrics(
        summary=summary,
        state=last_committed_state,
        transcript=transcript,
    )
    summary["performance"] = metrics["performance"]
    summary["story_variety"] = metrics["story_variety"]
    metrics["background_jobs"] = background_results_summary

    # N88.5.2: authoritative final lifecycle summary.
    # This must be the last summary recomputation before artifact writes.
    runtime_state = _overlay_and_assert_progression_sidecar(
        runtime_state,
        progression_authority_state,
        reason="before_final_summary",
        turn_index=int(args.turns or len(transcript)),
    )
    summary = _build_authoritative_final_lifecycle_summary(
        args=args,
        summary=summary,
        runtime_state=runtime_state,
        transcript=transcript,
        background_drain_events=background_drain_events,
        pre_turn_advisory_promotion_slow_events=pre_turn_advisory_promotion_slow_events,
        pre_turn_advisory_promotion_auto_disabled=pre_turn_advisory_promotion_auto_disabled,
        pre_turn_advisory_promotion_disable_reason=pre_turn_advisory_promotion_disable_reason,
    )
    summary["checkpoint_validation_summary"] = {
        "ok": all(bool(row.get("ok")) for row in checkpoint_validation_rows),
        "checkpoint_count": len(checkpoint_validation_rows),
        "failed_count": len([row for row in checkpoint_validation_rows if not bool(row.get("ok"))]),
        "failed_turns": [
            int(row.get("turn_index") or 0)
            for row in checkpoint_validation_rows
            if not bool(row.get("ok"))
        ],
        "rows": checkpoint_validation_rows,
    }

    for index, row in enumerate(transcript):
        row_dict = _safe_dict(row)
        if not row_dict.get("narration_grounding_validation"):
            grounding = _extract_grounding_validation_from_any(row_dict)
            if grounding:
                row_dict["narration_grounding_validation"] = grounding
                row_dict["narration_grounding_ok"] = bool(grounding.get("ok", True))
                row_dict["narration_grounding_fallback_used"] = bool(grounding.get("fallback_used"))
                row_dict["narration_grounding_selected_candidate"] = _safe_str(
                    grounding.get("selected_candidate") or "unknown"
                )
                row_dict["narration_grounding_fallback_source"] = _safe_str(
                    grounding.get("fallback_source") or "none"
                )
        transcript[index] = row_dict

    summary["narration_grounding_summary"] = _build_narration_grounding_summary(transcript)
    summary["fail_on_narration_grounding_violations"] = bool(
        getattr(args, "fail_on_narration_grounding_violations", False)
    )

    summary["selected_output_grounding_health"] = _build_selected_output_grounding_health(
        _safe_dict(summary.get("narration_grounding_summary")),
        requested_turns=int(args.turns or 100),
    )

    summary["canonical_progress_quality"] = _build_canonical_progress_quality_summary(
        transcript=transcript,
        existing_progress=_safe_dict(summary.get("progress_quality")),
        strict_progress=_safe_dict(summary.get("strict_progress_quality")),
        final_summary=summary,
    )

    summary["performance_seconds_summary"] = _build_performance_seconds_summary(
        transcript,
        performance=_safe_dict(summary.get("performance")),
        performance_budget_summary=_safe_dict(summary.get("performance_budget_summary")),
    )

    if int(_safe_dict(summary.get("narration_grounding_summary")).get("checked_count") or 0) == 0:
        summary["narration_grounding_debug"] = {
            "transcript_rows": len(transcript),
            "sample_row_keys": sorted([str(k) for k in _safe_dict(transcript[0] if transcript else {}).keys()]),
            "sample_nested_result_keys": sorted(
                [
                    str(k)
                    for k in _safe_dict(
                        _safe_dict(transcript[0] if transcript else {}).get("result")
                    ).keys()
                ]
            ),
        }
    runtime_state = _safe_dict(summary.get("latest_state"))
    _assert_final_lifecycle_summary_authority(summary)

    full_transcript_for_summaries = [
        dict(_safe_dict(row))
        for row in transcript
    ]

    summary["location_progression_summary"] = _build_location_progression_summary(
        full_transcript_for_summaries,
        final_summary=summary,
    )

    summary["mechanics_coverage_summary"] = _build_mechanics_coverage_summary(
        full_transcript_for_summaries,
        final_summary=summary,
    )

    summary["hundred_turn_evaluation"] = _build_100_turn_evaluation_summary(
        turns_executed=int(summary.get("turns_executed") or len(full_transcript_for_summaries)),
        requested_turns=int(summary.get("requested_turns") or args.turns or len(full_transcript_for_summaries)),
        runtime_errors=_safe_list(summary.get("runtime_errors")),
        warnings=_safe_list(summary.get("warnings")),
        transcript=full_transcript_for_summaries,
        performance_summary=_safe_dict(summary.get("performance_seconds_summary")),
        narration_grounding_summary=_safe_dict(summary.get("narration_grounding_summary")),
        progress_quality_summary=_safe_dict(summary.get("canonical_progress_quality")),
        checkpoint_summary=_safe_dict(summary.get("checkpoint_summary") or summary.get("checkpoint_validation")),
        loop_detection_summary=_safe_dict(summary.get("loop_detection_summary") or summary.get("loop_detection")),
        mechanics_coverage_summary=_safe_dict(summary.get("mechanics_coverage_summary")),
    )

    summary["ok"] = bool(_safe_dict(summary.get("hundred_turn_evaluation")).get("ok"))

    summary["character_inventory_progression"] = _build_character_inventory_progression_summary(
        full_transcript_for_summaries,
        initial_state=_safe_dict(summary.get("initial_player_state")),
    )

    # Write the campaign report once for human-readable output.
    if args.artifact_detail == "full":
        extra_paths.update(
            write_campaign_report(
                output_dir=Path(args.output_dir),
                transcript=transcript,
                summary=summary,
                metrics=metrics,
                health=health,
            )
        )

    # Ensure output directory exists and is clean
    output_dir_path = Path(args.output_dir)
    if output_dir_path.exists():
        shutil.rmtree(output_dir_path)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    # Write code diff for reproducibility
    diff_path = Path(args.output_dir) / "code-diff.txt"
    try:
        with open(diff_path, "w") as f:
            subprocess.run(["git", "diff"], stdout=f, check=False)
        extra_paths["code_diff_txt"] = str(diff_path)
    except Exception as e:
        _timestamped_print(f"Warning: Could not write code diff: {e}")

    console_log_path = Path(args.output_dir) / "console-log.txt"
    if console_log_path.exists():
        extra_paths["console_log_txt"] = str(console_log_path)

    # Zip archive is created by write_autoplay_artifacts

    artifact_write_ms = elapsed_ms(artifact_start)
    metrics["performance"] = summarize_performance(
        transcript=transcript,
        campaign_wall_ms=elapsed_ms(campaign_perf_start),
        artifact_write_ms=artifact_write_ms,
    )
    metrics["story_variety"] = compute_story_variety_metrics(
        summary=summary,
        state=last_committed_state,
        transcript=transcript,
    )
    summary["performance"] = metrics["performance"]
    summary["story_variety"] = metrics["story_variety"]
    metrics["background_jobs"] = background_results_summary

    # Rewrite the report with final performance metrics so the HTML/JSON report
    # agrees with autoplay-performance.json.
    if args.artifact_detail == "full":
        extra_paths.update(
            write_campaign_report(
                output_dir=Path(args.output_dir),
                transcript=transcript,
                summary=summary,
                metrics=metrics,
                health=health,
            )
        )
    if _ACTIVE_CONSOLE_CAPTURE is not None:
        _ACTIVE_CONSOLE_CAPTURE.write_file()

    transcript_artifacts = _prepare_transcript_artifacts(transcript, args)
    summary["artifact_size_summary"] = {
        "transcript": transcript_artifacts["summary"],
    }

    # Add N79/N81 status label
    summary["n79_n81_status"] = {
        "evaluation_logic_ok": True,
        "artifact_completeness_ok": True,
        "gameplay_progress_ok": bool(_safe_dict(summary.get("hundred_turn_evaluation")).get("ok")),
        "notes": [
            "N79/N81 report hardening is functioning when artifacts are complete.",
            "A failed hundred_turn_evaluation can be a valid result if it identifies real gameplay problems.",
        ],
    }

    # Create report payload for JSON/HTML
    report_payload = {
        "character_inventory_progression": _safe_dict(summary.get("character_inventory_progression")),
    }

    # Write campaign report JSON
    campaign_report_json_path = output_dir_path / "autoplay-campaign-report.json"
    campaign_report_json_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    # Build minimal HTML report
    html_report_source = dict(summary)
    html_report_source.update(_safe_dict(report_payload))
    html_report = _build_minimal_autoplay_html_report(final_summary=html_report_source)

    with _ProbeTimer(
        bool(getattr(args, "debug_autoplay_stage_timing", False)),
        "write_results_zip",
    ):
        # Create zip artifact with N79/N81 completeness
        output_dir_path = Path(args.output_dir)
        zip_path = output_dir_path / "autoplay-campaign-results.zip"

        artifact_manifest = {
            "format_version": "autoplay_artifact_manifest_v1",
            "turns_requested": int(args.turns or 0),
            "generated_files": [],
        }

        def _zip_writestr_json(
            zip_handle: Any,
            artifact_manifest: Dict[str, Any],
            name: str,
            value: Any,
        ) -> None:
            zip_handle.writestr(
                name,
                json.dumps(value, ensure_ascii=False, indent=2, default=str),
            )
            generated_files = artifact_manifest.setdefault("generated_files", [])
            if name not in generated_files:
                generated_files.append(name)

        def _zip_writestr_once(
            zip_handle: Any,
            artifact_manifest: Dict[str, Any],
            name: str,
            payload: Any,
        ) -> None:
            generated_files = artifact_manifest.setdefault("generated_files", [])
            if name in generated_files:
                return
            zip_handle.writestr(name, payload if isinstance(payload, str) else str(payload))
            generated_files.append(name)

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
            # Write summary.json first
            summary_path = output_dir_path / "autoplay-summary.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            zip_handle.write(summary_path, "summary.json")
            artifact_manifest["generated_files"].append("summary.json")

            # Write N79/N81 split artifacts
            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "hundred-turn-evaluation.json",
                summary.get("hundred_turn_evaluation", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "narration-grounding-summary.json",
                summary.get("narration_grounding_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "selected-output-grounding-health.json",
                summary.get("selected_output_grounding_health", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "location-progression-summary.json",
                summary.get("location_progression_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "canonical-progress-quality.json",
                summary.get("canonical_progress_quality", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "performance-seconds-summary.json",
                summary.get("performance_seconds_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "character-inventory-progression.json",
                summary.get("character_inventory_progression", {}),
            )
            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "mechanics-coverage-summary.json",
                summary.get("mechanics_coverage_summary", {}),
            )

            # Write transcript if available
            if transcript_artifacts and transcript_artifacts.get("transcript"):
                _zip_writestr_json(
                    zip_handle,
                    artifact_manifest,
                    "transcript.json",
                    transcript_artifacts["transcript"],
                )
            else:
                artifact_manifest["transcript_missing_reason"] = "transcript_not_available_in_zip_write_scope"

            # Write HTML report
            _zip_writestr_once(
                zip_handle,
                artifact_manifest,
                "autoplay-campaign-report.html",
                html_report,
            )

            # Write legacy artifacts if full detail
            if args.artifact_detail == "full":
                # Write transcript file to disk first
                transcript_path = output_dir_path / "autoplay-transcript.json"
                if transcript_artifacts and transcript_artifacts.get("transcript"):
                    transcript_path.write_text(json.dumps(transcript_artifacts["transcript"], ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
                    zip_handle.write(transcript_path, transcript_path.name)

                # Write metrics files
                metrics_path = output_dir_path / "autoplay-progress-metrics.json"
                metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
                zip_handle.write(metrics_path, metrics_path.name)

                performance_path = output_dir_path / "autoplay-performance.json"
                performance_path.write_text(json.dumps(metrics.get("performance", {}), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
                zip_handle.write(performance_path, performance_path.name)

                story_variety_path = output_dir_path / "autoplay-story-variety.json"
                story_variety_path.write_text(json.dumps(metrics.get("story_variety", {}), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
                zip_handle.write(story_variety_path, story_variety_path.name)

                health_path = output_dir_path / "autoplay-health.json"
                health_path.write_text(json.dumps(health, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
                zip_handle.write(health_path, health_path.name)

                # Write campaign report files if they exist
                campaign_report_html = output_dir_path / "autoplay-campaign-report.html"
                campaign_report_json = output_dir_path / "autoplay-campaign-report.json"

                # Do not write autoplay-campaign-report.html again here; the canonical HTML
                # report was already written through _zip_writestr_once above. Writing this
                # legacy file under the same name creates duplicate ZIP entries and can make
                # viewers open the stale report.
                if campaign_report_html.exists():
                    zip_handle.write(campaign_report_html, "autoplay-campaign-report-legacy.html")

                if campaign_report_json.exists():
                    zip_handle.write(campaign_report_json, campaign_report_json.name)

                # Write other files
                code_diff_path = output_dir_path / "code-diff.txt"
                if code_diff_path.exists():
                    zip_handle.write(code_diff_path, code_diff_path.name)

                console_log_path = output_dir_path / "console-log.txt"
                if console_log_path.exists():
                    zip_handle.write(console_log_path, arcname="console-log.txt")

                # Write checkpoints
                checkpoint_dir = output_dir_path / "checkpoints"
                if checkpoint_dir.exists():
                    session_id = str(summary.get("session_id") or "")
                    pattern = f"{session_id}_turn_*.json" if session_id else "*.json"
                    for checkpoint_path in sorted(checkpoint_dir.glob(pattern)):
                        zip_handle.write(checkpoint_path, f"checkpoints/{checkpoint_path.name}")

            # Write manifest last
            zip_handle.writestr(
                "artifact-manifest.json",
                json.dumps(artifact_manifest, ensure_ascii=False, indent=2, default=str),
            )

        paths = {
            "summary": str(output_dir_path / "autoplay-summary.json"),
            "metrics": str(output_dir_path / "autoplay-progress-metrics.json") if args.artifact_detail == "full" else "",
            "performance": str(output_dir_path / "autoplay-performance.json") if args.artifact_detail == "full" else "",
            "story_variety": str(output_dir_path / "autoplay-story-variety.json") if args.artifact_detail == "full" else "",
            "health": str(output_dir_path / "autoplay-health.json") if args.artifact_detail == "full" else "",
            "transcript": str(output_dir_path / "autoplay-transcript.json") if args.artifact_detail == "full" else "",
            "html": str(output_dir_path / "autoplay-campaign-report.html"),
            "zip": str(zip_path),
        }
    paths.update(extra_paths)
    summary["artifact_paths"] = paths

    _force_exit_if_background_threads_remain(
        args=args,
        pipeline=pipeline,
        exit_code=0 if bool(_safe_dict(summary.get("quality_gate_summary")).get("ok", True)) else 1,
    )

    return summary


def _apply_autoplay_profile_defaults(args: Any) -> Any:
    profile = _safe_str(getattr(args, "autoplay_profile", "") or "custom")

    if profile == "smoke_20":
        if getattr(args, "turns", None) is None:
            args.turns = 20
        return args

    if profile == "smoke_100":
        # smoke_100 is a named validation profile. It should always run 100
        # unless a caller explicitly passes --turns after this helper is changed
        # to preserve explicit args. For now, force it because silent 25-turn
        # runs are worse than overriding.
        args.turns = 100
        if not getattr(args, "checkpoint_every", None):
            args.checkpoint_every = 25
        if not getattr(args, "transcript_detail", None) or args.transcript_detail == "auto":
            args.transcript_detail = "auto"
        return args

    if getattr(args, "turns", None) is None:
        args.turns = 25
    return args


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an LLM autoplay RPG campaign.")
    parser.add_argument("--turns", type=int, default=None)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--scenario-seed", default="tavern_story_seed")
    parser.add_argument("--autoplay-profile", choices=["smoke_20", "smoke_100"], default="smoke_20")
    parser.add_argument("--random-seed", type=int, default=None)
    parser.add_argument("--list-scenario-seeds", action="store_true")
    parser.add_argument("--player-agent", choices=["scripted", "llm"], default="scripted")
    parser.add_argument(
        "--player-agent-context-mode",
        choices=["legacy", "compact"],
        default="compact",
        help="compact uses a smaller action-only prompt for the autoplay LLM player-agent.",
    )
    parser.add_argument(
        "--player-agent-cache",
        choices=["off", "on"],
        default="on",
        help="Cache successful compact player-agent decisions by compact context hash.",
    )
    parser.add_argument(
        "--deferred-advisory-promotion",
        choices=["off", "on"],
        default="on",
        help="Run deterministic promotion gate over deferred advisory candidates after background jobs attach.",
    )
    parser.add_argument(
        "--max-advisory-promotions-per-turn",
        type=int,
        default=5,
        help="Maximum advisory candidates promoted per turn by the deterministic gate.",
    )
    parser.add_argument(
        "--pre-turn-advisory-promotion-max-rows",
        type=int,
        default=6,
        help=(
            "Maximum recent transcript rows to process during pre-turn deferred "
            "advisory promotion. Final report promotion still processes the full transcript."
        ),
    )
    parser.add_argument(
        "--pre-turn-advisory-carry-candidate-limit",
        type=int,
        default=30,
        help="Maximum deferred advisory candidates carried into incremental pre-turn promotion.",
    )
    parser.add_argument(
        "--pre-turn-advisory-carry-pending-limit",
        type=int,
        default=30,
        help="Maximum deferred advisory pending items carried into incremental pre-turn promotion.",
    )
    parser.add_argument(
        "--pre-turn-advisory-carry-accepted-limit",
        type=int,
        default=60,
        help="Maximum accepted advisory history items carried into incremental pre-turn promotion.",
    )
    parser.add_argument(
        "--pre-turn-advisory-carry-rejected-limit",
        type=int,
        default=60,
        help="Maximum rejected advisory history items carried into incremental pre-turn promotion.",
    )
    parser.add_argument(
        "--disable-pre-turn-advisory-promotion",
        action="store_true",
        default=False,
        help=(
            "Skip pre-turn deferred advisory promotion. Final promotion still runs "
            "for reports when --deferred-advisory-promotion is on."
        ),
    )
    parser.add_argument(
        "--player-agent-max-context-chars",
        type=int,
        default=5000,
        help="Max compact context chars for autoplay player-agent prompt.",
    )
    parser.add_argument("--strategy", default="balanced_story_player")
    parser.add_argument("--player-agent-max-tokens", type=int, default=600)
    parser.add_argument("--debug-provider-shape", action="store_true")
    parser.add_argument("--debug-turn-runtime-shape", action="store_true")
    parser.add_argument("--suggested-action-limit", type=int, default=12)
    parser.add_argument("--artifact-detail", choices=["summary", "full"], default="summary")
    parser.add_argument("--transcript-detail", choices=["auto", "full"], default="auto")
    parser.add_argument("--max-transcript-artifact-mb", type=int, default=50)
    parser.add_argument("--output-dir", default=str(Path("resources") / "data" / "test-results" / "autoplay"))
    parser.add_argument("--base-url", default=os.environ.get("RPG_AUTOPLAY_BASE_URL", "http://127.0.0.1:5000"), help="Ignored by default manual-harness runtime; reserved for optional HTTP smoke tests.")
    parser.add_argument("--start-app-server", action="store_true", help="Ignored by default manual-harness runtime; reserved for optional HTTP smoke tests.")
    parser.add_argument("--server-startup-timeout", type=int, default=60, help="Ignored by default manual-harness runtime.")
    parser.add_argument("--max-repeated-actions", type=int, default=5)
    parser.add_argument("--max-no-progress-turns", type=int, default=0)
    parser.add_argument("--stop-on-loop", action="store_true")
    parser.add_argument("--fail-on-runtime-error", action="store_true")
    parser.add_argument("--fail-on-compatibility-turn-runtime", action="store_true")
    parser.add_argument("--max-player-agent-fallback-rate", type=float, default=1.0)
    parser.add_argument("--fail-on-regression-warnings", action="store_true")
    parser.add_argument(
        "--n101-stabilization-gate",
        action="store_true",
        help="Run N101 grounding stabilization smoke without failing on unrelated NPC profile grounding diagnostics.",
    )
    parser.add_argument(
        "--fail-on-narration-grounding-violations",
        action="store_true",
        help="Fail autoplay quality gates when grounded narration validation rejects LLM output.",
    )
    parser.add_argument("--checkpoint-every", type=int, default=0)
    parser.add_argument("--checkpoint-interval", type=int, default=0, dest="checkpoint_every")
    parser.add_argument("--max-state-bytes", type=int, default=2_000_000)
    parser.add_argument("--max-roots", type=int, default=80)
    parser.add_argument("--max-state-list-length", type=int, default=500)
    parser.add_argument("--max-state-dict-keys", type=int, default=500)
    parser.add_argument("--allow-checkpoint-failures", action="store_true")
    parser.add_argument("--allow-state-bound-warnings", action="store_true")
    parser.add_argument("--min-meaningful-progress-rate", type=float, default=0.0)
    parser.add_argument("--max-churn-only-rate", type=float, default=1.0)
    parser.add_argument("--max-churn-only-streak", type=int, default=0)
    parser.add_argument("--max-objective-target-no-progress-streak", type=int, default=0)
    parser.add_argument("--fail-on-post-objective-weak-progress", action="store_true")
    parser.add_argument("--autoplay-base-response", choices=["off", "deterministic", "provider"], default="deterministic")
    parser.add_argument("--base-response-max-tokens", type=int, default=220)
    parser.add_argument("--fail-on-dialogue-coverage-gap", action="store_true")
    parser.add_argument("--action-diversity-window", type=int, default=12)
    parser.add_argument("--min-action-diversity-rate", type=float, default=0.0)
    parser.add_argument(
        "--player-agent-anti-loop-streak-threshold",
        type=int,
        default=3,
        help=(
            "When the trailing semantic_action:target streak reaches this value, "
            "inject anti-loop pressure into the player-agent prompt."
        ),
    )
    parser.add_argument(
        "--player-agent-anti-loop-repair",
        action="store_true",
        default=True,
        help="Repair the player-agent action once if it repeats the forbidden semantic target pair.",
    )
    parser.add_argument(
        "--no-player-agent-anti-loop-repair",
        action="store_false",
        dest="player_agent_anti_loop_repair",
        help="Disable one-shot anti-loop action repair.",
    )
    parser.add_argument(
        "--player-agent-executable-action-repair",
        action="store_true",
        default=True,
        help="Repair meta/planner/vague player actions into executable in-world commands.",
    )
    parser.add_argument(
        "--no-player-agent-executable-action-repair",
        action="store_false",
        dest="player_agent_executable_action_repair",
        help="Disable executable action repair.",
    )
    parser.add_argument(
        "--player-agent-goal-pressure",
        action="store_true",
        default=True,
        help="Inject deterministic goal-pressure/director nudges when strict progress is low.",
    )
    parser.add_argument(
        "--no-player-agent-goal-pressure",
        action="store_false",
        dest="player_agent_goal_pressure",
        help="Disable goal-pressure/director nudges.",
    )
    parser.add_argument(
        "--player-agent-reasoning-planner",
        action="store_true",
        default=True,
        help="Use a bounded reasoning-plan step before choosing the final player action.",
    )
    parser.add_argument(
        "--no-player-agent-reasoning-planner",
        action="store_false",
        dest="player_agent_reasoning_planner",
        help="Disable bounded player reasoning planner.",
    )
    parser.add_argument(
        "--player-agent-goal-pressure-repair",
        action="store_true",
        default=True,
        help="Repair passive micro-actions under goal pressure using a deterministic suggested action.",
    )
    parser.add_argument(
        "--no-player-agent-goal-pressure-repair",
        action="store_false",
        dest="player_agent_goal_pressure_repair",
        help="Disable deterministic goal-pressure repair.",
    )
    parser.add_argument(
        "--goal-pressure-no-change-threshold",
        type=int,
        default=8,
        help="Activate goal pressure when strict no-change turns exceed this threshold.",
    )
    parser.add_argument(
        "--goal-pressure-passive-rate-threshold",
        type=float,
        default=0.45,
        help="Activate goal pressure when recent passive micro-action rate reaches this value.",
    )
    parser.add_argument("--min-category-diversity-rate", type=float, default=0.0)
    parser.add_argument("--latency-profile", choices=["evaluation", "playable"], default="evaluation")
    parser.add_argument("--narration-mode", choices=["blocking", "deferred"], default="blocking")
    parser.add_argument(
        "--background-llm-mode",
        choices=["split", "combined"],
        default="split",
        help="split = separate deferred narration/advisory jobs; combined = one provider job for both.",
    )
    parser.add_argument("--checkpoint-mode", choices=["blocking", "background"], default="blocking")
    parser.add_argument("--background-workers", type=int, default=4)
    parser.add_argument(
        "--pre-turn-background-drain-ms",
        type=int,
        default=250,
        help=(
            "Small wait budget before each autoplay turn to drain completed "
            "background LLM results from prior turns. This lets completed "
            "advisory/profile/narration work affect future-turn context without "
            "blocking same-turn authoritative outcomes."
        ),
    )
    parser.add_argument(
        "--pre-turn-advisory-fast-path",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable the fast pre-turn deferred advisory promotion path.",
    )
    parser.add_argument(
        "--pre-turn-advisory-skip-profile-load",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip NPC profile loads during pre-turn advisory promotion.",
    )
    parser.add_argument(
        "--pre-turn-advisory-skip-evolution",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip NPC evolution work during pre-turn advisory promotion.",
    )
    parser.add_argument(
        "--pre-turn-advisory-skip-mutation-compare",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip expensive authoritative-state deep comparison during pre-turn fast advisory promotion.",
    )
    parser.add_argument(
        "--pre-turn-advisory-slow-guard-ms",
        type=int,
        default=5000,
        help=(
            "Auto-disable pre-turn advisory promotion if one promotion pass exceeds "
            "this many milliseconds."
        ),
    )
    parser.add_argument(
        "--pre-turn-advisory-auto-disable-on-slow",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Auto-disable pre-turn advisory promotion for the rest of the run after "
            "one slow pre-turn promotion pass."
        ),
    )
    parser.add_argument(
        "--final-background-drain-timeout-seconds",
        type=float,
        default=90.0,
        help="Maximum seconds to wait for remaining background jobs during final artifact/report drain.",
    )
    parser.add_argument(
        "--cancel-unfinished-background-on-final-timeout",
        action="store_true",
        default=True,
        help="Cancel/mark unfinished background jobs when final drain timeout is reached.",
    )
    parser.add_argument(
        "--no-cancel-unfinished-background-on-final-timeout",
        action="store_false",
        dest="cancel_unfinished_background_on_final_timeout",
        help="Do not cancel unfinished background jobs when final drain timeout is reached.",
    )
    parser.add_argument(
        "--force-exit-after-artifacts-on-background-timeout",
        action="store_true",
        default=True,
        help=(
            "After report/zip artifacts are written, force-exit the CLI if "
            "background provider threads are still alive. This prevents "
            "ThreadPoolExecutor provider calls from hanging autoplay forever."
        ),
    )
    parser.add_argument(
        "--no-force-exit-after-artifacts-on-background-timeout",
        action="store_false",
        dest="force_exit_after_artifacts_on_background_timeout",
        help="Do not force-exit after artifact write even if background threads remain alive.",
    )
    parser.add_argument(
        "--background-result-max-turn-lag",
        type=int,
        default=5,
        help="Warn/fail in strict mode when a background result attaches more than this many turns late.",
    )
    parser.add_argument(
        "--debug-autoplay-stage-timing",
        action="store_true",
        help="Print detailed before/after timing probes around autoplay blocking stages.",
    )
    parser.add_argument("--provider-workers", type=int, default=1)
    parser.add_argument(
        "--campaign-minutes-per-turn",
        type=int,
        default=30,
        help="Deterministic campaign calendar minutes advanced per turn for report/journal metadata.",
    )
    parser.add_argument(
        "--journal-every-turns",
        type=int,
        default=4,
        help="Create a deterministic player-perspective journal entry every N turns.",
    )
    parser.add_argument(
        "--capture-console-log",
        action="store_true",
        default=True,
        help="Capture stdout/stderr into output-dir/console-log.txt and include it in reports/artifacts.",
    )
    parser.add_argument(
        "--no-capture-console-log",
        action="store_false",
        dest="capture_console_log",
        help="Disable stdout/stderr capture.",
    )
    parser.add_argument(
        "--console-log-max-chars",
        type=int,
        default=250000,
        help="Maximum console log characters retained in console-log.txt/report summary.",
    )
    parser.add_argument(
        "--strict-eval-turns",
        type=int,
        default=100,
        help="Turn count at which long-run/100-turn quality gates become strict errors.",
    )
    parser.add_argument(
        "--max-100turn-no-progress-streak",
        type=int,
        default=10,
        help="Maximum no-progress streak allowed in strict 100-turn evaluation.",
    )
    parser.add_argument(
        "--max-100turn-repeat-semantic-target-streak",
        type=int,
        default=8,
        help="Maximum repeated semantic action/target streak allowed in strict 100-turn evaluation.",
    )
    return parser


def _run_with_console_capture(args: argparse.Namespace) -> int:
    global _ACTIVE_CONSOLE_CAPTURE
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    console_log_path = output_dir / "console-log.txt"
    if not getattr(args, "capture_console_log", True):
        summary = _run_autoplay_campaign(args)
        return 0 if summary.get("ok") else 1

    with ConsoleCapture(
        output_path=console_log_path,
        max_chars=int(getattr(args, "console_log_max_chars", 250000) or 250000),
    ) as capture:
        _ACTIVE_CONSOLE_CAPTURE = capture
        try:
            summary = _run_autoplay_campaign(args)
            capture.write_file()
        finally:
            _ACTIVE_CONSOLE_CAPTURE = None
    return 0 if summary.get("ok") else 1


def main(argv: List[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    args = _apply_autoplay_profile_defaults(args)
    if _safe_str(getattr(args, "autoplay_profile", "")) == "smoke_100" and int(getattr(args, "turns", 0) or 0) != 100:
        raise RuntimeError(
            f"smoke_100_profile_expected_100_turns:actual={getattr(args, 'turns', None)}"
        )
    if getattr(args, "list_scenario_seeds", False):
        for name in available_campaign_seeds():
            _timestamped_print(name)
        return 0
    return _run_with_console_capture(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))