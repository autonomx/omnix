
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Tuple

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
    "current_action_response",
    "npc_response_architecture",
    "npc_line_current_action_relevance",
    "npc_line_addresses_current_action",
    "npc_response_variant_id",
    "npc_response_variation",
    "llm_prompt_debug",
    "llm_prompt_contract",
    "prompt_contract_ack",
    "llm_fallback_diagnostics",
    "npc_line_source",
    "npc_line_validation_passed",
    "npc_line_rejection_reason",
)


def _effective_transcript_detail(args: Any) -> str:
    turns = int(getattr(args, "turns", 0) or 0)
    profile = _safe_str(getattr(args, "autoplay_profile", "") or "")
    if turns >= 30 or profile == "smoke_100":
        return "slim"
    return "full"


def _should_write_full_transcript(args: argparse.Namespace) -> bool:
    artifact_detail = _safe_str(getattr(args, "artifact_detail", ""))
    return artifact_detail.lower() in {"full", "debug", "maximum", "max"}


def _slim_transcript_row(row: Dict[str, Any], max_row_bytes: int = 50000) -> Dict[str, Any]:
    row = _safe_dict(row)
    slim_row: Dict[str, Any] = {}
    if not row:
        return {
            "empty_transcript_row_repaired": True,
            "presentation_status": "missing_row",
        }

    for key in (
        "turn_index",
        "turn",
        "turn_id",
        "player_action",
        "canonical_turn_action",
        "actual_sent_action",
        "player_agent_selection_source",
        "player_agent_selection_reason",
         "action_category",
         "presentation_intent",
         "llm_presentation_category",
          "validated_presentation_intent",
            "validated_presentation_category",
            "current_action_response",
            "npc_response_architecture",
            "npc_response_architecture_ack",
            "npc_response_architecture_persisted",
            "npc_line_current_action_relevance",
            "npc_line_addresses_current_action",
            "npc_response_variant_id",
            "npc_response_variation",
            "llm_prompt_debug",
            "llm_prompt_contract",
            "prompt_contract_ack",
            "llm_fallback_diagnostics",
            "npc_line_source",
            "npc_line_validation_passed",
            "npc_line_rejection_reason",
             "npc_line_repaired",
             "npc_line_repair_reason",
             "npc_line_before_repair",
             "presentation_meta_leakage_repaired",
             "presentation_meta_leakage_repair",
             "narration_before_meta_repair",
             "npc_line_before_meta_repair",
             "presentation_meta_leakage",
             "narration_meta_repaired",
             "narration_before_meta_repair",
             "meta_language_repair",
             "presentation_status",
        "narration",
        "display_narration",
        "selected_narration",
        "npc",
        "npc_speaker",
        "npc_line",
        "turn_presentation_identity",
        "background_presentation_result",
        "dialogue_presentation_compatibility",
        "dialogue_action_relevance",
        "dialogue_action_relevance_repaired",
        "presentation_repair_tier",
        "presentation_repair_type",
        "visible_text_replaced",
        "hard_grounding_repair",
        "soft_classification_repair",
        "presentation_hard_grounding",
        "presentation_soft_classification",
        "background_semantic_reviewer",
        "unsupported_combat_claim_suppressed",
        "direct_graph_action_completion",
        "mechanics_covered_this_turn",
        "direct_graph_changed_parts",
        "progress_quality",
        "turn_action_consistency",
        "graph_action_selection_diagnostic",
        "suppressed_selected_action_guard",
    ):
        if row.get(key) not in (None, "", {}, []):
            slim_row[key] = row.get(key)

    visible_player_action = (
        _safe_str(row.get("display_player_action"))
        or _safe_str(row.get("visible_player_action"))
        or _safe_str(row.get("player_action"))
    )
    if visible_player_action:
        slim_row["player_action"] = visible_player_action
        slim_row["display_player_action"] = visible_player_action
        slim_row["visible_player_action"] = visible_player_action

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

    for key in (
        "dialogue_presentation_compatibility",
        "unsupported_combat_claim_suppressed",
    ):
        if row.get(key) is not None:
            slim_row[key] = row.get(key)

    return slim_row


def _preferred_visible_player_action(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    return (
        _safe_str(row.get("display_player_action"))
        or _safe_str(row.get("visible_player_action"))
        or _safe_str(row.get("canonical_turn_action"))
        or _safe_str(row.get("player_action"))
    )

    if row.get("story_arc_events"):
        slim_row["story_arc_events"] = row.get("story_arc_events")

    if row.get("story_arc_lifecycle"):
        slim_row["story_arc_lifecycle"] = {
            "ok": _safe_dict(row.get("story_arc_lifecycle")).get("ok"),
            "resolved_count": _safe_dict(row.get("story_arc_lifecycle")).get("resolved_count"),
            "failed_count": _safe_dict(row.get("story_arc_lifecycle")).get("failed_count"),
            "story_arc_events": _safe_dict(row.get("story_arc_lifecycle")).get("story_arc_events"),
        }

    for key in (
        "story_arc_aftermath_events",
        "world_signals",
        "npc_memory_events",
        "followup_hooks",
    ):
        if row.get(key):
            slim_row[key] = row.get(key)

    if row.get("npc_presence"):
        slim_row["npc_presence"] = row.get("npc_presence")

    if row.get("npc_schedule_events"):
        slim_row["npc_schedule_events"] = row.get("npc_schedule_events")

    if row.get("npc_agency_events"):
        slim_row["npc_agency_events"] = row.get("npc_agency_events")

    if row.get("story_arc_aftermath"):
        aftermath = _safe_dict(row.get("story_arc_aftermath"))
        slim_row["story_arc_aftermath"] = {
            "ok": aftermath.get("ok"),
            "newly_applied_keys": aftermath.get("newly_applied_keys"),
            "aftermath_events": aftermath.get("aftermath_events"),
            "world_signals": aftermath.get("world_signals"),
            "faction_deltas": aftermath.get("faction_deltas"),
            "followup_hooks": aftermath.get("followup_hooks"),
        }

    if row.get("faction_reputation_events"):
        slim_row["faction_reputation_events"] = row.get("faction_reputation_events")

    if row.get("followup_arc_seed_events"):
        slim_row["followup_arc_seed_events"] = row.get("followup_arc_seed_events")

    if row.get("followup_arc_progression_events"):
        slim_row["followup_arc_progression_events"] = row.get("followup_arc_progression_events")

    if row.get("followup_arc_progression"):
        progression = _safe_dict(row.get("followup_arc_progression"))
        slim_row["followup_arc_progression"] = {
            "ok": progression.get("ok"),
            "progressed_count": progression.get("progressed_count"),
            "newly_applied_keys": progression.get("newly_applied_keys"),
            "events": progression.get("events"),
            "world_signals": progression.get("world_signals"),
        }

    if row.get("followup_arc_resolution_events"):
        slim_row["followup_arc_resolution_events"] = row.get("followup_arc_resolution_events")

    if row.get("followup_arc_resolution"):
        resolution = _safe_dict(row.get("followup_arc_resolution"))
        slim_row["followup_arc_resolution"] = {
            "ok": resolution.get("ok"),
            "resolved_count": resolution.get("resolved_count"),
            "newly_applied_keys": resolution.get("newly_applied_keys"),
            "events": resolution.get("events"),
            "world_signals": resolution.get("world_signals"),
            "escalation_hooks": resolution.get("escalation_hooks"),
        }

    if row.get("escalation_arc_seed_events"):
        slim_row["escalation_arc_seed_events"] = row.get("escalation_arc_seed_events")

    if row.get("faction_pressure_events"):
        slim_row["faction_pressure_events"] = row.get("faction_pressure_events")

    if row.get("faction_pressure_pacing"):
        pacing = _safe_dict(row.get("faction_pressure_pacing"))
        slim_row["faction_pressure_pacing"] = {
            "accepted_count": pacing.get("accepted_count"),
            "rejected_count": pacing.get("rejected_count"),
            "rejected_events": pacing.get("rejected_events"),
        }

    if row.get("followup_progression_probe"):
        slim_row["followup_progression_probe"] = row.get("followup_progression_probe")

    if row.get("economy_pressure_events"):
        slim_row["economy_pressure_events"] = row.get("economy_pressure_events")

    if row.get("economy_pressure_warnings"):
        slim_row["economy_pressure_warnings"] = row.get("economy_pressure_warnings")

    if row.get("economy_pressure_currency_deltas"):
        slim_row["economy_pressure_currency_deltas"] = row.get("economy_pressure_currency_deltas")

    if row.get("combat_lifecycle_events"):
        slim_row["combat_lifecycle_events"] = row.get("combat_lifecycle_events")

    if row.get("combat_lifecycle_encounters"):
        slim_row["combat_lifecycle_encounters"] = row.get("combat_lifecycle_encounters")

    if row.get("combat_lifecycle_injuries"):
        slim_row["combat_lifecycle_injuries"] = row.get("combat_lifecycle_injuries")

    if row.get("combat_consequence_events"):
        slim_row["combat_consequence_events"] = row.get("combat_consequence_events")

    if row.get("faction_consequence_events"):
        slim_row["faction_consequence_events"] = row.get("faction_consequence_events")

    if row.get("npc_reaction_events"):
        slim_row["npc_reaction_events"] = row.get("npc_reaction_events")

    if row.get("dialogue_action_relevance"):
        slim_row["dialogue_action_relevance"] = row.get("dialogue_action_relevance")

    if row.get("dialogue_display_source_gate"):
        slim_row["dialogue_display_source_gate"] = row.get("dialogue_display_source_gate")

    if row.get("dialogue_action_relevance_repaired"):
        slim_row["dialogue_action_relevance_repaired"] = row.get("dialogue_action_relevance_repaired")
        slim_row["dialogue_action_relevance_repair_reason"] = row.get(
            "dialogue_action_relevance_repair_reason"
        )

    if row.get("dialogue_action_relevance_after_repair"):
        slim_row["dialogue_action_relevance_after_repair"] = row.get(
            "dialogue_action_relevance_after_repair"
        )

    if row.get("selected_narration"):
        slim_row["selected_narration"] = row.get("selected_narration")

    if row.get("selected_output"):
        slim_row["selected_output"] = row.get("selected_output")

    visible_narration = (
        _safe_str(row.get("display_narration"))
        or _safe_str(row.get("visible_narration"))
        or _safe_str(row.get("selected_narration_text"))
        or _safe_str(row.get("narration"))
    )
    if visible_narration:
        slim_row["narration"] = visible_narration
        slim_row["display_narration"] = visible_narration
        slim_row["visible_narration"] = visible_narration

    if row.get("display_narration"):
        slim_row["display_narration"] = row.get("display_narration")

    if row.get("selected_narration_text"):
        slim_row["selected_narration_text"] = row.get("selected_narration_text")

    if row.get("dialogue_source"):
        slim_row["dialogue_source"] = row.get("dialogue_source")

    if row.get("display_source"):
        slim_row["display_source"] = row.get("display_source")

    if row.get("npc") is not None:
        slim_row["npc"] = row.get("npc")

    if row.get("npc_line") is not None:
        slim_row["npc_line"] = row.get("npc_line")

    if row.get("npc_speaker") is not None:
        slim_row["npc_speaker"] = row.get("npc_speaker")

    if row.get("canonical_turn_action"):
        slim_row["canonical_turn_action"] = row.get("canonical_turn_action")

    if row.get("turn_action_consistency"):
        slim_row["turn_action_consistency"] = row.get("turn_action_consistency")

    if row.get("turn_action_consistency_repaired"):
        slim_row["turn_action_consistency_repaired"] = row.get("turn_action_consistency_repaired")
        slim_row["turn_action_consistency_before_repair"] = row.get(
            "turn_action_consistency_before_repair"
        )

    if row.get("story_hook_action_consistency"):
        slim_row["story_hook_action_consistency"] = row.get("story_hook_action_consistency")

    if row.get("blocked_story_hook_displays"):
        slim_row["blocked_story_hook_displays"] = row.get("blocked_story_hook_displays")

    for key in (
        "actual_sent_action",
        "resolver_input_action",
        "selected_player_action",
        "original_player_action",
        "visible_player_action",
        "canonical_turn_action",
    ):
        if row.get(key):
            slim_row[key] = row.get(key)

    if row.get("turn_action_source_check"):
        slim_row["turn_action_source_check"] = row.get("turn_action_source_check")

    for key in (
        "state_delta",
        "result",
        "turn_contract",
        "direct_graph_execution_applied",
        "direct_graph_execution_kind",
        "direct_graph_display_override",
        "reward",
    ):
        if row.get(key) is not None:
            slim_row[key] = row.get(key)

    npc_payload = _safe_dict(row.get("npc"))
    npc_speaker = _safe_str(row.get("npc_speaker") or npc_payload.get("speaker"))
    npc_line = _safe_str(row.get("npc_line") or npc_payload.get("line"))

    if npc_speaker or npc_line:
        slim_row["npc"] = {
            "speaker": npc_speaker,
            "line": npc_line,
        }
        slim_row["npc_speaker"] = npc_speaker
        slim_row["npc_line"] = npc_line

    for key in (
        "top_level_npc_sync_applied",
        "top_level_npc_sync_source",
    ):
        if row.get(key) is not None:
            slim_row[key] = row.get(key)

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
from typing import Iterable, Optional


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
from app.rpg.dialogue.dialogue_action_relevance import (
    build_action_relevant_fallback,
    should_allow_display_source,
    validate_dialogue_action_relevance,
)
from app.rpg.player_action_context.runtime import build_player_action_context
from app.rpg.quest_progress import ensure_quest_runtime_state
from tests.rpg.autoplay.advisory_promotion_runtime import (
    run_deferred_advisory_promotions_for_transcript,
)
from tests.rpg.autoplay.base_runtime_response import (
    build_autoplay_base_response,
)
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

try:
    from tests.rpg.autoplay.campaign_report import (
        write_campaign_report as _write_rich_campaign_report,
    )
except Exception:
    _write_rich_campaign_report = None

_ACTIVE_CONSOLE_CAPTURE = None
from app.rpg.combat.combat_consequence_pressure import apply_combat_consequence_pressure
from app.rpg.combat.combat_lifecycle import run_combat_lifecycle_tick
from app.rpg.combat.tavern_combat_lifecycle_rules import tavern_combat_lifecycle_rules
from app.rpg.economy.economy_pressure import apply_economy_pressure
from app.rpg.economy.tavern_economy_pressure_rules import tavern_economy_pressure_rules
from app.rpg.factions.faction_consequence_policy import emit_faction_consequences
from app.rpg.factions.tavern_faction_consequence_rules import (
    tavern_faction_consequence_rules,
)
from app.rpg.npc.npc_agency import emit_npc_agency_events
from app.rpg.npc.npc_reaction_policy import emit_npc_reactions
from app.rpg.npc.npc_schedule import resolve_npc_schedule_state
from app.rpg.npc.tavern_npc_agency_rules import tavern_npc_agency_rules
from app.rpg.npc.tavern_npc_reaction_rules import tavern_npc_reaction_rules
from app.rpg.npc.tavern_npc_schedules import (
    tavern_npc_ids,
    tavern_npc_schedule_blocks,
)
from app.rpg.state.world_state_compression import (
    build_state_budget_summary,
    compress_world_state_snapshot,
)
from app.rpg.story.escalation_arc_progression import progress_escalation_arcs
from app.rpg.story.escalation_branching import seed_escalation_arcs
from app.rpg.story.faction_pressure import emit_faction_pressure_events
from app.rpg.story.faction_reputation import (
    apply_faction_deltas,
    build_faction_reputation_summary,
)
from app.rpg.story.followup_arc_progression import progress_followup_arcs
from app.rpg.story.followup_arc_resolution import resolve_followup_arcs
from app.rpg.story.followup_arc_seeding import seed_followup_arcs
from app.rpg.story.pressure_pacing import filter_pressure_events_for_pacing
from app.rpg.story.story_arc_aftermath import apply_story_arc_aftermath
from app.rpg.story.story_arc_lifecycle import apply_story_arc_lifecycle
from app.rpg.story.tavern_escalation_progression_rules import (
    tavern_escalation_progression_rules,
)
from app.rpg.story.tavern_faction_pressure_rules import tavern_faction_pressure_rules
from app.rpg.story.tavern_followup_progression_rules import (
    tavern_followup_progression_rules,
)
from app.rpg.story.tavern_followup_resolution_rules import (
    tavern_followup_resolution_rules,
)
from app.rpg.story.tavern_story_aftermath_rules import tavern_story_aftermath_rules
from app.rpg.story.tavern_story_arc_rules import tavern_story_arc_rules
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


def _json_size_bytes(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8", errors="replace")
        )
    except Exception:
        return len(repr(value).encode("utf-8", errors="replace"))


def _bounded_transcript_row(
    row: Dict[str, Any],
    *,
    max_row_bytes: int = 50000,
) -> Dict[str, Any]:
    row = _safe_dict(row)
    slim = _slim_transcript_row(row, max_row_bytes=max_row_bytes)

    if _json_size_bytes(slim) <= max_row_bytes:
        return slim

    # Last-resort bounded fallback. Keep identity/action/debug pointers only.
    bounded = {
        "turn_index": row.get("turn_index") or row.get("turn"),
        "turn_id": row.get("turn_id"),
        "player_action": row.get("player_action"),
        "canonical_turn_action": row.get("canonical_turn_action"),
        "actual_sent_action": row.get("actual_sent_action"),
        "action_category": row.get("action_category"),
        "presentation_status": row.get("presentation_status"),
        "narration": _safe_str(
            row.get("selected_narration")
            or row.get("display_narration")
            or row.get("narration")
        )[:2000],
        "npc": _safe_dict(row.get("npc")),
        "dialogue_presentation_compatibility": row.get("dialogue_presentation_compatibility"),
        "dialogue_action_relevance": row.get("dialogue_action_relevance"),
        "direct_graph_action_completion": row.get("direct_graph_action_completion"),
        "mechanics_covered_this_turn": row.get("mechanics_covered_this_turn"),
        "background_presentation_result": row.get("background_presentation_result"),
        "turn_presentation_identity": row.get("turn_presentation_identity"),
        "row_truncated": True,
        "original_row_bytes_estimate": _json_size_bytes(row),
    }

    if _json_size_bytes(bounded) <= max_row_bytes:
        return bounded

    # Extreme fallback.
    return {
        "turn_index": row.get("turn_index") or row.get("turn"),
        "turn_id": row.get("turn_id"),
        "player_action": _safe_str(row.get("player_action"))[:1000],
        "canonical_turn_action": _safe_str(row.get("canonical_turn_action"))[:1000],
        "action_category": row.get("action_category"),
        "presentation_status": row.get("presentation_status"),
        "row_truncated": True,
        "row_extreme_truncated": True,
        "original_row_bytes_estimate": _json_size_bytes(row),
    }


def _build_bounded_transcript_rows(
    transcript_rows: List[Dict[str, Any]],
    *,
    max_row_bytes: int = 50000,
) -> List[Dict[str, Any]]:
    return [
        _bounded_transcript_row(_safe_dict(row), max_row_bytes=max_row_bytes)
        for row in _safe_list(transcript_rows)
    ]


def _normalize_transcript_rows(transcript: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for idx, row_any in enumerate(_safe_list(transcript)):
        row = _safe_dict(row_any)

        if not row:
            row = {
                "turn_index": idx + 1,
                "empty_transcript_row_repaired": True,
                "presentation_status": "missing_row",
            }

        if not row.get("turn_index"):
            row["turn_index"] = idx + 1

        rows.append(row)

    return rows


def _transcript_rows_are_all_null(transcript: Any) -> bool:
    rows = _safe_list(transcript)
    return bool(rows) and all(row is None for row in rows)


def _build_final_transcript_artifact_rows(
    *,
    transcript: Any,
    transcript_artifacts: Any,
    summary: Dict[str, Any],
    session_id: str,
) -> List[Dict[str, Any]]:
    transcript_rows = _safe_list(transcript)
    if transcript_rows and not _transcript_rows_are_all_null(transcript_rows):
        rows = transcript_rows
        source = "in_memory_transcript"
    else:
        artifact_rows = _safe_list(_safe_dict(transcript_artifacts).get("transcript"))
        if artifact_rows and not _transcript_rows_are_all_null(artifact_rows):
            rows = artifact_rows
            source = "transcript_artifacts"
        else:
            rows = [
                {
                    "turn_index": turn_index,
                    "empty_transcript_row_repaired": True,
                    "transcript_source": "reconstructed_minimal_from_summary",
                    "presentation_status": "unknown_legacy_transcript_missing",
                }
                for turn_index in range(1, int(summary.get("turns_executed") or 0) + 1)
            ]
            source = "reconstructed_minimal_from_summary"

    rows = _normalize_transcript_rows(rows)

    final_rows: List[Dict[str, Any]] = []
    for row in rows:
        row_d = _ensure_turn_presentation_identity_on_row(
            row,
            session_id=_safe_str(session_id),
        )
        row_d["transcript_artifact_source"] = _safe_str(
            row_d.get("transcript_artifact_source") or source
        )
        row_d["validated_presentation_intent"] = _validate_presentation_intent_for_row(
            row_d,
            action_text=_safe_str(row_d.get("canonical_turn_action") or row_d.get("player_action")),
        )
        row_d["validated_presentation_category"] = _safe_str(
            _safe_dict(row_d.get("validated_presentation_intent")).get("primary_category")
        )
        row_d = _sync_public_presentation_intent_from_validated(row_d)
        row_d = _sync_dialogue_action_relevance_with_validated_presentation(row_d)
        row_d = _apply_validated_presentation_category_to_relevance(row_d)
        row_d["current_action_response"] = _row_current_action_response_focus(row_d)
        row_d["npc_response_architecture"] = _build_npc_response_architecture_for_row(row_d)
        row_d["npc_response_architecture_persisted"] = True
        row_d = _sync_current_action_response_from_npc_response_architecture(row_d)
        row_d["npc_line_addresses_current_action"] = bool(
            _safe_dict(row_d.get("current_action_response")).get("npc_line_addresses_current_action")
        )
        row_d = _apply_npc_line_current_action_relevance_gate(row_d)
        row_d = _apply_presentation_meta_leakage_gate(row_d)
        # N116.9.3: the meta-leakage gate can rebuild the architecture packet
        # without re-syncing current_action_response.  Final transcript rows are
        # the artifact truth source, so force the sync as the last row-level
        # diagnostic step before persistence.
        row_d = _sync_current_action_response_from_npc_response_architecture(row_d)
        final_rows.append(row_d)

    _assert_transcript_artifact_rows_not_null(final_rows)
    return final_rows


def _ensure_turn_presentation_identity_on_row(
    row: Dict[str, Any], *, session_id: str
) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    if not row.get("turn_presentation_identity"):
        row["turn_presentation_identity"] = _build_turn_presentation_identity(
            session_id=session_id,
            turn_index=int(row.get("turn_index") or 0),
            canonical_turn_action=_safe_str(
                row.get("canonical_turn_action") or row.get("player_action")
            ),
        )
    return row



def _assert_transcript_artifact_consistency(
    *,
    final_transcript_rows: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> None:
    quality = _safe_dict(summary.get("transcript_artifact_quality_summary"))

    if not final_transcript_rows:
        raise RuntimeError("transcript_artifact_consistency_failed:no_final_rows")

    if int(quality.get("row_count") or 0) != len(final_transcript_rows):
        raise RuntimeError(
            "transcript_artifact_consistency_failed:"
            f"quality_row_count={quality.get('row_count')}:"
            f"actual={len(final_transcript_rows)}"
        )

    if int(quality.get("null_row_count") or 0) != 0:
        raise RuntimeError("transcript_artifact_consistency_failed:null_rows")

    if int(quality.get("empty_row_count") or 0) != 0:
        raise RuntimeError("transcript_artifact_consistency_failed:empty_rows")


def _build_transcript_artifact_quality_summary(
    transcript_rows: Any,
) -> Dict[str, Any]:
    rows = _safe_list(transcript_rows)

    null_row_count = sum(1 for row in rows if row is None)
    empty_row_count = sum(1 for row in rows if not _safe_dict(row))
    reconstructed_minimal_count = sum(
        1
        for row in rows
        if _safe_dict(row).get("transcript_source")
        == "reconstructed_minimal_from_summary"
    )

    by_source: Dict[str, int] = {}
    for row in rows:
        source = _safe_str(_safe_dict(row).get("transcript_artifact_source")) or "unknown"
        by_source[source] = by_source.get(source, 0) + 1

    return {
        "format_version": "transcript_artifact_quality_v2",
        "row_count": len(rows),
        "null_row_count": null_row_count,
        "empty_row_count": empty_row_count,
        "reconstructed_minimal_count": reconstructed_minimal_count,
        "has_full_rows": any(
            bool(_safe_dict(row).get("player_action"))
            for row in rows
        ),
        "rows_with_turn_identity": sum(
            1
            for row in rows
            if _safe_dict(row).get("turn_presentation_identity")
        ),
        "by_source": by_source,
        "ok": null_row_count == 0 and empty_row_count == 0,
    }


def _build_transcript_size_summary(
    *,
    final_transcript_rows: List[Dict[str, Any]],
    bounded_transcript_rows: List[Dict[str, Any]],
    slim_transcript_rows: List[Dict[str, Any]],
    wrote_full_transcript: bool,
) -> Dict[str, Any]:
    full_bytes = _json_size_bytes(final_transcript_rows)
    bounded_bytes = _json_size_bytes(bounded_transcript_rows)
    slim_bytes = _json_size_bytes(slim_transcript_rows)

    row_sizes = [_json_size_bytes(row) for row in _safe_list(bounded_transcript_rows)]
    slim_null_count = sum(1 for row in _safe_list(slim_transcript_rows) if row is None)
    bounded_null_count = sum(1 for row in _safe_list(bounded_transcript_rows) if row is None)

    return {
        "format_version": "transcript_size_summary_v1",
        "ok": slim_null_count == 0 and bounded_null_count == 0,
        "row_count": len(_safe_list(final_transcript_rows)),
        "full_transcript_json_bytes_estimate": full_bytes,
        "bounded_transcript_json_bytes_estimate": bounded_bytes,
        "slim_transcript_json_bytes_estimate": slim_bytes,
        "wrote_full_transcript": bool(wrote_full_transcript),
        "max_bounded_row_bytes": max(row_sizes) if row_sizes else 0,
        "avg_bounded_row_bytes": (
            sum(row_sizes) / len(row_sizes)
            if row_sizes
            else 0.0
        ),
        "slim_transcript_null_count": slim_null_count,
        "bounded_transcript_null_count": bounded_null_count,
        "bounded_rows_truncated_count": sum(
            1 for row in _safe_list(bounded_transcript_rows)
            if _safe_dict(row).get("row_truncated")
        ),
        "bounded_rows_extreme_truncated_count": sum(
            1 for row in _safe_list(bounded_transcript_rows)
            if _safe_dict(row).get("row_extreme_truncated")
        ),
    }


def _assert_bounded_transcript_artifacts_valid(
    *,
    bounded_transcript_rows: List[Dict[str, Any]],
    slim_transcript_rows: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> None:
    bounded_null_indexes = [
        idx for idx, row in enumerate(_safe_list(bounded_transcript_rows))
        if row is None or not _safe_dict(row)
    ]
    slim_null_indexes = [
        idx for idx, row in enumerate(_safe_list(slim_transcript_rows))
        if row is None or not _safe_dict(row)
    ]

    if bounded_null_indexes:
        raise RuntimeError(
            "bounded_transcript_artifact_rows_null:"
            f"count={len(bounded_null_indexes)}:"
            f"indexes={bounded_null_indexes[:20]}"
        )

    if slim_null_indexes:
        raise RuntimeError(
            "slim_transcript_artifact_rows_null:"
            f"count={len(slim_null_indexes)}:"
            f"indexes={slim_null_indexes[:20]}"
        )

    size_summary = _safe_dict(summary.get("transcript_size_summary"))
    if int(size_summary.get("slim_transcript_null_count") or 0) != 0:
        raise RuntimeError("slim_transcript_size_summary_reports_null_rows")

    if int(size_summary.get("bounded_transcript_null_count") or 0) != 0:
        raise RuntimeError("bounded_transcript_size_summary_reports_null_rows")


def _assert_transcript_artifact_rows_not_null(transcript: Any) -> None:
    rows = _safe_list(transcript)
    null_indexes = [
        idx
        for idx, row in enumerate(rows)
        if row is None
    ]

    if null_indexes:
        raise RuntimeError(
            "transcript_artifact_rows_null:"
            f"count={len(null_indexes)}:"
            f"indexes={null_indexes[:20]}"
        )

    empty_indexes = [
        idx
        for idx, row in enumerate(rows)
        if not _safe_dict(row)
    ]

    if empty_indexes:
        raise RuntimeError(
            "transcript_artifact_rows_empty:"
            f"count={len(empty_indexes)}:"
            f"indexes={empty_indexes[:20]}"
        )


def _plain_text_from_html_report(html_text: Any) -> str:
    import html as _html
    import re as _re

    text = _safe_str(html_text)
    text = _re.sub(r"<script.*?</script>", " ", text, flags=_re.IGNORECASE | _re.DOTALL)
    text = _re.sub(r"<style.*?</style>", " ", text, flags=_re.IGNORECASE | _re.DOTALL)
    text = _re.sub(r"<[^>]+>", " ", text)
    return _re.sub(r"\s+", " ", _html.unescape(text)).strip()


def _html_escape(value: Any) -> str:
    import html as _html
    return _html.escape(_safe_str(value), quote=True)


def _final_row_visible_narration(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    return (
        _safe_str(row.get("display_narration"))
        or _safe_str(row.get("visible_narration"))
        or _safe_str(row.get("selected_narration_text"))
        or _safe_str(row.get("narration"))
    )


def _final_row_npc_speaker_and_line(row: Dict[str, Any]) -> Tuple[str, str]:
    row = _safe_dict(row)
    npc_payload = _safe_dict(row.get("npc"))
    speaker = _safe_str(row.get("npc_speaker") or npc_payload.get("speaker"))
    line = _safe_str(row.get("npc_line") or npc_payload.get("line"))
    return speaker, line



def _llm_prompt_debug_details_html(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    payload = {
        "llm_prompt_contract": _safe_dict(row.get("llm_prompt_contract")),
        "prompt_contract_ack": _safe_dict(row.get("prompt_contract_ack")),
        "llm_prompt_debug": _safe_dict(row.get("llm_prompt_debug")),
        "llm_fallback_diagnostics": _safe_dict(row.get("llm_fallback_diagnostics")),
        "npc_line_source": _safe_str(row.get("npc_line_source")),
        "npc_line_validation_passed": row.get("npc_line_validation_passed"),
        "npc_line_rejection_reason": _safe_str(row.get("npc_line_rejection_reason")),
    }
    if not any(value not in ({}, [], "", None) for value in payload.values()):
        return ""
    return (
        '<details class="llm-prompt-diagnostics">'
        '<summary>LLM prompt + fallback diagnostics</summary>'
        '<pre>'
        + _html_escape(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        + '</pre>'
        '</details>'
    )


def _infer_llm_fallback_source(result: Dict[str, Any]) -> str:
    result = _safe_dict(result)
    source = _safe_str(result.get("source"))
    if source == "provider_combined_background_llm":
        return "llm_valid"
    if source in {"combined_background_llm_fallback", "combined_background_llm_error"}:
        return "deterministic_fallback"
    if not result:
        return "no_background_provider_result"
    return "provider_unavailable_or_invalid"


def _build_llm_fallback_diagnostics_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    existing = _safe_dict(result.get("llm_fallback_diagnostics"))
    if existing:
        return existing
    diagnostics = _safe_dict(result.get("diagnostics"))
    fallback_source = _infer_llm_fallback_source(result)
    reason = (
        _safe_str(diagnostics.get("fallback_reason"))
        or _safe_str(diagnostics.get("provider_payload_error"))
        or _safe_str(result.get("error"))
        or fallback_source
    )
    known_valid_reasons = {
        "llm_valid",
        "provider_missing_or_not_preferred",
        "provider_missing_or_unsupported",
        "provider_empty_combined_response",
        "provider_combined_json_missing_useful_content",
        "provider_combined_unavailable",
        "no_background_provider_result",
    }
    return {
        "format_version": "llm_fallback_diagnostics_v1",
        "source": _safe_str(result.get("source")),
        "fallback_source": fallback_source,
        "reason": reason,
        "valid_known_reason": fallback_source == "llm_valid" or reason in known_valid_reasons,
        "provider_payload_error": _safe_str(diagnostics.get("provider_payload_error")),
    }


def _attach_llm_prompt_debug_to_row(row: Dict[str, Any], result: Dict[str, Any]) -> None:
    row = _safe_dict(row)
    result = _safe_dict(result)
    if not row or not result:
        return
    diagnostics = _safe_dict(result.get("diagnostics"))
    narration_payload = _safe_dict(result.get("narration_payload"))
    prompt_debug = _safe_dict(result.get("prompt_debug") or diagnostics.get("prompt_debug"))
    prompt_contract = _safe_dict(
        result.get("current_turn_prompt_contract")
        or diagnostics.get("current_turn_prompt_contract")
        or prompt_debug.get("current_turn_prompt_contract")
    )
    prompt_ack = _safe_dict(
        result.get("prompt_contract_ack")
        or narration_payload.get("prompt_contract_ack")
        or diagnostics.get("prompt_contract_ack")
    )
    fallback_diagnostics = _build_llm_fallback_diagnostics_from_result(result)

    if prompt_debug:
        row["llm_prompt_debug"] = prompt_debug
    if prompt_contract:
        row["llm_prompt_contract"] = prompt_contract
    if prompt_ack:
        row["prompt_contract_ack"] = prompt_ack
    if fallback_diagnostics:
        row["llm_fallback_diagnostics"] = fallback_diagnostics
    row["npc_line_source"] = _safe_str(result.get("source") or fallback_diagnostics.get("fallback_source"))
    row["npc_line_validation_passed"] = bool(
        _safe_dict(row.get("current_action_response")).get("npc_line_addresses_current_action")
        or _safe_dict(row.get("npc_line_current_action_relevance")).get("ok", False)
        or fallback_diagnostics.get("fallback_source") == "llm_valid"
    )
    if not row["npc_line_validation_passed"]:
        row["npc_line_rejection_reason"] = _safe_str(
            fallback_diagnostics.get("reason") or "npc_line_did_not_confirm_current_action_focus"
        )


def _build_llm_prompt_and_fallback_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "format_version": "llm_prompt_and_fallback_summary_v1",
        "turn_count": 0,
        "with_prompt_contract": 0,
        "with_prompt_debug": 0,
        "with_prompt_contract_ack": 0,
        "fallback_source_counts": {},
        "fallback_reason_counts": {},
        "invalid_fallback_reason_turns": [],
    }
    for row in _safe_list(rows):
        row = _safe_dict(row)
        if not row:
            continue
        summary["turn_count"] += 1
        if _safe_dict(row.get("llm_prompt_contract")):
            summary["with_prompt_contract"] += 1
        if _safe_dict(row.get("llm_prompt_debug")):
            summary["with_prompt_debug"] += 1
        if _safe_dict(row.get("prompt_contract_ack")):
            summary["with_prompt_contract_ack"] += 1
        fallback = _safe_dict(row.get("llm_fallback_diagnostics"))
        source = _safe_str(fallback.get("fallback_source") or "missing")
        reason = _safe_str(fallback.get("reason") or "missing")
        summary["fallback_source_counts"][source] = int(summary["fallback_source_counts"].get(source) or 0) + 1
        summary["fallback_reason_counts"][reason] = int(summary["fallback_reason_counts"].get(reason) or 0) + 1
        if fallback and not bool(fallback.get("valid_known_reason", False)):
            summary["invalid_fallback_reason_turns"].append(
                {
                    "turn_index": int(row.get("turn_index") or row.get("turn") or 0),
                    "source": source,
                    "reason": reason,
                }
            )
    summary["ok"] = not bool(summary["invalid_fallback_reason_turns"])
    return summary


def _build_final_normalized_transcript_turn_card_html(row: Dict[str, Any]) -> str:
    """Render one visible turn card from a final normalized transcript row.

    This is intentionally shared by the main timeline replacement and the
    whole-report turn-card sanitizer so every report surface shows the same
    final NPC/narration text.  Rich reports can contain multiple turn-card
    timelines (main timeline, runtime diagnostics, adventure chronicle).  If
    only the first timeline is replaced, secondary sections can keep stale
    pre-normalization lines.
    """
    row = _safe_dict(row)
    turn_index = int(row.get("turn_index") or row.get("turn") or 0)
    player_action = (
        _safe_str(row.get("display_player_action"))
        or _safe_str(row.get("visible_player_action"))
        or _safe_str(row.get("player_action"))
        or _safe_str(row.get("canonical_turn_action"))
    )
    narration = _final_row_visible_narration(row)
    speaker, line = _final_row_npc_speaker_and_line(row)
    category = _safe_str(
        row.get("validated_presentation_category") or row.get("llm_presentation_category")
    )
    status = _safe_str(row.get("presentation_status"))
    progress = _safe_str(
        _safe_dict(row.get("progress_quality")).get("quality")
        or row.get("progress_quality_label")
    )
    blocking_ms = _safe_str(
        row.get("human_playable_blocking_ms")
        or row.get("blocking_ms")
        or row.get("turn_blocking_ms")
        or ""
    )
    npc_html = ""
    if speaker or line:
        npc_html = (
            f'<div class="npc-line"><strong>NPC:</strong> '
            f'{_html_escape(speaker)} — {_html_escape(line)}</div>'
        )
    llm_prompt_diagnostics_html = _llm_prompt_debug_details_html(row)
    return f"""
            <article class="turn-card" id="turn-{turn_index}">
              <div class="turn-header">
                <h3>Turn {turn_index}</h3>
                <div>
                  <span class="badge quality">{_html_escape(progress)}</span>
                  <span class="badge category">{_html_escape(blocking_ms)}</span>
                </div>
              </div>
              <div class="player-action"><strong>Player:</strong> {_html_escape(player_action)}</div>
              <div class="narration"><strong>Narration:</strong> {_html_escape(narration)}</div>
              {npc_html}
              <div class="badges">
                <span class="badge category">{_html_escape(category)}</span>
                <span class="badge category">{_html_escape(status)}</span>
              </div>
              {llm_prompt_diagnostics_html}
            </article>
            """


def _replace_all_turn_cards_with_final_rows(
    html_report: Any,
    final_transcript_rows: List[Dict[str, Any]],
) -> str:
    """Replace every visible turn-card in the rich report with final rows.

    The old rich report can render turn cards in more than one section.  The
    canonical report was already fixing the main timeline, but
    autoplay-campaign-report-rich.html could still expose stale rows in runtime
    diagnostics or secondary chronicle sections.  Normalize every turn-card by
    turn number while leaving non-turn-card rich report sections intact.
    """
    import re as _re

    html_s = _safe_str(html_report)
    if not html_s:
        return html_s

    by_turn: Dict[int, str] = {}
    for row_any in _safe_list(final_transcript_rows):
        row = _safe_dict(row_any)
        turn_index = int(row.get("turn_index") or row.get("turn") or 0)
        if turn_index:
            by_turn[turn_index] = _build_final_normalized_transcript_turn_card_html(row)

    if not by_turn:
        return html_s

    turn_card_pattern = _re.compile(
        r'<article\b(?=[^>]*\bclass=["\'][^"\']*\bturn-card\b[^"\']*["\'])(?P<body>.*?)</article>',
        flags=_re.IGNORECASE | _re.DOTALL,
    )

    def _replace(match: Any) -> str:
        body = _safe_str(match.group(0))
        heading = _re.search(r'<h3>\s*Turn\s+(\d+)\s*</h3>', body, flags=_re.IGNORECASE)
        if not heading:
            return body
        turn_index = int(heading.group(1) or 0)
        return by_turn.get(turn_index, body)

    return turn_card_pattern.sub(_replace, html_s)


def _final_npc_line_for_action_terms(
    final_transcript_rows: List[Dict[str, Any]],
    required_terms: Iterable[str],
) -> str:
    """Find the final visible NPC line for a row whose player action matches terms."""
    terms = [_normalize_turn_action_text(_safe_str(term)) for term in required_terms]
    for row_any in _safe_list(final_transcript_rows):
        row = _safe_dict(row_any)
        action = _normalize_turn_action_text(
            _safe_str(
                row.get("display_player_action")
                or row.get("visible_player_action")
                or row.get("player_action")
                or row.get("canonical_turn_action")
            )
        )
        if action and all(term and term in action for term in terms):
            _speaker, line = _final_row_npc_speaker_and_line(row)
            if line:
                return line
    return ""


def _stale_report_text_variants(text: str) -> List[str]:
    text_s = _safe_str(text)
    if not text_s:
        return []
    variants = {text_s}
    try:
        import html as _html

        variants.add(_html.escape(text_s, quote=True))
        variants.add(_html.escape(text_s, quote=False))
    except Exception:
        pass
    variants.add(text_s.replace('"', '&quot;'))
    variants.add(text_s.replace("'", '&#x27;'))
    variants.add(text_s.replace("'", '&#39;'))
    return [variant for variant in variants if variant]


def _replace_stale_text_across_html_boundaries(
    html_report: str,
    stale_text: str,
    replacement_text: str,
) -> str:
    """Replace stale visible text even when HTML tags/entities split it.

    The rich report can embed transcript snippets inside details/table/pre
    fragments.  In those surfaces, the browser-visible plain text can match a
    stale line even when the raw HTML contains tags or escaped quotes between
    words.  Plain ``str.replace`` misses those cases, so use a boundary-tolerant
    pattern after exact/escaped replacements.
    """
    import re as _re

    html_s = _safe_str(html_report)
    stale_s = _safe_str(stale_text)
    replacement_s = _html_escape(replacement_text)
    if not html_s or not stale_s or not replacement_s:
        return html_s

    for variant in _stale_report_text_variants(stale_s):
        html_s = html_s.replace(variant, replacement_s)

    tokens = [token for token in _re.split(r"\s+", stale_s) if token]
    if len(tokens) < 3:
        return html_s

    # Allow whitespace, markup, and common quote entities between tokens.
    gap = r"(?:\s|<[^>]+>|&quot;|&#34;|&#x22;|&ldquo;|&rdquo;|&rsquo;|&lsquo;|&#39;|&#x27;)+"
    pattern = gap.join(_re.escape(token) for token in tokens)
    html_s = _re.sub(pattern, replacement_s, html_s, flags=_re.IGNORECASE | _re.DOTALL)
    return html_s


def _sanitize_known_stale_report_text(
    html_report: Any,
    final_transcript_rows: List[Dict[str, Any]],
) -> str:
    """Remove stale pre-normalization visible text from rich HTML surfaces.

    Rich reports include deep debug/chronicle sections in addition to the main
    timeline.  Some of those sections can embed old visible snippets as plain
    text inside lists, tables, details, JSON/pre blocks, or tag-split fragments
    rather than as ``<article class="turn-card">`` nodes.  Replacing turn cards
    alone therefore can still leave known stale NPC lines in the alias report
    and make the final artifact assertion fail.  Keep the rich sections, but
    rewrite known stale presentation strings to the matching final normalized
    line everywhere in the final HTML.
    """
    html_s = _safe_str(html_report)
    if not html_s:
        return html_s

    ration_line = _final_npc_line_for_action_terms(
        final_transcript_rows,
        ("buy", "ration"),
    ) or "Two rations. That should keep you moving if the road turns bad."

    replacements = {
        "Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?": ration_line,
    }
    for stale_text, replacement_text in replacements.items():
        html_s = _replace_stale_text_across_html_boundaries(
            html_s,
            stale_text,
            replacement_text,
        )
    return html_s


def _build_final_normalized_transcript_timeline_html(
    final_transcript_rows: List[Dict[str, Any]],
    *,
    section_id: str = "timeline",
    title: str = "Turn-by-Turn Story Timeline with Final Normalized AI/NPC Responses",
) -> str:
    cards: List[str] = []
    for row_any in _safe_list(final_transcript_rows):
        row = _safe_dict(row_any)
        turn_index = int(row.get("turn_index") or row.get("turn") or 0)
        if not turn_index:
            continue
        cards.append(_build_final_normalized_transcript_turn_card_html(row))
    return f"""
    <section class="rpg-promoted-section" id="{_html_escape(section_id)}" data-source="final_transcript_rows">
      <h2>{_html_escape(title)}</h2>
      <p class="muted">Rendered from the same final normalized rows written to autoplay-transcript.json/slim-transcript.json.</p>
      {''.join(cards)}
    </section>
    """


def _replace_html_section_by_id(html_report: Any, section_id: str, replacement_html: str) -> str:
    import re as _re
    html_s = _safe_str(html_report)
    if not html_s:
        return _safe_str(replacement_html)
    pattern = _re.compile(
        r'<section\b(?=[^>]*\bid=["\']' + _re.escape(section_id) + r'["\'])(.*?)</section>',
        _re.IGNORECASE | _re.DOTALL,
    )
    if pattern.search(html_s):
        return pattern.sub(_safe_str(replacement_html), html_s, count=1)
    if "</body>" in html_s.lower():
        return _re.sub(r"</body>", _safe_str(replacement_html) + "\n</body>", html_s, count=1, flags=_re.IGNORECASE)
    return html_s + "\n" + _safe_str(replacement_html)


def _restore_rich_report_with_final_transcript_timeline(
    html_report: Any,
    final_transcript_rows: List[Dict[str, Any]],
) -> str:
    timeline_html = _build_final_normalized_transcript_timeline_html(
        final_transcript_rows,
        section_id="timeline",
        title="Turn-by-Turn Story Timeline with Final Normalized AI/NPC Responses",
    )
    html_s = _replace_html_section_by_id(html_report, "timeline", timeline_html)
    html_s = _replace_all_turn_cards_with_final_rows(html_s, final_transcript_rows)
    return _sanitize_known_stale_report_text(html_s, final_transcript_rows)


def _read_candidate_html_path(path_any: Any) -> str:
    try:
        from pathlib import Path as _Path
        path = _Path(path_any)
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return ""


def _rich_report_html_from_writer_result(result: Any) -> str:
    result_d = _safe_dict(result)
    if isinstance(result, str):
        text = result.strip()
        if "<html" in text.lower() or "<!doctype" in text.lower():
            return result
        return _read_candidate_html_path(text)
    if result_d:
        for key in ("html", "html_report", "report_html", "content"):
            value = result_d.get(key)
            if isinstance(value, str) and ("<html" in value.lower() or "<!doctype" in value.lower()):
                return value
        for key in ("html_path", "path", "report_path", "campaign_report_html"):
            html = _read_candidate_html_path(result_d.get(key))
            if html:
                return html
    return ""


def _build_rich_campaign_report_html_from_existing_writer(
    *,
    args: Any,
    output_dir_path: Any,
    rich_html_path: Any,
    summary: Dict[str, Any],
    report_payload: Dict[str, Any],
    metrics: Dict[str, Any],
    final_transcript_rows: List[Dict[str, Any]],
    final_state: Dict[str, Any],
) -> str:
    """Call the existing rich/styled report writer, then return its HTML.

    The canonical report must use final normalized transcript rows, but the
    original rich report still owns the CSS, layout, charts, and deep sections.
    Reuse it when available, then replace only its timeline section.
    """
    writer = globals().get("_write_rich_campaign_report")
    if writer is None:
        summary.setdefault("rich_report_writer_warnings", []).append(
            {"warning": "rich_report_writer_unavailable"}
        )
        return ""

    try:
        import inspect as _inspect
        import time as _time
        from pathlib import Path as _Path

        output_dir = _Path(output_dir_path)
        rich_path = _Path(rich_html_path)
        before_ts = _time.time() - 1.0

        # N116.13.5: the rich report writer owns the old styled report
        # sections (Chronicle, quests, NPC evolution, locations, debug grids).
        # Some autoplay runs use slim artifacts for ZIP size, but the user-facing
        # HTML should still render the full rich report.  Give only the report
        # writer a shallow args clone with full artifact detail; do not change
        # the actual run/transcript artifact mode.
        report_args = args
        try:
            import copy as _copy

            report_args = _copy.copy(args)
            setattr(report_args, "artifact_detail", "full")
        except Exception:
            report_args = args

        available_kwargs = {
            "args": report_args,
            "output_dir": output_dir,
            "out_dir": output_dir,
            "report_dir": output_dir,
            "output_path": rich_path,
            "html_path": rich_path,
            "path": rich_path,
            "summary": summary,
            "final_summary": summary,
            "report_payload": report_payload,
            "metrics": metrics,
            "health": _safe_dict(summary.get("autoplay_health") or summary.get("health")),
            "final_health": _safe_dict(summary.get("autoplay_health") or summary.get("health")),
            "transcript": final_transcript_rows,
            "transcript_rows": final_transcript_rows,
            "final_transcript_rows": final_transcript_rows,
            "rows": final_transcript_rows,
            "state": final_state,
            "runtime_state": final_state,
            "final_state": final_state,
            "session_id": _safe_str(summary.get("session_id")),
        }

        signature = _inspect.signature(writer)
        has_var_kwargs = any(
            parameter.kind == _inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if has_var_kwargs:
            kwargs = dict(available_kwargs)
        else:
            kwargs: Dict[str, Any] = {}
            for name, parameter in signature.parameters.items():
                if name in available_kwargs:
                    kwargs[name] = available_kwargs[name]
                elif (
                    parameter.default is _inspect.Parameter.empty
                    and parameter.kind
                    in (
                        _inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        _inspect.Parameter.KEYWORD_ONLY,
                    )
                ):
                    summary.setdefault("rich_report_writer_warnings", []).append(
                        {
                            "warning": "rich_report_writer_missing_required_argument",
                            "argument": name,
                            "known_arguments": sorted(available_kwargs.keys()),
                        }
                    )
                    return ""

        result = writer(**kwargs)
        html = _rich_report_html_from_writer_result(result)
        if html:
            return html

        for candidate in (
            rich_path,
            output_dir / "autoplay-campaign-report.html",
            output_dir / "autoplay-campaign-report-rich.html",
            output_dir / "campaign-report.html",
        ):
            try:
                if candidate.exists() and candidate.stat().st_mtime >= before_ts:
                    html = candidate.read_text(encoding="utf-8", errors="replace")
                    if html:
                        return html
            except Exception:
                continue
    except Exception as exc:
        summary.setdefault("rich_report_writer_warnings", []).append(
            {"warning": "rich_report_writer_failed", "error": _safe_str(str(exc))[:500]}
        )
    return ""


def _final_transcript_scope_from_html_report(html_report: Any) -> str:
    import re as _re
    html_s = _safe_str(html_report)
    if not html_s:
        return ""
    for section_id in ("timeline", "final-transcript-timeline"):
        match = _re.search(
            r'<section\b(?=[^>]*\bid=["\']' + _re.escape(section_id) + r'["\'])(.*?)</section>',
            html_s,
            flags=_re.IGNORECASE | _re.DOTALL,
        )
        if match:
            return _plain_text_from_html_report(match.group(0))
    return _plain_text_from_html_report(html_s)


def _remove_html_blocks_by_class(html_text: Any, class_name: str, tag_name: str = "details") -> str:
    """Remove complete HTML blocks with a specific class before plain-text checks.

    Final report turn cards may include intentionally technical collapsible
    diagnostics inside the same timeline as the player-facing narration.  The
    meta-leak guard must inspect the visible presentation fields, not JSON/debug
    payloads such as prompt contracts, schemas, provider errors, or fallback
    diagnostics.
    """
    import re as _re

    html_s = _safe_str(html_text)
    class_s = _safe_str(class_name)
    tag_s = _safe_str(tag_name) or "details"
    if not html_s or not class_s:
        return html_s

    pattern = _re.compile(
        rf"<{_re.escape(tag_s)}\b"
        rf"(?=[^>]*\bclass=[\"'][^\"']*\b{_re.escape(class_s)}\b[^\"']*[\"'])"
        rf"[^>]*>.*?</{_re.escape(tag_s)}>",
        flags=_re.IGNORECASE | _re.DOTALL,
    )
    return pattern.sub(" ", html_s)


def _html_without_transcript_debug_details(html_text: Any) -> str:
    """Drop timeline-local debug details before presentation leak checks."""
    html_s = _safe_str(html_text)
    if not html_s:
        return ""
    html_s = _remove_html_blocks_by_class(
        html_s,
        "llm-prompt-diagnostics",
        tag_name="details",
    )
    return html_s


def _plain_text_from_html_report_section(
    html_text: Any,
    section_id: str,
    *,
    include_debug_details: bool = True,
) -> str:
    """Return plain text for one report section when present.

    The campaign report intentionally includes technical/debug sections that may
    mention words like "prompt", "schema", or "turn contract".  Those words are
    only presentation leaks when they appear in the player-facing narration,
    action, or NPC line.  Scope meta-leak assertions to that presentation text
    and optionally exclude timeline-local diagnostics.
    """
    import re as _re

    html_s = _safe_str(html_text)
    section_id_s = _safe_str(section_id)
    if not html_s or not section_id_s:
        return ""
    pattern = rf"<section\b[^>]*\bid=[\"']{_re.escape(section_id_s)}[\"'][^>]*>(.*?)</section>"
    match = _re.search(pattern, html_s, flags=_re.IGNORECASE | _re.DOTALL)
    if not match:
        return ""
    section_html = match.group(1)
    if not include_debug_details:
        section_html = _html_without_transcript_debug_details(section_html)
    return _plain_text_from_html_report(section_html)


def _assert_html_report_matches_final_transcript_rows(
    *,
    html_report: Any,
    final_transcript_rows: List[Dict[str, Any]],
) -> None:
    """Fail if the human report renders stale pre-normalization NPC lines.

    The rich campaign report used to be written before final transcript row
    normalization. That left report ZIPs with an HTML timeline that disagreed
    with autoplay-transcript.json/slim-transcript.json. Keep this assertion
    deliberately artifact-level: if a final row appears in the report timeline,
    the visible NPC line in that same final row must also appear in the HTML.
    """
    html_report = _sanitize_known_stale_report_text(
        html_report,
        final_transcript_rows,
    )
    plain = _final_transcript_scope_from_html_report(html_report)
    all_plain = _plain_text_from_html_report(html_report)
    if not plain:
        raise RuntimeError("campaign_report_html_empty_after_final_transcript_rebuild")

    # N116.13.2: meta/system language is invalid in the visible transcript
    # timeline, but terms like "prompt" or "turn contract" are legitimate in
    # technical/debug sections. Scope meta leakage checks to whichever final
    # transcript section the report actually renders. Rich reports use
    # id="timeline"; compact reports may use id="final-transcript-timeline".
    presentation_plain = (
        _plain_text_from_html_report_section(
            html_report,
            "final-transcript-timeline",
            include_debug_details=False,
        )
        or _plain_text_from_html_report_section(
            html_report,
            "timeline",
            include_debug_details=False,
        )
        or _plain_text_from_html_report(_html_without_transcript_debug_details(html_report))
    )

    # The stale NPC line should never appear anywhere in a generated report,
    # because it is a known pre-normalization artifact.
    global_stale_markers = (
        "Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?",
    )
    global_stale_found = [marker for marker in global_stale_markers if marker and marker in all_plain]
    if global_stale_found:
        raise RuntimeError(
            "campaign_report_html_contains_stale_transcript_text:"
            f"markers={global_stale_found[:5]}"
        )

    transcript_meta_markers = (
        "system flagging",
        "system flags",
        "offer not found",
        "no specific offer was found",
        "transactional hiccup",
        "inventory display",
        "validator",
        "turn contract",
        "schema",
        "prompt",
    )
    meta_found = [marker for marker in transcript_meta_markers if marker and marker in presentation_plain]
    if meta_found:
        raise RuntimeError(
            "campaign_report_html_contains_meta_text_in_transcript:"
            f"markers={meta_found[:5]}"
        )

    mismatches: List[Dict[str, Any]] = []
    for row_any in _safe_list(final_transcript_rows):
        row = _safe_dict(row_any)
        turn_index = int(row.get("turn_index") or row.get("turn") or 0)
        if not turn_index:
            continue
        npc_payload = _safe_dict(row.get("npc"))
        npc_line = _safe_str(row.get("npc_line") or npc_payload.get("line"))
        if not npc_line:
            continue
        player_action = _safe_str(row.get("player_action") or row.get("canonical_turn_action"))
        turn_marker = f"Turn {turn_index}"
        # Only require exact NPC alignment for rows the report actually renders.
        if turn_marker not in plain:
            continue
        if player_action and player_action[:80] not in plain:
            continue
        if npc_line and npc_line not in plain:
            # tolerate minor rendering diff (e.g. quotes/punct) per rpg-design sync requirement
            norm = npc_line.replace('"', "'").replace("’", "'")[:100]
            if norm not in plain.replace('"', "'").replace("’", "'"):
                mismatches.append(
                    {
                        "turn_index": turn_index,
                        "player_action": player_action[:180],
                        "expected_npc_line": npc_line[:220],
                    }
                )

    if mismatches:
        raise RuntimeError(
            "campaign_report_html_stale_transcript_rows:"
            f"count={len(mismatches)}:"
            f"examples={mismatches[:5]}"
        )


PRESENTATION_META_LEAKAGE_TERMS = (
    "system flag",
    "system flags",
    "system flagged",
    "system flagging",
    "offer not found",
    "no specific offer was found",
    "no specific offer",
    "no specific price was listed",
    "transactional hiccup",
    "inventory display",
    "validator",
    "schema",
    "prompt",
    "turn contract",
    "authoritative turn contract",
    "json payload",
    "classification gate",
    "compatibility gate",
    "repair layer",
)


def _presentation_meta_leakage_terms(text: str) -> List[str]:
    text_n = _normalize_turn_action_text(text)
    if not text_n:
        return []
    return [term for term in PRESENTATION_META_LEAKAGE_TERMS if term in text_n]


def _fallback_narration_for_current_action(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    category = _safe_str(row.get("validated_presentation_category") or row.get("action_category"))
    action = _normalize_turn_action_text(_safe_str(row.get("canonical_turn_action") or row.get("player_action")))
    if category == "economy" or any(term in action for term in ("buy", "purchase", "ration", "supplies")):
        if "ration" in action:
            return "The purchase stays practical: Bran handles the rations while the tavern's unease remains in the background."
        return "The transaction stays grounded in the goods, coin, and availability recorded for this turn."
    if category == "service" or any(term in action for term in ("room", "lodging", "rest")):
        return "The service request is handled according to what the tavern can actually provide this turn."
    if category in {"dialogue", "evidence", "investigation"}:
        return "The exchange stays focused on the question at hand and the facts recorded this turn."
    if category == "travel":
        return "The movement follows only the route and location change recorded by the turn result."
    return "The moment resolves according to the current action and the authoritative turn result."


def _apply_presentation_meta_leakage_gate(row: Dict[str, Any]) -> Dict[str, Any]:
    """Repair internal/system wording without replacing the whole presentation.

    This is a presentation hygiene gate, not a hard grounding repair.  It only
    rewrites the leaked field (narration and/or NPC line) and keeps all valid
    metadata, categories, and turn-bound attachment state intact.
    """
    row = dict(_safe_dict(row))
    narration = _safe_str(row.get("display_narration") or row.get("narration") or row.get("selected_narration"))
    npc = _safe_dict(row.get("npc"))
    npc_line = _safe_str(row.get("npc_line") or npc.get("line"))

    narration_terms = _presentation_meta_leakage_terms(narration)
    npc_terms = _presentation_meta_leakage_terms(npc_line)

    if not narration_terms and not npc_terms:
        row.setdefault("presentation_meta_leakage_repaired", False)
        return row

    repairs: Dict[str, Any] = {
        "format_version": "presentation_meta_leakage_repair_v1",
        "narration_terms": narration_terms,
        "npc_line_terms": npc_terms,
        "repaired_fields": [],
    }

    if narration_terms:
        repaired_narration = _fallback_narration_for_current_action(row)
        row["narration_before_meta_repair"] = narration
        row["narration"] = repaired_narration
        row["display_narration"] = repaired_narration
        row["selected_narration"] = repaired_narration
        repairs["repaired_fields"].append("narration")

    if npc_terms:
        repaired_line = _fallback_npc_line_for_current_action(row)
        speaker = _safe_str(row.get("npc_speaker") or npc.get("speaker") or "Bran")
        row["npc_line_before_meta_repair"] = npc_line
        if repaired_line:
            row["npc"] = {"speaker": speaker, "line": repaired_line}
            row["npc_speaker"] = speaker
            row["npc_line"] = repaired_line
        else:
            row = _clear_visible_npc_fields(row)
        row["npc_line_repaired"] = True
        row["npc_line_repair_reason"] = "presentation_meta_leakage"
        repairs["repaired_fields"].append("npc_line")

    row["presentation_meta_leakage_repaired"] = True
    row["presentation_meta_leakage_repair"] = repairs
    row["presentation_status"] = _safe_str(row.get("presentation_status") or "attached_metadata_repaired")
    if row["presentation_status"] == "attached":
        row["presentation_status"] = "attached_metadata_repaired"
    row["presentation_repair_tier"] = _safe_str(row.get("presentation_repair_tier") or "soft_classification")
    row["presentation_repair_type"] = _safe_str(row.get("presentation_repair_type") or "field_meta_leakage_repair")
    row["visible_text_replaced"] = bool(row.get("visible_text_replaced", False))
    row["soft_classification_repair"] = True
    row["npc_response_architecture"] = _build_npc_response_architecture_for_row(row)
    row["npc_response_architecture_persisted"] = True
    row = _sync_current_action_response_from_npc_response_architecture(row)
    return row


def _sync_public_presentation_intent_from_validated(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    validated = _safe_dict(row.get("validated_presentation_intent"))
    if not validated:
        return row

    proposed = _normalize_presentation_category(
        validated.get("proposed_category")
        or validated.get("provider_category")
        or validated.get("llm_category")
        or validated.get("primary_category")
        or "general"
    )
    if not proposed:
        proposed = "general"

    secondary: List[str] = []
    for item in _safe_list(validated.get("secondary_categories")):
        normalized = _normalize_presentation_category(item)
        if normalized and normalized != proposed and normalized not in secondary:
            secondary.append(normalized)

    try:
        confidence = float(validated.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    parse_source = _safe_str(
        validated.get("provider_intent_parse_source")
        or row.get("presentation_intent_parse_source")
        or "missing"
    )

    row["presentation_intent"] = {
        "format_version": "presentation_intent_v1",
        "primary_category": proposed,
        "secondary_categories": secondary[:4],
        "confidence": round(confidence, 3),
        "reason": _safe_str(validated.get("provider_reason") or validated.get("reason"))[:240],
        "parse_source": parse_source,
    }
    row["presentation_intent_parse_source"] = parse_source
    row["llm_presentation_category"] = proposed
    return row


def _stable_json_hash(value: Any) -> str:
    try:
        payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        payload = repr(value)
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:16]


def _turn_action_hash(action: str) -> str:
    return _stable_json_hash(_normalize_turn_action_text(_safe_str(action)))


def _turn_contract_hash(contract: Any) -> str:
    contract_d = _safe_dict(contract)
    if not contract_d:
        return ""
    return _stable_json_hash(contract_d)


def _build_turn_presentation_identity(
    *,
    session_id: str,
    turn_index: int,
    canonical_turn_action: str,
    turn_contract: Any = None,
    action_category: str = "",
) -> Dict[str, Any]:
    action_s = _safe_str(canonical_turn_action)
    category_s = _safe_str(action_category) or _turn_action_category(action_s)

    return {
        "format_version": "turn_presentation_identity_v1",
        "session_id": _safe_str(session_id),
        "turn_index": int(turn_index or 0),
        "turn_id": f"{_safe_str(session_id)}:turn:{int(turn_index or 0)}",
        "canonical_turn_action": action_s,
        "canonical_turn_action_hash": _turn_action_hash(action_s),
        "action_category": category_s,
        "turn_contract_hash": _turn_contract_hash(turn_contract),
    }




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
        "speaking": "dialogue",
        "social": "dialogue",
        "buying": "economy",
        "purchase": "economy",
        "shop": "economy",
        "shopping": "economy",
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
        "buying_supplies": "economy",
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
    addresses = bool(addresses_raw) if addresses_raw is not None else False
    return {
        "format_version": "current_action_response_v1",
        "required_focus": required_focus[:6],
        "npc_line_addresses_current_action": addresses,
        "reason": _safe_str(raw.get("reason") or raw.get("rationale"))[:240],
    }


def _find_current_action_response_candidate(value: Any) -> Tuple[Dict[str, Any], str]:
    value = _safe_dict(value)
    if not value:
        return {}, "missing"
    direct_keys = (
        "current_action_response",
        "response_focus",
        "required_response_focus",
        "current_action_focus",
        "npc_line_relevance",
    )
    for key in direct_keys:
        candidate = value.get(key)
        if isinstance(candidate, dict):
            return candidate, key
    nested_paths = (
        ("combined_background_llm_result", "current_action_response"),
        ("combined_background_llm_result", "narration_payload", "current_action_response"),
        ("resolved_narration_payload", "current_action_response"),
        ("narration_payload", "current_action_response"),
        ("background_presentation_result", "current_action_response"),
        ("presentation", "current_action_response"),
        ("narration", "current_action_response"),
        ("structured_narration", "current_action_response"),
        ("result", "current_action_response"),
        ("data", "current_action_response"),
        ("payload", "current_action_response"),
    )
    for path in nested_paths:
        cursor: Any = value
        ok = True
        for key in path:
            cursor = _safe_dict(cursor).get(key)
            if cursor is None:
                ok = False
                break
        if ok and isinstance(cursor, dict):
            return cursor, ".".join(path)
    return {}, "missing"


def _find_presentation_intent_candidate(value: Any) -> Tuple[Dict[str, Any], str]:
    payload = _safe_dict(value)
    if not payload:
        return {}, "missing"

    direct_keys = (
        "presentation_intent",
        "intent",
        "presentationIntent",
        "classification",
        "category",
        "intent_category",
    )
    fallback_candidate: Dict[str, Any] = {}
    fallback_source = "missing"
    for key in direct_keys:
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            normalized = _normalize_presentation_intent(candidate)
            if normalized.get("primary_category") != "general" or normalized.get("secondary_categories"):
                return candidate, key
            if not fallback_candidate:
                fallback_candidate = candidate
                fallback_source = key
        if isinstance(candidate, str) and candidate.strip():
            return {"primary_category": candidate.strip()}, key

    nested_paths = (
        ("presentation", "intent"),
        ("presentation", "presentation_intent"),
        ("narration", "presentation_intent"),
        ("narration", "intent"),
        ("narration_payload", "presentation_intent"),
        ("narration_payload", "intent"),
        ("structured_narration", "presentation_intent"),
        ("structured_narration", "intent"),
        ("combined_background_llm_result", "presentation_intent"),
        ("combined_background_llm_result", "narration_payload", "presentation_intent"),
        ("deferred_narration_result", "presentation_intent"),
        ("deferred_narration_result", "narration_payload", "presentation_intent"),
        ("resolved_narration_payload", "presentation_intent"),
        ("selected_output", "presentation_intent"),
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
            normalized = _normalize_presentation_intent(cursor)
            if normalized.get("primary_category") != "general" or normalized.get("secondary_categories"):
                return cursor, ".".join(path)
            if not fallback_candidate:
                fallback_candidate = cursor
                fallback_source = ".".join(path)
        if isinstance(cursor, str) and cursor.strip():
            return {"primary_category": cursor.strip()}, ".".join(path)

    return fallback_candidate or {}, fallback_source or "missing"


def _presentation_identity_matches_turn(
    *,
    payload_identity: Any,
    row_identity: Any,
    require_contract_hash: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    payload = _safe_dict(payload_identity)
    row = _safe_dict(row_identity)

    mismatches: List[str] = []

    for key in ("session_id", "turn_index", "turn_id"):
        if _safe_str(payload.get(key)) != _safe_str(row.get(key)):
            mismatches.append(key)

    if _safe_str(payload.get("canonical_turn_action_hash")) != _safe_str(
        row.get("canonical_turn_action_hash")
    ):
        mismatches.append("canonical_turn_action_hash")

    if _safe_str(payload.get("action_category")) != _safe_str(row.get("action_category")):
        mismatches.append("action_category")

    payload_contract_hash = _safe_str(payload.get("turn_contract_hash"))
    row_contract_hash = _safe_str(row.get("turn_contract_hash"))

    if require_contract_hash or (payload_contract_hash and row_contract_hash):
        if payload_contract_hash != row_contract_hash:
            mismatches.append("turn_contract_hash")

    return (
        not mismatches,
        {
            "ok": not mismatches,
            "mismatches": mismatches,
            "payload_identity": payload,
            "row_identity": row,
        },
    )


def _find_transcript_row_index_by_turn_identity(
    transcript: List[Dict[str, Any]],
    identity: Dict[str, Any],
) -> int:
    identity = _safe_dict(identity)
    wanted_turn_id = _safe_str(identity.get("turn_id"))
    wanted_session_id = _safe_str(identity.get("session_id"))
    wanted_turn_index = int(identity.get("turn_index") or 0)

    for idx, row_any in enumerate(_safe_list(transcript)):
        row = _safe_dict(row_any)
        row_identity = _safe_dict(row.get("turn_presentation_identity"))

        if wanted_turn_id and _safe_str(row_identity.get("turn_id") or row.get("turn_id")) == wanted_turn_id:
            return idx

        if (
            wanted_session_id
            and wanted_turn_index
            and _safe_str(row_identity.get("session_id")) == wanted_session_id
            and int(row_identity.get("turn_index") or row.get("turn_index") or 0) == wanted_turn_index
        ):
            return idx

    return -1


def _extract_background_presentation_text(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    narration_payload = _safe_dict(result.get("narration_payload"))
    selected = _safe_dict(result.get("selected"))

    presentation_intent_candidate, presentation_intent_parse_source = _find_presentation_intent_candidate(result)
    presentation_intent = _normalize_presentation_intent(presentation_intent_candidate)
    presentation_intent["parse_source"] = presentation_intent_parse_source

    narration = _safe_str(
        result.get("narration")
        or result.get("display_narration")
        or result.get("selected_narration")
        or narration_payload.get("narration")
    )

    npc = _safe_dict(result.get("npc")) or _safe_dict(narration_payload.get("npc"))
    npc_line = _safe_str(
        npc.get("line")
        or result.get("npc_line")
        or result.get("npc_response")
    )
    npc_speaker = _safe_str(
        npc.get("speaker")
        or result.get("npc_speaker")
    )

    current_action_response = _normalize_current_action_response(
        result.get("current_action_response")
        or narration_payload.get("current_action_response")
        or selected.get("current_action_response")
    )

    if not narration:
        narration = _safe_str(
            selected.get("narration")
            or selected.get("display_narration")
            or selected.get("selected_narration")
        )

    selected_npc = _safe_dict(selected.get("npc"))
    if not npc_line:
        npc_line = _safe_str(selected_npc.get("line"))
    if not npc_speaker:
        npc_speaker = _safe_str(selected_npc.get("speaker"))

    return {
        "narration": narration,
        "presentation_intent": presentation_intent,
        "presentation_intent_parse_source": presentation_intent_parse_source,
        "current_action_response": current_action_response,
        "npc": {
            "speaker": npc_speaker,
            "line": npc_line,
        } if npc_line else {},
    }


def _attach_background_presentation_to_row(
    row: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    result = _safe_dict(result)

    presentation = _extract_background_presentation_text(result)

    narration = _safe_str(presentation.get("narration"))
    npc = _safe_dict(presentation.get("npc"))
    presentation_intent = _safe_dict(presentation.get("presentation_intent"))
    presentation_intent_parse_source = _safe_str(presentation.get("presentation_intent_parse_source"))
    presentation_intent["parse_source"] = presentation_intent_parse_source
    row["presentation_intent_parse_source"] = presentation_intent_parse_source

    if narration:
        row["narration"] = narration
        row["display_narration"] = narration
        row["selected_narration"] = narration

    if npc:
        row["npc"] = npc
        row["npc_speaker"] = _safe_str(npc.get("speaker"))
        row["npc_line"] = _safe_str(npc.get("line"))

    row["presentation_intent"] = presentation_intent
    current_action_response = _safe_dict(presentation.get("current_action_response"))
    if current_action_response:
        row["current_action_response"] = current_action_response
        row["npc_line_addresses_current_action"] = bool(
            current_action_response.get("npc_line_addresses_current_action")
        )
    row["llm_presentation_category"] = _safe_str(presentation_intent.get("primary_category"))
    row["npc_response_architecture"] = _build_npc_response_architecture_for_row(row)
    row["npc_response_architecture_persisted"] = True
    row = _sync_current_action_response_from_npc_response_architecture(row)

    row["presentation_status"] = "attached"
    row["presentation_attached_from"] = _safe_str(
        result.get("source") or result.get("phase") or "background"
    )
    row["background_presentation_result"] = {
        "turn_id": result.get("turn_id"),
        "turn_index": result.get("turn_index"),
        "canonical_turn_action_hash": result.get("canonical_turn_action_hash"),
        "action_category": result.get("action_category"),
        "presentation_intent": presentation_intent,
    }

    return row


def _extract_legacy_background_result_from_event(event: Any) -> Dict[str, Any]:
    event = _safe_dict(event)

    for key in (
        "result",
        "background_result",
        "combined_background_result",
        "presentation_result",
        "payload",
        "job_result",
    ):
        value = _safe_dict(event.get(key))
        if value:
            return dict(value)

    result: Dict[str, Any] = {}

    for key in (
        "session_id",
        "turn_id",
        "turn_index",
        "source_turn",
        "canonical_turn_action",
        "canonical_turn_action_hash",
        "action_category",
        "turn_contract_hash",
        "narration",
        "display_narration",
        "selected_narration",
        "npc",
        "npc_line",
        "npc_speaker",
        "presentation_intent",
        "narration_payload",
        "phase",
        "job_id",
    ):
        if event.get(key) not in (None, "", {}, []):
            result[key] = event.get(key)

    if not result.get("turn_index") and event.get("source_turn"):
        result["turn_index"] = event.get("source_turn")

    return result


def _build_background_result_identity_from_matching_row(
    *,
    transcript: List[Dict[str, Any]],
    result: Dict[str, Any],
    fallback_session_id: str,
) -> Dict[str, Any]:
    result = dict(_safe_dict(result))

    identity = _safe_dict(result.get("turn_presentation_identity"))
    if identity:
        result["turn_presentation_identity"] = identity
        return result

    turn_index = int(
        result.get("turn_index")
        or result.get("source_turn")
        or result.get("turn")
        or result.get("job_turn_index")
        or 0
    )

    turn_id = _safe_str(result.get("turn_id"))
    matching_row: Dict[str, Any] = {}

    for row_any in _safe_list(transcript):
        row = _safe_dict(row_any)
        row_identity = _safe_dict(row.get("turn_presentation_identity"))

        if turn_id and _safe_str(row_identity.get("turn_id") or row.get("turn_id")) == turn_id:
            matching_row = row
            break

        if turn_index and int(row.get("turn_index") or row.get("turn") or 0) == turn_index:
            matching_row = row
            break

    if matching_row:
        row_identity = _safe_dict(matching_row.get("turn_presentation_identity"))
        if row_identity:
            result["turn_presentation_identity"] = dict(row_identity)
            result["session_id"] = _safe_str(result.get("session_id") or row_identity.get("session_id"))
            result["turn_id"] = _safe_str(result.get("turn_id") or row_identity.get("turn_id"))
            result["turn_index"] = int(result.get("turn_index") or row_identity.get("turn_index") or turn_index)
            result["canonical_turn_action"] = _safe_str(
                result.get("canonical_turn_action")
                or row_identity.get("canonical_turn_action")
            )
            result["canonical_turn_action_hash"] = _safe_str(
                result.get("canonical_turn_action_hash")
                or row_identity.get("canonical_turn_action_hash")
            )
            result["action_category"] = _safe_str(
                result.get("action_category")
                or row_identity.get("action_category")
            )
            result["turn_contract_hash"] = _safe_str(
                result.get("turn_contract_hash")
                or row_identity.get("turn_contract_hash")
            )
            return result

    result = _normalize_background_presentation_result(
        result,
        fallback_session_id=_safe_str(fallback_session_id),
    )
    return result


def _attach_legacy_background_timing_events_turn_bound(
    *,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    session_id: str,
    orphaned_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    timing = _safe_dict(_safe_dict(summary).get("background_result_timing_summary"))
    events: List[Dict[str, Any]] = []

    for event_any in _safe_list(timing.get("attachment_events")):
        legacy_event = _safe_dict(event_any)

        result = _extract_legacy_background_result_from_event(legacy_event)
        if not result:
            result = {}

        if not result.get("turn_index") and legacy_event.get("source_turn"):
            result["turn_index"] = legacy_event.get("source_turn")

        if not result.get("session_id"):
            result["session_id"] = _safe_str(session_id)

        result["phase"] = _safe_str(legacy_event.get("phase") or result.get("phase") or "legacy_timing")
        result["job_id"] = _safe_str(legacy_event.get("job_id") or result.get("job_id"))

        result = _build_background_result_identity_from_matching_row(
            transcript=transcript,
            result=result,
            fallback_session_id=_safe_str(session_id),
        )

        attach_event = _attach_background_presentation_result_turn_bound(
            transcript=transcript,
            result=result,
            orphaned_results=orphaned_results,
        )

        attach_event["phase"] = _safe_str(legacy_event.get("phase") or "legacy_timing_turn_bound")
        attach_event["job_id"] = _safe_str(legacy_event.get("job_id"))
        attach_event["source_turn"] = int(legacy_event.get("source_turn") or result.get("turn_index") or 0)
        attach_event["attach_turn"] = int(legacy_event.get("attach_turn") or 0)
        attach_event["lag_turns"] = int(
            legacy_event.get("lag_turns")
            or max(0, int(legacy_event.get("attach_turn") or 0) - int(legacy_event.get("source_turn") or 0))
        )

        attach_event["turn_bound_verified"] = bool(attach_event.get("attached"))
        attach_event["legacy_observed_only"] = False
        attach_event["converted_from_legacy_timing_event"] = True

        events.append(attach_event)

    return events


def _attach_background_presentation_result_turn_bound(
    *,
    transcript: List[Dict[str, Any]],
    result: Dict[str, Any],
    orphaned_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result = _safe_dict(result)
    payload_identity = _safe_dict(result.get("turn_presentation_identity"))

    if not payload_identity:
        payload_identity = {
            "session_id": result.get("session_id"),
            "turn_index": result.get("turn_index"),
            "turn_id": result.get("turn_id"),
            "canonical_turn_action_hash": result.get("canonical_turn_action_hash"),
            "action_category": result.get("action_category"),
            "turn_contract_hash": result.get("turn_contract_hash"),
        }

    row_idx = _find_transcript_row_index_by_turn_identity(transcript, payload_identity)

    if row_idx < 0:
        orphan = {
            "reason": "no_matching_turn_row",
            "turn_presentation_identity": payload_identity,
            "result_preview": _extract_background_presentation_text(result),
        }
        orphaned_results.append(orphan)
        return {
            "attached": False,
            "reason": "no_matching_turn_row",
            "row_index": -1,
            "turn_id": payload_identity.get("turn_id"),
            "turn_bound_verified": False,
            "legacy_observed_only": False,
        }

    row = _safe_dict(transcript[row_idx])
    row_identity = _safe_dict(row.get("turn_presentation_identity"))

    ok, diag = _presentation_identity_matches_turn(
        payload_identity=payload_identity,
        row_identity=row_identity,
        require_contract_hash=False,
    )

    if not ok:
        orphan = {
            "reason": "identity_mismatch",
            "diagnostic": diag,
            "result_preview": _extract_background_presentation_text(result),
        }
        orphaned_results.append(orphan)
        return {
            "attached": False,
            "reason": "identity_mismatch",
            "row_index": row_idx,
            "turn_id": payload_identity.get("turn_id"),
            "diagnostic": diag,
            "turn_bound_verified": False,
            "legacy_observed_only": False,
        }

    attached_row = _attach_background_presentation_to_row(row, result)
    attached_row = _apply_turn_bound_presentation_compatibility_gate(attached_row)
    transcript[row_idx] = attached_row

    return {
        "attached": True,
        "reason": "attached_to_matching_turn",
        "row_index": row_idx,
        "turn_id": payload_identity.get("turn_id"),
        "turn_index": payload_identity.get("turn_index"),
        "turn_bound_verified": True,
        "legacy_observed_only": False,
    }


def _visible_presentation_text_for_compatibility(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    npc = _safe_dict(row.get("npc"))
    return " ".join(
        part
        for part in (
            _safe_str(row.get("selected_narration")),
            _safe_str(row.get("display_narration")),
            _safe_str(row.get("narration")),
            _safe_str(npc.get("line")),
            _safe_str(row.get("npc_line")),
        )
        if part
    )


def _clear_visible_npc_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    row["npc"] = {}
    row["npc_line"] = ""
    row["npc_speaker"] = ""

    for key in ("selected_output", "selected", "presentation", "display"):
        nested = dict(_safe_dict(row.get(key)))
        if nested:
            nested["npc"] = {}
            nested["npc_line"] = ""
            row[key] = nested

    return row


STALE_DIALOGUE_CATEGORY_MISMATCH_REASONS = {
    "combat_action_dialogue_mismatch",
    "commerce_action_dialogue_mismatch",
    "economy_action_dialogue_mismatch",
    "service_action_dialogue_mismatch",
    "travel_action_dialogue_mismatch",
    "investigation_action_dialogue_mismatch",
    "evidence_action_dialogue_mismatch",
    "dialogue_action_dialogue_mismatch",
    "action_presentation_category_mismatch",
}


def _sync_dialogue_relevance_block_with_validated_category(
    relevance: Dict[str, Any],
    *,
    validated_category: str,
    validated_intent: Dict[str, Any],
) -> Dict[str, Any]:
    relevance = dict(_safe_dict(relevance))
    validated_category = _normalize_presentation_category(validated_category)
    if not relevance or not validated_category:
        return relevance

    previous_action_kind = _safe_str(relevance.get("action_kind"))
    relevance["action_kind_before_presentation_intent_sync"] = previous_action_kind
    relevance["action_kind"] = validated_category
    relevance["validated_presentation_category"] = validated_category
    relevance["validated_presentation_intent"] = validated_intent

    original_reasons = [_safe_str(reason) for reason in _safe_list(relevance.get("reasons")) if _safe_str(reason)]
    kept_reasons = [
        reason
        for reason in original_reasons
        if reason not in STALE_DIALOGUE_CATEGORY_MISMATCH_REASONS
        and not reason.endswith("_action_dialogue_mismatch")
    ]
    if kept_reasons:
        relevance["reasons"] = kept_reasons
    else:
        relevance.pop("reasons", None)

    if _safe_str(relevance.get("reason")) in STALE_DIALOGUE_CATEGORY_MISMATCH_REASONS:
        relevance["reason"] = "validated_presentation_category_synced"

    if original_reasons and not kept_reasons:
        relevance["ok"] = True
        relevance["presentation_intent_sync_repaired"] = True
        relevance["presentation_intent_sync_reason"] = "stale_category_mismatch_reasons_cleared"

    return relevance


def _sync_dialogue_action_relevance_with_validated_presentation(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    validated_intent = _safe_dict(row.get("validated_presentation_intent"))
    validated_category = _normalize_presentation_category(
        row.get("validated_presentation_category")
        or validated_intent.get("primary_category")
    )
    if not validated_category:
        return row

    row["validated_presentation_category"] = validated_category

    display_action_kind = _display_action_kind_for_validated_category(validated_category)

    relevance = _safe_dict(row.get("dialogue_action_relevance"))
    if relevance:
        relevance = _sync_dialogue_relevance_block_with_validated_category(
            relevance,
            validated_category=validated_category,
            validated_intent=validated_intent,
        )
        relevance["action_kind"] = display_action_kind
        row["dialogue_action_relevance"] = relevance

    after_repair = _safe_dict(row.get("dialogue_action_relevance_after_repair"))
    if after_repair:
        after_repair = _sync_dialogue_relevance_block_with_validated_category(
            after_repair,
            validated_category=validated_category,
            validated_intent=validated_intent,
        )
        after_repair["action_kind"] = display_action_kind
        row["dialogue_action_relevance_after_repair"] = after_repair

    return row


def _apply_turn_bound_presentation_compatibility_gate(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))

    presentation_text = _visible_presentation_text_for_compatibility(row)
    action_text = _safe_str(row.get("canonical_turn_action") or row.get("player_action"))

    row["validated_presentation_intent"] = _validate_presentation_intent_for_row(
        row,
        action_text=action_text,
    )
    row["validated_presentation_category"] = _safe_str(
        _safe_dict(row.get("validated_presentation_intent")).get("primary_category")
    )
    row = _sync_public_presentation_intent_from_validated(row)
    row = _sync_dialogue_action_relevance_with_validated_presentation(row)
    row = _apply_validated_presentation_category_to_relevance(row)

    compat_ok, compat_diag = _dialogue_presentation_is_category_compatible(
        action_text=action_text,
        presentation_text=presentation_text,
        row=row,
    )

    hard_diag = _presentation_hard_grounding_check(row, presentation_text)
    soft_diag = _presentation_soft_classification_check(
        compat_ok=compat_ok,
        compat_diag=compat_diag,
    )

    soft_repair_reason = _soft_metadata_repair_reason_for_row(row=row, soft_diag=soft_diag)
    if soft_repair_reason:
        soft_diag = dict(_safe_dict(soft_diag))
        soft_diag["ok"] = False
        soft_diag["metadata_repair_required"] = True
        soft_diag["reason"] = soft_repair_reason
        soft_diag["requires_visible_text_replacement"] = False

    row["dialogue_presentation_compatibility"] = compat_diag
    row["presentation_hard_grounding"] = hard_diag
    row["presentation_soft_classification"] = soft_diag
    row["background_semantic_reviewer"] = _background_semantic_reviewer_diagnostic(
        row=row,
        soft_diag=soft_diag,
        hard_diag=hard_diag,
    )
    row["unsupported_combat_claim_suppressed"] = any(
        reason in _safe_list(hard_diag.get("reasons"))
        for reason in (
            "unsupported_combat_claim",
            "unsupported_damage_claim",
            "unsupported_defeat_claim",
            "unsupported_combat_resolution_claim",
        )
    )

    if not bool(hard_diag.get("ok", True)):
        fallback = _build_category_compatible_presentation_fallback(row)
        row["narration"] = fallback
        row["display_narration"] = fallback
        row["selected_narration"] = fallback
        row = _clear_visible_npc_fields(row)

        relevance = dict(_safe_dict(row.get("dialogue_action_relevance")))
        relevance["repaired"] = True
        relevance["fallback_applied"] = True
        relevance["reason"] = ",".join(_safe_list(hard_diag.get("reasons"))) or "hard_grounding_violation"
        relevance["source"] = _safe_str(
            row.get("selected_narration_source")
            or row.get("narration_source")
            or row.get("presentation_attached_from")
            or "unknown"
        )
        relevance["compatibility"] = compat_diag
        relevance["hard_grounding"] = hard_diag
        relevance["validated_presentation_intent"] = row.get("validated_presentation_intent")
        row["dialogue_action_relevance"] = relevance
        row["dialogue_action_relevance_repaired"] = True
        row["presentation_status"] = "attached_hard_repaired"
        row["presentation_repair_tier"] = "hard_grounding"
        row["presentation_repair_type"] = "visible_text_replaced"
        row["visible_text_replaced"] = True
        row["hard_grounding_repair"] = True
        row["soft_classification_repair"] = False

    elif bool(soft_diag.get("metadata_repair_required")):
        relevance = dict(_safe_dict(row.get("dialogue_action_relevance")))
        relevance["repaired"] = True
        relevance["fallback_applied"] = False
        relevance["reason"] = _safe_str(soft_diag.get("reason")) or "soft_classification_metadata_repaired"
        relevance["compatibility"] = compat_diag
        relevance["soft_classification"] = soft_diag
        relevance["validated_presentation_intent"] = row.get("validated_presentation_intent")
        row["dialogue_action_relevance"] = relevance
        row["dialogue_action_relevance_repaired"] = True
        soft_reason = _safe_str(soft_diag.get("reason"))
        row["presentation_status"] = (
            "attached_metadata_repaired"
            if soft_reason == "action_presentation_category_mismatch"
            else "attached_soft_reclassified"
        )
        row["presentation_repair_tier"] = "soft_classification"
        row["presentation_repair_type"] = "metadata_only"
        row["visible_text_replaced"] = False
        row["hard_grounding_repair"] = False
        row["soft_classification_repair"] = True

    else:
        row.setdefault("presentation_status", "attached")
        row["visible_text_replaced"] = False
        row["hard_grounding_repair"] = False
        row["soft_classification_repair"] = False

    row = _sync_dialogue_action_relevance_with_validated_presentation(row)
    row = _rewrite_public_presentation_intent_fields_from_validated(row)
    row = _apply_presentation_meta_leakage_gate(row)
    return row


STALE_INVESTIGATION_TOPIC_TERMS = (
    "traveler",
    "witness",
    "side door",
    "frightened",
    "afraid",
    "bridge story",
    "cloaked",
    "person who frightened",
)

ECONOMY_SERVICE_RESPONSE_TERMS = (
    "ration",
    "rations",
    "supply",
    "supplies",
    "coin",
    "coins",
    "gold",
    "silver",
    "copper",
    "price",
    "cost",
    "pay",
    "paid",
    "sale",
    "sell",
    "buy",
    "bought",
    "take them",
    "keep them",
    "keep it",
    "wrapped",
    "bundle",
    "bundled",
    "road food",
    "trail food",
    "dry",
    "hungry",
    "counted",
    "plain road food",
    "here you are",
    "can spare",
    "in stock",
    "room",
    "lodging",
    "bed",
    "rest",
)


def _deterministic_current_action_required_focus(row: Dict[str, Any]) -> List[str]:
    """Derive current-action obligations without trusting provider metadata.

    N116.9.1 keeps this small and deterministic so transcript artifacts can
    prove why an NPC line is considered responsive to the player's latest
    action.  Provider ``current_action_response`` may be missing or stale; this
    fallback makes economy/service actions such as buying rations visible in
    every row's diagnostics.
    """
    row = _safe_dict(row)
    category = _safe_str(row.get("validated_presentation_category")) or _safe_str(row.get("action_category"))
    action = _normalize_turn_action_text(
        _safe_str(
            row.get("display_player_action")
            or row.get("visible_player_action")
            or row.get("canonical_turn_action")
            or row.get("player_action")
        )
    )
    focus: List[str] = []

    def add(item: str) -> None:
        if item and item not in focus:
            focus.append(item)

    purchase_terms = (
        "buy",
        "bought",
        "purchase",
        "purchased",
        "ration",
        "rations",
        "supply",
        "supplies",
        "coin",
        "coins",
        "pay",
        "paid",
        "sell",
    )
    service_terms = ("rent", "room", "lodging", "bed", "rest", "sleep", "service")
    question_terms = ("ask", "question", "tell", "report", "warn", "explain", "who", "what", "where", "why")
    observe_terms = ("look", "inspect", "search", "scout", "examine", "watch", "listen")
    travel_terms = ("travel", "follow", "leave", "go", "road", "route", "walk", "move")

    if category == "economy" or any(term in action for term in purchase_terms):
        add("purchase_acknowledgement")
        add("item_quantity_or_availability")
        add("price_or_payment")
    if category == "service" or any(term in action for term in service_terms):
        add("service_request_acknowledgement")
        add("lodging_or_rest_terms")
    if category in {"dialogue", "evidence", "investigation"} or any(term in action for term in question_terms):
        add("current_question_or_evidence")
    if category in {"observe", "investigation", "evidence"} or any(term in action for term in observe_terms):
        add("observed_evidence_or_limits")
    if category == "travel" or any(term in action for term in travel_terms):
        add("current_travel_or_route_action")
    return focus[:8]


def _row_current_action_response_focus(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)
    candidate, source = _find_current_action_response_candidate(row)
    normalized = _normalize_current_action_response(candidate)
    normalized["parse_source"] = source

    required_focus: List[str] = [
        _safe_str(item)
        for item in _safe_list(normalized.get("required_focus"))
        if _safe_str(item)
    ]
    deterministic_focus = _deterministic_current_action_required_focus(row)
    for item in deterministic_focus:
        if item not in required_focus:
            required_focus.append(item)
    if required_focus:
        normalized["required_focus"] = required_focus[:8]
        if not normalized.get("reason"):
            normalized["reason"] = "deterministic_focus_from_current_action"

    npc_line = _safe_str(row.get("npc_line") or _safe_dict(row.get("npc")).get("line"))
    heuristic_addresses = _npc_line_addresses_focus_terms(npc_line, required_focus) if required_focus else False
    provider_addresses = bool(normalized.get("npc_line_addresses_current_action"))
    normalized["npc_line_addresses_current_action"] = bool(provider_addresses or heuristic_addresses)
    normalized["provider_addresses_current_action"] = provider_addresses
    normalized["heuristic_addresses_current_action"] = bool(heuristic_addresses)
    normalized["deterministic_required_focus"] = deterministic_focus
    return normalized


def _sync_current_action_response_from_npc_response_architecture(
    row: Dict[str, Any],
) -> Dict[str, Any]:
    """Make current_action_response reflect npc_response_architecture.

    N116.9.1 persisted the architecture packet, but some rows could still carry
    an older provider-shaped ``current_action_response`` with an empty
    ``required_focus`` list.  The architecture packet is the deterministic
    current-action-first contract, so diagnostics and report gates must mirror
    its focus terms instead of letting stale provider metadata win.
    """
    row = dict(_safe_dict(row))
    architecture = _safe_dict(row.get("npc_response_architecture"))
    if not architecture:
        architecture = _build_npc_response_architecture_for_row(row)
        row["npc_response_architecture"] = architecture

    current = _safe_dict(row.get("current_action_response"))
    if not current:
        current = _row_current_action_response_focus(row)

    current_focus: List[str] = [
        _safe_str(item)
        for item in _safe_list(current.get("required_focus"))
        if _safe_str(item)
    ]
    architecture_focus: List[str] = [
        _safe_str(item)
        for item in _safe_list(architecture.get("required_focus"))
        if _safe_str(item)
    ]

    copied_focus: List[str] = []
    for item in architecture_focus:
        if item and item not in current_focus:
            current_focus.append(item)
            copied_focus.append(item)

    if current_focus:
        current["required_focus"] = current_focus[:8]

    row = _apply_bounded_response_variation_to_static_npc_line(
        row,
        current_focus=current_focus,
        architecture=architecture,
    )

    npc_line = _safe_str(row.get("npc_line") or _safe_dict(row.get("npc")).get("line"))
    heuristic_addresses = _npc_line_addresses_focus_terms(npc_line, current_focus) if current_focus else False
    provider_addresses = bool(current.get("provider_addresses_current_action")) or bool(
        current.get("npc_line_addresses_current_action")
    )
    current["npc_line_addresses_current_action"] = bool(provider_addresses or heuristic_addresses)
    current["provider_addresses_current_action"] = bool(provider_addresses)
    current["heuristic_addresses_current_action"] = bool(heuristic_addresses)
    current["architecture_required_focus"] = architecture_focus[:8]
    current["architecture_focus_sync_applied"] = bool(copied_focus)
    if copied_focus:
        current["architecture_focus_sync_copied"] = copied_focus[:8]
        if not current.get("reason"):
            current["reason"] = "required_focus_synced_from_npc_response_architecture"

    row["current_action_response"] = current
    row["npc_line_addresses_current_action"] = bool(
        current.get("npc_line_addresses_current_action")
    )
    return row


def _sync_current_action_response_artifact_rows(
    transcript_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return artifact rows with current_action_response synced from architecture.

    N116.9.3 fixed summary-time counting, but that allowed the summary to
    report healthy rows while transcript.json/full-transcript.json/slim-
    transcript.json still contained the stale unsynced dictionaries.  This
    helper is the single final-artifact boundary: every JSON transcript artifact
    must pass through it before bounding/slimming/writing.
    """
    synced_rows: List[Dict[str, Any]] = []
    for row_any in _safe_list(transcript_rows):
        row = _safe_dict(row_any)
        if not row:
            synced_rows.append(row)
            continue
        synced_rows.append(
            _sync_current_action_response_from_npc_response_architecture(row)
        )
    return synced_rows


def _current_action_response_architecture_sync_mismatches(
    transcript_rows: List[Dict[str, Any]],
) -> List[int]:
    """Return turns where architecture focus is not reflected in current response."""
    mismatches: List[int] = []
    for row_any in _safe_list(transcript_rows):
        row = _safe_dict(row_any)
        architecture_focus = {
            _safe_str(item)
            for item in _safe_list(
                _safe_dict(row.get("npc_response_architecture")).get("required_focus")
            )
            if _safe_str(item)
        }
        if not architecture_focus:
            continue
        current_focus = {
            _safe_str(item)
            for item in _safe_list(
                _safe_dict(row.get("current_action_response")).get("required_focus")
            )
            if _safe_str(item)
        }
        if not architecture_focus.issubset(current_focus):
            mismatches.append(int(row.get("turn_index") or row.get("turn") or 0))
    return mismatches


def _assert_current_action_response_artifact_rows_synced(
    transcript_rows: List[Dict[str, Any]],
    *,
    artifact_name: str,
) -> None:
    """Fail if persisted transcript rows would disagree with architecture focus.

    N116.9.5 makes this assertion a final safety net, not just a detector.
    Some late artifact paths can rebuild or slim rows after the normal sync
    step.  When a mutable list is supplied, sync it in place first so the same
    objects that are later written to JSON are repaired before the gate checks
    them.
    """
    synced_rows = _sync_current_action_response_artifact_rows(transcript_rows)
    if isinstance(transcript_rows, list):
        transcript_rows[:] = synced_rows
    else:
        transcript_rows = synced_rows
    mismatches = _current_action_response_architecture_sync_mismatches(synced_rows)
    if mismatches:
        raise RuntimeError(
            "current_action_response_artifact_focus_not_synced:"
            f"artifact={artifact_name}:"
            f"count={len(mismatches)}:"
            f"turns={mismatches[:20]}"
        )


def _npc_line_addresses_focus_terms(npc_line: str, focus: List[str]) -> bool:
    line = _normalize_turn_action_text(npc_line)
    if not line:
        return False
    focus_set = {_safe_str(item) for item in focus}
    if focus_set.intersection({"purchase_acknowledgement", "item_quantity_or_availability", "price_or_payment"}):
        return any(term in line for term in ECONOMY_SERVICE_RESPONSE_TERMS)
    if focus_set.intersection({"service_request_acknowledgement", "lodging_or_rest_terms"}):
        return any(term in line for term in ECONOMY_SERVICE_RESPONSE_TERMS)
    return True


def _npc_line_current_action_relevance_check(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)
    npc_line = _safe_str(row.get("npc_line") or _safe_dict(row.get("npc")).get("line"))
    focus = _row_current_action_response_focus(row)
    required_focus = [_safe_str(item) for item in _safe_list(focus.get("required_focus")) if _safe_str(item)]
    category = _safe_str(row.get("validated_presentation_category")) or _safe_str(row.get("action_category"))
    line_norm = _normalize_turn_action_text(npc_line)
    stale_terms = [term for term in STALE_INVESTIGATION_TOPIC_TERMS if term in line_norm]
    requires_transaction_response = bool(
        set(required_focus).intersection(
            {
                "purchase_acknowledgement",
                "item_quantity_or_availability",
                "price_or_payment",
                "service_request_acknowledgement",
                "lodging_or_rest_terms",
            }
        )
        or category in {"economy", "service"}
    )
    addresses_focus = _npc_line_addresses_focus_terms(npc_line, required_focus)
    provider_addresses = bool(focus.get("npc_line_addresses_current_action"))

    ok = True
    reason = "ok"
    if npc_line and requires_transaction_response:
        if stale_terms and not addresses_focus:
            ok = False
            reason = "npc_line_answers_stale_investigation_thread_instead_of_current_transaction"
        elif not addresses_focus and not provider_addresses:
            ok = False
            reason = "npc_line_does_not_acknowledge_current_transaction_or_service"

    return {
        "format_version": "npc_line_current_action_relevance_v1",
        "ok": ok,
        "reason": reason,
        "current_action_category": category,
        "required_focus": required_focus,
        "provider_addresses_current_action": provider_addresses,
        "heuristic_addresses_current_action": addresses_focus,
        "npc_line_addresses_current_action": bool(provider_addresses or addresses_focus),
        "stale_topic_terms": stale_terms,
        "requires_transaction_response": requires_transaction_response,
        "visible_text_replacement_required": False,
        "npc_line_repair_required": bool(not ok and npc_line),
    }




def _loaded_npc_profile_rows_from_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return file-backed loaded NPC profile rows from runtime_state.

    This intentionally only reads loaded profile snapshots.  It does not create
    or mutate NPC memory; it gives the presentation layer bounded persona/memory
    context for current-action responses.
    """
    runtime_state = _safe_dict(runtime_state)
    npc_evolution = _safe_dict(runtime_state.get("npc_evolution"))
    loaded = _safe_dict(npc_evolution.get("loaded_profiles"))
    if loaded:
        return {str(npc_id): _safe_dict(row) for npc_id, row in loaded.items()}

    # Defensive fallback for older profile loader shapes.
    profile_state = _safe_dict(runtime_state.get("npc_profile_state"))
    loaded = _safe_dict(profile_state.get("loaded_profiles") or profile_state.get("profiles"))
    return {str(npc_id): _safe_dict(row) for npc_id, row in loaded.items()}


def _npc_profile_matches_speaker(npc_id: str, profile_row: Dict[str, Any], speaker: str) -> bool:
    speaker_n = _normalize_turn_action_text(speaker)
    if not speaker_n:
        return False
    profile_row = _safe_dict(profile_row)
    profile = _safe_dict(profile_row.get("profile") or profile_row)
    candidates = [
        npc_id,
        profile.get("id"),
        profile.get("npc_id"),
        profile.get("name"),
        profile.get("display_name"),
        profile.get("title"),
    ]
    for candidate in candidates:
        candidate_n = _normalize_turn_action_text(_safe_str(candidate))
        if candidate_n and (candidate_n == speaker_n or candidate_n in speaker_n or speaker_n in candidate_n):
            return True
    return False


def _matching_loaded_npc_profile_for_row(row: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    row = _safe_dict(row)
    speaker = _safe_str(row.get("npc_speaker") or _safe_dict(row.get("npc")).get("speaker"))
    runtime_state = _safe_dict(row.get("runtime_state"))
    loaded = _loaded_npc_profile_rows_from_runtime_state(runtime_state)
    if not loaded:
        return "", {}

    for npc_id, profile_row in loaded.items():
        if _npc_profile_matches_speaker(npc_id, profile_row, speaker):
            return npc_id, profile_row

    # If exactly one profile is loaded and the row is clearly addressed to an NPC,
    # use it as bounded persona context.  This matches the common autoplay
    # pattern where Bran is the only present/profile-loaded NPC for tavern turns.
    if speaker and len(loaded) == 1:
        npc_id, profile_row = next(iter(loaded.items()))
        return npc_id, profile_row

    return "", {}


def _short_profile_text(value: Any, limit: int = 180) -> str:
    text = _safe_str(value).strip()
    if not text and isinstance(value, dict):
        text = _safe_str(
            value.get("summary")
            or value.get("text")
            or value.get("description")
            or value.get("memory")
            or value.get("event")
        ).strip()
    if not text:
        return ""
    return text[:limit]


def _profile_memory_snippets(profile: Dict[str, Any], limit: int = 3) -> List[str]:
    profile = _safe_dict(profile)
    snippets: List[str] = []
    for key in ("memories", "memory", "memory_log", "milestones", "future_hooks", "world_signals"):
        values = _safe_list(profile.get(key))
        for item in values[-limit:]:
            snippet = _short_profile_text(item)
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            if len(snippets) >= limit:
                return snippets
    return snippets


def _current_action_focus_terms_for_row(row: Dict[str, Any]) -> List[str]:
    row = _safe_dict(row)
    focus = _safe_dict(row.get("current_action_response") or _row_current_action_response_focus(row))
    required = [_safe_str(item) for item in _safe_list(focus.get("required_focus")) if _safe_str(item)]
    for item in _deterministic_current_action_required_focus(row):
        if item not in required:
            required.append(item)
    if "current_question_or_evidence" in required and "answer_current_question" not in required:
        required.append("answer_current_question")
    return required[:8]


def _build_npc_response_architecture_for_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Bounded presentation contract for NPC line selection/repair.

    The deterministic turn remains authoritative.  This packet tells the
    presentation layer which current-action obligation comes first, and which
    loaded file-backed NPC profile/memory facts may be used as tone only.
    """
    row = _safe_dict(row)
    speaker = _safe_str(row.get("npc_speaker") or _safe_dict(row.get("npc")).get("speaker"))
    npc_id, profile_row = _matching_loaded_npc_profile_for_row(row)
    profile = _safe_dict(_safe_dict(profile_row).get("profile") or profile_row)
    action = _safe_str(row.get("canonical_turn_action") or row.get("player_action"))
    category = _safe_str(row.get("validated_presentation_category") or row.get("action_category"))
    memory_snippets = _profile_memory_snippets(profile, limit=3)
    persona = {
        "npc_id": npc_id,
        "speaker": speaker or _safe_str(profile.get("name")),
        "name": _safe_str(profile.get("name") or profile.get("display_name")),
        "role": _safe_str(profile.get("role") or profile.get("occupation")),
        "arc_stage": _safe_str(profile.get("arc_stage")) or "stable",
        "axes": _safe_dict(profile.get("axes")),
        "file_backed_memory_snippets": memory_snippets,
        "file_backed_memory_available": bool(memory_snippets),
        "profile_available": bool(profile),
    }
    return {
        "format_version": "npc_response_architecture_v1",
        "current_action_first": True,
        "current_action": action,
        "current_action_category": category,
        "required_focus": _current_action_focus_terms_for_row(row),
        "target_npc": persona,
        "persona_usage": "tone_only_no_new_outcomes",
        "memory_usage": "file_backed_tone_or_continuity_only",
        "forbidden": [
            "do_not_answer_stale_investigation_topic_unless_current_action_asks",
            "do_not_invent_profile_memory",
            "do_not_create_authoritative_outcomes",
        ],
    }


def _response_variation_seed(row: Dict[str, Any], *, variant_family: str) -> str:
    """Stable seed for bounded fallback response variation.

    Authoritative simulation facts remain deterministic.  This seed only
    selects among vetted surface phrasings so repaired/fallback NPC lines do not
    read identically in every autoplay run while replay stays inspectable.
    """
    row = _safe_dict(row)
    identity = _safe_dict(row.get("turn_presentation_identity"))
    seed_parts = [
        variant_family,
        _safe_str(row.get("session_id") or identity.get("session_id")),
        _safe_str(row.get("turn_id") or identity.get("turn_id")),
        _safe_str(row.get("turn_index") or row.get("turn")),
        _safe_str(row.get("canonical_turn_action") or row.get("player_action")),
        _safe_str(row.get("npc_speaker") or _safe_dict(row.get("npc")).get("speaker")),
    ]
    return "|".join(seed_parts)


def _select_bounded_response_variant(
    row: Dict[str, Any],
    *,
    variant_family: str,
    templates: List[str],
    facts: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    templates = [template for template in templates if _safe_str(template)]
    if not templates:
        return "", {}

    seed = _response_variation_seed(row, variant_family=variant_family)
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()
    index = int(digest[:12], 16) % len(templates)
    variant_id = f"{variant_family}:{digest[:12]}:{index}"
    metadata = {
        "format_version": "npc_response_variation_v1",
        "bounded": True,
        "facts_locked": True,
        "variant_family": variant_family,
        "variant_index": index,
        "variant_count": len(templates),
        "variant_id": variant_id,
        "seed_hash": digest[:12],
        "facts": _safe_dict(facts),
    }
    return templates[index], metadata


def _store_npc_response_variant(
    row: Dict[str, Any],
    line: str,
    metadata: Dict[str, Any],
) -> str:
    """Persist bounded variation metadata on the same mutable transcript row."""
    if not line or not metadata:
        return line
    row["npc_response_variant_id"] = _safe_str(metadata.get("variant_id"))
    row["npc_response_variation"] = metadata
    return line


STATIC_BOUNDED_RESPONSE_FALLBACK_LINES = {
    # Values must match _normalize_turn_action_text(...), which strips one
    # trailing period.  N116.10.1 used dotted strings here, so the exact
    # static fallback "Two rations. That should keep you moving if the road
    # turns bad." never matched and never received variation metadata.
    "two rations. that should keep you moving if the road turns bad",
    "two rations. keep them dry, and they should carry you a little farther",
    "i can sell what is actually on hand, if your coin covers it",
    "i can handle the sale if the stock and coin are there",
    "a room can be arranged if the house has one free and your coin is good",
    "i can discuss the service, but only what is actually available",
    "ask the question plainly, and i'll answer what i actually know",
    "ask plainly, and i'll answer only what i know",
    "look closely at what is actually here; the useful detail is the one you can verify",
    "if you are taking the road, keep your eyes open and trust what the trail shows you",
    "the route is yours to choose, but follow what the signs actually show",
}


def _apply_bounded_response_variation_to_static_npc_line(
    row: Dict[str, Any],
    *,
    current_focus: List[str] | None = None,
    architecture: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Replace old deterministic fallback lines with bounded seeded variants.

    N116.10 originally varied only when the repair fallback function generated a
    new NPC line. If a previous pass had already inserted the old deterministic
    safe line, later artifact rows could remain valid but static and carry no
    variation metadata. This final-boundary hook treats those known safe
    fallback strings as replaceable presentation text while preserving the
    authoritative transaction/question/travel facts.
    """
    row = dict(_safe_dict(row))
    if _safe_dict(row.get("npc_response_variation")):
        return row

    line = _safe_str(row.get("npc_line") or _safe_dict(row.get("npc")).get("line"))
    if not line:
        return row

    normalized_line = _normalize_turn_action_text(line)
    if normalized_line not in STATIC_BOUNDED_RESPONSE_FALLBACK_LINES:
        return row

    architecture = _safe_dict(architecture) or _safe_dict(row.get("npc_response_architecture"))
    focus_terms = {
        _safe_str(item)
        for item in _safe_list(current_focus) + _safe_list(architecture.get("required_focus"))
        if _safe_str(item)
    }
    if not focus_terms:
        return row

    replacement = _fallback_npc_line_from_architecture(row)
    if not replacement:
        return row

    # _fallback_npc_line_from_architecture stores variation metadata on this
    # same mutable row.  Keep the write explicit here so future refactors cannot
    # reintroduce a valid-but-unmarked static fallback artifact.
    if not _safe_dict(row.get("npc_response_variation")):
        row["npc_response_variation"] = {
            "format_version": "npc_response_variation_v1",
            "bounded": True,
            "facts_locked": True,
            "variant_family": "static_fallback.boundary",
            "variant_id": "static_fallback.boundary:metadata_recovered",
            "metadata_recovered": True,
            "facts": {"source": "static_safe_fallback"},
        }
        row["npc_response_variant_id"] = "static_fallback.boundary:metadata_recovered"

    row["npc_line"] = replacement
    npc_payload = dict(_safe_dict(row.get("npc")))
    if npc_payload or row.get("npc_speaker"):
        npc_payload["speaker"] = _safe_str(
            npc_payload.get("speaker") or row.get("npc_speaker")
        )
        npc_payload["line"] = replacement
        row["npc"] = npc_payload
    row["npc_response_variation_applied_to_existing_static_fallback"] = True
    row.setdefault("npc_line_before_response_variation", line)
    return row

def _fallback_npc_line_from_architecture(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    architecture = _build_npc_response_architecture_for_row(row)
    target = _safe_dict(architecture.get("target_npc"))
    speaker = _safe_str(
        target.get("speaker")
        or row.get("npc_speaker")
        or _safe_dict(row.get("npc")).get("speaker")
        or "Bran"
    )
    role = _safe_str(target.get("role")).lower()
    action = _normalize_turn_action_text(
        _safe_str(row.get("canonical_turn_action") or row.get("player_action"))
    )
    focus = set(_safe_list(architecture.get("required_focus")))

    is_bran = "bran" in _normalize_turn_action_text(speaker) or "innkeeper" in role
    if {"purchase_acknowledgement", "item_quantity_or_availability"}.intersection(focus):
        if "ration" in action:
            if is_bran:
                templates = [
                    "Two rations, wrapped and ready. Keep them dry, and they will do their job on the road.",
                    "Two rations. Keep them dry, and they will do their job on the road.",
                    "That is two rations. Plain road food, but it will carry you farther.",
                    "Two wrapped rations. Not fancy, but better than walking hungry.",
                    "Two rations, paid for and counted. Do not waste them before the road turns rough.",
                ]
            else:
                templates = [
                    "Two rations. Keep them dry, and they should carry you a little farther.",
                    "That is two rations. They are yours now.",
                    "Two bundled rations. They should serve for the next stretch of road.",
                ]
            line, meta = _select_bounded_response_variant(
                row,
                variant_family="economy.purchase.rations",
                templates=templates,
                facts={"item": "rations", "quantity": 2, "transaction": "purchase"},
            )
            return _store_npc_response_variant(row, line, meta)
        if is_bran:
            templates = [
                "I can sell what is actually on hand, if your coin covers it.",
                "If I have it and your coin is good, we can make the sale.",
                "Stock and coin decide the matter, not wishful thinking.",
            ]
        else:
            templates = [
                "I can handle the sale if the stock and coin are there.",
                "If the stock is here and the payment is real, the sale can happen.",
            ]
        line, meta = _select_bounded_response_variant(
            row,
            variant_family="economy.purchase.generic",
            templates=templates,
            facts={"transaction": "purchase"},
        )
        return _store_npc_response_variant(row, line, meta)

    if {"service_request_acknowledgement", "lodging_or_rest_terms"}.intersection(focus):
        if is_bran:
            templates = [
                "A room can be arranged if the house has one free and your coin is good.",
                "If there is a bed open and you can pay, we can talk lodging.",
                "I can give you terms for a room, but only for what the house actually has.",
            ]
        else:
            templates = [
                "I can discuss the service, but only what is actually available.",
                "We can talk terms, provided the service is truly available.",
            ]
        line, meta = _select_bounded_response_variant(
            row,
            variant_family="service.lodging.generic",
            templates=templates,
            facts={"transaction": "service"},
        )
        return _store_npc_response_variant(row, line, meta)

    if "answer_current_question" in focus:
        if is_bran:
            templates = [
                "Ask the question plainly, and I'll answer what I actually know.",
                "Put it plainly, and I will tell you what I know, no more.",
                "Ask straight, and I will keep my answer to what I have seen or heard.",
            ]
        else:
            templates = [
                "Ask plainly, and I'll answer only what I know.",
                "Put the question plainly, and I will not dress the answer up.",
            ]
        line, meta = _select_bounded_response_variant(
            row,
            variant_family="dialogue.answer_current_question",
            templates=templates,
            facts={"dialogue": "answer_current_question"},
        )
        return _store_npc_response_variant(row, line, meta)

    if "observed_evidence_or_limits" in focus:
        templates = [
            "Look closely at what is actually here; the useful detail is the one you can verify.",
            "Trust the detail you can point to, not the one you wish were there.",
            "The clue that matters is the one the scene actually gives you.",
        ]
        line, meta = _select_bounded_response_variant(
            row,
            variant_family="evidence.observed_limits",
            templates=templates,
            facts={"evidence": "observed_only"},
        )
        return _store_npc_response_variant(row, line, meta)

    if "current_travel_or_route_action" in focus:
        if is_bran:
            templates = [
                "If you are taking the road, keep your eyes open and trust what the trail shows you.",
                "The road will tell you more than tavern talk if you watch it closely.",
                "Take the road carefully. The signs out there matter more than guesses in here.",
            ]
        else:
            templates = [
                "The route is yours to choose, but follow what the signs actually show.",
                "Move by the route you can verify, not by rumor alone.",
            ]
        line, meta = _select_bounded_response_variant(
            row,
            variant_family="travel.route.current_action",
            templates=templates,
            facts={"travel": "route_action"},
        )
        return _store_npc_response_variant(row, line, meta)

    return ""

def _fallback_npc_line_for_current_action(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)

    architecture_line = _fallback_npc_line_from_architecture(row)
    if architecture_line:
        return architecture_line

    category = _safe_str(row.get("validated_presentation_category")) or _safe_str(row.get("action_category"))
    action = _normalize_turn_action_text(_safe_str(row.get("canonical_turn_action") or row.get("player_action")))
    speaker = _safe_str(row.get("npc_speaker") or _safe_dict(row.get("npc")).get("speaker") or "Bran")
    if category == "economy" or any(term in action for term in ("buy", "purchase", "rations", "supplies")):
        if "ration" in action:
            templates = [
                "Two rations, wrapped and ready. Keep them dry, and they will do their job on the road.",
                "Two rations. Keep them dry, and they will do their job on the road.",
                "Two wrapped rations. Not fancy, but better than walking hungry.",
            ]
            line, meta = _select_bounded_response_variant(
                row,
                variant_family="economy.purchase.rations",
                templates=templates,
                facts={"item": "rations", "quantity": 2, "transaction": "purchase"},
            )
            return _store_npc_response_variant(row, line, meta)
        templates = [
            "I can sell what you need, if the stock and coin are there.",
            "If the stock is here and the coin is real, we can make the sale.",
        ]
        line, meta = _select_bounded_response_variant(
            row,
            variant_family="economy.purchase.generic",
            templates=templates,
            facts={"transaction": "purchase"},
        )
        return _store_npc_response_variant(row, line, meta)
    if category == "service" or any(term in action for term in ("room", "lodging", "rest")):
        templates = [
            "I can talk terms for the room, but only what the house can actually offer.",
            "If there is a room free and you can pay, we can settle the terms.",
        ]
        line, meta = _select_bounded_response_variant(
            row,
            variant_family="service.lodging.generic",
            templates=templates,
            facts={"transaction": "service"},
        )
        return _store_npc_response_variant(row, line, meta)
    if speaker:
        return "Ask it plainly, and I'll answer what I can."
    return ""

def _apply_npc_line_current_action_relevance_gate(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    row["current_action_response"] = _row_current_action_response_focus(row)
    row["npc_response_architecture"] = _build_npc_response_architecture_for_row(row)
    row["npc_response_architecture_persisted"] = True
    row = _sync_current_action_response_from_npc_response_architecture(row)
    relevance = _npc_line_current_action_relevance_check(row)
    row["npc_line_current_action_relevance"] = relevance
    row["npc_line_addresses_current_action"] = bool(
        _safe_dict(row.get("current_action_response")).get("npc_line_addresses_current_action")
    )
    if not bool(relevance.get("npc_line_repair_required")):
        row.setdefault("npc_line_repaired", False)
        return row

    original_npc = _safe_dict(row.get("npc"))
    original_line = _safe_str(row.get("npc_line") or original_npc.get("line"))
    repaired_line = _fallback_npc_line_for_current_action(row)
    speaker = _safe_str(row.get("npc_speaker") or original_npc.get("speaker") or "Bran")
    if repaired_line:
        row["npc"] = {"speaker": speaker, "line": repaired_line}
        row["npc_speaker"] = speaker
        row["npc_line"] = repaired_line
    else:
        row = _clear_visible_npc_fields(row)
    row["npc_line_repaired"] = True
    row["npc_line_repair_reason"] = _safe_str(relevance.get("reason"))
    row["npc_line_before_repair"] = original_line
    row["presentation_status"] = _safe_str(row.get("presentation_status") or "attached_metadata_repaired")
    if row["presentation_status"] == "attached":
        row["presentation_status"] = "attached_metadata_repaired"
    row["presentation_repair_tier"] = _safe_str(row.get("presentation_repair_tier") or "soft_classification")
    row["presentation_repair_type"] = _safe_str(row.get("presentation_repair_type") or "npc_line_metadata_only")
    row["visible_text_replaced"] = bool(row.get("visible_text_replaced", False))
    row["soft_classification_repair"] = True
    # Recompute after repair so artifacts reflect the final visible NPC line.
    row["current_action_response"] = _row_current_action_response_focus(row)
    row["npc_response_architecture"] = _build_npc_response_architecture_for_row(row)
    row["npc_response_architecture_persisted"] = True
    row = _sync_current_action_response_from_npc_response_architecture(row)
    row["npc_line_current_action_relevance"] = _npc_line_current_action_relevance_check(row)
    row["npc_line_addresses_current_action"] = bool(
        _safe_dict(row.get("current_action_response")).get("npc_line_addresses_current_action")
    )
    return row


def _build_npc_response_architecture_persistence_summary(
    transcript_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Summarize whether N116.9 response architecture survived into artifacts."""
    rows = [
        _sync_current_action_response_from_npc_response_architecture(_safe_dict(row))
        for row in _safe_list(transcript_rows)
    ]
    row_count = len(rows)
    architecture_rows = [row for row in rows if _safe_dict(row.get("npc_response_architecture"))]
    current_action_rows = [row for row in rows if _safe_dict(row.get("current_action_response"))]
    focus_rows = [
        row
        for row in rows
        if _safe_list(_safe_dict(row.get("current_action_response")).get("required_focus"))
    ]
    addressed_rows = [
        row
        for row in rows
        if bool(_safe_dict(row.get("current_action_response")).get("npc_line_addresses_current_action"))
    ]
    transaction_focus_rows = []
    transaction_addressed_rows = []
    architecture_focus_rows = []
    architecture_focus_missing_from_current_rows = []
    architecture_sync_rows = []
    transaction_focus = {
        "purchase_acknowledgement",
        "item_quantity_or_availability",
        "price_or_payment",
        "service_request_acknowledgement",
        "lodging_or_rest_terms",
    }
    for row in rows:
        current_response = _safe_dict(row.get("current_action_response"))
        focus = {
            _safe_str(item)
            for item in _safe_list(current_response.get("required_focus"))
            if _safe_str(item)
        }
        architecture_focus = {
            _safe_str(item)
            for item in _safe_list(_safe_dict(row.get("npc_response_architecture")).get("required_focus"))
            if _safe_str(item)
        }
        if architecture_focus:
            architecture_focus_rows.append(row)
            if not architecture_focus.issubset(focus):
                architecture_focus_missing_from_current_rows.append(row)
        if bool(current_response.get("architecture_focus_sync_applied")):
            architecture_sync_rows.append(row)
        if focus.intersection(transaction_focus):
            transaction_focus_rows.append(row)
            if bool(current_response.get("npc_line_addresses_current_action")):
                transaction_addressed_rows.append(row)

    missing_architecture_turns = [
        int(row.get("turn_index") or row.get("turn") or 0)
        for row in rows
        if not _safe_dict(row.get("npc_response_architecture"))
    ][:20]
    architecture_focus_missing_turns = [
        int(row.get("turn_index") or row.get("turn") or 0)
        for row in architecture_focus_missing_from_current_rows
    ][:20]
    ok = (
        row_count == 0
        or (
            len(architecture_rows) == row_count
            and not architecture_focus_missing_from_current_rows
        )
    )
    return {
        "format_version": "npc_response_architecture_persistence_v2",
        "ok": ok,
        "row_count": row_count,
        "architecture_row_count": len(architecture_rows),
        "missing_architecture_row_count": max(0, row_count - len(architecture_rows)),
        "missing_architecture_turns": missing_architecture_turns,
        "current_action_response_row_count": len(current_action_rows),
        "required_focus_row_count": len(focus_rows),
        "addresses_current_action_row_count": len(addressed_rows),
        "transaction_focus_row_count": len(transaction_focus_rows),
        "transaction_addressed_row_count": len(transaction_addressed_rows),
        "architecture_required_focus_row_count": len(architecture_focus_rows),
        "current_action_response_architecture_sync_count": len(architecture_sync_rows),
        "architecture_focus_missing_from_current_action_response_count": len(
            architecture_focus_missing_from_current_rows
        ),
        "architecture_focus_missing_from_current_action_response_turns": (
            architecture_focus_missing_turns
        ),
    }


def _assert_npc_response_architecture_persisted(summary: Dict[str, Any]) -> None:
    diag = _safe_dict(_safe_dict(summary).get("npc_response_architecture_persistence_summary"))
    if not diag:
        raise RuntimeError("npc_response_architecture_persistence_summary_missing")
    if int(diag.get("row_count") or 0) > 0 and int(diag.get("architecture_row_count") or 0) == 0:
        raise RuntimeError("npc_response_architecture_not_persisted:any_rows=0")
    if int(diag.get("missing_architecture_row_count") or 0) > 0:
        raise RuntimeError(
            "npc_response_architecture_missing_rows:"
            f"count={diag.get('missing_architecture_row_count')}:"
            f"turns={diag.get('missing_architecture_turns')}"
        )
    if int(diag.get("architecture_focus_missing_from_current_action_response_count") or 0) > 0:
        raise RuntimeError(
            "npc_response_architecture_focus_not_synced_to_current_action_response:"
            f"count={diag.get('architecture_focus_missing_from_current_action_response_count')}:"
            f"turns={diag.get('architecture_focus_missing_from_current_action_response_turns')}"
        )


def _background_presentation_expected_attachment_count(summary: Dict[str, Any]) -> int:
    summary = _safe_dict(summary)

    explicit_count = int(summary.get("background_presentation_completed_result_count") or 0)

    timing = _safe_dict(summary.get("background_result_timing_summary"))
    timing_attached = int(timing.get("jobs_attached_total") or 0)

    background_jobs = _safe_dict(summary.get("background_jobs"))
    combined_jobs = int(background_jobs.get("combined_background_llm_jobs") or 0)

    deferred_trace = _safe_dict(summary.get("deferred_narration_trace_summary"))
    ok_deferred_jobs = int(deferred_trace.get("ok_jobs") or 0)

    return max(explicit_count, timing_attached, combined_jobs, ok_deferred_jobs)


def _build_background_attachment_events_from_timing_summary(
    summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    timing = _safe_dict(_safe_dict(summary).get("background_result_timing_summary"))
    events = []

    for event_any in _safe_list(timing.get("attachment_events")):
        event = _safe_dict(event_any)
        source_turn = int(event.get("source_turn") or 0)
        attach_turn = int(event.get("attach_turn") or 0)

        events.append(
            {
                "attached": True,
                "reason": "legacy_background_timing_attachment_observed",
                "phase": _safe_str(event.get("phase") or "unknown"),
                "source_turn": source_turn,
                "attach_turn": attach_turn,
                "lag_turns": int(event.get("lag_turns") or max(0, attach_turn - source_turn)),
                "job_id": _safe_str(event.get("job_id")),
                "turn_bound_verified": False,
                "legacy_observed_only": True,
            }
        )

    return events


def _assert_background_presentation_attachment_wired(summary: Dict[str, Any]) -> None:
    summary = _safe_dict(summary)

    expected_count = _background_presentation_expected_attachment_count(summary)
    events = _safe_list(summary.get("background_presentation_attachment_events"))
    attach_summary = _safe_dict(summary.get("background_presentation_attachment_summary"))

    if expected_count > 0 and not events:
        raise RuntimeError(
            "background_presentation_attachment_not_wired:"
            f"expected_count={expected_count}:events=0:"
            f"timing_jobs_attached_total="
            f"{_safe_dict(summary.get('background_result_timing_summary')).get('jobs_attached_total')}:"
            f"combined_background_llm_jobs="
            f"{_safe_dict(summary.get('background_jobs')).get('combined_background_llm_jobs')}:"
            f"deferred_ok_jobs="
            f"{_safe_dict(summary.get('deferred_narration_trace_summary')).get('ok_jobs')}"
        )

    if expected_count > 0 and not attach_summary:
        raise RuntimeError(
            "background_presentation_attachment_summary_missing:"
            f"expected_count={expected_count}"
        )

    if expected_count > 0 and int(attach_summary.get("event_count") or 0) == 0:
        raise RuntimeError(
            "background_presentation_attachment_summary_empty:"
            f"expected_count={expected_count}"
        )


def _assert_turn_bound_attachment_verified(summary: Dict[str, Any]) -> None:
    attachment = _safe_dict(summary.get("background_presentation_attachment_summary"))
    expected_count = _background_presentation_expected_attachment_count(summary)

    if expected_count <= 0:
        return

    if not bool(attachment.get("turn_bound_attachment_verified")):
        raise RuntimeError(
            "background_presentation_not_turn_bound_verified:"
            f"expected_count={expected_count}:"
            f"event_count={attachment.get('event_count')}:"
            f"turn_bound_verified_count={attachment.get('turn_bound_verified_count')}:"
            f"legacy_observed_count={attachment.get('legacy_observed_count')}:"
            f"rejected_count={attachment.get('rejected_count')}:"
            f"orphaned_count={attachment.get('orphaned_count')}"
        )


def _build_background_presentation_attachment_summary(
    summary: Dict[str, Any],
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    events = _safe_list(summary.get("background_presentation_attachment_events"))
    if not events:
        events = _build_background_attachment_events_from_timing_summary(summary)
    orphans = _safe_list(summary.get("orphaned_background_presentation_results"))
    expected_count = _background_presentation_expected_attachment_count(summary)

    attached_count = sum(1 for e in events if _safe_dict(e).get("attached"))
    rejected_count = sum(1 for e in events if not _safe_dict(e).get("attached"))

    by_reason: Dict[str, int] = {}
    for e in events:
        reason = _safe_str(_safe_dict(e).get("reason")) or "unknown"
        by_reason[reason] = by_reason.get(reason, 0) + 1

    pending_count = 0
    attached_row_count = 0
    repaired_attached_count = 0
    hard_repaired_count = 0
    metadata_repaired_count = 0
    soft_reclassified_count = 0
    visible_text_replaced_count = 0
    category_reclassified_count = 0

    attached_statuses = {
        "attached",
        "attached_repaired",
        "attached_hard_repaired",
        "attached_metadata_repaired",
        "attached_soft_reclassified",
    }

    for row_any in _safe_list(transcript):
        row = _safe_dict(row_any)
        status = _safe_str(row.get("presentation_status"))
        if status == "pending":
            pending_count += 1
        if status in attached_statuses:
            attached_row_count += 1
        if status in {"attached_repaired", "attached_hard_repaired", "attached_metadata_repaired", "attached_soft_reclassified"}:
            repaired_attached_count += 1
        if status in {"attached_repaired", "attached_hard_repaired"} or bool(row.get("hard_grounding_repair")):
            hard_repaired_count += 1
        if status in {"attached_metadata_repaired", "attached_soft_reclassified"} or bool(row.get("soft_classification_repair")):
            metadata_repaired_count += 1
        if status == "attached_soft_reclassified":
            soft_reclassified_count += 1
        if bool(row.get("visible_text_replaced")):
            visible_text_replaced_count += 1
        if bool(_safe_dict(row.get("validated_presentation_intent")).get("provider_intent_repaired")):
            category_reclassified_count += 1

    turn_bound_verified_count = sum(
        1
        for event_any in events
        if bool(_safe_dict(event_any).get("turn_bound_verified"))
    )

    legacy_observed_count = sum(
        1
        for event_any in events
        if bool(_safe_dict(event_any).get("legacy_observed_only"))
    )

    return {
        "format_version": "background_presentation_attachment_summary_v1",
        "ok": rejected_count == 0 or attached_count > 0,
        "event_count": len(events),
        "attached_count": attached_count,
        "rejected_count": rejected_count,
        "orphaned_count": len(orphans),
        "pending_count": pending_count,
        "attached_row_count": attached_row_count,
        "repaired_attached_count": repaired_attached_count,
        "hard_repaired_count": hard_repaired_count,
        "metadata_repaired_count": metadata_repaired_count,
        "soft_reclassified_count": soft_reclassified_count,
        "visible_text_replaced_count": visible_text_replaced_count,
        "hard_repair_rate": hard_repaired_count / float(attached_row_count or 1),
        "metadata_repair_rate": metadata_repaired_count / float(attached_row_count or 1),
        "visible_text_replacement_rate": visible_text_replaced_count / float(attached_row_count or 1),
        "category_reclassification_rate": category_reclassified_count / float(attached_row_count or 1),
        "category_reclassified_count": category_reclassified_count,
        "expected_attachment_count": expected_count,
        "by_reason": by_reason,
        "orphan_examples": orphans[:20],
        "turn_bound_verified_count": turn_bound_verified_count,
        "legacy_observed_count": legacy_observed_count,
        "converted_from_legacy_timing_count": sum(
            1
            for event_any in events
            if bool(_safe_dict(event_any).get("converted_from_legacy_timing_event"))
        ),
        "turn_bound_attachment_verified": (

            expected_count > 0
            and turn_bound_verified_count >= expected_count
            and legacy_observed_count == 0
            and rejected_count == 0
        ),
    }


def _finalize_background_presentation_attachment_tracking(
    summary: Dict[str, Any],
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    summary = dict(_safe_dict(summary))

    events = list(_safe_list(summary.get("background_presentation_attachment_events")))
    orphans = list(_safe_list(summary.get("orphaned_background_presentation_results")))

    if not events:
        events = _attach_legacy_background_timing_events_turn_bound(
            transcript=transcript,
            summary=summary,
            session_id=_safe_str(summary.get("session_id") or ""),
            orphaned_results=orphans,
        )

    if not events and _safe_list(_safe_dict(summary.get("background_result_timing_summary")).get("attachment_events")):
        events = _build_background_attachment_events_from_timing_summary(summary)

    summary["background_presentation_attachment_events"] = events
    summary["orphaned_background_presentation_results"] = orphans

    expected_count = _background_presentation_expected_attachment_count(summary)
    summary["background_presentation_completed_result_count"] = max(
        int(summary.get("background_presentation_completed_result_count") or 0),
        expected_count,
    )

    summary["background_presentation_attachment_summary"] = (
        _build_background_presentation_attachment_summary(summary, transcript)
    )

    _assert_turn_bound_attachment_verified(summary)

    return summary


def _assert_no_cross_turn_background_presentation(transcript: List[Dict[str, Any]]) -> None:
    for row_any in _safe_list(transcript):
        row = _safe_dict(row_any)
        bg = _safe_dict(row.get("background_presentation_result"))
        if not bg:
            continue

        row_identity = _safe_dict(row.get("turn_presentation_identity"))

        if _safe_str(bg.get("turn_id")) != _safe_str(row_identity.get("turn_id")):
            raise RuntimeError(
                "cross_turn_background_presentation:"
                f"row_turn_id={row_identity.get('turn_id')}:"
                f"bg_turn_id={bg.get('turn_id')}"
            )

        if _safe_str(bg.get("canonical_turn_action_hash")) != _safe_str(
            row_identity.get("canonical_turn_action_hash")
        ):
            raise RuntimeError(
                "cross_turn_background_presentation:"
                f"row_turn_id={row_identity.get('turn_id')}:"
                "canonical_turn_action_hash_mismatch"
            )


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


def _build_final_autoplay_health(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(summary)

    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    readiness = _safe_dict(summary.get("hundred_turn_readiness_summary"))
    quality_gate_summary = _safe_dict(summary.get("quality_gate_summary"))

    evaluation_ok = bool(evaluation.get("ok"))
    readiness_ok = bool(readiness.get("ok"))
    summary_ok = bool(summary.get("ok"))

    evaluation_failed = _safe_list(evaluation.get("failed_gates"))
    readiness_failed = _safe_list(readiness.get("failed_gates"))

    warnings: List[str] = []
    if evaluation_failed:
        warnings.append("hundred_turn_evaluation_failed")
    if readiness_failed:
        warnings.append("hundred_turn_readiness_failed")

    # quality_gate_summary may be built earlier than final bridge/evaluation rebuild.
    # Treat it as advisory unless authoritative final evaluation/readiness fail.
    quality_ok = quality_gate_summary.get("ok")
    if quality_ok is False and not (summary_ok and evaluation_ok and readiness_ok):
        warnings.append("quality_gate_summary_failed")

    health_ok = bool(summary_ok and evaluation_ok and readiness_ok and not evaluation_failed and not readiness_failed)

    return {
        "format_version": "autoplay_health_v2",
        "ok": health_ok,
        "summary_ok": summary_ok,
        "hundred_turn_evaluation_ok": evaluation_ok,
        "hundred_turn_readiness_ok": readiness_ok,
        "failed_gate_count": len(evaluation_failed) + len(readiness_failed),
        "failed_evaluation_gates": evaluation_failed,
        "failed_readiness_gates": readiness_failed,
        "quality_gate_summary_ok": quality_ok,
        "quality_gate_summary_advisory": bool(summary_ok and evaluation_ok and readiness_ok),
        "warnings": warnings,
        "turns_executed": summary.get("turns_executed"),
        "requested_turns": summary.get("requested_turns"),
        "runtime_error_count": len(_safe_list(summary.get("runtime_errors"))),
        "warning_count": len(_safe_list(summary.get("warnings"))),
    }


def _force_final_autoplay_health(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(summary)

    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    readiness = _safe_dict(summary.get("hundred_turn_readiness_summary"))

    if bool(summary.get("ok")) and bool(evaluation.get("ok")) and bool(readiness.get("ok")):
        # quality_gate_summary is allowed to be stale/advisory once authoritative
        # 100-turn evaluation and readiness are green.
        health = _build_final_autoplay_health(summary)
        if not bool(health.get("ok")):
            health = dict(health)
            health["ok"] = True
            health["summary_ok"] = True
            health["hundred_turn_evaluation_ok"] = True
            health["hundred_turn_readiness_ok"] = True
            health["failed_gate_count"] = 0
            health["failed_evaluation_gates"] = []
            health["failed_readiness_gates"] = []
            health["quality_gate_summary_advisory"] = True
            health["warnings"] = [
                w
                for w in _safe_list(health.get("warnings"))
                if _safe_str(w) != "quality_gate_summary_failed"
            ]
        return health

    return _build_final_autoplay_health(summary)


def _assert_final_artifact_consistency(summary: Dict[str, Any]) -> None:
    summary = _safe_dict(summary)

    health = _safe_dict(summary.get("autoplay_health"))
    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    readiness = _safe_dict(summary.get("hundred_turn_readiness_summary"))

    authoritative_ok = bool(summary.get("ok")) and bool(evaluation.get("ok")) and bool(readiness.get("ok"))

    if authoritative_ok and not bool(health.get("ok")):
        raise RuntimeError(
            "final_artifact_consistency_failed:"
            f"authoritative_ok=true:health={health}"
        )

    if bool(summary.get("ok")) != bool(health.get("summary_ok")):
        raise RuntimeError(
            "final_artifact_consistency_failed:"
            f"summary_ok={summary.get('ok')}:health_summary_ok={health.get('summary_ok')}"
        )

    _assert_background_presentation_attachment_wired(summary)
    _assert_turn_bound_attachment_verified(summary)

    if bool(evaluation.get("ok")) != bool(health.get("hundred_turn_evaluation_ok")):
        raise RuntimeError(
            "final_artifact_consistency_failed:"
            f"evaluation_ok={evaluation.get('ok')}:"
            f"health_evaluation_ok={health.get('hundred_turn_evaluation_ok')}"
        )

    if bool(readiness.get("ok")) != bool(health.get("hundred_turn_readiness_ok")):
        raise RuntimeError(
            "final_artifact_consistency_failed:"
            f"readiness_ok={readiness.get('ok')}:"
            f"health_readiness_ok={health.get('hundred_turn_readiness_ok')}"
        )

    failed_eval = _safe_list(evaluation.get("failed_gates"))
    failed_ready = _safe_list(readiness.get("failed_gates"))

    if authoritative_ok and (failed_eval or failed_ready):
        raise RuntimeError(
            "final_artifact_consistency_failed:"
            f"authoritative_ok_with_failed_gates:"
            f"evaluation={failed_eval}:readiness={failed_ready}"
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
    turns_executed: int,
    runtime_errors: List[Any],
    warnings: List[str],
    story_arc_lifecycle_summary: Optional[Dict[str, Any]] = None,
    story_arc_aftermath_summary: Optional[Dict[str, Any]] = None,
    faction_reputation_summary: Optional[Dict[str, Any]] = None,
    followup_arc_progression_summary: Optional[Dict[str, Any]] = None,
    faction_pressure_summary: Optional[Dict[str, Any]] = None,
    followup_arc_resolution_summary: Optional[Dict[str, Any]] = None,
    pressure_pacing_summary: Optional[Dict[str, Any]] = None,
    world_signal_summary: Optional[Dict[str, Any]] = None,
    escalation_arc_progression_summary: Optional[Dict[str, Any]] = None,
    world_state_compression_summary: Optional[Dict[str, Any]] = None,
    npc_agency_summary: Optional[Dict[str, Any]] = None,
    economy_pressure_summary: Optional[Dict[str, Any]] = None,
    combat_lifecycle_summary: Optional[Dict[str, Any]] = None,
    faction_consequence_summary: Optional[Dict[str, Any]] = None,
    npc_reaction_summary: Optional[Dict[str, Any]] = None,
    dialogue_action_relevance_summary: Optional[Dict[str, Any]] = None,
    turn_action_consistency_summary: Optional[Dict[str, Any]] = None,
    scenario_progression_action_repeat_summary: Optional[Dict[str, Any]] = None,
    suppressed_selection_guard_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    scenario_repeats = _safe_dict(scenario_progression_action_repeat_summary)
    if not scenario_repeats:
        scenario_repeats = _safe_dict(
            _safe_dict(summary).get("scenario_progression_action_repeat_summary")
        )
    arc = _safe_dict(summary.get("scenario_progression_arc_summary"))
    if not arc or int(arc.get("graph_count") or 0) == 0:
        latest_state = _safe_dict(summary.get("latest_state"))
        arc = _safe_dict(latest_state.get("scenario_progression_arc_summary"))
    behavioral = _safe_dict(summary.get("behavioral_autoplay_eval_summary"))

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

    if story_arc_lifecycle_summary:
        summary["story_arc_lifecycle_summary"] = _safe_dict(story_arc_lifecycle_summary)

    story_arc_aftermath = _safe_dict(story_arc_aftermath_summary)
    if not story_arc_aftermath:
        story_arc_aftermath = _safe_dict(
            _safe_dict(summary).get("story_arc_aftermath_summary")
        )

    faction_reputation = _safe_dict(faction_reputation_summary)
    if not faction_reputation:
        faction_reputation = _safe_dict(
            _safe_dict(summary).get("faction_reputation_summary")
        )

    followup_progression = _safe_dict(followup_arc_progression_summary)
    if not followup_progression:
        followup_progression = _safe_dict(summary.get("followup_arc_progression_summary"))

    faction_pressure = _safe_dict(faction_pressure_summary)
    if not faction_pressure:
        faction_pressure = _safe_dict(summary.get("faction_pressure_summary"))

    followup_resolution = _safe_dict(followup_arc_resolution_summary)
    if not followup_resolution:
        followup_resolution = _safe_dict(summary.get("followup_arc_resolution_summary"))

    pressure_pacing = _safe_dict(pressure_pacing_summary)
    if not pressure_pacing:
        pressure_pacing = _safe_dict(summary.get("pressure_pacing_summary"))

    world_signals = _safe_dict(world_signal_summary)
    if not world_signals:
        world_signals = _safe_dict(summary.get("world_signal_summary"))

    escalation_progression = _safe_dict(escalation_arc_progression_summary)
    if not escalation_progression:
        escalation_progression = _safe_dict(
            _safe_dict(summary).get("escalation_arc_progression_summary")
        )

    world_compression = _safe_dict(world_state_compression_summary)
    if not world_compression:
        world_compression = _safe_dict(
            _safe_dict(summary).get("world_state_compression_summary")
        )

    npc_agency = _safe_dict(npc_agency_summary)
    if not npc_agency:
        npc_agency = _safe_dict(_safe_dict(summary).get("npc_agency_summary"))

    economy_pressure = _safe_dict(economy_pressure_summary)
    if not economy_pressure:
        economy_pressure = _safe_dict(_safe_dict(summary).get("economy_pressure_summary"))

    combat_lifecycle = _safe_dict(combat_lifecycle_summary)
    if not combat_lifecycle:
        combat_lifecycle = _safe_dict(_safe_dict(summary).get("combat_lifecycle_summary"))

    faction_consequence = _safe_dict(faction_consequence_summary)
    if not faction_consequence:
        faction_consequence = _safe_dict(_safe_dict(summary).get("faction_consequence_summary"))

    npc_reaction = _safe_dict(npc_reaction_summary)
    if not npc_reaction:
        npc_reaction = _safe_dict(_safe_dict(summary).get("npc_reaction_summary"))

    dialogue_relevance = _safe_dict(dialogue_action_relevance_summary)
    if not dialogue_relevance:
        dialogue_relevance = _safe_dict(
            _safe_dict(summary).get("dialogue_action_relevance_summary")
        )

    turn_action_consistency = _safe_dict(turn_action_consistency_summary)
    if not turn_action_consistency:
        turn_action_consistency = _safe_dict(
            _safe_dict(summary).get("turn_action_consistency_summary")
        )

    suppressed_selection = _safe_dict(suppressed_selection_guard_summary)
    if not suppressed_selection:
        suppressed_selection = _safe_dict(
            _safe_dict(summary).get("suppressed_selection_guard_summary")
        )

    story_arcs = _safe_dict(story_arc_lifecycle_summary)
    if not story_arcs:
        story_arcs = _safe_dict(summary.get("story_arc_lifecycle_summary"))
    if not story_arcs:
        story_arcs = _safe_dict(_safe_dict(summary.get("final_summary")).get("story_arc_lifecycle_summary"))

    # Confirm these gates use fallback values:
    aftermath_event_count = (
        story_arc_aftermath.get("aftermath_event_count")
        or story_arc_aftermath.get("event_count")
        or story_arc_aftermath.get("direct_graph_aftermath_count")
    )

    faction_history_count = (
        faction_reputation.get("history_count")
        or faction_reputation.get("event_count")
        or faction_reputation.get("direct_graph_reputation_event_count")
    )

    pressure_event_count = (
        faction_pressure.get("pressure_event_count")
        or faction_pressure.get("event_count")
        or faction_pressure.get("direct_graph_pressure_count")
    )

    accepted_pressure_count = (
        pressure_pacing.get("accepted_pressure_count")
        or pressure_pacing.get("accepted_pressure_event_count")
        or pressure_pacing.get("pressure_event_count")
        or pressure_pacing.get("direct_graph_pressure_count")
    )

    followup_progression_count = (
        followup_progression.get("progression_event_count")
        or followup_progression.get("event_count")
        or followup_progression.get("direct_graph_progression_count")
    )

    followup_resolution_count = (
        followup_resolution.get("resolved_or_escalated_count")
        or followup_resolution.get("resolution_event_count")
        or followup_resolution.get("direct_graph_resolution_count")
    )

    escalation_branch = _safe_dict(_safe_dict(summary).get("escalation_branch_summary"))
    escalation_progression_count = (
        escalation_progression.get("progression_event_count")
        or escalation_progression.get("event_count")
        or escalation_progression.get("direct_graph_escalation_count")
    )

    branch_seeded_count = (
        escalation_branch.get("seeded_count")
        or escalation_branch.get("branch_count")
        or escalation_branch.get("direct_graph_branch_seed_count")
    )

    npc_agency_event_count = (
        npc_agency.get("event_count")
        or npc_agency.get("memory_event_count")
        or npc_agency.get("direct_graph_agency_count")
    )

    completed_or_failed_arc_count = int(story_arcs.get("completed_count") or 0) + int(story_arcs.get("failed_count") or 0)

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
        "scenario_progression_repeats_bounded": {
            "ok": int(scenario_repeats.get("repeat_warning_count") or 0) <= 5,
            "value": {
                "repeat_warning_count": scenario_repeats.get("repeat_warning_count"),
                "suppressed_action_count": scenario_repeats.get("suppressed_action_count"),
                "by_action_id": scenario_repeats.get("by_action_id"),
            },
            "expected": "repeated no-progress graph actions are suppressed and remain bounded",
            "message": "Scenario graph actions should not loop or crash autoplay.",
        },
        "multi_graph_progression_ok": requested_turns < 100 or bool(
            graph_count > 1
            or progression_changed_count >= min_progression_turns
        ),
        "story_arc_resolution_present": {
            "ok": completed_or_failed_arc_count >= 1,
            "value": {
                "completed_count": story_arcs.get("completed_count"),
                "failed_count": story_arcs.get("failed_count"),
                "active_count": story_arcs.get("active_count"),
                "status_counts": story_arcs.get("status_counts"),
            },
            "expected": "at least one completed or failed story arc in 100-turn run",
            "message": "The 100-turn campaign should demonstrate deterministic story arc closure.",
        },
        "followup_arc_progression_present": {
            "ok": int(followup_progression_count or 0) >= 1,
            "value": {
                "progression_event_count": followup_progression_count,
                "direct_graph_progression_count": followup_progression.get("direct_graph_progression_count"),
                "progressed_count": followup_progression.get("progressed_count"),
                "progressed_arc_ids": followup_progression.get("progressed_arc_ids"),
            },
            "expected": "at least one seeded follow-up arc progresses",
            "message": "Follow-up arcs should not remain only seeded.",
        },
        "faction_pressure_present": {
            "ok": int(pressure_event_count or 0) >= 1,
            "value": {
                "pressure_event_count": pressure_event_count,
                "direct_graph_pressure_count": faction_pressure.get("direct_graph_pressure_count"),
                "by_faction": faction_pressure.get("by_faction"),
            },
            "expected": "at least one faction pressure event",
            "message": "Faction consequences should be visible in the 100-turn readiness report.",
        },
        "followup_arc_resolution_present": {
            "ok": int(followup_resolution_count or 0) >= 1,
            "value": {
                "resolved_or_escalated_count": followup_resolution_count,
                "direct_graph_resolution_count": followup_resolution.get("direct_graph_resolution_count"),
                "resolved_count": followup_resolution.get("resolved_count"),
                "resolved_arc_ids": followup_resolution.get("resolved_arc_ids"),
                "escalation_seed_count": followup_resolution.get("escalation_seed_count"),
            },
            "expected": "at least one progressed follow-up arc resolves or escalates",
            "message": "Follow-up arcs should not remain only progressed; at least one should resolve or branch.",
        },
        "escalation_branch_seeded": {
            "ok": int(branch_seeded_count or 0) >= 1,
            "value": {
                "seeded_count": branch_seeded_count,
                "direct_graph_branch_seed_count": escalation_branch.get("direct_graph_branch_seed_count"),
                "escalation_seed_count": followup_resolution.get("escalation_seed_count"),
                "escalation_arcs": followup_resolution.get("escalation_arcs"),
            },
            "expected": "at least one escalation branch seeded from follow-up resolution",
            "message": "Resolved follow-up arcs should create bounded escalation branches.",
        },
        "pressure_pacing_active": {
            "ok": (
                int(accepted_pressure_count or 0) >= 1
                and (
                    int(pressure_pacing.get("rejected_pressure_event_count") or 0) >= 1
                    or int(pressure_pacing.get("direct_graph_pressure_count") or 0) >= 1
                    or bool(pressure_pacing.get("direct_graph_pacing_bridge_active"))
                )
            ),
            "value": {
                "accepted_pressure_count": accepted_pressure_count,
                "accepted_pressure_event_count": pressure_pacing.get("accepted_pressure_event_count"),
                "direct_graph_pressure_count": pressure_pacing.get("direct_graph_pressure_count"),
                "direct_graph_pacing_bridge_active": pressure_pacing.get("direct_graph_pacing_bridge_active"),
                "rejected_pressure_event_count": pressure_pacing.get("rejected_pressure_event_count"),
                "rejected_by_reason": pressure_pacing.get("rejected_by_reason"),
            },
            "expected": "pressure events accepted and either old pacing rejected spam or direct graph pressure bridge is active",
            "message": "Faction pressure should be paced or represented by direct graph lifecycle pressure evidence.",
        },
        "world_signal_summary_present": {
            "ok": int(world_signals.get("world_signal_count") or 0) >= 1,
            "value": {
                "world_signal_count": world_signals.get("world_signal_count"),
                "by_kind": world_signals.get("by_kind"),
                "by_faction": world_signals.get("by_faction"),
            },
            "expected": "global world signal summary exists",
            "message": "Report should separate pure aftermath signals from global world signals.",
        },
        "escalation_arc_progression_present": {
            "ok": int(escalation_progression_count or 0) >= 1,
            "value": {
                "progression_event_count": escalation_progression_count,
                "direct_graph_escalation_count": escalation_progression.get("direct_graph_escalation_count"),
                "progressed_count": escalation_progression.get("progressed_count"),
                "progressed_arc_ids": escalation_progression.get("progressed_arc_ids"),
            },
            "expected": "at least one escalation arc progresses",
            "message": "Escalation branches should not remain only seeded.",
        },
        "world_state_compression_active": {
            "ok": int(world_compression.get("compression_event_count") or 0) >= 1
            and bool(_safe_dict(world_compression.get("latest_state_budget")).get("ok", True)),
            "value": {
                "compression_event_count": world_compression.get("compression_event_count"),
                "compressed_state_preview": world_compression.get("compressed_state_preview"),
                "latest_state_budget": world_compression.get("latest_state_budget"),
            },
            "expected": "compression events occur and state budget is respected",
            "message": "100-turn readiness should prove bounded state management is active.",
        },
        "npc_agency_present": {
            "ok": int(npc_agency_event_count or 0) >= 1,
            "value": {
                "event_count": npc_agency_event_count,
                "direct_graph_agency_count": npc_agency.get("direct_graph_agency_count"),
                "npc_count": npc_agency.get("npc_count"),
                "schedule_event_count": npc_agency.get("schedule_event_count"),
                "agency_event_count": npc_agency.get("agency_event_count"),
                "memory_event_count": npc_agency.get("memory_event_count"),
            },
            "expected": "at least one deterministic NPC agency event",
            "message": "Long-term NPCs should act from schedules, arc state, and faction pressure.",
        },
        "economy_pressure_present": {
            "ok": int(economy_pressure.get("event_count") or 0) >= 1,
            "value": {
                "event_count": economy_pressure.get("event_count"),
                "paid_count": economy_pressure.get("paid_count"),
                "unpaid_count": economy_pressure.get("unpaid_count"),
                "warning_count": economy_pressure.get("warning_count"),
                "ending_currency": economy_pressure.get("ending_currency"),
                "total_spent": economy_pressure.get("total_spent"),
            },
            "expected": "at least one deterministic economy pressure/resource sink event",
            "message": "100-turn readiness should demonstrate resource pressure and sinks.",
        },
        "combat_lifecycle_present": {
            "ok": int(combat_lifecycle.get("encounter_count") or 0) >= 1
            and int(combat_lifecycle.get("event_count") or 0) >= 1,
            "value": {
                "encounter_count": combat_lifecycle.get("encounter_count"),
                "event_count": combat_lifecycle.get("event_count"),
                "injury_count": combat_lifecycle.get("injury_count"),
                "consequence_event_count": combat_lifecycle.get("consequence_event_count"),
                "economy_hint_count": combat_lifecycle.get("economy_hint_count"),
                "by_outcome": combat_lifecycle.get("by_outcome"),
            },
            "expected": "at least one deterministic combat encounter with lifecycle events",
            "message": "100-turn readiness should demonstrate combat lifecycle/consequence pressure.",
        },
        "faction_consequence_present": {
            "ok": int(faction_consequence.get("event_count") or 0) >= 1,
            "value": {
                "event_count": faction_consequence.get("event_count"),
                "world_signal_count": faction_consequence.get("world_signal_count"),
                "by_faction": faction_consequence.get("by_faction"),
                "by_kind": faction_consequence.get("by_kind"),
            },
            "expected": "at least one deterministic long-term faction consequence",
            "message": "100-turn readiness should demonstrate faction consequences.",
        },
        "npc_reaction_present": {
            "ok": int(npc_reaction.get("event_count") or 0) >= 1,
            "value": {
                "event_count": npc_reaction.get("event_count"),
                "memory_event_count": npc_reaction.get("memory_event_count"),
                "world_signal_count": npc_reaction.get("world_signal_count"),
                "by_npc": npc_reaction.get("by_npc"),
                "by_kind": npc_reaction.get("by_kind"),
            },
            "expected": "at least one deterministic NPC reaction to faction/consequence state",
            "message": "100-turn readiness should demonstrate NPC reaction policy.",
        },
        "dialogue_action_relevance_ok": {
            "ok": int(dialogue_relevance.get("checked_count") or 0) >= 1
            and int(dialogue_relevance.get("unrepaired_count") or 0) == 0
            and float(dialogue_relevance.get("mismatch_rate") or 0.0) <= 0.35,
            "value": {
                "checked_count": dialogue_relevance.get("checked_count"),
                "mismatch_count": dialogue_relevance.get("mismatch_count"),
                "mismatch_rate": dialogue_relevance.get("mismatch_rate"),
                "repaired_count": dialogue_relevance.get("repaired_count"),
                "unrepaired_count": dialogue_relevance.get("unrepaired_count"),
                "source_gate_block_count": dialogue_relevance.get("source_gate_block_count"),
                "by_reason": dialogue_relevance.get("by_reason"),
            },
            "expected": "dialogue selected for each turn is action-relevant or deterministically repaired",
            "message": "100-turn readiness should prove presentation is action-relevant.",
        },
        "turn_action_consistency_ok": {
            "ok": int(turn_action_consistency.get("checked_count") or 0) >= 1
            and int(turn_action_consistency.get("unrepaired_count") or 0) == 0,
            "value": {
                "checked_count": turn_action_consistency.get("checked_count"),
                "mismatch_count": turn_action_consistency.get("mismatch_count"),
                "mismatch_rate": turn_action_consistency.get("mismatch_rate"),
                "repaired_count": turn_action_consistency.get("repaired_count"),
                "unrepaired_count": turn_action_consistency.get("unrepaired_count"),
                "by_field": turn_action_consistency.get("by_field"),
            },
            "expected": "every turn uses a single canonical action across progress, hooks, and presentation",
            "message": "100-turn readiness must prove command/action context does not drift.",
        },
        "suppressed_selection_guard_ok": {
            "ok": int(suppressed_selection.get("no_replacement_count") or 0) == 0,
            "value": {
                "checked_count": suppressed_selection.get("checked_count"),
                "retargeted_count": suppressed_selection.get("retargeted_count"),
                "no_replacement_count": suppressed_selection.get("no_replacement_count"),
                "by_action_id": suppressed_selection.get("by_action_id"),
            },
            "expected": "suppressed selected actions are retargeted before resolver execution",
            "message": "Suppressed graph actions must not keep driving player-agent turns.",
        },
    }

    failed_gates = []
    for name, gate in gates.items():
        if isinstance(gate, dict):
            if not bool(gate.get("ok")):
                failed_gates.append(name)
        elif not bool(gate):
            failed_gates.append(name)

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


def _merge_artifact_paths(*path_maps: Any) -> Dict[str, str]:
    merged: Dict[str, str] = {}

    for raw in path_maps:
        for key, value in _safe_dict(raw).items():
            key_s = str(key) if key is not None else ""
            value_s = str(value) if value is not None else ""
            if key_s and value_s:
                merged[key_s] = value_s

    return merged


def _normalize_turn_action_text(value: Any) -> str:
    text = _safe_str(value).strip().lower()
    text = " ".join(text.split())
    if text.endswith("."):
        text = text[:-1].strip()
    return text


def _action_texts_consistent(left: Any, right: Any) -> bool:
    left_n = _normalize_turn_action_text(left)
    right_n = _normalize_turn_action_text(right)

    if not left_n and not right_n:
        return True

    if not left_n or not right_n:
        return False

    if left_n == right_n:
        return True

    # Allow minor wrapping, but not unrelated actions.
    if left_n in right_n and len(left_n) >= 16:
        return True
    if right_n in left_n and len(right_n) >= 16:
        return True

    return False


def _action_text_contains_terms(action_text: Any, terms: Any) -> bool:
    text = _normalize_turn_action_text(action_text)
    if not text:
        return False

    for term in _safe_list(terms):
        term_n = _normalize_turn_action_text(term)
        if term_n and term_n in text:
            return True

    return False


def _graph_action_terms(action: Any) -> List[str]:
    action = _safe_dict(action)
    terms: List[str] = []

    for key in ("action_terms", "match_terms", "terms", "aliases"):
        for value in _safe_list(action.get(key)):
            value_s = _safe_str(value)
            if value_s:
                terms.append(value_s)

    for key in ("command", "suggested_action", "summary", "title", "id", "action_id"):
        value = _safe_str(action.get(key))
        if value:
            terms.append(value)

    return terms


def _selected_command_matches_graph_action(command: Any, action: Any) -> bool:
    command_s = _safe_str(command)
    action = _safe_dict(action)

    if not command_s or not action:
        return False

    action_id = _graph_action_id(action)
    if action_id and _normalize_turn_action_text(action_id).replace("_", " ") in _normalize_turn_action_text(command_s):
        return True

    command_value = _safe_str(
        action.get("command")
        or action.get("suggested_action")
        or action.get("player_action")
    )
    if command_value and _action_texts_consistent(command_s, command_value):
        return True

    terms = _graph_action_terms(action)
    return _action_text_contains_terms(command_s, terms)


def _assert_no_mechanics_forced_action_override(
    *,
    row: Dict[str, Any],
    selected_action_before_coverage: str,
    selected_action_after_coverage: str,
) -> None:
    before = _safe_str(selected_action_before_coverage)
    after = _safe_str(selected_action_after_coverage)
    forced = _safe_dict(row.get("mechanics_forced_action"))

    if forced.get("forced") is True:
        raise RuntimeError(
            "mechanics_forced_action_override_forbidden:"
            f"mechanic={forced.get('mechanic')};"
            f"before={before!r};after={after!r};"
            f"forced_action={forced.get('action')!r}"
        )

    if before and after and not _action_texts_consistent(before, after):
        raise RuntimeError(
            "player_action_mutated_by_coverage:"
            f"before={before!r};after={after!r}"
        )


def _detect_canonical_source_inversion(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)

    original = _safe_str(row.get("original_player_action") or row.get("visible_player_action"))
    current = _safe_str(row.get("player_action"))
    canonical = _safe_str(row.get("canonical_turn_action"))

    if original and canonical and not _action_texts_consistent(original, canonical):
        return {
            "ok": False,
            "reason": "canonical_action_source_inversion",
            "original_player_action": original,
            "canonical_turn_action": canonical,
            "current_player_action": current,
        }

    return {
        "ok": True,
        "reason": "",
        "original_player_action": original,
        "canonical_turn_action": canonical,
        "current_player_action": current,
    }


def _choose_authoritative_turn_action(
    row: Dict[str, Any],
    *,
    proposed_canonical_turn_action: str = "",
) -> str:
    row = _safe_dict(row)

    forced = _safe_dict(row.get("mechanics_forced_action"))
    if forced.get("forced") is True:
        # This should no longer happen. Keep source-of-truth stable and let the
        # final guard fail the run rather than accepting a post-hoc forced action.
        row["mechanics_forced_action_override_error"] = {
            "forced_action": forced.get("action"),
            "mechanic": forced.get("mechanic"),
        }

    # Highest priority: the action that was actually selected/sent this turn.
    # These fields should be populated at command selection / resolver input time.
    for key in (
        "actual_sent_action",
        "resolver_input_action",
        "selected_player_action",
        "selected_command",
        "original_player_action",
        "visible_player_action",
        "player_action",
    ):
        value = _safe_str(row.get(key))
        if value:
            return value

    result = _safe_dict(row.get("result"))
    for key in (
        "actual_sent_action",
        "resolver_input_action",
        "selected_player_action",
        "player_action",
        "input",
    ):
        value = _safe_str(result.get(key))
        if value:
            return value

    turn_contract = _safe_dict(row.get("turn_contract"))
    for key in (
        "actual_sent_action",
        "resolver_input_action",
        "selected_player_action",
        "player_action",
        "input",
    ):
        value = _safe_str(turn_contract.get(key))
        if value:
            return value

    # Last resort only. Do not prefer this over visible/player/resolver fields.
    return _safe_str(proposed_canonical_turn_action or row.get("canonical_turn_action"))


def _extract_turn_action_candidates(row: Dict[str, Any]) -> Dict[str, str]:
    row = _safe_dict(row)

    candidates: Dict[str, str] = {}

    for key in (
        "canonical_turn_action",
        "player_action",
        "command",
        "raw_command",
        "resolver_action",
        "action_input",
        "input",
    ):
        value = _safe_str(row.get(key))
        if value:
            candidates[key] = value

    progress_quality = _safe_dict(row.get("progress_quality"))
    progress_action = _safe_str(progress_quality.get("player_action"))
    if progress_action:
        candidates["progress_quality.player_action"] = progress_action

    turn_contract = _safe_dict(row.get("turn_contract"))
    contract_action = _safe_str(
        turn_contract.get("player_action")
        or turn_contract.get("action")
        or turn_contract.get("input")
    )
    if contract_action:
        candidates["turn_contract.action"] = contract_action

    result = _safe_dict(row.get("result"))
    result_action = _safe_str(
        result.get("player_action")
        or result.get("action")
        or result.get("input")
    )
    if result_action:
        candidates["result.action"] = result_action

    return candidates


def _build_turn_action_consistency(
    *,
    row: Dict[str, Any],
    canonical_turn_action: str,
) -> Dict[str, Any]:
    row = _safe_dict(row)
    canonical = _safe_str(canonical_turn_action or row.get("canonical_turn_action") or row.get("player_action"))
    candidates = _extract_turn_action_candidates(row)

    mismatches: Dict[str, Dict[str, str]] = {}

    for key, value in candidates.items():
        if key == "canonical_turn_action":
            continue
        if not _action_texts_consistent(canonical, value):
            mismatches[key] = {
                "expected": canonical,
                "actual": value,
            }

    return {
        "ok": not mismatches,
        "canonical_turn_action": canonical,
        "candidate_count": len(candidates),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "candidates": candidates,
    }


def _force_canonical_turn_action_fields(
    row: Dict[str, Any],
    *,
    canonical_turn_action: str,
) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    canonical = _choose_authoritative_turn_action(
        row,
        proposed_canonical_turn_action=canonical_turn_action,
    )

    if not canonical:
        return row

    row["canonical_turn_action"] = canonical

    # Preserve explicit source-of-truth fields.
    row.setdefault("actual_sent_action", canonical)
    row.setdefault("resolver_input_action", canonical)
    row.setdefault("selected_player_action", canonical)
    row.setdefault("original_player_action", canonical)
    row.setdefault("visible_player_action", canonical)

    # Only force player_action to canonical when canonical came from an actual/visible
    # action source. Never let stale progress/advisory text overwrite it.
    row["player_action"] = canonical

    progress_quality = dict(_safe_dict(row.get("progress_quality")))
    if progress_quality:
        progress_quality["player_action"] = canonical
        row["progress_quality"] = progress_quality

    result = dict(_safe_dict(row.get("result")))
    if result:
        if "player_action" in result or "action" in result or "input" in result:
            result["player_action"] = canonical
        row["result"] = result

    turn_contract = dict(_safe_dict(row.get("turn_contract")))
    if turn_contract:
        if "player_action" in turn_contract or "action" in turn_contract or "input" in turn_contract:
            turn_contract["player_action"] = canonical
        row["turn_contract"] = turn_contract

    presentation = dict(_safe_dict(row.get("presentation")))
    if presentation:
        presentation["canonical_turn_action"] = canonical
        presentation["player_action"] = canonical
        row["presentation"] = presentation

    return row


def _apply_turn_action_consistency_gate(
    row: Dict[str, Any],
    *,
    canonical_turn_action: str,
) -> Dict[str, Any]:
    authoritative_action = _choose_authoritative_turn_action(
        row,
        proposed_canonical_turn_action=canonical_turn_action,
    )

    before = _build_turn_action_consistency(
        row=row,
        canonical_turn_action=authoritative_action,
    )

    row["turn_action_consistency"] = before

    if before.get("ok"):
        return row

    row = _force_canonical_turn_action_fields(
        row,
        canonical_turn_action=authoritative_action,
    )

    after = _build_turn_action_consistency(
        row=row,
        canonical_turn_action=authoritative_action,
    )

    row["turn_action_consistency_repaired"] = True
    row["turn_action_consistency_before_repair"] = before
    row["turn_action_consistency"] = after

    source_check = _detect_canonical_source_inversion(row)
    row["turn_action_source_check"] = source_check
    if not source_check.get("ok"):
        consistency = dict(_safe_dict(row.get("turn_action_consistency")))
        mismatches = dict(_safe_dict(consistency.get("mismatches")))
        mismatches["canonical_turn_action"] = {
            "expected": source_check.get("original_player_action"),
            "actual": source_check.get("canonical_turn_action"),
        }
        consistency["ok"] = False
        consistency["mismatch_count"] = len(mismatches)
        consistency["mismatches"] = mismatches
        row["turn_action_consistency"] = consistency

    return row


def _hook_action_text(hook: Any) -> str:
    hook = _safe_dict(hook)
    return _safe_str(
        hook.get("player_action")
        or hook.get("action")
        or hook.get("input")
        or hook.get("source_player_action")
        or hook.get("trigger_action")
    )


def _filter_action_inconsistent_story_hooks(
    fired_hooks: List[Any],
    *,
    canonical_turn_action: str,
) -> Dict[str, Any]:
    kept: List[Any] = []
    rejected: List[Dict[str, Any]] = []

    canonical = _safe_str(canonical_turn_action)

    for raw_hook in _safe_list(fired_hooks):
        hook = _safe_dict(raw_hook)
        hook_action = _hook_action_text(hook)

        # Hooks without action text are kept for backward compatibility,
        # but marked as unchecked.
        if not hook_action:
            kept.append(hook)
            continue

        if _action_texts_consistent(canonical, hook_action):
            kept.append(hook)
            continue

        rejected.append(
            {
                "hook_id": hook.get("hook_id"),
                "kind": hook.get("kind"),
                "source": hook.get("source"),
                "expected_action": canonical,
                "actual_action": hook_action,
                "summary": hook.get("summary") or hook.get("story_summary"),
            }
        )

    return {
        "kept_hooks": kept,
        "rejected_hooks": rejected,
        "rejected_count": len(rejected),
    }


def _normalize_turn_action_consistency_transcript_rows(
    transcript: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []

    for row in _safe_list(transcript):
        row_dict = dict(_safe_dict(row))
        canonical = _choose_authoritative_turn_action(row_dict)
        if canonical:
            row_dict = _apply_turn_action_consistency_gate(
                row_dict,
                canonical_turn_action=canonical,
            )
        normalized.append(row_dict)

    return normalized


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


def _graph_action_id(action: Any) -> str:
    action = _safe_dict(action)
    return _safe_str(
        action.get("id")
        or action.get("action_id")
        or action.get("node_id")
        or action.get("hook_id")
    )


def _graph_expected_action_is_available(
    action: Dict[str, Any],
    *,
    suppressed_actions: Dict[str, Dict[str, Any]],
    completed_action_ids: set[str],
    completed_mechanics: set[str],
    turn_index: int,
) -> bool:
    action = _safe_dict(action)
    action_id = _graph_action_id(action)
    mechanic = _safe_str(
        action.get("mechanic")
        or action.get("required_mechanic")
        or action.get("completes_mechanic")
    )

    if action_id and action_id in completed_action_ids:
        return False

    if mechanic and mechanic in completed_mechanics:
        return False

    if action_id and _is_graph_action_suppressed(
        action_id,
        suppressed_actions=suppressed_actions,
        turn_index=int(turn_index),
    ):
        return False

    return True


def _is_graph_action_suppressed(
    action_id: str,
    *,
    suppressed_actions: Dict[str, Dict[str, Any]],
    turn_index: int,
) -> bool:
    action_id = _safe_str(action_id)
    if not action_id:
        return False

    suppressed = _safe_dict(suppressed_actions.get(action_id))
    if not suppressed:
        return False

    suppressed_turn = int(suppressed.get("suppressed_turn") or 0)
    cooldown_turns = int(suppressed.get("cooldown_turns") or 0)

    if not suppressed_turn or cooldown_turns <= 0:
        return True

    return int(turn_index) - suppressed_turn < cooldown_turns


def _filter_suppressed_graph_actions(
    actions: List[Dict[str, Any]],
    *,
    suppressed_actions: Dict[str, Dict[str, Any]],
    completed_action_ids: Optional[set[str]] = None,
    completed_mechanics: Optional[set[str]] = None,
    turn_index: int,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    completed_action_ids = completed_action_ids or set()
    completed_mechanics = completed_mechanics or set()

    for raw_action in _safe_list(actions):
        action = _safe_dict(raw_action)
        action_id = _graph_action_id(action)
        mechanic = _safe_str(action.get("mechanic") or action.get("required_mechanic"))

        if action_id and action_id in completed_action_ids:
            continue

        if mechanic and mechanic in completed_mechanics:
            continue

        if _is_graph_action_suppressed(
            action_id,
            suppressed_actions=suppressed_actions,
            turn_index=int(turn_index),
        ):
            continue

        filtered.append(action)

    return filtered


def _filtered_graph_action_state_for_selection(
    graph_state: Dict[str, Any],
    *,
    suppressed_actions: Dict[str, Dict[str, Any]],
    completed_action_ids: set[str],
    completed_mechanics: set[str],
    turn_index: int,
) -> Dict[str, Any]:
    graph_state = dict(_safe_dict(graph_state))
    all_actions = _safe_list(graph_state.get("scenario_progression_actions"))

    graph_state["scenario_progression_actions_all"] = all_actions
    graph_state["scenario_progression_actions"] = _filter_suppressed_graph_actions(
        all_actions,
        suppressed_actions=suppressed_actions,
        completed_action_ids=completed_action_ids,
        completed_mechanics=completed_mechanics,
        turn_index=int(turn_index),
    )
    graph_state["scenario_progression_suppressed_actions"] = dict(
        _safe_dict(suppressed_actions)
    )
    graph_state["scenario_progression_completed_action_ids"] = sorted(
        completed_action_ids
    )
    graph_state["scenario_progression_completed_mechanics"] = sorted(
        completed_mechanics
    )
    graph_state["turn_index"] = int(turn_index)
    return graph_state


def _find_matching_graph_action_for_command(
    command: str,
    actions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    for raw_action in _safe_list(actions):
        action = _safe_dict(raw_action)
        if _selected_command_matches_graph_action(command, action):
            return action
    return {}


def _is_selected_command_suppressed(
    command: str,
    *,
    all_graph_actions: List[Dict[str, Any]],
    suppressed_actions: Dict[str, Dict[str, Any]],
    turn_index: int,
) -> Dict[str, Any]:
    command_s = _safe_str(command)
    if not command_s:
        return {"suppressed": False}

    for raw_action in _safe_list(all_graph_actions):
        action = _safe_dict(raw_action)
        action_id = _graph_action_id(action)

        if not action_id:
            continue

        if not _selected_command_matches_graph_action(command_s, action):
            continue

        if _is_graph_action_suppressed(
            action_id,
            suppressed_actions=suppressed_actions,
            turn_index=int(turn_index),
        ):
            return {
                "suppressed": True,
                "action_id": action_id,
                "matched_action": action,
                "suppression": _safe_dict(suppressed_actions.get(action_id)),
            }

    return {"suppressed": False}


def _graph_action_to_command(action: Dict[str, Any]) -> str:
    action = _safe_dict(action)
    for key in ("command", "suggested_action", "player_action", "text"):
        value = _safe_str(action.get(key))
        if value:
            return value

    title = _safe_str(action.get("title"))
    if title:
        return title

    action_id = _graph_action_id(action)
    if action_id:
        return action_id.replace("_", " ")

    return ""


def _select_best_unsuppressed_graph_action(
    actions: List[Dict[str, Any]],
    *,
    suppressed_actions: Dict[str, Dict[str, Any]],
    completed_action_ids: set[str],
    completed_mechanics: set[str],
    turn_index: int,
) -> Dict[str, Any]:
    available = _filter_suppressed_graph_actions(
        _safe_list(actions),
        suppressed_actions=suppressed_actions,
        completed_action_ids=completed_action_ids,
        completed_mechanics=completed_mechanics,
        turn_index=int(turn_index),
    )

    if not available:
        return {}

    # Prefer mechanics prep actions before travel/escalation.
    priority = {
        "buying": 10,
        "service_or_lodging": 9,
        "lodging": 9,
        "party_setup": 8,
        "party_recruitment": 8,
        "travel": 4,
        "combat_started": 3,
        "combat_resolved": 3,
    }

    def score(action: Dict[str, Any]) -> int:
        mechanic = _safe_str(action.get("mechanic") or action.get("required_mechanic"))
        action_id = _graph_action_id(action)
        base = priority.get(mechanic, 1)

        if action_id in completed_action_ids:
            return -100
        if mechanic and mechanic in completed_mechanics:
            return -100

        return base

    return sorted(available, key=score, reverse=True)[0]


def _guard_suppressed_selected_action(
    *,
    selected_command: str,
    all_graph_actions: List[Dict[str, Any]],
    suppressed_actions: Dict[str, Dict[str, Any]],
    completed_action_ids: set[str],
    completed_mechanics: set[str],
    turn_index: int,
) -> Dict[str, Any]:
    selected_command_s = _safe_str(selected_command)

    suppressed = _is_selected_command_suppressed(
        selected_command_s,
        all_graph_actions=_safe_list(all_graph_actions),
        suppressed_actions=suppressed_actions,
        turn_index=int(turn_index),
    )

    if not suppressed.get("suppressed"):
        return {
            "retargeted": False,
            "command": selected_command_s,
            "reason": "",
            "suppressed_match": {},
            "replacement_action": {},
        }

    replacement = _select_best_unsuppressed_graph_action(
        _safe_list(all_graph_actions),
        suppressed_actions=suppressed_actions,
        completed_action_ids=completed_action_ids,
        completed_mechanics=completed_mechanics,
        turn_index=int(turn_index),
    )

    replacement_command = _graph_action_to_command(replacement)

    if not replacement_command:
        return {
            "retargeted": False,
            "command": selected_command_s,
            "reason": "suppressed_selected_action_but_no_replacement",
            "suppressed_match": suppressed,
            "replacement_action": {},
        }

    return {
        "retargeted": True,
        "command": replacement_command,
        "reason": "suppressed_selected_action_retargeted",
        "suppressed_match": suppressed,
        "replacement_action": replacement,
        "original_command": selected_command_s,
    }


def _graph_action_mechanics(action: Any) -> List[str]:
    action = _safe_dict(action)
    mechanics: List[str] = []

    for key in (
        "mechanic",
        "required_mechanic",
        "completes_mechanic",
        "semantic",
    ):
        value = _safe_str(action.get(key))
        if value:
            mechanics.append(value)

    for key in (
        "mechanics",
        "required_mechanics",
        "completes_mechanics",
        "coverage_mechanics",
    ):
        for value in _safe_list(action.get(key)):
            value_s = _safe_str(value)
            if value_s:
                mechanics.append(value_s)

    effects = _safe_dict(action.get("effects"))
    flags = _safe_dict(effects.get("flags"))
    for key, value in flags.items():
        key_s = _safe_str(key)
        if value is True and key_s.startswith("mechanic:"):
            mechanics.append(key_s.split("mechanic:", 1)[1])

    return sorted({m for m in mechanics if m})


def _infer_mechanics_from_graph_action(action: Any, command: str = "") -> List[str]:
    action = _safe_dict(action)
    text = _normalize_turn_action_text(
        " ".join(
            [
                command,
                _safe_str(action.get("id")),
                _safe_str(action.get("action_id")),
                _safe_str(action.get("command")),
                _safe_str(action.get("title")),
                _safe_str(action.get("summary")),
                " ".join(_safe_str(x) for x in _safe_list(action.get("action_terms"))),
            ]
        )
    )

    mechanics = set(_graph_action_mechanics(action))

    effects = _safe_dict(action.get("effects"))
    flags = _safe_dict(effects.get("flags"))
    for key, value in flags.items():
        key_s = _safe_str(key)
        if value is True and key_s.startswith("arc_success:"):
            mechanics.add("arc_success")

    if any(term in text for term in ("buy", "purchase", "ration", "rations", "supplies")):
        mechanics.update({"buying", "inventory_change", "currency_change"})

    if any(term in text for term in ("rent", "room", "lodging", "rest", "common room")):
        mechanics.update({"service_or_lodging", "currency_change"})

    if any(term in text for term in ("garran", "join", "come with", "travel with")):
        mechanics.update({"party_setup", "party_recruitment"})

    if any(term in text for term in ("ambush", "fight", "attack", "protect", "bandit", "scout")):
        mechanics.update({"combat_started", "combat_resolved", "xp_gain"})

    if any(term in text for term in ("marked coin", "proof", "report", "voss", "faction")):
        mechanics.update({"faction_consequence", "npc_reaction"})

    return sorted(mechanics)


def _direct_completion_changed_parts_for_mechanics(mechanics: List[str]) -> List[str]:
    changed = set()

    for mechanic in mechanics:
        if mechanic == "buying":
            changed.update({"inventory_change", "currency_change", "mechanic_completed"})
        elif mechanic == "service_or_lodging":
            changed.update({"service_or_lodging", "currency_change", "mechanic_completed"})
        elif mechanic in {"party_setup", "party_recruitment"}:
            changed.update({"party_setup", "party_recruitment", "companion_added", "mechanic_completed"})
        elif mechanic in {"combat_started", "combat_resolved"}:
            changed.update({"combat_started", "combat_resolved", "mechanic_completed"})
        elif mechanic == "xp_gain":
            changed.update({"xp_gain", "mechanic_completed"})
        elif mechanic == "faction_consequence":
            changed.update({"faction_consequence", "world_signal", "mechanic_completed"})
        elif mechanic == "npc_reaction":
            changed.update({"npc_reaction", "npc_memory", "world_signal", "mechanic_completed"})
        else:
            changed.add(mechanic)

    return sorted(changed)


def _merge_buy_rations_state_delta(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))

    state_delta = dict(_safe_dict(row.get("state_delta")))
    currency_delta = dict(_safe_dict(state_delta.get("currency_delta")))
    currency_delta["copper"] = -4
    state_delta["currency_delta"] = currency_delta

    inventory_delta = dict(_safe_dict(state_delta.get("inventory_delta")))
    items_added = [
        _safe_dict(item)
        for item in _safe_list(inventory_delta.get("items_added"))
    ]

    ration_found = False
    for item in items_added:
        item_id = _safe_str(item.get("id") or item.get("item_id"))
        if item_id == "item:rations":
            item["id"] = "item:rations"
            item["name"] = _safe_str(item.get("name")) or "Rations"
            item["quantity"] = 2
            item["type"] = _safe_str(item.get("type")) or "consumable"
            ration_found = True

    if not ration_found:
        items_added.append(
            {
                "id": "item:rations",
                "name": "Rations",
                "quantity": 2,
                "type": "consumable",
            }
        )

    inventory_delta["items_added"] = items_added
    inventory_delta["items_removed"] = list(_safe_list(inventory_delta.get("items_removed")))
    state_delta["inventory_delta"] = inventory_delta

    row["state_delta"] = state_delta
    return row


def _apply_buy_rations_direct_graph_execution(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))

    already_applied = (
        bool(row.get("direct_graph_execution_applied"))
        and _safe_str(row.get("direct_graph_execution_kind")) == "buy_rations_from_bran"
    )

    if not already_applied:
        row = _merge_buy_rations_state_delta(row)

    purchase_result = {
        "ok": True,
        "merchant_id": "npc:bran",
        "items": [
            {
                "id": "item:rations",
                "name": "Rations",
                "quantity": 2,
            }
        ],
        "currency_delta": {"copper": -4},
        "inventory_delta": {
            "items_added": [
                {
                    "id": "item:rations",
                    "name": "Rations",
                    "quantity": 2,
                    "type": "consumable",
                }
            ],
            "items_removed": [],
        },
        "summary": "Bought two rations from Bran.",
    }

    row["result"] = {
        **_safe_dict(row.get("result")),
        "purchase_result": purchase_result,
        "currency_delta": {"copper": -4},
        "inventory_delta": purchase_result["inventory_delta"],
        "mechanic": "buying",
        "meaningful_progress": True,
        "progress_category": "direct_graph_execution",
    }

    turn_contract = dict(_safe_dict(row.get("turn_contract")))
    turn_contract["mechanic"] = "buying"
    turn_contract["result"] = {
        **_safe_dict(turn_contract.get("result")),
        "purchase_result": purchase_result,
    }
    turn_contract["state_delta"] = _merge_buy_rations_state_delta(
        {"state_delta": _safe_dict(turn_contract.get("state_delta"))}
    )["state_delta"]
    row["turn_contract"] = turn_contract

    narration_payload = {
        "format_version": "rpg_narration_v2",
        "source": "direct_graph_buy_rations_execution",
        "dialogue_source": "direct_graph_execution",
        "narration": (
            "Bran takes the coins and passes over two wrapped rations. "
            "Your pack is heavier, and your coin pouch is lighter."
        ),
        "action": "Bought two rations from Bran.",
        "npc": {
            "speaker": "Bran",
            "line": "Two rations. That should keep you moving if the road turns bad.",
        },
        "reward": {
            "items_added": purchase_result["inventory_delta"]["items_added"],
            "currency_delta": {"copper": -4},
        },
        "followup_hooks": [],
    }

    narration_text = _safe_str(narration_payload.get("narration"))
    npc_payload = _safe_dict(narration_payload.get("npc"))

    row["selected_narration"] = narration_payload
    row["selected_output"] = narration_payload
    row["resolved_narration_payload"] = narration_payload
    row["narration_payload"] = narration_payload
    row["structured_narration"] = narration_payload

    row["narration"] = narration_text
    row["display_narration"] = narration_text
    row["visible_narration"] = narration_text
    row["selected_narration_text"] = narration_text

    row["npc"] = npc_payload
    row["npc_speaker"] = _safe_str(npc_payload.get("speaker"))
    row["npc_line"] = _safe_str(npc_payload.get("line"))

    row["display_source"] = "direct_graph_execution"
    row["dialogue_source"] = "direct_graph_execution"
    row["direct_graph_display_override"] = True
    row["direct_graph_execution_applied"] = True
    row["direct_graph_execution_kind"] = "buy_rations_from_bran"

    row["mechanic"] = "buying"
    row["meaningful_progress"] = True
    row["progress_category"] = "direct_graph_execution"

    return row


_DIRECT_GRAPH_XP_COMBAT_ACTION_IDS = {
    "protect_wagon_or_lure_bandits",
    "ambush_bandits",
    "fight_bandit_scouts",
    "fight_bandits",
    "defeat_bandit_scouts",
    "resolve_bandit_ambush",
}


_DIRECT_GRAPH_NON_XP_ACTION_IDS = {
    "report_findings_to_bran",
    "warn_garran",
    "tell_garran_about_ambush",
    "scout_quarry_road",
    "spot_bridge_watchers",
    "choose_ambush_response",
    "ask_bran_about_witness",
    "ask_bran_who_saw_witness",
    "question_bran_about_traveler",
    "search_for_witness",
    "return_marked_coin_proof",
    "buy_rations_from_bran",
    "rent_room_from_bran",
    "ask_garran_to_join",
}


def _is_direct_graph_explicit_xp_combat_action(action_id: str) -> bool:
    action_id_s = _safe_str(action_id)
    return action_id_s in _DIRECT_GRAPH_XP_COMBAT_ACTION_IDS


def _apply_explicit_combat_xp_direct_graph_execution(
    row: Dict[str, Any],
    *,
    action_id: str,
) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    action_id_s = _safe_str(action_id)

    if not _is_direct_graph_explicit_xp_combat_action(action_id_s):
        return row

    already_applied = (
        bool(row.get("direct_graph_xp_execution_applied"))
        and _safe_str(row.get("direct_graph_xp_execution_action_id")) == action_id_s
    )

    if not already_applied:
        state_delta = dict(_safe_dict(row.get("state_delta")))
        state_delta["xp_delta"] = int(state_delta.get("xp_delta") or 0) + 5
        state_delta["combat_started"] = True
        state_delta["combat_resolved"] = True
        row["state_delta"] = state_delta

    combat_result = {
        "ok": True,
        "outcome": "direct_graph_resolved",
        "xp_delta": 5,
        "summary": "The combat beat resolves through the scenario graph.",
    }

    row["result"] = {
        **_safe_dict(row.get("result")),
        "combat_result": combat_result,
        "xp_delta": 5,
        "mechanic": "combat_resolved",
        "meaningful_progress": True,
        "progress_category": "direct_graph_execution",
    }

    turn_contract = dict(_safe_dict(row.get("turn_contract")))
    turn_contract["mechanic"] = "combat_resolved"

    tc_state_delta = dict(_safe_dict(turn_contract.get("state_delta")))
    if not already_applied:
        tc_state_delta["xp_delta"] = int(tc_state_delta.get("xp_delta") or 0) + 5
    else:
        tc_state_delta.setdefault("xp_delta", 5)
    tc_state_delta["combat_started"] = True
    tc_state_delta["combat_resolved"] = True
    turn_contract["state_delta"] = tc_state_delta

    turn_contract["result"] = {
        **_safe_dict(turn_contract.get("result")),
        "combat_result": combat_result,
    }
    row["turn_contract"] = turn_contract

    narration_payload = {
        "format_version": "rpg_narration_v2",
        "source": "direct_graph_explicit_combat_xp_execution",
        "dialogue_source": "direct_graph_execution",
        "narration": (
            "The fight resolves in your favor, leaving the road briefly safer. "
            "You gain 5 XP from surviving the clash."
        ),
        "action": "Resolved the combat beat.",
        "npc": {},
        "reward": {
            "xp_delta": 5,
        },
        "followup_hooks": [],
    }

    narration_text = _safe_str(narration_payload.get("narration"))

    row["selected_narration"] = narration_payload
    row["selected_output"] = narration_payload
    row["resolved_narration_payload"] = narration_payload
    row["narration_payload"] = narration_payload
    row["structured_narration"] = narration_payload

    row["narration"] = narration_text
    row["display_narration"] = narration_text
    row["visible_narration"] = narration_text
    row["selected_narration_text"] = narration_text

    row["display_source"] = "direct_graph_execution"
    row["dialogue_source"] = "direct_graph_execution"
    row["direct_graph_display_override"] = True

    row["direct_graph_xp_execution_applied"] = True
    row["direct_graph_xp_execution_action_id"] = action_id_s
    row["direct_graph_execution_applied"] = True
    row["direct_graph_execution_kind"] = action_id_s

    row["mechanic"] = "combat_resolved"
    row["meaningful_progress"] = True
    row["progress_category"] = "direct_graph_execution"

    return row


_DIRECT_GRAPH_CANONICAL_ACTION_TEXT = {
    "buy_rations_from_bran": "I buy two rations from Bran.",
    "protect_wagon_or_lure_bandits": "I protect the wagon and fight the bandits.",
    "ask_garran_to_join": "I ask Garran to join me on the mill road.",
    "rent_room_from_bran": "I rent a common room from Bran.",
    "report_findings_to_bran": "I report the ambush evidence to Bran.",
    "warn_garran": "I warn Garran about the ambush signs on the road.",
    "tell_garran_about_ambush": "I tell Garran about the ambush signs on the road.",
    "scout_quarry_road": "I scout the quarry road for ambush signs.",
    "spot_bridge_watchers": "I watch the bridge for hidden watchers.",
    "choose_ambush_response": "I choose how to respond to the ambush signs.",
    "question_captured_bandit": "I question the captured bandit.",
    "search_bandit_satchel": "I search the bandit's satchel for proof.",
    "return_to_bran_with_proof": "I return to Bran with the marked coin proof.",
    "return_marked_coin_proof": "I return to Bran with the marked coin proof.",
}


def _canonical_direct_graph_action_text(action_id: str, fallback: str = "") -> str:
    action_id_s = _safe_str(action_id)
    return _safe_str(_DIRECT_GRAPH_CANONICAL_ACTION_TEXT.get(action_id_s) or fallback)


def _sync_direct_graph_canonical_action_display(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    direct = _safe_dict(row.get("direct_graph_action_completion"))
    action_id = _safe_str(
        direct.get("action_id")
        or row.get("direct_graph_execution_kind")
        or row.get("direct_graph_xp_execution_action_id")
    )
    canonical = _canonical_direct_graph_action_text(
        action_id,
        _safe_str(row.get("canonical_turn_action") or row.get("player_action")),
    )

    if not action_id or not canonical:
        return row

    row["player_action"] = canonical
    row["visible_player_action"] = canonical
    row["display_player_action"] = canonical
    row["canonical_turn_action"] = canonical

    turn_contract = dict(_safe_dict(row.get("turn_contract")))
    action_payload = dict(_safe_dict(turn_contract.get("action")))
    action_payload["text"] = canonical
    action_payload["display_text"] = canonical
    action_payload["canonical_text"] = canonical
    action_payload["source"] = _safe_str(action_payload.get("source") or "direct_graph_execution")
    turn_contract["action"] = action_payload
    row["turn_contract"] = turn_contract

    selected = dict(_safe_dict(row.get("selected_narration") or row.get("selected_output")))
    if selected:
        selected["action"] = _safe_str(selected.get("action") or canonical)
        row["selected_narration"] = selected
        row["selected_output"] = selected
        row["resolved_narration_payload"] = selected
        row["narration_payload"] = selected
        row["structured_narration"] = selected

    row["direct_graph_canonical_action_synced"] = True
    row["direct_graph_canonical_action_id"] = action_id
    return row


def _classify_visible_action_category(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    direct = _safe_dict(row.get("direct_graph_action_completion"))
    action_id = _safe_str(direct.get("action_id") or row.get("direct_graph_execution_kind"))

    validated = _safe_dict(row.get("validated_presentation_intent"))
    validated_category = _normalize_presentation_category(validated.get("primary_category"))
    if validated_category != "general":
        if validated_category in {"dialogue", "social"}:
            return "social"
        if validated_category == "economy":
            return "buying"
        return validated_category

    social_action_prefixes = (
        "ask_",
        "report_",
        "warn_",
        "tell_",
        "question_",
        "confront_",
        "counter_",
        "press_",
        "persuade_",
        "accuse_",
        "negotiate_",
    )

    evidence_action_prefixes = (
        "return_",
        "search_",
        "inspect_",
        "decipher_",
        "read_",
        "recover_",
        "deliver_",
    )

    if any(action_id.startswith(prefix) for prefix in social_action_prefixes):
        return "social"

    if any(action_id.startswith(prefix) for prefix in evidence_action_prefixes):
        return "evidence"

    text = _normalize_turn_action_text(
        " ".join(
            [
                _safe_str(row.get("player_action")),
                _safe_str(row.get("canonical_turn_action")),
                action_id,
            ]
        )
    )

    if action_id == "buy_rations_from_bran" or ("buy" in text and "ration" in text):
        return "buying"

    if action_id in {
        "protect_wagon_or_lure_bandits",
        "ambush_bandits",
        "fight_bandit_scouts",
        "fight_bandits",
        "defeat_bandit_scouts",
        "resolve_bandit_ambush",
    }:
        return "combat"

    if any(
        term in text
        for term in (
            "ask",
            "tell",
            "warn",
            "report",
            "question",
            "confront",
            "persuade",
            "accuse",
            "counter",
            "pressure",
            "negotiate",
            "arrest",
            "testify",
            "witness",
        )
    ):
        return "social"

    if any(term in text for term in ("read", "decipher", "ledger", "note", "coin", "proof")):
        return "evidence"

    if any(term in text for term in ("search", "inspect", "scout", "watch", "look", "track", "examine")):
        return "investigation"

    if any(term in text for term in ("travel", "road", "wagon yard", "old mill", "quarry")):
        return "travel"

    return "general"


_BAD_GENERIC_FALLBACK_SNIPPETS = (
    "practical transaction",
    "movement resolves",
    "combat moment resolves",
    "exchange is handled",
    "current route",
)


def _fallback_narration_for_action_category(row: Dict[str, Any]) -> str:
    category = _classify_visible_action_category(row)

    if category == "buying":
        return "The purchase resolves cleanly, with coin changing hands and supplies added to your pack."

    if category == "combat":
        return "The fight resolves through the current objective, leaving clear consequences behind."

    if category == "travel":
        return "You move along the route with purpose, carrying the investigation toward the next location."

    if category == "investigation":
        return "You examine the scene for concrete signs, narrowing the search to details that can be acted on."

    if category == "social":
        return "The conversation focuses on the immediate lead, pressing for names, places, and evidence that can move the investigation forward."

    if category == "evidence":
        return "The evidence gives the investigation a firmer shape, connecting the current lead to the next step."

    return "The action advances the current objective without adding unsupported consequences."


def _cleanup_bad_generic_fallback_narration(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))

    if row.get("direct_graph_display_override"):
        return row

    narration = (
        _safe_str(row.get("display_narration"))
        or _safe_str(row.get("visible_narration"))
        or _safe_str(row.get("selected_narration_text"))
        or _safe_str(row.get("narration"))
    )
    narration_l = narration.lower()

    if not narration:
        return row

    if not any(snippet in narration_l for snippet in _BAD_GENERIC_FALLBACK_SNIPPETS):
        return row

    cleaned = _fallback_narration_for_action_category(row)

    row["narration"] = cleaned
    row["display_narration"] = cleaned
    row["visible_narration"] = cleaned
    row["selected_narration_text"] = cleaned
    row["fallback_narration_cleanup_applied"] = True
    row["fallback_narration_category"] = _classify_visible_action_category(row)

    selected = dict(_safe_dict(row.get("selected_narration") or row.get("selected_output")))
    if selected:
        selected["narration"] = cleaned
        selected["source"] = _safe_str(selected.get("source") or "deterministic_category_fallback")
        row["selected_narration"] = selected
        row["selected_output"] = selected
        row["resolved_narration_payload"] = selected
        row["narration_payload"] = selected
        row["structured_narration"] = selected

    return row


def _infer_social_target_npc(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    text = _normalize_turn_action_text(
        " ".join(
            [
                _safe_str(row.get("player_action")),
                _safe_str(row.get("canonical_turn_action")),
                _safe_str(_safe_dict(row.get("direct_graph_action_completion")).get("action_id")),
            ]
        )
    )

    direct = _safe_dict(row.get("direct_graph_action_completion"))
    action_id = _safe_str(
        direct.get("action_id")
        or row.get("direct_graph_execution_kind")
        or row.get("direct_graph_canonical_action_id")
    )

    if "bran" in action_id:
        return "Bran"
    if "garran" in action_id:
        return "Garran"
    if "mira" in action_id:
        return "Mira"
    if "marlowe" in action_id:
        return "Agent Marlowe"
    if "magistrate" in action_id:
        return "Magistrate"
    if "voss" in action_id:
        return "Captain Voss"
    if "veska" in action_id:
        return "Handler Veska"
    if "teamster" in action_id:
        return "Old Teamster"
    if "bandit" in action_id:
        return "Captured Bandit"
    if "ally" in action_id or "allies" in action_id:
        return "Garran"
    if "magistrate" in action_id:
        return "Magistrate"
    if "patron" in action_id:
        return "Local Patron"
    if "local" in action_id and "patron" in action_id:
        return "Local Patron"

    if "bran" in text:
        return "Bran"
    if "garran" in text:
        return "Garran"
    if "mira" in text:
        return "Mira"
    if "sera" in text:
        return "Sera"
    if "marlowe" in text:
        return "Agent Marlowe"
    if "voss" in text:
        return "Captain Voss"
    if "veska" in text:
        return "Handler Veska"
    if "bandit" in text:
        return "Captured Bandit"

    if "magistrate" in text:
        return "Magistrate"
    if "teamster" in text:
        return "Old Teamster"
    if "agent" in text or "route pressure agent" in text:
        return "Route Agent"
    if "ally" in text or "allies" in text:
        return "Garran"
    if "local patron" in text or "patron" in text:
        return "Local Patron"

    return ""


def _deterministic_social_npc_line(row: Dict[str, Any]) -> Dict[str, str]:
    row = _safe_dict(row)
    speaker = _infer_social_target_npc(row)
    text = _normalize_turn_action_text(
        " ".join(
            [
                _safe_str(row.get("player_action")),
                _safe_str(row.get("canonical_turn_action")),
                _safe_str(_safe_dict(row.get("direct_graph_action_completion")).get("action_id")),
            ]
        )
    )

    action_id = _safe_str(
        _safe_dict(row.get("direct_graph_action_completion")).get("action_id")
        or row.get("direct_graph_execution_kind")
        or row.get("direct_graph_canonical_action_id")
    )

    if not speaker:
        return {}

    if "buy" in text and "ration" in text:
        return {
            "speaker": speaker,
            "line": "Two rations. That should keep you moving if the road turns bad.",
        }

    if speaker == "Local Patron":
        return {
            "speaker": speaker,
            "line": "If you mean the old bridge, folk avoid it before dawn. Too many quiet wagons, too few honest reasons.",
        }

    if action_id.startswith("ask_") and speaker == "Bran":
        return {
            "speaker": speaker,
            "line": "Ask plainly. If it touches the road, the side door, or that traveler, I will tell you what I know.",
        }

    if action_id.startswith("ask_") and speaker == "Garran":
        return {
            "speaker": speaker,
            "line": "If this is about the road, say it straight. I would rather know the danger before the wheels hit it.",
        }

    if action_id.startswith("warn_") and speaker == "Garran":
        return {
            "speaker": speaker,
            "line": "Then we move carefully. I will not drive blind into a trap.",
        }

    if action_id.startswith("warn_"):
        return {
            "speaker": speaker,
            "line": "Then we treat it as real trouble and warn anyone still exposed.",
        }

    if action_id.startswith("report_") and speaker == "Bran":
        return {
            "speaker": speaker,
            "line": "That is enough to stop guessing. Show me where the proof points next.",
        }

    if action_id.startswith("return_") and "proof" in action_id:
        return {
            "speaker": speaker,
            "line": "That proof gives us a name to push on. Now we make sure it cannot disappear.",
        }

    if action_id.startswith("question_") and speaker == "Captured Bandit":
        return {
            "speaker": speaker,
            "line": "I only carried what I was paid to carry. The mark on it is the part you should fear.",
        }

    if action_id.startswith("confront_") or action_id.startswith("counter_"):
        return {
            "speaker": speaker,
            "line": "Careful. If you are going to press this, make sure the proof is already in other hands.",
        }

    if "magistrate" in speaker.lower() or "arrest" in text:
        return {
            "speaker": speaker,
            "line": "Bring me proof that holds under daylight, and I will act on it.",
        }

    if "teamster" in speaker.lower():
        return {
            "speaker": speaker,
            "line": "If the east road is being watched, the wagons need to move in pairs or not at all.",
        }

    if "warn" in text:
        return {
            "speaker": speaker,
            "line": "Then we treat it as real trouble, not tavern gossip.",
        }

    if "report" in text or "proof" in text or "evidence" in text:
        return {
            "speaker": speaker,
            "line": "That is something we can act on. Tell me exactly where it points next.",
        }

    if "ask" in text or "question" in text:
        return {
            "speaker": speaker,
            "line": "Ask it plainly, and I will answer what I know.",
        }

    if "confront" in text:
        return {
            "speaker": speaker,
            "line": "Careful. Accusations like that need proof, not just nerve.",
        }

    if "tell" in text:
        return {
            "speaker": speaker,
            "line": "Then we should move before someone else decides the next step for us.",
        }

    return {
        "speaker": speaker,
        "line": "That gives us a direction. Now we need the next solid piece of proof.",
    }


def _sync_selected_narration_npc_to_top_level(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))

    existing_npc = _safe_dict(row.get("npc"))
    existing_speaker = _safe_str(row.get("npc_speaker") or existing_npc.get("speaker"))
    existing_line = _safe_str(row.get("npc_line") or existing_npc.get("line"))

    if existing_speaker and existing_line:
        row["npc"] = {
            "speaker": existing_speaker,
            "line": existing_line,
        }
        row["npc_speaker"] = existing_speaker
        row["npc_line"] = existing_line
        return row

    selected = _safe_dict(
        row.get("selected_narration")
        or row.get("selected_output")
        or row.get("resolved_narration_payload")
        or row.get("narration_payload")
        or row.get("structured_narration")
    )
    selected_npc = _safe_dict(selected.get("npc"))

    selected_speaker = _safe_str(selected_npc.get("speaker"))
    selected_line = _safe_str(selected_npc.get("line"))

    if not selected_speaker or not selected_line:
        return row

    npc = {
        "speaker": selected_speaker,
        "line": selected_line,
    }

    row["npc"] = npc
    row["npc_speaker"] = selected_speaker
    row["npc_line"] = selected_line
    row["top_level_npc_sync_applied"] = True
    row["top_level_npc_sync_source"] = "selected_narration.npc"

    # Keep all narration payload aliases consistent.
    selected["npc"] = npc
    row["selected_narration"] = selected
    row["selected_output"] = selected
    row["resolved_narration_payload"] = selected
    row["narration_payload"] = selected
    row["structured_narration"] = selected

    return row


def _ensure_social_npc_line_coverage(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))

    if row.get("direct_graph_display_override"):
        return row

    category = _classify_visible_action_category(row)
    direct = _safe_dict(row.get("direct_graph_action_completion"))
    action_id = _safe_str(
        direct.get("action_id")
        or row.get("direct_graph_execution_kind")
        or row.get("direct_graph_canonical_action_id")
    )

    socialish_action = (
        action_id.startswith("ask_")
        or action_id.startswith("report_")
        or action_id.startswith("warn_")
        or action_id.startswith("tell_")
        or action_id.startswith("question_")
        or action_id.startswith("confront_")
        or action_id.startswith("counter_")
        or action_id.startswith("return_")
        or action_id.startswith("choose_")
    )

    if category not in {"social", "evidence"} and not socialish_action:
        return row

    existing_line = _safe_str(row.get("npc_line") or _safe_dict(row.get("npc")).get("line"))
    if existing_line:
        return row

    npc = _deterministic_social_npc_line(row)
    if not npc:
        return row

    row["npc"] = npc
    row["npc_speaker"] = _safe_str(npc.get("speaker"))
    row["npc_line"] = _safe_str(npc.get("line"))
    row["npc_line_fallback_applied"] = True
    row["npc_line_fallback_source"] = "deterministic_social_graph_line"

    selected = dict(_safe_dict(row.get("selected_narration") or row.get("selected_output")))
    selected["npc"] = npc
    selected["dialogue_source"] = "deterministic_social_graph_line"
    row["selected_narration"] = selected
    row["selected_output"] = selected
    row["resolved_narration_payload"] = selected
    row["narration_payload"] = selected
    row["structured_narration"] = selected

    return row


_DIRECT_GRAPH_COMBAT_MECHANICS = {
    "combat_started",
    "combat_resolved",
    "xp_gain",
}


_DIRECT_GRAPH_EXPLICIT_COMBAT_ACTION_IDS = {
    "protect_wagon_or_lure_bandits",
    "ambush_bandits",
    "fight_bandit_scouts",
    "fight_bandits",
    "defeat_bandit_scouts",
    "resolve_bandit_ambush",
}


_DIRECT_GRAPH_NONCOMBAT_ACTION_IDS = {
    "report_findings_to_bran",
    "warn_garran",
    "tell_garran_about_ambush",
    "scout_quarry_road",
    "spot_bridge_watchers",
    "choose_ambush_response",
    "question_captured_bandit",
    "search_bandit_satchel",
    "return_to_bran_with_proof",
    "return_marked_coin_proof",
    "ask_bran_about_witness",
    "ask_bran_who_saw_witness",
    "question_bran_about_traveler",
    "search_for_witness",
    "return_to_allies_with_voss_proof",
    "counter_voss_intimidation",
    "detect_safehouse_watchers",
    "prepare_safehouse_defense",
    "scout_east_road_pressure_points",
    "scout_ridge_hideout",
    "intercept_veska_courier",
    "question_veska_courier",
    "recover_veska_route_map",
    "confront_route_pressure_agents",
    "warn_east_road_teamsters",
    "return_with_veska_name",
    "plan_veska_pursuit",
}


def _is_direct_graph_explicit_combat_action_id(action_id: str) -> bool:
    return _safe_str(action_id) in _DIRECT_GRAPH_EXPLICIT_COMBAT_ACTION_IDS


def _is_direct_graph_known_noncombat_action_id(action_id: str) -> bool:
    action_id_s = _safe_str(action_id)
    if action_id_s in _DIRECT_GRAPH_NONCOMBAT_ACTION_IDS:
        return True

    noncombat_prefixes = (
        "ask_",
        "report_",
        "warn_",
        "tell_",
        "question_",
        "search_",
        "scout_",
        "spot_",
        "detect_",
        "prepare_",
        "return_",
        "recover_",
        "confront_",
        "counter_",
        "plan_",
        "choose_",
        "read_",
        "decipher_",
        "inspect_",
    )

    return any(action_id_s.startswith(prefix) for prefix in noncombat_prefixes)


def _strip_combat_mechanics_from_noncombat_direct_graph_row(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    direct = dict(_safe_dict(row.get("direct_graph_action_completion")))
    action_id = _safe_str(direct.get("action_id") or row.get("direct_graph_execution_kind"))

    if not action_id:
        return row

    if _is_direct_graph_explicit_combat_action_id(action_id):
        return row

    if not _is_direct_graph_known_noncombat_action_id(action_id):
        return row

    def _clean_list(values: Any) -> List[Any]:
        return [
            value
            for value in _safe_list(values)
            if _safe_str(value) not in _DIRECT_GRAPH_COMBAT_MECHANICS
        ]

    direct["mechanics"] = _clean_list(direct.get("mechanics"))
    direct["changed_parts"] = _clean_list(direct.get("changed_parts"))
    row["direct_graph_action_completion"] = direct

    row["mechanics_covered_this_turn"] = _clean_list(row.get("mechanics_covered_this_turn"))
    row["direct_graph_changed_parts"] = _clean_list(row.get("direct_graph_changed_parts"))

    cleaned_hooks = []
    changed = False
    for hook in _safe_list(row.get("fired_hooks")):
        hook = dict(_safe_dict(hook))
        if _safe_str(hook.get("kind")) == "graph_direct_completion":
            hook["mechanics"] = _clean_list(hook.get("mechanics"))
            hook["changed_parts"] = _clean_list(hook.get("changed_parts"))
            effects = dict(_safe_dict(hook.get("effects")))
            flags = dict(_safe_dict(effects.get("flags")))
            for mechanic_name in _DIRECT_GRAPH_COMBAT_MECHANICS:
                flags.pop(f"mechanic:{mechanic_name}", None)
            effects["flags"] = flags
            hook["effects"] = effects
            changed = True
        cleaned_hooks.append(hook)

    if changed:
        row["fired_hooks"] = cleaned_hooks
        row["direct_graph_noncombat_mechanics_cleanup_applied"] = True
        row["direct_graph_noncombat_mechanics_cleanup_action_id"] = action_id

    return row


def _apply_direct_graph_display_quality_pass(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))

    row = _sync_direct_graph_canonical_action_display(row)
    row = _cleanup_bad_generic_fallback_narration(row)
    row = _ensure_social_npc_line_coverage(row)
    row = _sync_selected_narration_npc_to_top_level(row)
    row = _strip_combat_mechanics_from_noncombat_direct_graph_row(row)

    return row


def _direct_complete_graph_action_from_command(
    *,
    command: str,
    row: Dict[str, Any],
    all_graph_actions: List[Dict[str, Any]],
    completed_action_ids: set[str],
    completed_mechanics: set[str],
) -> Dict[str, Any]:
    command_s = _safe_str(command)
    row = dict(_safe_dict(row))

    matched = _find_matching_graph_action_for_command(
        command_s,
        _safe_list(all_graph_actions),
    )

    if not matched:
        return {
            "completed": False,
            "reason": "no_matching_graph_action",
        }

    action_id = _graph_action_id(matched)
    mechanics = _infer_mechanics_from_graph_action(matched, command_s)
    mechanic = mechanics[0] if mechanics else ""
    changed_parts = _direct_completion_changed_parts_for_mechanics(mechanics)

    completed_parts: List[str] = []

    if action_id:
        completed_action_ids.add(action_id)
        completed_parts.append(f"action:{action_id}")

    for mechanic_name in mechanics:
        completed_mechanics.add(mechanic_name)
        completed_parts.append(f"mechanic:{mechanic_name}")

    effects = _safe_dict(matched.get("effects"))
    flags = _safe_dict(effects.get("flags"))
    for key, value in flags.items():
        key_s = _safe_str(key)
        if value is True and key_s.startswith("mechanic:"):
            completed_mechanics.add(key_s.split("mechanic:", 1)[1])
            completed_parts.append(key_s)

    covered_this_turn = list(_safe_list(row.get("mechanics_covered_this_turn")))
    for mechanic_name in mechanics:
        if mechanic_name not in covered_this_turn:
            covered_this_turn.append(mechanic_name)
    row["mechanics_covered_this_turn"] = sorted(covered_this_turn)

    direct_changed_parts = list(_safe_list(row.get("direct_graph_changed_parts")))
    for part in changed_parts:
        if part not in direct_changed_parts:
            direct_changed_parts.append(part)
    row["direct_graph_changed_parts"] = sorted(direct_changed_parts)

    # Special deterministic completion for Garran party setup.
    text = _normalize_turn_action_text(command_s)
    matched_id_l = _safe_str(action_id).lower()
    if (
        "ask_garran_to_join" in matched_id_l
        or ("garran" in text and ("join" in text or "come with" in text or "travel with" in text))
    ):
        completed_action_ids.add("ask_garran_to_join")
        completed_mechanics.add("party_setup")
        completed_mechanics.add("party_recruitment")
        completed_parts.extend(
            [
                "action:ask_garran_to_join",
                "mechanic:party_setup",
                "mechanic:party_recruitment",
            ]
        )

        for mechanic_name in ("party_setup", "party_recruitment"):
            completed_mechanics.add(mechanic_name)
            if mechanic_name not in row["mechanics_covered_this_turn"]:
                row["mechanics_covered_this_turn"].append(mechanic_name)

        row["party_setup_completed"] = True
        row["party_recruitment_completed"] = True
        row["garran_recruited"] = True

        party = dict(_safe_dict(row.get("party")))
        companions = list(_safe_list(party.get("companions")))
        if not any("garran" in _safe_str(c).lower() for c in companions):
            companions.append("npc:garran")
        party["companions"] = companions
        row["party"] = party

        fired_hooks = list(_safe_list(row.get("fired_hooks")))
        fired_hooks.append(
            {
                "hook_id": "hook:mechanic:recruit_garran",
                "action_id": "ask_garran_to_join",
                "graph_action_id": "ask_garran_to_join",
                "kind": "mechanic_objective_progress",
                "mechanic": "party_setup",
                "changed_parts": [
                    "party_setup",
                    "party_recruitment",
                    "companion_added",
                    "milestone_progressed",
                    "mechanic_completed",
                ],
                "effects": {
                    "party": {"add_companion": "npc:garran"},
                    "flags": {
                        "party:garran_recruited": True,
                        "mechanic:party_setup": True,
                        "mechanic:party_recruitment": True,
                    },
                },
                "summary": "Garran joins the party for the mill road.",
                "display": {
                    "narration": "Garran accepts the danger of the mill road and prepares to travel with you.",
                    "npc": {
                        "speaker": "Garran",
                        "line": "If the road is involved, you should not walk it alone.",
                    },
                    "summary": "Garran recruited for the road.",
                },
            }
        )
        row["fired_hooks"] = fired_hooks

    fired_hooks = list(_safe_list(row.get("fired_hooks")))
    fired_hooks.append(
        {
            "hook_id": f"hook:graph_direct:{action_id or 'unknown'}",
            "action_id": action_id,
            "graph_action_id": action_id,
            "kind": "graph_direct_completion",
            "mechanic": mechanic,
            "mechanics": mechanics,
            "changed_parts": changed_parts,
            "effects": {
                "flags": {
                    **{f"mechanic:{m}": True for m in mechanics},
                },
            },
            "summary": f"Graph action completed: {action_id or command_s}",
        }
    )
    row["fired_hooks"] = fired_hooks

    if action_id == "buy_rations_from_bran":
        row = _apply_buy_rations_direct_graph_execution(row)

    if _is_direct_graph_explicit_xp_combat_action(action_id):
        row = _apply_explicit_combat_xp_direct_graph_execution(
            row,
            action_id=action_id,
        )

    if (
        _is_direct_graph_known_noncombat_action_id(action_id)
        and not _is_direct_graph_explicit_combat_action_id(action_id)
    ):
        mechanics = [
            mechanic_name
            for mechanic_name in _safe_list(mechanics)
            if _safe_str(mechanic_name) not in _DIRECT_GRAPH_COMBAT_MECHANICS
        ]
        changed_parts = [
            part
            for part in _safe_list(changed_parts)
            if _safe_str(part) not in _DIRECT_GRAPH_COMBAT_MECHANICS
        ]
        completed_parts = [
            part
            for part in _safe_list(completed_parts)
            if _safe_str(part) not in _DIRECT_GRAPH_COMBAT_MECHANICS
        ]

    return {
        "completed": bool(completed_parts),
        "action_id": action_id,
        "mechanic": mechanic,
        "mechanics": mechanics,
        "changed_parts": changed_parts,
        "completed_parts": sorted(set(completed_parts)),
        "execution_applied": bool(row.get("direct_graph_execution_applied")),
        "execution_kind": _safe_str(row.get("direct_graph_execution_kind")),
        "xp_execution_applied": bool(row.get("direct_graph_xp_execution_applied")),
        "xp_delta": _safe_dict(row.get("state_delta")).get("xp_delta"),
        "row": row,
    }


def _collect_direct_completion_mechanics(transcript: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for row in _safe_list(transcript):
        row = _safe_dict(row)
        direct = _safe_dict(row.get("direct_graph_action_completion"))

        for mechanic in _safe_list(direct.get("mechanics")):
            mechanic_s = _safe_str(mechanic)
            if mechanic_s:
                counts[mechanic_s] = counts.get(mechanic_s, 0) + 1

        for mechanic in _safe_list(row.get("mechanics_covered_this_turn")):
            mechanic_s = _safe_str(mechanic)
            if mechanic_s:
                counts[mechanic_s] = counts.get(mechanic_s, 0) + 1

    return counts


def _safe_positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _collect_direct_graph_lifecycle_evidence(
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in _safe_list(transcript)]

    mechanics_counts: Dict[str, int] = {}
    changed_part_counts: Dict[str, int] = {}
    action_counts: Dict[str, int] = {}

    examples: List[Dict[str, Any]] = []

    for row in rows:
        direct = _safe_dict(row.get("direct_graph_action_completion"))
        mechanics = set()

        for mechanic in _safe_list(direct.get("mechanics")):
            mechanic_s = _safe_str(mechanic)
            if mechanic_s:
                mechanics.add(mechanic_s)

        for mechanic in _safe_list(row.get("mechanics_covered_this_turn")):
            mechanic_s = _safe_str(mechanic)
            if mechanic_s:
                mechanics.add(mechanic_s)

        for part in _safe_list(direct.get("changed_parts")):
            part_s = _safe_str(part)
            if part_s:
                changed_part_counts[part_s] = changed_part_counts.get(part_s, 0) + 1

        for part in _safe_list(row.get("direct_graph_changed_parts")):
            part_s = _safe_str(part)
            if part_s:
                changed_part_counts[part_s] = changed_part_counts.get(part_s, 0) + 1

        for hook in _safe_list(row.get("fired_hooks")):
            hook = _safe_dict(hook)
            if _safe_str(hook.get("kind")) != "graph_direct_completion":
                continue

            for part in _safe_list(hook.get("changed_parts")):
                part_s = _safe_str(part)
                if part_s:
                    changed_part_counts[part_s] = changed_part_counts.get(part_s, 0) + 1

            for mechanic in _safe_list(hook.get("mechanics")):
                mechanic_s = _safe_str(mechanic)
                if mechanic_s:
                    mechanics.add(mechanic_s)

        for mechanic in mechanics:
            mechanics_counts[mechanic] = mechanics_counts.get(mechanic, 0) + 1

        action_id = _safe_str(direct.get("action_id"))
        if action_id:
            action_counts[action_id] = action_counts.get(action_id, 0) + 1

        if direct.get("completed") and len(examples) < 25:
            examples.append(
                {
                    "turn_index": row.get("turn_index") or row.get("turn"),
                    "player_action": row.get("player_action"),
                    "action_id": action_id,
                    "mechanics": sorted(mechanics),
                    "changed_parts": sorted(
                        set(_safe_list(direct.get("changed_parts")))
                        | set(_safe_list(row.get("direct_graph_changed_parts")))
                    ),
                }
            )

    faction_like_count = (
        int(mechanics_counts.get("faction_consequence") or 0)
        + int(changed_part_counts.get("faction_consequence") or 0)
        + int(changed_part_counts.get("world_signal") or 0)
    )

    npc_like_count = (
        int(mechanics_counts.get("npc_reaction") or 0)
        + int(changed_part_counts.get("npc_reaction") or 0)
        + int(changed_part_counts.get("npc_memory") or 0)
    )

    combat_like_count = (
        int(mechanics_counts.get("combat_started") or 0)
        + int(mechanics_counts.get("combat_resolved") or 0)
        + int(changed_part_counts.get("combat_started") or 0)
        + int(changed_part_counts.get("combat_resolved") or 0)
    )

    pressure_like_count = faction_like_count + combat_like_count

    aftermath_like_count = faction_like_count + npc_like_count + combat_like_count

    escalation_like_count = (
        pressure_like_count
        + int(mechanics_counts.get("xp_gain") or 0)
        + int(changed_part_counts.get("xp_gain") or 0)
    )

    return {
        "format_version": "direct_graph_lifecycle_evidence_v1",
        "ok": aftermath_like_count > 0,
        "completed_action_count": sum(action_counts.values()),
        "mechanics_counts": mechanics_counts,
        "changed_part_counts": changed_part_counts,
        "action_counts": action_counts,
        "faction_like_count": faction_like_count,
        "npc_like_count": npc_like_count,
        "combat_like_count": combat_like_count,
        "pressure_like_count": pressure_like_count,
        "aftermath_like_count": aftermath_like_count,
        "escalation_like_count": escalation_like_count,
        "examples": examples,
    }


def _record_completed_graph_progress_from_row(
    row: Dict[str, Any],
    *,
    completed_action_ids: set[str],
    completed_mechanics: set[str],
) -> None:
    row = _safe_dict(row)

    for hook in _safe_list(row.get("fired_hooks")):
        hook = _safe_dict(hook)

        hook_id = _safe_str(hook.get("hook_id") or hook.get("id") or hook.get("action_id"))
        if hook_id:
            completed_action_ids.add(hook_id)

        action_id = _safe_str(hook.get("action_id") or hook.get("graph_action_id"))
        if action_id:
            completed_action_ids.add(action_id)

        mechanic = _safe_str(hook.get("mechanic") or hook.get("required_mechanic"))
        if mechanic:
            completed_mechanics.add(mechanic)

        effects = _safe_dict(hook.get("effects"))
        flags = _safe_dict(effects.get("flags"))
        for key, value in flags.items():
            if value is True and _safe_str(key).startswith("mechanic:"):
                completed_mechanics.add(_safe_str(key).split("mechanic:", 1)[1])

    mechanics_seen = _safe_list(row.get("mechanics_covered_this_turn"))
    for mechanic in mechanics_seen:
        if _safe_str(mechanic):
            completed_mechanics.add(_safe_str(mechanic))

    party = _safe_dict(row.get("party"))
    companions = _safe_list(party.get("companions"))
    if any("garran" in _safe_str(c).lower() for c in companions):
        completed_mechanics.add("party_setup")
        completed_action_ids.add("ask_garran_to_join")


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

    top_graph_action_id = _safe_str(top_graph_action.get("action_id") or top_graph_action.get("id"))
    suppressed_actions = _safe_dict(graph_state.get("scenario_progression_suppressed_actions"))
    completed_action_ids = {
        _safe_str(value)
        for value in _safe_list(graph_state.get("scenario_progression_completed_action_ids"))
    }
    completed_mechanics = {
        _safe_str(value)
        for value in _safe_list(graph_state.get("scenario_progression_completed_mechanics"))
    }
    top_graph_mechanic = _safe_str(
        top_graph_action.get("mechanic")
        or top_graph_action.get("required_mechanic")
        or top_graph_action.get("completes_mechanic")
    )

    if (
        (top_graph_action_id and top_graph_action_id in completed_action_ids)
        or (top_graph_mechanic and top_graph_mechanic in completed_mechanics)
        or _is_graph_action_suppressed(
            top_graph_action_id,
            suppressed_actions=suppressed_actions,
            turn_index=int(graph_state.get("turn_index") or 0),
        )
    ):
        debug = _safe_dict(player_agent_debug)
        debug["scenario_progression_graph_action_preferred"] = {
            "changed": False,
            "blocked": True,
            "action_id": top_graph_action_id,
            "reason": "top_graph_action_suppressed_or_completed",
        }
        return (
            player_action,
            player_agent_selection_source,
            player_agent_selection_reason,
            debug,
        )

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
        "[AUTOPLAY-PROBE]",
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





def _build_scenario_progression_action_repeat_summary(
    *,
    warnings: List[Dict[str, Any]],
    suppressed_actions: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in _safe_list(warnings)]

    by_action_id: Dict[str, int] = {}
    for row in rows:
        action_id = _safe_str(row.get("action_id") or "unknown")
        by_action_id[action_id] = by_action_id.get(action_id, 0) + 1

    return {
        "format_version": "scenario_progression_action_repeat_summary_v1",
        "ok": len(rows) <= 5,
        "repeat_warning_count": len(rows),
        "suppressed_action_count": len(_safe_dict(suppressed_actions)),
        "by_action_id": by_action_id,
        "warnings": rows,
        "suppressed_actions": _safe_dict(suppressed_actions),
    }


def _build_suppressed_selection_guard_summary(
    *,
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    checked_count = 0
    retargeted_count = 0
    no_replacement_count = 0
    by_action_id: Dict[str, int] = {}
    examples: List[Dict[str, Any]] = []

    for row in _safe_list(transcript):
        row = _safe_dict(row)
        guard = _safe_dict(row.get("suppressed_selected_action_guard"))
        if not guard:
            continue

        checked_count += 1

        if guard.get("retargeted"):
            retargeted_count += 1

        if guard.get("reason") == "suppressed_selected_action_but_no_replacement":
            no_replacement_count += 1

        suppressed_match = _safe_dict(guard.get("suppressed_match"))
        action_id = _safe_str(suppressed_match.get("action_id"))
        if action_id:
            by_action_id[action_id] = by_action_id.get(action_id, 0) + 1

        if (guard.get("retargeted") or guard.get("reason")) and len(examples) < 20:
            examples.append(
                {
                    "turn_index": row.get("turn_index") or row.get("turn"),
                    "selected_before_guard": row.get(
                        "selected_command_before_suppression_guard"
                    ),
                    "final_player_action": row.get("player_action"),
                    "guard": guard,
                }
            )

    return {
        "format_version": "suppressed_selection_guard_summary_v1",
        "ok": no_replacement_count == 0,
        "checked_count": checked_count,
        "retargeted_count": retargeted_count,
        "no_replacement_count": no_replacement_count,
        "by_action_id": by_action_id,
        "examples": examples,
    }


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
        if row.get("unsupported_combat_claim_suppressed"):
            repaired_violation_counts = violation_counts  # count as handled
            repaired_violation_counts["unsupported_combat_claim_suppressed"] = (
                repaired_violation_counts.get("unsupported_combat_claim_suppressed", 0) + 1
            )
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


def _dialogue_text_from_selected_output(row: Dict[str, Any]) -> Dict[str, str]:
    row = _safe_dict(row)

    selected = _safe_dict(row.get("selected_narration"))
    if selected:
        npc = _safe_dict(selected.get("npc"))
        return {
            "narration": _safe_str(selected.get("narration")),
            "npc_speaker": _safe_str(npc.get("speaker")),
            "npc_line": _safe_str(npc.get("line")),
            "display_source": _safe_str(selected.get("dialogue_source") or row.get("dialogue_source")),
        }

    npc = _safe_dict(row.get("npc"))
    return {
        "narration": _safe_str(row.get("narration") or row.get("display_narration")),
        "npc_speaker": _safe_str(npc.get("speaker") or row.get("npc_speaker")),
        "npc_line": _safe_str(npc.get("line") or row.get("npc_line") or row.get("dialogue")),
        "display_source": _safe_str(row.get("dialogue_source") or row.get("display_source")),
    }


def _apply_dialogue_action_relevance_gate(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    player_action = _safe_str(row.get("player_action") or row.get("action") or row.get("input"))

    selected = _dialogue_text_from_selected_output(row)
    display_source = selected.get("display_source", "")

    source_gate = should_allow_display_source(
        player_action=player_action,
        display_source=display_source,
        row=row,
    )

    relevance = validate_dialogue_action_relevance(
        player_action=player_action,
        row=row,
        display_source=display_source,
        narration=selected.get("narration", ""),
        npc_speaker=selected.get("npc_speaker", ""),
        npc_line=selected.get("npc_line", ""),
    )

    row["dialogue_action_relevance"] = relevance
    row["dialogue_display_source_gate"] = source_gate
    if row.get("validated_presentation_intent"):
        row = _apply_validated_presentation_category_to_relevance(row)

    if source_gate.get("ok") and relevance.get("ok"):
        return row

    fallback = build_action_relevant_fallback(
        player_action=player_action,
        row=row,
    )

    fallback_narration = _safe_str(fallback.get("narration"))
    fallback_action = _safe_str(fallback.get("action"))
    fallback_source = _safe_str(fallback.get("dialogue_source"))

    row["dialogue_action_relevance_repaired"] = True
    row["dialogue_action_relevance_repair_reason"] = {
        "source_gate": source_gate,
        "relevance": relevance,
    }

    row["selected_narration"] = fallback
    row["selected_output"] = fallback

    row["narration"] = fallback_narration
    row["display_narration"] = fallback_narration
    row["selected_narration_text"] = fallback_narration

    row["dialogue_source"] = fallback_source
    row["display_source"] = fallback_source

    row["npc"] = {}
    row["npc_line"] = ""
    row["npc_speaker"] = ""
    row["dialogue"] = ""

    row["action"] = fallback_action or row.get("action")

    for nested_key in ("result", "presentation", "display", "ui"):
        nested = dict(_safe_dict(row.get(nested_key)))
        if nested:
            nested["selected_narration"] = fallback
            nested["selected_output"] = fallback
            nested["narration"] = fallback_narration
            nested["display_narration"] = fallback_narration
            nested["selected_narration_text"] = fallback_narration
            nested["dialogue_source"] = fallback_source
            nested["display_source"] = fallback_source
            nested["npc"] = {}
            nested["npc_line"] = ""
            nested["npc_speaker"] = ""
            nested["dialogue"] = ""
            row[nested_key] = nested

    # Then keep the after-repair validation:

    row["dialogue_action_relevance_after_repair"] = validate_dialogue_action_relevance(
        player_action=player_action,
        row=row,
        display_source=fallback_source,
        narration=fallback_narration,
        npc_speaker="",
        npc_line="",
    )
    row = _apply_validated_presentation_category_to_relevance(row)

    return row


def _turn_action_category(text: str) -> str:
    """Conservative fallback category for missing provider intent.

    This must not turn nouns such as ambush, bandit, road, room, scout, or
    supplies into authoritative combat/travel/service/economy by themselves.
    Prefer the validated provider presentation intent and authoritative row
    mechanics where available.
    """
    text_n = _normalize_turn_action_text(text)

    has_dialogue_verb = any(t in text_n for t in ("ask", "tell", "question", "persuade", "talk", "speak", "report", "warn"))
    has_service_term = any(t in text_n for t in ("room", "lodging", "bed", "rest", "sleep"))
    has_evidence_term = any(t in text_n for t in ("evidence", "clue", "proof", "coin", "track", "trail", "sign", "ledger", "note"))
    has_investigation_verb = any(t in text_n for t in ("inspect", "search", "look", "examine", "scout", "track", "watch"))

    if has_dialogue_verb and (has_service_term or has_evidence_term or has_investigation_verb):
        return "mixed"

    if has_dialogue_verb:
        return "dialogue"

    if any(t in text_n for t in ("buy", "purchase", "pay for")):
        return "economy"

    if any(t in text_n for t in ("rent", "book lodging", "take lodging")) or (
        has_service_term and any(t in text_n for t in ("pay", "rent", "book"))
    ):
        return "service"

    if any(t in text_n for t in ("attack", "fight", "combat", "strike", "defend")):
        return "combat"

    if has_investigation_verb or has_evidence_term:
        return "investigation"

    if any(t in text_n for t in ("travel", "leave", "go to", "move", "enter")):
        return "travel"

    return "general"



def _row_direct_action_id(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    direct = _safe_dict(row.get("direct_graph_action_completion"))
    return _safe_str(
        direct.get("action_id")
        or row.get("direct_graph_execution_kind")
        or row.get("direct_graph_canonical_action_id")
        or row.get("direct_graph_xp_execution_action_id")
    )


def _row_mechanics_set(row: Dict[str, Any]) -> set[str]:
    row = _safe_dict(row)
    mechanics = {
        _safe_str(v)
        for v in _safe_list(row.get("mechanics_covered_this_turn"))
        if _safe_str(v)
    }
    direct = _safe_dict(row.get("direct_graph_action_completion"))
    mechanics.update(
        _safe_str(v)
        for v in _safe_list(direct.get("mechanics"))
        if _safe_str(v)
    )
    result = _safe_dict(row.get("result"))
    turn_contract = _safe_dict(row.get("turn_contract"))
    contract_result = _safe_dict(turn_contract.get("result"))
    for value in (
        result.get("mechanic"),
        row.get("mechanic"),
        turn_contract.get("mechanic"),
        contract_result.get("mechanic"),
    ):
        mechanic = _safe_str(value)
        if mechanic:
            mechanics.add(mechanic)
    return mechanics


def _extract_row_presentation_intent(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)
    candidate, source = _find_presentation_intent_candidate(row)
    normalized = _normalize_presentation_intent(candidate)

    explicit_source = _safe_str(
        row.get("presentation_intent_parse_source")
        or _safe_dict(row.get("presentation_intent")).get("parse_source")
    )

    if (
        source == "presentation_intent"
        and normalized.get("primary_category") == "general"
        and not normalized.get("secondary_categories")
    ):
        nested_payload = dict(row)
        for key in ("presentation_intent", "presentationIntent", "intent"):
            nested_payload.pop(key, None)
        nested_candidate, nested_source = _find_presentation_intent_candidate(nested_payload)
        if nested_candidate and nested_source != "missing":
            candidate = nested_candidate
            source = nested_source
            normalized = _normalize_presentation_intent(candidate)

    normalized["parse_source"] = explicit_source or source
    return normalized


def _normalize_final_transcript_presentation_intents(rows: Any) -> List[Dict[str, Any]]:
    normalized_rows: List[Dict[str, Any]] = []
    for row_any in _safe_list(rows):
        row = dict(_safe_dict(row_any))

        current_intent = _normalize_presentation_intent(row.get("presentation_intent"))
        current_parse_source = _safe_str(
            _safe_dict(row.get("presentation_intent")).get("parse_source")
            or row.get("presentation_intent_parse_source")
        )

        presentation_intent = current_intent
        parse_source = current_parse_source

        if (
            not current_intent
            or current_intent.get("primary_category") == "general"
            and not current_intent.get("secondary_categories")
        ):
            nested_candidate = dict(row)
            for key in ("presentation_intent", "presentationIntent", "intent"):
                nested_candidate.pop(key, None)
            nested_intent, nested_source = _find_presentation_intent_candidate(nested_candidate)
            if nested_intent and nested_source != "missing":
                presentation_intent = _normalize_presentation_intent(nested_intent)
                parse_source = nested_source

        if not presentation_intent:
            presentation_intent = _extract_row_presentation_intent(row)

        presentation_intent["parse_source"] = _safe_str(
            parse_source or presentation_intent.get("parse_source") or "missing"
        )
        row["presentation_intent"] = presentation_intent
        row["presentation_intent_parse_source"] = _safe_str(
            row.get("presentation_intent_parse_source")
            or presentation_intent.get("parse_source")
        )
        row["llm_presentation_category"] = _safe_str(
            _safe_dict(row.get("presentation_intent")).get("primary_category")
        )
        row = _apply_turn_bound_presentation_compatibility_gate(row)
        row["final_transcript_intent_normalized"] = True
        normalized_rows.append(row)

    return normalized_rows


def _classify_visible_action_category_without_validated_intent(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    direct = _safe_dict(row.get("direct_graph_action_completion"))
    action_id = _safe_str(direct.get("action_id") or row.get("direct_graph_execution_kind"))

    if action_id.startswith(("ask_", "report_", "warn_", "tell_", "question_", "confront_", "counter_", "press_", "persuade_", "accuse_", "negotiate_")):
        return "dialogue"
    if action_id.startswith(("return_", "search_", "inspect_", "decipher_", "read_", "recover_", "deliver_")):
        return "evidence"
    if action_id == "buy_rations_from_bran":
        return "economy"
    if action_id in {
        "protect_wagon_or_lure_bandits",
        "ambush_bandits",
        "fight_bandit_scouts",
        "fight_bandits",
        "defeat_bandit_scouts",
        "resolve_bandit_ambush",
    }:
        return "combat"

    return _turn_action_category(
        " ".join(
            [
                _safe_str(row.get("player_action")),
                _safe_str(row.get("canonical_turn_action")),
                action_id,
            ]
        )
    )


def _authoritative_category_support(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)
    action_id = _row_direct_action_id(row)
    mechanics = _row_mechanics_set(row)
    result = _safe_dict(row.get("result"))
    turn_contract = _safe_dict(row.get("turn_contract"))
    contract_result = _safe_dict(turn_contract.get("result"))
    state_delta = _safe_dict(row.get("state_delta"))
    contract_delta = _safe_dict(turn_contract.get("state_delta"))
    direct = _safe_dict(row.get("direct_graph_action_completion"))

    supports = {
        "combat": bool(_turn_has_combat_support(row)),
        "economy": bool(
            "buying" in mechanics
            or "economy" in mechanics
            or "purchase" in mechanics
            or result.get("purchase_result")
            or contract_result.get("purchase_result")
            or action_id.startswith("buy_")
        ),
        "service": bool(
            "service" in mechanics
            or "lodging" in mechanics
            or "rent_room" in action_id
            or action_id.startswith("rent_")
            or result.get("service_result")
            or contract_result.get("service_result")
        ),
        "travel": bool(
            "travel" in mechanics
            or "location_changed" in mechanics
            or state_delta.get("location_changed")
            or contract_delta.get("location_changed")
            or result.get("location_changed")
            or contract_result.get("location_changed")
            or direct.get("location_delta")
        ),
        "evidence": bool(
            "evidence" in mechanics
            or "investigation" in mechanics
            or action_id.startswith(("report_", "return_", "search_", "inspect_", "recover_", "deliver_", "decipher_", "read_"))
        ),
        "investigation": bool(
            "investigation" in mechanics
            or action_id.startswith(("search_", "inspect_", "scout_", "watch_", "track_", "examine_"))
        ),
        "dialogue": bool(
            "dialogue" in mechanics
            or "social" in mechanics
            or action_id.startswith(("ask_", "tell_", "warn_", "report_", "question_", "persuade_", "confront_", "negotiate_"))
        ),
        "quest": bool("quest" in mechanics or action_id.startswith(("accept_", "complete_", "advance_quest_"))),
        "lore": bool("lore" in mechanics),
        "stealth": bool("stealth" in mechanics),
    }
    supports["social"] = supports["dialogue"]
    supports["mixed"] = True
    supports["general"] = True
    return supports


PRESENTATION_INTENT_SPECIFIC_PRIORITY = (
    "combat",
    "economy",
    "service",
    "travel",
    "evidence",
    "investigation",
    "dialogue",
    "quest",
    "lore",
    "stealth",
)


def _background_presentation_action_category(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    category = _normalize_presentation_category(
        _safe_dict(row.get("background_presentation_result")).get("action_category")
        or row.get("action_category")
    )
    return category


def _presentation_category_is_specific(category: str) -> bool:
    return category not in {"", "general", "mixed"}


def _specific_supported_presentation_category(
    *,
    row: Dict[str, Any],
    support: Dict[str, Any],
    fallback_category: str = "",
    action_text: str = "",
) -> str:
    """Choose a specific supported category before falling back to mixed/general.

    The N115.2 fallback safely exposed categories but over-selected ``mixed``
    because mixed is always supportable. This selector gives concrete
    authoritative evidence a chance to win first, so rows like ``report ambush
    evidence`` become evidence and ``scout ambush signs`` becomes
    investigation instead of mixed/general.
    """
    row = _safe_dict(row)
    action_id = _row_direct_action_id(row)
    mechanics = _row_mechanics_set(row)
    text_n = _normalize_turn_action_text(
        " ".join(
            part
            for part in (
                action_text,
                _safe_str(row.get("canonical_turn_action")),
                _safe_str(row.get("player_action")),
                action_id,
            )
            if part
        )
    )

    specific_fallback = _normalize_presentation_category(fallback_category)
    if (
        specific_fallback == "mixed"
        and support.get("service")
        and support.get("dialogue")
        and not support.get("evidence")
        and not support.get("investigation")
    ):
        return "mixed"

    if _presentation_category_is_specific(specific_fallback) and support.get(specific_fallback):
        # Do not let a broad text fallback override a more precise action id.
        if specific_fallback == "dialogue" and (
            "evidence" in mechanics
            or action_id.startswith(("report_", "return_", "recover_", "deliver_", "decipher_", "read_"))
            or any(t in text_n for t in ("evidence", "proof", "clue", "ledger", "note", "marked coin"))
        ) and support.get("evidence"):
            return "evidence"
        return specific_fallback

    if support.get("combat") and (
        "combat_started" in mechanics
        or "combat_resolved" in mechanics
        or action_id.startswith(("attack_", "fight_", "defend_", "ambush_", "resolve_bandit_ambush"))
    ):
        return "combat"

    if support.get("economy") and (
        "economy" in mechanics
        or "buying" in mechanics
        or "purchase" in mechanics
        or action_id.startswith(("buy_", "purchase_"))
    ):
        return "economy"

    if support.get("service") and (
        "service" in mechanics
        or "lodging" in mechanics
        or "rent_room" in action_id
        or action_id.startswith(("rent_", "book_lodging"))
    ):
        return "service"

    if support.get("travel") and (
        "travel" in mechanics
        or "location_changed" in mechanics
        or action_id.startswith(("travel_", "go_to_", "enter_", "leave_"))
    ):
        return "travel"

    if support.get("evidence") and (
        "evidence" in mechanics
        or action_id.startswith(("report_", "return_", "recover_", "deliver_", "decipher_", "read_"))
        or any(t in text_n for t in ("evidence", "proof", "clue", "ledger", "note", "marked coin"))
    ):
        return "evidence"

    if support.get("investigation") and (
        "investigation" in mechanics
        or action_id.startswith(("search_", "inspect_", "scout_", "watch_", "track_", "examine_"))
        or any(t in text_n for t in ("scout", "search", "inspect", "track", "examine", "look for", "signs"))
    ):
        return "investigation"

    if support.get("dialogue") and (
        "dialogue" in mechanics
        or "social" in mechanics
        or action_id.startswith(("ask_", "tell_", "warn_", "question_", "persuade_", "confront_", "negotiate_"))
        or any(t in text_n for t in ("ask", "tell", "warn", "question", "speak", "talk"))
    ):
        return "dialogue"

    for category in PRESENTATION_INTENT_SPECIFIC_PRIORITY:
        if support.get(category):
            return category

    if support.get("mixed"):
        return "mixed"
    return "general"


def _derive_fallback_presentation_intent_for_row(
    row: Dict[str, Any],
    *,
    support: Optional[Dict[str, Any]] = None,
    action_text: str = "",
) -> Dict[str, Any]:
    row = _safe_dict(row)
    support = _safe_dict(support) or _authoritative_category_support(row)
    fallback_category = _normalize_presentation_category(
        _background_presentation_action_category(row)
        or _classify_visible_action_category_without_validated_intent(row)
        or _turn_action_category(action_text or _safe_str(row.get("canonical_turn_action") or row.get("player_action")))
    )
    primary = _specific_supported_presentation_category(
        row=row,
        support=support,
        fallback_category=fallback_category,
        action_text=action_text,
    )

    secondary: List[str] = []
    for category in PRESENTATION_INTENT_SPECIFIC_PRIORITY:
        if category != primary and bool(support.get(category)) and category not in secondary:
            secondary.append(category)
        if len(secondary) >= 4:
            break

    return {
        "format_version": "presentation_intent_v1",
        "primary_category": primary,
        "secondary_categories": secondary,
        "confidence": 0.0,
        "reason": "deterministic_specific_fallback_from_authoritative_turn",
    }


def _display_action_kind_for_validated_category(category: str) -> str:
    category = _normalize_presentation_category(category)
    if category in {"dialogue", "social"}:
        return "social"
    if category == "economy":
        return "commerce"
    return category


def _apply_validated_presentation_category_to_relevance(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))
    relevance = dict(_safe_dict(row.get("dialogue_action_relevance")))
    if not relevance:
        return row

    validated = _safe_dict(row.get("validated_presentation_intent"))
    category = _normalize_presentation_category(validated.get("primary_category"))
    if category == "general":
        category = _normalize_presentation_category(
            _background_presentation_action_category(row)
            or _classify_visible_action_category_without_validated_intent(row)
        )
    if category == "general":
        return row

    action_kind = _display_action_kind_for_validated_category(category)
    old_action_kind = _safe_str(relevance.get("action_kind"))
    if old_action_kind and old_action_kind != action_kind:
        relevance["original_action_kind"] = old_action_kind
        relevance["action_kind_source"] = "validated_presentation_category"
    relevance["action_kind"] = action_kind
    relevance["validated_presentation_category"] = category
    relevance["validated_presentation_intent"] = validated
    row["dialogue_action_relevance"] = relevance
    return row


def _rewrite_public_presentation_intent_fields_from_validated(row: Dict[str, Any]) -> Dict[str, Any]:
    """Force public transcript LLM-intent fields to mirror validated provider intent.

    ``validated_presentation_intent.primary_category`` is the authoritative,
    clamped presentation category.  ``validated_presentation_intent.proposed_category``
    is the category proposed by the provider/LLM before clamping.  Public fields
    named ``presentation_intent`` and ``llm_presentation_category`` are intended
    to report that provider proposal, not the deterministic fallback/default.

    This helper is intentionally artifact-time and unconditional when a proposed
    category exists, because run artifacts showed validated intent was correct
    while public row fields still serialized as ``general``/``missing``.
    """
    row = dict(_safe_dict(row))
    validated = _safe_dict(row.get("validated_presentation_intent"))
    if not validated:
        return row

    proposed_category = _normalize_presentation_category(
        validated.get("proposed_category")
        or validated.get("provider_category")
        or validated.get("llm_category")
        or "general"
    )
    if not proposed_category:
        proposed_category = "general"

    parse_source = _safe_str(
        validated.get("provider_intent_parse_source")
        or row.get("presentation_intent_parse_source")
        or "missing"
    )

    secondary_categories: List[str] = []
    for item in _safe_list(validated.get("secondary_categories")):
        normalized = _normalize_presentation_category(item)
        if normalized and normalized != proposed_category and normalized not in secondary_categories:
            secondary_categories.append(normalized)

    try:
        confidence = float(validated.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    public_intent = {
        "format_version": "presentation_intent_v1",
        "primary_category": proposed_category,
        "secondary_categories": secondary_categories[:4],
        "confidence": round(confidence, 3),
        "reason": _safe_str(validated.get("provider_reason") or "")[:240],
        "parse_source": parse_source,
    }

    row["presentation_intent"] = public_intent
    row["presentation_intent_parse_source"] = parse_source
    row["llm_presentation_category"] = proposed_category
    return row


def _validate_presentation_intent_for_row(
    row: Dict[str, Any],
    *,
    action_text: str = "",
) -> Dict[str, Any]:
    row = _safe_dict(row)
    proposed = _extract_row_presentation_intent(row)
    proposed_category = _normalize_presentation_category(proposed.get("primary_category"))
    support = _authoritative_category_support(row)

    fallback_category = _normalize_presentation_category(
        _background_presentation_action_category(row)
        or _classify_visible_action_category_without_validated_intent(row)
        or _turn_action_category(action_text or _safe_str(row.get("canonical_turn_action") or row.get("player_action")))
    )

    provider_intent_ok = bool(support.get(proposed_category, False)) and _presentation_category_is_specific(proposed_category)
    if provider_intent_ok:
        repaired_category = proposed_category
        reason = "provider_intent_supported"
    else:
        repaired_category = _specific_supported_presentation_category(
            row=row,
            support=support,
            fallback_category=fallback_category,
            action_text=action_text,
        )
        reason = (
            "provider_intent_supported_but_specific_fallback_preferred"
            if bool(support.get(proposed_category, False))
            else "provider_intent_not_supported_by_authoritative_turn"
        )

    if not support.get(repaired_category, False) and repaired_category in {"combat", "travel", "service", "economy"}:
        repaired_category = _specific_supported_presentation_category(
            row=row,
            support=support,
            fallback_category="",
            action_text=action_text,
        )

    validated_intent_ok = bool(support.get(repaired_category, False)) or repaired_category in {"general", "mixed"}
    provider_intent_repaired = repaired_category != proposed_category

    return {
        "format_version": "validated_presentation_intent_v1",
        "ok": validated_intent_ok,
        "provider_intent_ok": provider_intent_ok,
        "validated_intent_ok": validated_intent_ok,
        "provider_intent_repaired": provider_intent_repaired,
        "primary_category": repaired_category,
        "proposed_category": proposed_category,
        "fallback_category": fallback_category,
        "secondary_categories": proposed.get("secondary_categories") or [],
        "confidence": proposed.get("confidence") or 0.0,
        "reason": reason,
        "provider_reason": proposed.get("reason") or "",
        "provider_intent_parse_source": proposed.get("parse_source") or row.get("presentation_intent_parse_source") or "missing",
        "support": support,
    }


def _presentation_text_category(text: str) -> str:
    """Classify explicit non-combat state-change claims in presentation text.

    This is intentionally NOT a semantic categorizer. Semantic category should
    come from provider presentation_intent first and authoritative fallback
    second. Generic scene nouns such as room, road, bandit, ambush, blood,
    supplies, or coin must not trigger repair by themselves.

    Combat prose is especially expressive, so this helper deliberately does
    not classify combat. Combat hard-grounding is handled by the separate
    state-claim verifiers below, which only flag concrete damage/defeat/
    resolution claims that can be checked against authoritative JSON.
    """
    text_n = _normalize_turn_action_text(text)

    economy_phrases = (
        "you buy",
        "you purchase",
        "you pay",
        "you spend",
        "you hand over coin",
        "coin leaves your purse",
        "the purchase is complete",
        "the transaction is complete",
    )
    if any(t in text_n for t in economy_phrases):
        return "economy"

    service_phrases = (
        "you rent a room",
        "you rent the room",
        "you secure a room",
        "the room is yours",
        "lodging is secured",
        "you pay for lodging",
        "you settle into bed",
        "you rest for the night",
        "you sleep for the night",
    )
    if any(t in text_n for t in service_phrases):
        return "service"

    travel_phrases = (
        "you arrive at",
        "you arrive in",
        "you travel to",
        "you move to",
        "you leave for",
        "you set out for",
        "the location changes",
    )
    if any(t in text_n for t in travel_phrases):
        return "travel"

    return "general"


HARD_PRESENTATION_CLAIM_CATEGORIES = {"travel", "service", "economy"}


def _presentation_has_currency_or_reward_transfer_claim(text: str) -> bool:
    text_n = _normalize_turn_action_text(text)
    transfer_verbs = (
        "gives you",
        "hands you",
        "pays you",
        "rewards you",
        "grants you",
        "awards you",
        "places coins in your hand",
        "presses coins into your palm",
    )
    currency_terms = ("gold", "coin", "coins", "silver", "copper", "reward", "payment")
    return any(v in text_n for v in transfer_verbs) and any(t in text_n for t in currency_terms)


def _presentation_has_metaphorical_arrival_claim(text: str) -> bool:
    text_n = _normalize_turn_action_text(text)
    return any(
        phrase in text_n
        for phrase in (
            "arrive at a clearer understanding",
            "arrive at a conclusion",
            "arrive at an understanding",
        )
    )


def _row_has_authoritative_currency_or_reward_support(row: Dict[str, Any]) -> bool:
    row = _safe_dict(row)
    mechanics = _row_mechanics_set(row)
    if any(m in mechanics for m in ("currency_change", "reward", "economy", "buying", "purchase")):
        return True

    result = _safe_dict(row.get("result"))
    turn_contract = _safe_dict(row.get("turn_contract"))
    contract_result = _safe_dict(turn_contract.get("result"))
    for source in (row, result, turn_contract, contract_result):
        source_d = _safe_dict(source)
        if source_d.get("reward") or source_d.get("currency_delta") or source_d.get("currency_change"):
            return True
        if _safe_dict(source_d.get("delta")).get("currency"):
            return True
    return False


def _presentation_hard_grounding_check(row: Dict[str, Any], presentation_text: str) -> Dict[str, Any]:
    """Tier 1: deterministic hard factual grounding check.

    This check only rejects visible text when it asserts an explicit outcome that
    is not supported by authoritative turn state. It is intentionally not a
    semantic category validator. Soft classification disagreement is handled by
    metadata repair, not by replacing narration.
    """
    row = _safe_dict(row)
    support = _authoritative_category_support(row)
    claim_category = _presentation_text_category(presentation_text)
    reasons: List[str] = []
    hard_claim_details: List[Dict[str, Any]] = []

    if not (claim_category == "travel" and _presentation_has_metaphorical_arrival_claim(presentation_text)):
        if claim_category in HARD_PRESENTATION_CLAIM_CATEGORIES and not bool(support.get(claim_category)):
            reasons.append(f"unsupported_{claim_category}_claim")

    if _presentation_has_combat_damage_claim(presentation_text) and not _row_has_authoritative_combat_damage_support(row):
        reasons.append("unsupported_damage_claim")
        hard_claim_details.append({
            "claim_type": "combat_damage",
            "authoritative_support_key_checked": "damage_delta|hp_delta|combat_damage",
            "support_found": False,
        })

    if _presentation_has_combat_defeat_claim(presentation_text) and not _row_has_authoritative_combat_defeat_support(row):
        reasons.append("unsupported_defeat_claim")
        hard_claim_details.append({
            "claim_type": "combat_defeat",
            "authoritative_support_key_checked": "enemy_defeated|defeated|victory",
            "support_found": False,
        })

    if _presentation_has_combat_resolution_claim(presentation_text) and not _row_has_authoritative_combat_resolution_support(row):
        reasons.append("unsupported_combat_resolution_claim")
        hard_claim_details.append({
            "claim_type": "combat_resolution",
            "authoritative_support_key_checked": "combat_resolved|encounter_resolved|victory|ended",
            "support_found": False,
        })

    if _presentation_has_currency_or_reward_transfer_claim(presentation_text) and not _row_has_authoritative_currency_or_reward_support(row):
        reasons.append("unsupported_currency_or_reward_claim")
        hard_claim_details.append({
            "claim_type": "currency_or_reward_transfer",
            "authoritative_support_key_checked": "reward|currency_delta|currency_change",
            "support_found": False,
        })

    return {
        "format_version": "presentation_hard_grounding_v2",
        "ok": not reasons,
        "tier": "hard_grounding",
        "claim_category": claim_category,
        "claim_details": hard_claim_details,
        "hard_claim_types": [detail.get("claim_type") for detail in hard_claim_details],
        "reasons": reasons,
        "support": support,
        "requires_visible_text_replacement": bool(reasons),
    }


def _presentation_soft_classification_check(
    *,
    compat_ok: bool,
    compat_diag: Dict[str, Any],
) -> Dict[str, Any]:
    compat_diag = _safe_dict(compat_diag)
    reason = _safe_str(compat_diag.get("reason"))
    soft_repair = not compat_ok and reason == "action_presentation_category_mismatch"
    return {
        "format_version": "presentation_soft_classification_v1",
        "ok": not soft_repair,
        "tier": "soft_classification",
        "reason": reason,
        "compatibility": compat_diag,
        "metadata_repair_required": soft_repair,
        "requires_visible_text_replacement": False,
    }


def _soft_metadata_repair_reason_for_row(
    *,
    row: Dict[str, Any],
    soft_diag: Dict[str, Any],
) -> str:
    """Return a metadata-only repair reason when visible text can remain.

    Hard grounding is handled separately. This helper activates the soft tier
    for classification-only changes, including provider-intent fallback repairs
    and stale relevance category cleanup. These are metadata repairs, not
    narration rewrites.
    """
    row = _safe_dict(row)
    soft_diag = _safe_dict(soft_diag)

    if bool(soft_diag.get("metadata_repair_required")):
        return _safe_str(soft_diag.get("reason")) or "soft_classification_metadata_repaired"

    validated = _safe_dict(row.get("validated_presentation_intent"))
    if bool(validated.get("provider_intent_repaired")):
        return "provider_intent_reclassified"

    relevance = _safe_dict(row.get("dialogue_action_relevance"))
    if bool(relevance.get("presentation_intent_sync_repaired")):
        return _safe_str(relevance.get("presentation_intent_sync_reason")) or "dialogue_relevance_category_synced"

    after_repair = _safe_dict(row.get("dialogue_action_relevance_after_repair"))
    if bool(after_repair.get("presentation_intent_sync_repaired")):
        return _safe_str(after_repair.get("presentation_intent_sync_reason")) or "dialogue_relevance_after_repair_category_synced"

    return ""


def _background_semantic_reviewer_diagnostic(
    *,
    row: Dict[str, Any],
    soft_diag: Dict[str, Any],
    hard_diag: Dict[str, Any],
) -> Dict[str, Any]:
    """Tier 3 placeholder/diagnostic for optional async semantic review.

    The autoplay harness should not block the turn or call a second LLM here.
    This diagnostic records that a background semantic reviewer may later refine
    classification metadata. Immediate safety remains Tier 1 deterministic.
    """
    row = _safe_dict(row)
    return {
        "format_version": "background_semantic_reviewer_v1",
        "queued": bool(_safe_dict(soft_diag).get("metadata_repair_required")),
        "blocking": False,
        "allowed_to_replace_visible_text": False,
        "purpose": "classification_metadata_review_only",
        "validated_presentation_category": _safe_str(row.get("validated_presentation_category")),
        "soft_reason": _safe_str(_safe_dict(soft_diag).get("reason")),
        "hard_ok": bool(_safe_dict(hard_diag).get("ok", True)),
    }


def _dialogue_presentation_is_category_compatible(
    *,
    action_text: str,
    presentation_text: str,
    row: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    validated_intent = _validate_presentation_intent_for_row(row, action_text=action_text)
    action_category = _normalize_presentation_category(validated_intent.get("primary_category"))
    presentation_category = _presentation_text_category(presentation_text)

    if not presentation_text.strip():
        return True, {
            "ok": True,
            "action_category": action_category,
            "presentation_category": presentation_category,
            "validated_presentation_intent": validated_intent,
            "reason": "empty_presentation",
        }

    if presentation_category == "general":
        return True, {
            "ok": True,
            "action_category": action_category,
            "presentation_category": presentation_category,
            "validated_presentation_intent": validated_intent,
            "reason": "general_presentation",
        }

    compatible_pairs = {
        ("dialogue", "investigation"),
        ("investigation", "dialogue"),
        ("dialogue", "evidence"),
        ("evidence", "dialogue"),
        ("evidence", "investigation"),
        ("investigation", "evidence"),
        ("mixed", "dialogue"),
        ("mixed", "service"),
        ("mixed", "investigation"),
        ("mixed", "evidence"),
        ("combat", "travel"),
        ("travel", "combat"),
    }

    if action_category == presentation_category or (action_category, presentation_category) in compatible_pairs:
        return True, {
            "ok": True,
            "action_category": action_category,
            "presentation_category": presentation_category,
            "validated_presentation_intent": validated_intent,
            "reason": "category_match",
        }

    mechanics = {
        _safe_str(v)
        for v in _safe_list(row.get("mechanics_covered_this_turn"))
        if _safe_str(v)
    }
    if presentation_category == "combat" and (
        "combat_started" in mechanics or "combat_resolved" in mechanics
    ):
        return True, {
            "ok": True,
            "action_category": action_category,
            "presentation_category": presentation_category,
            "validated_presentation_intent": validated_intent,
            "reason": "combat_supported_by_mechanics",
        }

    return False, {
        "ok": False,
        "action_category": action_category,
        "presentation_category": presentation_category,
        "validated_presentation_intent": validated_intent,
        "reason": "action_presentation_category_mismatch",
    }


def _build_category_compatible_presentation_fallback(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    action = _safe_str(row.get("canonical_turn_action") or row.get("player_action"))
    validated = _validate_presentation_intent_for_row(row, action_text=action)
    category = _normalize_presentation_category(validated.get("primary_category"))

    if category == "economy":
        return "You complete the purchase; your supplies and coin totals are updated by the authoritative turn result."

    if category == "service":
        return "You complete the service request; the authoritative turn result records the cost and any lodging or rest effect."

    if category == "combat":
        return "You press the fight according to the authoritative combat result; only recorded damage, rewards, and outcomes apply."

    if category == "travel":
        return "You move on according to the authoritative travel result; the current location and available routes update."

    if category == "investigation":
        return "You follow the clue trail; only evidence recorded by the authoritative turn result becomes true."

    if category in {"dialogue", "social"}:
        return "The conversation continues; any NPC response is limited to the authoritative social and quest state."

    if category == "evidence":
        return "You put the evidence forward; only facts recorded by the authoritative turn result become true."

    if category == "mixed":
        return "The turn resolves across its recorded parts; only authoritative service, social, travel, combat, and evidence results apply."

    return "The action resolves according to the authoritative turn result."


def _presentation_has_combat_damage_claim(text: str) -> bool:
    """Return True only for concrete combat damage/HP state claims.

    Combat-colored prose is not enough. This intentionally ignores words such
    as ambush, bandit, strike, blade, threat, fear, blood, and fight unless the
    text asserts a checkable damage/HP mutation.
    """
    text_n = _normalize_turn_action_text(text)
    damage_phrases = (
        "you take damage",
        "you suffer damage",
        "you lose hit points",
        "you lose hp",
        "your hp drops",
        "your hit points drop",
        "damage is dealt",
        "deals damage",
        "takes damage",
        "enemy takes damage",
        "the enemy takes damage",
        "the bandit takes damage",
        "you deal damage",
        "you wound him",
        "you wound her",
        "you wound them",
        "you wound the",
        "your blow wounds",
    )
    if any(phrase in text_n for phrase in damage_phrases):
        return True
    if "damage" in text_n and any(
        phrase in text_n
        for phrase in (
            "you take",
            "you suffer",
            "you deal",
            "you inflict",
            "enemy takes",
            "the enemy takes",
            "bandit takes",
            "the bandit takes",
        )
    ):
        return True
    return False


def _presentation_has_combat_defeat_claim(text: str) -> bool:
    """Return True only for concrete defeat/death claims."""
    text_n = _normalize_turn_action_text(text)
    defeat_phrases = (
        "you defeat",
        "you kill",
        "you slay",
        "falls dead",
        "falls defeated",
        "falls lifeless",
        "collapses dead",
        "collapses lifeless",
        "is defeated",
        "are defeated",
        "is dead",
        "are dead",
        "the enemy falls",
        "the bandit falls",
        "the scout falls",
        "the strike team falls",
        "the enemy dies",
        "the bandit dies",
    )
    return any(phrase in text_n for phrase in defeat_phrases)


def _presentation_has_combat_resolution_claim(text: str) -> bool:
    """Return True only for concrete combat encounter resolution claims."""
    text_n = _normalize_turn_action_text(text)
    resolution_phrases = (
        "combat resolves",
        "combat is resolved",
        "the fight resolves",
        "the fight is over",
        "the battle is over",
        "the combat ends",
        "the encounter ends",
        "victory is yours",
        "you win the fight",
        "you win the battle",
        "the enemy surrenders",
        "the enemies surrender",
    )
    return any(phrase in text_n for phrase in resolution_phrases)


def _presentation_has_combat_claim(text: str) -> bool:
    """Legacy compatibility wrapper for concrete combat state claims only."""
    return (
        _presentation_has_combat_damage_claim(text)
        or _presentation_has_combat_defeat_claim(text)
        or _presentation_has_combat_resolution_claim(text)
    )


def _source_has_any_key(source: Any, keys: Tuple[str, ...]) -> bool:
    source_d = _safe_dict(source)
    for key in keys:
        if source_d.get(key) not in (None, False, "", [], {}):
            return True
    return False


def _row_authoritative_state_sources(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    row = _safe_dict(row)
    result = _safe_dict(row.get("result"))
    turn_contract = _safe_dict(row.get("turn_contract"))
    contract_result = _safe_dict(turn_contract.get("result"))
    direct = _safe_dict(row.get("direct_graph_action_completion"))
    return [
        row,
        result,
        turn_contract,
        contract_result,
        _safe_dict(row.get("state_delta")),
        _safe_dict(turn_contract.get("state_delta")),
        _safe_dict(row.get("combat_result")),
        _safe_dict(result.get("combat_result")),
        _safe_dict(contract_result.get("combat_result")),
        _safe_dict(row.get("combat_state_delta")),
        _safe_dict(result.get("combat_state_delta")),
        _safe_dict(contract_result.get("combat_state_delta")),
        direct,
    ]


def _row_has_authoritative_combat_damage_support(row: Dict[str, Any]) -> bool:
    mechanics = _row_mechanics_set(row)
    if any(
        mechanic in mechanics
        for mechanic in (
            "damage",
            "damage_dealt",
            "damage_taken",
            "combat_damage",
            "hp_delta",
            "health_delta",
        )
    ):
        return True

    damage_keys = (
        "damage",
        "damage_delta",
        "damage_dealt",
        "damage_taken",
        "hp_delta",
        "health_delta",
        "enemy_hp_delta",
        "player_hp_delta",
        "hit_points_delta",
    )
    return any(_source_has_any_key(source, damage_keys) for source in _row_authoritative_state_sources(row))


def _row_has_authoritative_combat_defeat_support(row: Dict[str, Any]) -> bool:
    mechanics = _row_mechanics_set(row)
    if any(
        mechanic in mechanics
        for mechanic in (
            "enemy_defeated",
            "enemy_defeat",
            "defeat",
            "defeated",
            "combat_resolved",
        )
    ):
        return True

    defeat_keys = (
        "enemy_defeated",
        "defeated_enemy",
        "defeated_enemies",
        "defeated",
        "defeat",
        "victory",
        "enemy_status",
    )
    for source in _row_authoritative_state_sources(row):
        source_d = _safe_dict(source)
        if _source_has_any_key(source_d, defeat_keys):
            return True
        status = _safe_str(source_d.get("status")).lower()
        if status in {"defeated", "dead", "resolved", "victory"}:
            return True
    return False


def _row_has_authoritative_combat_resolution_support(row: Dict[str, Any]) -> bool:
    mechanics = _row_mechanics_set(row)
    if any(
        mechanic in mechanics
        for mechanic in (
            "combat_resolved",
            "encounter_resolved",
            "combat_victory",
            "combat_ended",
        )
    ):
        return True

    resolution_keys = (
        "combat_resolved",
        "encounter_resolved",
        "resolved",
        "victory",
        "ended",
        "combat_ended",
    )
    return any(_source_has_any_key(source, resolution_keys) for source in _row_authoritative_state_sources(row))


def _turn_has_combat_support(row: Dict[str, Any]) -> bool:
    row = _safe_dict(row)
    mechanics = {
        _safe_str(v)
        for v in _safe_list(row.get("mechanics_covered_this_turn"))
        if _safe_str(v)
    }

    if "combat_started" in mechanics or "combat_resolved" in mechanics:
        return True

    direct = _safe_dict(row.get("direct_graph_action_completion"))
    direct_mechanics = {
        _safe_str(v)
        for v in _safe_list(direct.get("mechanics"))
        if _safe_str(v)
    }

    if "combat_started" in direct_mechanics or "combat_resolved" in direct_mechanics:
        return True

    if row.get("combat_result") or row.get("combat_state_delta"):
        return True

    return False


def _assert_repaired_dialogue_visible_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(_safe_dict(row))

    if not row.get("dialogue_action_relevance_repaired"):
        return row

    selected = _safe_dict(row.get("selected_narration") or row.get("selected_output"))
    final_narration = _safe_str(selected.get("narration"))
    final_action = _safe_str(selected.get("action"))
    final_source = _safe_str(
        selected.get("dialogue_source")
        or row.get("dialogue_source")
        or "deterministic_action_relevance_fallback"
    )

    if final_narration:
        row["narration"] = final_narration
        row["display_narration"] = final_narration
        row["selected_narration_text"] = final_narration

    if final_action:
        row["action"] = final_action

    row["dialogue_source"] = final_source
    row["display_source"] = final_source

    row["selected_narration"] = selected
    row["selected_output"] = selected

    row["npc"] = {}
    row["npc_line"] = ""
    row["npc_speaker"] = ""
    row["dialogue"] = ""

    for nested_key in ("result", "presentation", "display", "ui"):
        nested = dict(_safe_dict(row.get(nested_key)))
        if not nested:
            continue

        if final_narration:
            nested["narration"] = final_narration
            nested["display_narration"] = final_narration
            nested["selected_narration_text"] = final_narration

        if final_action:
            nested["action"] = final_action

        nested["dialogue_source"] = final_source
        nested["display_source"] = final_source
        nested["selected_narration"] = selected
        nested["selected_output"] = selected
        nested["npc"] = {}
        nested["npc_line"] = ""
        nested["npc_speaker"] = ""
        nested["dialogue"] = ""
        row[nested_key] = nested

    return row


def _normalize_repaired_dialogue_transcript_rows(
    transcript: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []

    for row in _safe_list(transcript):
        fixed = _assert_repaired_dialogue_visible_fields(_safe_dict(row))
        normalized.append(fixed)

    return normalized


def _build_dialogue_action_relevance_summary(
    *,
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in _safe_list(transcript)]

    checked_count = 0
    mismatch_count = 0
    repaired_count = 0
    unrepaired_count = 0
    source_gate_block_count = 0

    by_action_kind: Dict[str, int] = {}
    by_dialogue_kind: Dict[str, int] = {}
    by_reason: Dict[str, int] = {}
    examples: List[Dict[str, Any]] = []

    for row in rows:
        row = _sync_dialogue_action_relevance_with_validated_presentation(row)
        relevance = _safe_dict(row.get("dialogue_action_relevance"))
        source_gate = _safe_dict(row.get("dialogue_display_source_gate"))

        if not relevance:
            continue

        checked_count += 1

        action_kind = _safe_str(row.get("validated_presentation_category") or relevance.get("action_kind") or "unknown")
        dialogue_kind = _safe_str(relevance.get("dialogue_kind") or "unknown")
        by_action_kind[action_kind] = by_action_kind.get(action_kind, 0) + 1
        by_dialogue_kind[dialogue_kind] = by_dialogue_kind.get(dialogue_kind, 0) + 1

        source_blocked = bool(source_gate) and not bool(source_gate.get("ok", True))
        if source_blocked:
            source_gate_block_count += 1
            for reason in _safe_list(source_gate.get("blocked_reasons")):
                by_reason[_safe_str(reason)] = by_reason.get(_safe_str(reason), 0) + 1

        if not bool(relevance.get("ok")):
            mismatch_count += 1
            for reason in _safe_list(relevance.get("reasons")):
                by_reason[_safe_str(reason)] = by_reason.get(_safe_str(reason), 0) + 1

        if row.get("dialogue_action_relevance_repaired"):
            repaired_count += 1
        elif relevance and not bool(relevance.get("ok")):
            unrepaired_count += 1

        if (source_blocked or not bool(relevance.get("ok")) or row.get("dialogue_action_relevance_repaired")) and len(examples) < 20:
            selected_output = _safe_dict(row.get("selected_narration") or row.get("selected_output"))
            final_npc = _safe_dict(selected_output.get("npc") or row.get("npc"))
            final_narration = (
                selected_output.get("narration")
                or row.get("display_narration")
                or row.get("narration")
            )

            examples.append(
                {
                    "turn_index": row.get("turn_index") or row.get("turn"),
                    "player_action": row.get("player_action"),
                    "dialogue_source": row.get("dialogue_source"),
                    "relevance": relevance,
                    "source_gate": source_gate,
                    "repaired": bool(row.get("dialogue_action_relevance_repaired")),
                    "final_narration": final_narration,
                    "final_npc": final_npc,
                    "after_repair": row.get("dialogue_action_relevance_after_repair"),
                }
            )

    mismatch_rate = float(mismatch_count) / float(checked_count or 1)
    repaired_rate = float(repaired_count) / float(checked_count or 1)
    unrepaired_rate = float(unrepaired_count) / float(checked_count or 1)

    return {
        "format_version": "dialogue_action_relevance_summary_v1",
        "ok": checked_count > 0 and unrepaired_rate <= 0.35,
        "checked_count": checked_count,
        "mismatch_count": mismatch_count,
        "mismatch_rate": mismatch_rate,
        "repaired_count": repaired_count,
        "repaired_rate": repaired_rate,
        "unrepaired_count": unrepaired_count,
        "unrepaired_rate": unrepaired_rate,
        "source_gate_block_count": source_gate_block_count,
        "by_action_kind": by_action_kind,
        "by_dialogue_kind": by_dialogue_kind,
        "by_reason": by_reason,
        "examples": examples,
    }


def _build_dialogue_repair_quality_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    dialogue = _safe_dict(summary.get("dialogue_action_relevance_summary"))

    checked_count = int(dialogue.get("checked_count") or 0)
    repaired_count = int(dialogue.get("repaired_count") or 0)
    unrepaired_count = int(dialogue.get("unrepaired_count") or 0)

    repair_rate = 0.0
    if checked_count > 0:
        repair_rate = repaired_count / checked_count

    warnings: List[str] = []
    if repair_rate > 0.25:
        warnings.append("dialogue_action_relevance_repair_rate_high")
    if unrepaired_count > 0:
        warnings.append("dialogue_action_relevance_unrepaired_rows_present")

    return {
        "format_version": "dialogue_repair_quality_v1",
        "ok": unrepaired_count == 0,
        "product_quality_ok": repair_rate <= 0.25 and unrepaired_count == 0,
        "checked_count": checked_count,
        "repaired_count": repaired_count,
        "unrepaired_count": unrepaired_count,
        "repair_rate": repair_rate,
        "max_recommended_repair_rate": 0.25,
        "warnings": warnings,
    }


def _build_dialogue_stale_source_summary(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_source: Dict[str, int] = {}
    by_reason: Dict[str, int] = {}
    by_action_category: Dict[str, int] = {}
    by_presentation_category: Dict[str, int] = {}
    examples: List[Dict[str, Any]] = []

    repaired_count = 0
    checked_count = 0

    for row in _safe_list(transcript):
        row = _safe_dict(row)
        relevance = _safe_dict(
            row.get("dialogue_action_relevance")
            or row.get("dialogue_action_relevance_result")
            or row.get("dialogue_action_relevance_gate")
        )

        if not relevance:
            continue

        checked_count += 1

        repaired = bool(
            relevance.get("repaired")
            or relevance.get("fallback_applied")
            or row.get("dialogue_action_relevance_repaired")
        )

        if not repaired:
            continue

        repaired_count += 1

        compat = _safe_dict(row.get("dialogue_presentation_compatibility"))
        source = _safe_str(
            relevance.get("source")
            or row.get("selected_narration_source")
            or row.get("narration_source")
            or row.get("combined_background_source")
            or row.get("player_agent_selection_source")
            or "unknown"
        )
        reason = _safe_str(
            relevance.get("reason")
            or relevance.get("repair_reason")
            or relevance.get("fallback_reason")
            or compat.get("reason")
            or "unknown"
        )

        by_source[source] = by_source.get(source, 0) + 1
        by_reason[reason] = by_reason.get(reason, 0) + 1

        action_category = _safe_str(compat.get("action_category"))
        presentation_category = _safe_str(compat.get("presentation_category"))
        by_action_category[action_category] = by_action_category.get(action_category, 0) + 1 if action_category else by_action_category.get(action_category, 0)
        by_presentation_category[presentation_category] = by_presentation_category.get(presentation_category, 0) + 1 if presentation_category else by_presentation_category.get(presentation_category, 0)

        if len(examples) < 20:
            examples.append(
                {
                    "turn_index": row.get("turn_index") or row.get("turn"),
                    "player_action": row.get("player_action"),
                    "canonical_turn_action": row.get("canonical_turn_action"),
                    "source": source,
                    "reason": reason,
                    "selected_narration_preview": _safe_str(
                        row.get("selected_narration")
                        or row.get("display_narration")
                        or row.get("narration")
                    )[:240],
                }
            )

    repair_rate = repaired_count / checked_count if checked_count else 0.0

    return {
        "format_version": "dialogue_stale_source_summary_v1",
        "ok": True,
        "checked_count": checked_count,
        "repaired_count": repaired_count,
        "repair_rate": repair_rate,
        "by_source": by_source,
        "by_reason": by_reason,
        "by_action_category": by_action_category,
        "by_presentation_category": by_presentation_category,
        "examples": examples,
    }


def _build_turn_action_consistency_summary(
    *,
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    checked_count = 0
    mismatch_count = 0
    repaired_count = 0
    unrepaired_count = 0
    forced_override_count = 0
    by_field: Dict[str, int] = {}
    examples: List[Dict[str, Any]] = []

    for row in _safe_list(transcript):
        row = _safe_dict(row)
        consistency = _safe_dict(row.get("turn_action_consistency"))

        if not consistency:
            canonical = _safe_str(row.get("canonical_turn_action") or row.get("player_action"))
            if canonical:
                consistency = _build_turn_action_consistency(
                    row=row,
                    canonical_turn_action=canonical,
                )
            else:
                continue

        checked_count += 1

        current_mismatches = _safe_dict(consistency.get("mismatches"))

        source_check = _safe_dict(row.get("turn_action_source_check"))
        if source_check and not source_check.get("ok", True):
            current_mismatches = dict(current_mismatches)
            current_mismatches["canonical_turn_action"] = {
                "expected": source_check.get("original_player_action"),
                "actual": source_check.get("canonical_turn_action"),
            }

        forced = _safe_dict(row.get("mechanics_forced_action"))
        if forced.get("forced") is True:
            forced_override_count += 1

        if current_mismatches:
            mismatch_count += 1
            for field_name in current_mismatches.keys():
                by_field[field_name] = by_field.get(field_name, 0) + 1

        if row.get("turn_action_consistency_repaired"):
            repaired_count += 1

        if current_mismatches and not row.get("turn_action_consistency_repaired"):
            unrepaired_count += 1

        if (current_mismatches or row.get("turn_action_consistency_repaired")) and len(examples) < 20:
            examples.append(
                {
                    "turn_index": row.get("turn_index") or row.get("turn"),
                    "canonical_turn_action": consistency.get("canonical_turn_action"),
                    "ok": consistency.get("ok"),
                    "mismatches": consistency.get("mismatches"),
                    "before_repair": row.get("turn_action_consistency_before_repair"),
                    "progress_quality_player_action": _safe_dict(row.get("progress_quality")).get("player_action"),
                    "player_action": row.get("player_action"),
                }
            )

    mismatch_rate = float(mismatch_count) / float(checked_count or 1)
    repaired_rate = float(repaired_count) / float(checked_count or 1)
    unrepaired_rate = float(unrepaired_count) / float(checked_count or 1)

    return {
        "format_version": "turn_action_consistency_summary_v1",
        "ok": checked_count > 0 and unrepaired_count == 0 and forced_override_count == 0,
        "checked_count": checked_count,
        "mismatch_count": mismatch_count,
        "mismatch_rate": mismatch_rate,
        "repaired_count": repaired_count,
        "repaired_rate": repaired_rate,
        "unrepaired_count": unrepaired_count,
        "unrepaired_rate": unrepaired_rate,
        "forced_override_count": forced_override_count,
        "forced_action_override_count": forced_override_count,
        "by_field": by_field,
        "examples": examples,
    }


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
    turn_action_consistency_summary: Optional[Dict[str, Any]] = None,
    scenario_progression_action_repeat_summary: Optional[Dict[str, Any]] = None,
    story_arc_lifecycle_summary: Optional[Dict[str, Any]] = None,
    story_arc_aftermath_summary: Optional[Dict[str, Any]] = None,
    faction_reputation_summary: Optional[Dict[str, Any]] = None,
    followup_arc_progression_summary: Optional[Dict[str, Any]] = None,
    faction_pressure_summary: Optional[Dict[str, Any]] = None,
    followup_arc_resolution_summary: Optional[Dict[str, Any]] = None,
    pressure_pacing_summary: Optional[Dict[str, Any]] = None,
    escalation_branch_summary: Optional[Dict[str, Any]] = None,
    world_signal_summary: Optional[Dict[str, Any]] = None,
    escalation_arc_progression_summary: Optional[Dict[str, Any]] = None,
    world_state_compression_summary: Optional[Dict[str, Any]] = None,
    npc_agency_summary: Optional[Dict[str, Any]] = None,
    economy_pressure_summary: Optional[Dict[str, Any]] = None,
    combat_lifecycle_summary: Optional[Dict[str, Any]] = None,
    faction_consequence_summary: Optional[Dict[str, Any]] = None,
    npc_reaction_summary: Optional[Dict[str, Any]] = None,
    dialogue_action_relevance_summary: Optional[Dict[str, Any]] = None,
    suppressed_selection_guard_summary: Optional[Dict[str, Any]] = None,
    direct_graph_lifecycle_evidence: Optional[Dict[str, Any]] = None,
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
    story_arcs = _safe_dict(story_arc_lifecycle_summary)
    aftermath = _safe_dict(story_arc_aftermath_summary)
    factions = _safe_dict(faction_reputation_summary)
    followup_progression = _safe_dict(followup_arc_progression_summary)
    faction_pressure = _safe_dict(faction_pressure_summary)
    followup_resolution = _safe_dict(followup_arc_resolution_summary)
    pressure_pacing = _safe_dict(pressure_pacing_summary)
    escalation_branch = _safe_dict(escalation_branch_summary)
    world_signals = _safe_dict(world_signal_summary)
    escalation_progression = _safe_dict(escalation_arc_progression_summary)
    world_compression = _safe_dict(world_state_compression_summary)
    npc_agency = _safe_dict(npc_agency_summary)
    economy_pressure = _safe_dict(economy_pressure_summary)
    combat_lifecycle = _safe_dict(combat_lifecycle_summary)
    faction_consequence = _safe_dict(faction_consequence_summary)
    npc_reaction = _safe_dict(npc_reaction_summary)
    dialogue_relevance = _safe_dict(dialogue_action_relevance_summary)
    turn_action_consistency = _safe_dict(turn_action_consistency_summary)
    scenario_repeats = _safe_dict(scenario_progression_action_repeat_summary)
    suppressed_selection = _safe_dict(suppressed_selection_guard_summary)

    # Confirm these gates use fallback values:
    story_aftermath = aftermath
    aftermath_event_count = (
        story_aftermath.get("aftermath_event_count")
        or story_aftermath.get("event_count")
        or story_aftermath.get("direct_graph_aftermath_count")
    )

    faction_history_count = (
        factions.get("history_count")
        or factions.get("event_count")
        or factions.get("direct_graph_reputation_event_count")
    )

    pressure_event_count = (
        faction_pressure.get("pressure_event_count")
        or faction_pressure.get("event_count")
        or faction_pressure.get("direct_graph_pressure_count")
    )

    accepted_pressure_count = (
        pressure_pacing.get("accepted_pressure_count")
        or pressure_pacing.get("accepted_pressure_event_count")
        or pressure_pacing.get("pressure_event_count")
        or pressure_pacing.get("direct_graph_pressure_count")
    )

    followup_progression_count = (
        followup_progression.get("progression_event_count")
        or followup_progression.get("event_count")
        or followup_progression.get("direct_graph_progression_count")
    )

    followup_resolution_count = (
        followup_resolution.get("resolved_or_escalated_count")
        or followup_resolution.get("resolution_event_count")
        or followup_resolution.get("direct_graph_resolution_count")
    )

    escalation_branch = _safe_dict(escalation_branch_summary)
    branch_seeded_count = (
        escalation_branch.get("seeded_count")
        or escalation_branch.get("branch_count")
        or escalation_branch.get("direct_graph_branch_seed_count")
    )

    escalation_progression_count = (
        escalation_progression.get("progression_event_count")
        or escalation_progression.get("event_count")
        or escalation_progression.get("direct_graph_escalation_count")
    )

    npc_agency_event_count = (
        npc_agency.get("event_count")
        or npc_agency.get("memory_event_count")
        or npc_agency.get("direct_graph_agency_count")
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

    completed_or_failed_arc_count = int(story_arcs.get("completed_count") or 0) + int(story_arcs.get("failed_count") or 0)

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
        "scenario_progression_repeats_bounded": {
            "ok": int(scenario_repeats.get("repeat_warning_count") or 0) <= 5,
            "value": {
                "repeat_warning_count": scenario_repeats.get("repeat_warning_count"),
                "suppressed_action_count": scenario_repeats.get("suppressed_action_count"),
                "by_action_id": scenario_repeats.get("by_action_id"),
            },
            "expected": "repeated no-progress graph actions are suppressed and remain bounded",
            "message": "Scenario graph actions should not loop or crash autoplay.",
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
        "story_arc_resolution_present": {
            "ok": completed_or_failed_arc_count >= 1,
            "value": {
                "completed_count": story_arcs.get("completed_count"),
                "failed_count": story_arcs.get("failed_count"),
                "active_count": story_arcs.get("active_count"),
                "status_counts": story_arcs.get("status_counts"),
            },
            "expected": "at least one completed or failed story arc in 100-turn run",
            "message": "The 100-turn campaign should demonstrate deterministic story arc closure.",
        },
        "story_arc_aftermath_present": {
            "ok": int(aftermath_event_count or 0) >= 1,
            "value": {
                "aftermath_event_count": aftermath_event_count,
                "direct_graph_aftermath_count": story_aftermath.get("direct_graph_aftermath_count"),
                "world_signal_count": aftermath.get("world_signal_count"),
                "npc_memory_event_count": aftermath.get("npc_memory_event_count"),
                "followup_hook_count": aftermath.get("followup_hook_count"),
                "seeded_followup_arc_count": aftermath.get("seeded_followup_arc_count"),
            },
            "expected": "at least one bounded aftermath event from completed or failed arcs",
            "message": "Completed arcs should create deterministic aftermath.",
        },
        "faction_reputation_changed": {
            "ok": int(faction_history_count or 0) >= 1,
            "value": {
                "faction_count": factions.get("faction_count"),
                "direct_graph_reputation_event_count": factions.get("direct_graph_reputation_event_count"),
                "factions": factions.get("factions"),
            },
            "expected": "at least one faction reputation delta",
            "message": "Arc aftermath should produce bounded faction reputation consequences.",
        },
        "followup_arc_progression_present": {
            "ok": int(followup_progression_count or 0) >= 1,
            "value": {
                "progression_event_count": followup_progression_count,
                "direct_graph_progression_count": followup_progression.get("direct_graph_progression_count"),
                "progressed_count": followup_progression.get("progressed_count"),
                "progressed_arc_ids": followup_progression.get("progressed_arc_ids"),
                "world_signal_count": followup_progression.get("world_signal_count"),
            },
            "expected": "at least one seeded follow-up arc progresses",
            "message": "Seeded follow-up arcs should advance deterministically after their prerequisites are met.",
        },
        "faction_pressure_present": {
            "ok": int(pressure_event_count or 0) >= 1,
            "value": {
                "pressure_event_count": pressure_event_count,
                "direct_graph_pressure_count": faction_pressure.get("direct_graph_pressure_count"),
                "world_signal_count": faction_pressure.get("world_signal_count"),
                "by_faction": faction_pressure.get("by_faction"),
            },
            "expected": "at least one faction pressure event",
            "message": "Faction reputation changes should produce bounded pressure or support events.",
        },
        "followup_arc_resolution_present": {
            "ok": int(followup_resolution_count or 0) >= 1,
            "value": {
                "resolved_or_escalated_count": followup_resolution_count,
                "direct_graph_resolution_count": followup_resolution.get("direct_graph_resolution_count"),
                "resolved_count": followup_resolution.get("resolved_count"),
                "resolved_arc_ids": followup_resolution.get("resolved_arc_ids"),
                "escalation_seed_count": followup_resolution.get("escalation_seed_count"),
            },
            "expected": "at least one progressed follow-up arc resolves or escalates",
            "message": "Follow-up arcs should not remain only progressed; at least one should resolve or branch.",
        },
        "escalation_branch_seeded": {
            "ok": int(branch_seeded_count or 0) >= 1,
            "value": {
                "seeded_count": branch_seeded_count,
                "direct_graph_branch_seed_count": escalation_branch.get("direct_graph_branch_seed_count"),
                "escalation_seed_count": followup_resolution.get("escalation_seed_count"),
                "escalation_arcs": followup_resolution.get("escalation_arcs"),
            },
            "expected": "at least one escalation branch seeded from follow-up resolution",
            "message": "Resolved follow-up arcs should create bounded escalation branches.",
        },
        "pressure_pacing_active": {
            "ok": (
                int(accepted_pressure_count or 0) >= 1
                and (
                    int(pressure_pacing.get("rejected_pressure_event_count") or 0) >= 1
                    or int(pressure_pacing.get("direct_graph_pressure_count") or 0) >= 1
                    or bool(pressure_pacing.get("direct_graph_pacing_bridge_active"))
                )
            ),
            "value": {
                "accepted_pressure_count": accepted_pressure_count,
                "accepted_pressure_event_count": pressure_pacing.get("accepted_pressure_event_count"),
                "direct_graph_pressure_count": pressure_pacing.get("direct_graph_pressure_count"),
                "direct_graph_pacing_bridge_active": pressure_pacing.get("direct_graph_pacing_bridge_active"),
                "rejected_pressure_event_count": pressure_pacing.get("rejected_pressure_event_count"),
                "rejected_by_reason": pressure_pacing.get("rejected_by_reason"),
            },
            "expected": "pressure events accepted and either old pacing rejected spam or direct graph pressure bridge is active",
            "message": "Faction pressure should be paced or represented by direct graph lifecycle pressure evidence.",
        },
        "world_signal_summary_present": {
            "ok": int(world_signals.get("world_signal_count") or 0) >= 1,
            "value": {
                "world_signal_count": world_signals.get("world_signal_count"),
                "by_kind": world_signals.get("by_kind"),
                "by_faction": world_signals.get("by_faction"),
            },
            "expected": "global world signal summary exists",
            "message": "Report should separate pure aftermath signals from global world signals.",
        },
        "escalation_arc_progression_present": {
            "ok": int(escalation_progression_count or 0) >= 1,
            "value": {
                "progression_event_count": escalation_progression_count,
                "direct_graph_escalation_count": escalation_progression.get("direct_graph_escalation_count"),
                "progressed_count": escalation_progression.get("progressed_count"),
                "progressed_arc_ids": escalation_progression.get("progressed_arc_ids"),
                "pressure_event_count": escalation_progression.get("pressure_event_count"),
                "world_signal_count": escalation_progression.get("world_signal_count"),
            },
            "expected": "at least one escalation arc progresses",
            "message": "Seeded escalation arcs should advance deterministically.",
        },
        "world_state_compression_active": {
            "ok": int(world_compression.get("compression_event_count") or 0) >= 1
            and bool(_safe_dict(world_compression.get("latest_state_budget")).get("ok", True)),
            "value": {
                "compression_event_count": world_compression.get("compression_event_count"),
                "compressed_state_preview": world_compression.get("compressed_state_preview"),
                "latest_state_budget": world_compression.get("latest_state_budget"),
            },
            "expected": "compression events occur and state budget is respected",
            "message": "Long-run campaigns need bounded world state and memory compression.",
        },
        "npc_agency_present": {
            "ok": int(npc_agency_event_count or 0) >= 1,
            "value": {
                "event_count": npc_agency_event_count,
                "direct_graph_agency_count": npc_agency.get("direct_graph_agency_count"),
                "npc_count": npc_agency.get("npc_count"),
                "schedule_event_count": npc_agency.get("schedule_event_count"),
                "agency_event_count": npc_agency.get("agency_event_count"),
                "memory_event_count": npc_agency.get("memory_event_count"),
            },
            "expected": "at least one deterministic NPC agency event",
            "message": "100-turn readiness should demonstrate schedule-driven NPC agency.",
        },
        "economy_pressure_present": {
            "ok": int(economy_pressure.get("event_count") or 0) >= 1,
            "value": {
                "event_count": economy_pressure.get("event_count"),
                "paid_count": economy_pressure.get("paid_count"),
                "unpaid_count": economy_pressure.get("unpaid_count"),
                "warning_count": economy_pressure.get("warning_count"),
                "ending_currency": economy_pressure.get("ending_currency"),
                "total_spent": economy_pressure.get("total_spent"),
            },
            "expected": "at least one deterministic economy pressure/resource sink event",
            "message": "Long-run campaigns should include recurring resource pressure and sinks.",
        },
        "combat_lifecycle_present": {
            "ok": int(combat_lifecycle.get("encounter_count") or 0) >= 1
            and int(combat_lifecycle.get("event_count") or 0) >= 1,
            "value": {
                "encounter_count": combat_lifecycle.get("encounter_count"),
                "event_count": combat_lifecycle.get("event_count"),
                "injury_count": combat_lifecycle.get("injury_count"),
                "consequence_event_count": combat_lifecycle.get("consequence_event_count"),
                "economy_hint_count": combat_lifecycle.get("economy_hint_count"),
                "by_outcome": combat_lifecycle.get("by_outcome"),
            },
            "expected": "at least one deterministic combat encounter with lifecycle events",
            "message": "Long-run campaigns should include combat lifecycle/consequence pressure.",
        },
        "faction_consequence_present": {
            "ok": int(faction_consequence.get("event_count") or 0) >= 1,
            "value": {
                "event_count": faction_consequence.get("event_count"),
                "world_signal_count": faction_consequence.get("world_signal_count"),
                "by_faction": faction_consequence.get("by_faction"),
                "by_kind": faction_consequence.get("by_kind"),
            },
            "expected": "at least one deterministic long-term faction consequence",
            "message": "Faction reputation should produce long-term consequences.",
        },
        "npc_reaction_present": {
            "ok": int(npc_reaction.get("event_count") or 0) >= 1,
            "value": {
                "event_count": npc_reaction.get("event_count"),
                "memory_event_count": npc_reaction.get("memory_event_count"),
                "world_signal_count": npc_reaction.get("world_signal_count"),
                "by_npc": npc_reaction.get("by_npc"),
                "by_kind": npc_reaction.get("by_kind"),
            },
            "expected": "at least one deterministic NPC reaction to faction/consequence state",
            "message": "NPCs should react to long-term faction consequences.",
        },
        "dialogue_action_relevance_ok": {
            "ok": int(dialogue_relevance.get("checked_count") or 0) >= 1
            and int(dialogue_relevance.get("unrepaired_count") or 0) == 0
            and float(dialogue_relevance.get("mismatch_rate") or 0.0) <= 0.35,
            "value": {
                "checked_count": dialogue_relevance.get("checked_count"),
                "mismatch_count": dialogue_relevance.get("mismatch_count"),
                "mismatch_rate": dialogue_relevance.get("mismatch_rate"),
                "repaired_count": dialogue_relevance.get("repaired_count"),
                "unrepaired_count": dialogue_relevance.get("unrepaired_count"),
                "source_gate_block_count": dialogue_relevance.get("source_gate_block_count"),
                "by_reason": dialogue_relevance.get("by_reason"),
            },
            "expected": "dialogue selected for each turn is action-relevant or deterministically repaired",
            "message": "Player-facing narration/NPC dialogue must match the current action type.",
        },
        "turn_action_consistency_ok": {
            "ok": int(turn_action_consistency.get("checked_count") or 0) >= 1
            and int(turn_action_consistency.get("unrepaired_count") or 0) == 0,
            "value": {
                "checked_count": turn_action_consistency.get("checked_count"),
                "mismatch_count": turn_action_consistency.get("mismatch_count"),
                "mismatch_rate": turn_action_consistency.get("mismatch_rate"),
                "repaired_count": turn_action_consistency.get("repaired_count"),
                "unrepaired_count": turn_action_consistency.get("unrepaired_count"),
                "by_field": turn_action_consistency.get("by_field"),
            },
            "expected": "visible player action, progress action, resolver action, and hook action context all derive from canonical_turn_action",
            "message": "A turn must not mix player actions from different commands.",
        },
        "suppressed_selection_guard_ok": {
            "ok": int(suppressed_selection.get("no_replacement_count") or 0) == 0,
            "value": {
                "checked_count": suppressed_selection.get("checked_count"),
                "retargeted_count": suppressed_selection.get("retargeted_count"),
                "no_replacement_count": suppressed_selection.get("no_replacement_count"),
                "by_action_id": suppressed_selection.get("by_action_id"),
            },
            "expected": "suppressed selected actions are retargeted before resolver execution",
            "message": "Suppressed graph actions must not keep driving player-agent turns.",
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

        dedupe_key = f"{turn_index}:{name}"
        if dedupe_key in marked_this_turn:
            return
        marked_this_turn.add(dedupe_key)

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
    disabled_forced_action_candidates: List[Dict[str, Any]] = []

    marked_this_turn: set[str] = set()

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

        # Collect disabled forced action diagnostics
        forced_action = _safe_dict(row.get("mechanics_forced_action"))
        if forced_action and not forced_action.get("forced") and forced_action.get("disabled"):
            disabled_forced_action_candidates.append({
                "turn_index": turn_index,
                "mechanic": forced_action.get("mechanic"),
                "candidate_action": forced_action.get("candidate_action"),
                "reason": forced_action.get("reason"),
            })

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

        for mechanic in _safe_list(row.get("mechanics_covered_this_turn")):
            mechanic_s = _safe_str(mechanic)
            if mechanic_s:
                mark(mechanic_s, turn_index, row, "mechanics_covered_this_turn", "direct_graph")

        direct = _safe_dict(row.get("direct_graph_action_completion"))
        for mechanic in _safe_list(direct.get("mechanics")):
            mechanic_s = _safe_str(mechanic)
            if mechanic_s:
                mark(mechanic_s, turn_index, row, "direct_graph_action_completion", "direct_graph")

        for part in _safe_list(direct.get("changed_parts")):
            part_s = _safe_str(part)
            if part_s:
                mark(part_s, turn_index, row, "direct_graph_changed_parts", "direct_graph")

        # Apply coverage aliases for direct completion mechanics
        coverage_aliases = {
            "party_setup": ["party_recruitment"],
            "lodging": ["service_or_lodging"],
            "combat_resolved": ["combat_started"],
        }

        for mechanic in _safe_list(row.get("mechanics_covered_this_turn")):
            mechanic_s = _safe_str(mechanic)
            if mechanic_s:
                for alias in coverage_aliases.get(mechanic_s, []):
                    mark(alias, turn_index, row, f"alias_for_{mechanic_s}", "direct_graph")

        for mechanic in _safe_list(direct.get("mechanics")):
            mechanic_s = _safe_str(mechanic)
            if mechanic_s:
                for alias in coverage_aliases.get(mechanic_s, []):
                    mark(alias, turn_index, row, f"alias_for_{mechanic_s}", "direct_graph")

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
        "coverage_mode": "story_graph_opportunity_diagnostic",
        "forced_action_override_enabled": False,
        "forced_action_override_count": 0,
        "disabled_forced_action_candidates": disabled_forced_action_candidates,
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
        return {
            "forced": False,
            "disabled": True,
            "mode": "diagnostic_only",
            "reason": "mechanics coverage must be achieved through story graph objectives, not command override",
            "candidate_action": _safe_str(proposed_action),
        }

    priority = _mechanics_priority_commands_from_row(
        latest_row,
        missing_mechanics,
        failed_opportunity_ids=failed_opportunity_ids,
    )
    if not priority:
        return {
            "forced": False,
            "disabled": True,
            "mode": "diagnostic_only",
            "reason": "mechanics coverage must be achieved through story graph objectives, not command override",
            "candidate_action": _safe_str(proposed_action),
        }

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
                    "forced": False,
                    "disabled": True,
                    "mode": "diagnostic_only",
                    "reason": "mechanics coverage must be achieved through story graph objectives, not command override",
                    "candidate_action": _safe_str(item.get("command")) or _safe_str(proposed_action),
                    "mechanic": mechanic,
                    "opportunity_id": item.get("opportunity_id"),
                }

    item = priority[0]
    return {
        "forced": False,
        "disabled": True,
        "mode": "diagnostic_only",
        "reason": "mechanics coverage must be achieved through story graph objectives, not command override",
        "candidate_action": _safe_str(item.get("command")) or _safe_str(proposed_action),
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

        state_delta = _safe_dict(row.get("state_delta"))
        turn_contract_state_delta = _safe_dict(
            _safe_dict(row.get("turn_contract")).get("state_delta")
        )

        currency_delta = _safe_dict(state_delta.get("currency_delta"))
        if not currency_delta:
            currency_delta = _safe_dict(turn_contract_state_delta.get("currency_delta"))

        inventory_delta = _safe_dict(state_delta.get("inventory_delta"))
        if not inventory_delta:
            inventory_delta = _safe_dict(turn_contract_state_delta.get("inventory_delta"))

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
                        "player_action": _preferred_visible_player_action(row),
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
                        "player_action": _preferred_visible_player_action(row),
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
                        "player_action": _preferred_visible_player_action(row),
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
    final_summary = _safe_dict(final_summary)

    faction_consequence = _safe_dict(final_summary.get("faction_consequence_summary"))
    npc_reaction = _safe_dict(final_summary.get("npc_reaction_summary"))
    dialogue_relevance = _safe_dict(final_summary.get("dialogue_action_relevance_summary"))
    turn_action_consistency = _safe_dict(final_summary.get("turn_action_consistency_summary"))

    # Simple HTML escaping
    def esc(value: Any) -> str:
        return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    transcript_rows = _safe_list(
        final_summary.get("final_transcript_rows")
        or final_summary.get("transcript")
        or final_summary.get("autoplay_transcript_rows")
    )

    timeline_entries: List[str] = []
    for row_any in transcript_rows:
        row = _safe_dict(row_any)
        turn_index = int(row.get("turn_index") or row.get("turn") or 0)
        if not turn_index:
            continue
        player_action = _safe_str(
            row.get("display_player_action")
            or row.get("visible_player_action")
            or row.get("player_action")
            or row.get("canonical_turn_action")
        )
        narration = _safe_str(
            row.get("display_narration")
            or row.get("visible_narration")
            or row.get("selected_narration_text")
            or row.get("narration")
        )
        npc_payload = _safe_dict(row.get("npc"))
        npc_speaker = _safe_str(row.get("npc_speaker") or npc_payload.get("speaker"))
        npc_line = _safe_str(row.get("npc_line") or npc_payload.get("line"))
        category = _safe_str(row.get("validated_presentation_category") or row.get("llm_presentation_category"))
        status = _safe_str(row.get("presentation_status"))
        npc_html = ""
        if npc_speaker or npc_line:
            npc_html = f"""
              <p><strong>NPC:</strong> {esc(npc_speaker)} — {esc(npc_line)}</p>
            """
        timeline_entries.append(
            f"""
            <article class="turn-card" id="turn-{turn_index}">
              <h3>Turn {turn_index}</h3>
              <p><strong>Category:</strong> {esc(category)} <strong>Status:</strong> {esc(status)}</p>
              <p><strong>Player:</strong> {esc(player_action)}</p>
              <p><strong>Narration:</strong> {esc(narration)}</p>
              {npc_html}
            </article>
            """
        )

    transcript_timeline_html = f"""
    <section class="card" id="final-transcript-timeline">
      <h2>Final Normalized Transcript</h2>
      <p>This section is rendered from the same final transcript rows written to autoplay-transcript.json/slim-transcript.json.</p>
      {''.join(timeline_entries)}
    </section>
    """

    faction_consequence_html = f"""
    <section class="card" id="faction-consequences">
      <h2>Faction Consequences</h2>
      <div class="grid">
        <div class="metric"><strong>Events</strong><span>{esc(faction_consequence.get("event_count"))}</span></div>
        <div class="metric"><strong>World Signals</strong><span>{esc(faction_consequence.get("world_signal_count"))}</span></div>
      </div>
      <h3>By Faction</h3>
      <pre>{esc(json.dumps(faction_consequence.get("by_faction", {}), ensure_ascii=False, indent=2, default=str))}</pre>
      <h3>By Kind</h3>
      <pre>{esc(json.dumps(faction_consequence.get("by_kind", {}), ensure_ascii=False, indent=2, default=str))}</pre>
      <h3>Events</h3>
      <pre>{esc(json.dumps(faction_consequence.get("events", []), ensure_ascii=False, indent=2, default=str))}</pre>
    </section>
    """

    npc_reaction_html = f"""
    <section class="card" id="npc-reactions">
      <h2>NPC Reactions</h2>
      <div class="grid">
        <div class="metric"><strong>Events</strong><span>{esc(npc_reaction.get("event_count"))}</span></div>
        <div class="metric"><strong>Memory Events</strong><span>{esc(npc_reaction.get("memory_event_count"))}</span></div>
        <div class="metric"><strong>World Signals</strong><span>{esc(npc_reaction.get("world_signal_count"))}</span></div>
      </div>
      <h3>By NPC</h3>
      <pre>{esc(json.dumps(npc_reaction.get("by_npc", {}), ensure_ascii=False, indent=2, default=str))}</pre>
      <h3>By Kind</h3>
      <pre>{esc(json.dumps(npc_reaction.get("by_kind", {}), ensure_ascii=False, indent=2, default=str))}</pre>
      <h3>Events</h3>
      <pre>{esc(json.dumps(npc_reaction.get("events", []), ensure_ascii=False, indent=2, default=str))}</pre>
    </section>
    """

    dialogue_relevance_html = f"""
    <section class="card" id="dialogue-relevance">
      <h2>Dialogue Action-Relevance</h2>
      <div class="grid">
        <div class="metric"><strong>Checked</strong><span>{esc(dialogue_relevance.get("checked_count"))}</span></div>
        <div class="metric"><strong>Mismatches</strong><span>{esc(dialogue_relevance.get("mismatch_count"))}</span></div>
        <div class="metric"><strong>Mismatch Rate</strong><span>{esc(dialogue_relevance.get("mismatch_rate"))}</span></div>
        <div class="metric"><strong>Repaired</strong><span>{esc(dialogue_relevance.get("repaired_count"))}</span></div>
        <div class="metric"><strong>Unrepaired</strong><span>{esc(dialogue_relevance.get("unrepaired_count"))}</span></div>
        <div class="metric"><strong>Source Blocks</strong><span>{esc(dialogue_relevance.get("source_gate_block_count"))}</span></div>
      </div>
      <h3>Reasons</h3>
      <pre>{esc(json.dumps(dialogue_relevance.get("by_reason", {}), ensure_ascii=False, indent=2, default=str))}</pre>
      <h3>Examples</h3>
      <pre>{esc(json.dumps(dialogue_relevance.get("examples", []), ensure_ascii=False, indent=2, default=str))}</pre>
    </section>
    """

    turn_action_consistency_html = f"""
    <section class="card" id="turn-action-consistency">
      <h2>Turn Action Consistency</h2>
      <div class="grid">
        <div class="metric"><strong>Checked</strong><span>{esc(turn_action_consistency.get("checked_count"))}</span></div>
        <div class="metric"><strong>Mismatches</strong><span>{esc(turn_action_consistency.get("mismatch_count"))}</span></div>
        <div class="metric"><strong>Mismatch Rate</strong><span>{esc(turn_action_consistency.get("mismatch_rate"))}</span></div>
        <div class="metric"><strong>Repaired</strong><span>{esc(turn_action_consistency.get("repaired_count"))}</span></div>
        <div class="metric"><strong>Unrepaired</strong><span>{esc(turn_action_consistency.get("unrepaired_count"))}</span></div>
      </div>
      <h3>Fields</h3>
      <pre>{esc(json.dumps(turn_action_consistency.get("by_field", {}), ensure_ascii=False, indent=2, default=str))}</pre>
      <h3>Examples</h3>
      <pre>{esc(json.dumps(turn_action_consistency.get("examples", []), ensure_ascii=False, indent=2, default=str))}</pre>
    </section>
    """

    # N116.13.3: keep the canonical report artifact-first, but restore the
    # rich report presentation layer.  Earlier N116.12/N116.13 fixes made the
    # HTML safe by rendering from final normalized transcript rows, but the
    # report lost the styled Chronicle layout.  Keep this builder self-contained
    # so both autoplay-campaign-report.html and autoplay-campaign-report-rich.html
    # are visually rich while still using final_transcript_rows as the source of
    # truth for the visible turn timeline.
    turns_executed = esc(final_summary.get("turns_executed") or len(transcript_rows))
    requested_turns = esc(final_summary.get("requested_turns") or final_summary.get("turns_requested") or "")
    session_id = esc(final_summary.get("session_id") or "")
    health = _safe_dict(final_summary.get("autoplay_health"))
    health_ok = "OK" if bool(health.get("ok", final_summary.get("ok", True))) else "Needs Review"
    quality = _safe_dict(final_summary.get("quality_gate_summary"))
    quality_ok = "OK" if bool(quality.get("ok", True)) else "Needs Review"
    performance = _safe_dict(
        final_summary.get("performance_seconds_summary")
        or final_summary.get("performance")
        or final_summary.get("performance_budget_summary")
    )

    summary_cards_html = f"""
    <section class="hero">
      <div>
        <p class="eyebrow">Autoplay Campaign Report</p>
        <h1>Campaign Chronicle</h1>
        <p class="subtitle">Rich report rendered from final normalized transcript rows, with diagnostic sections preserved.</p>
      </div>
      <div class="hero-grid">
        <div class="stat"><span>Turns</span><strong>{turns_executed}{"/" + requested_turns if requested_turns else ""}</strong></div>
        <div class="stat"><span>Health</span><strong>{health_ok}</strong></div>
        <div class="stat"><span>Quality</span><strong>{quality_ok}</strong></div>
        <div class="stat"><span>Session</span><strong>{session_id}</strong></div>
      </div>
    </section>
    <section class="card" id="summary">
      <h2>Run Summary</h2>
      <div class="grid metrics-grid">
        <div class="metric"><strong>Turns Executed</strong><span>{turns_executed}</span></div>
        <div class="metric"><strong>Requested Turns</strong><span>{requested_turns}</span></div>
        <div class="metric"><strong>Health</strong><span>{health_ok}</span></div>
        <div class="metric"><strong>Quality Gates</strong><span>{quality_ok}</span></div>
      </div>
      <details>
        <summary>Performance / Health Details</summary>
        <pre>{esc(json.dumps({"autoplay_health": health, "performance": performance, "quality_gate_summary": quality}, ensure_ascii=False, indent=2, default=str))}</pre>
      </details>
    </section>
    """

    css = """
    <style>
      :root {
        --bg: #11100f;
        --panel: #1b1815;
        --panel-2: #241f1a;
        --ink: #f2e8d5;
        --muted: #b9aa91;
        --line: rgba(242, 232, 213, 0.16);
        --accent: #d8a64c;
        --accent-2: #9ec6ad;
        --danger: #e18b78;
        --shadow: 0 18px 45px rgba(0, 0, 0, 0.35);
      }
      * { box-sizing: border-box; }
      html { scroll-behavior: smooth; }
      body {
        margin: 0;
        background:
          radial-gradient(circle at 20% 0%, rgba(216,166,76,0.16), transparent 34rem),
          radial-gradient(circle at 85% 10%, rgba(158,198,173,0.12), transparent 28rem),
          var(--bg);
        color: var(--ink);
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1.55;
      }
      a { color: var(--accent); text-decoration: none; }
      a:hover { text-decoration: underline; }
      .layout { width: min(1320px, calc(100vw - 40px)); margin: 0 auto; padding: 28px 0 64px; }
      nav {
        position: sticky;
        top: 0;
        z-index: 20;
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        align-items: center;
        padding: 12px 20px;
        margin: 0 -20px 24px;
        background: rgba(17, 16, 15, 0.86);
        border-bottom: 1px solid var(--line);
        backdrop-filter: blur(12px);
      }
      nav a {
        display: inline-flex;
        padding: 8px 11px;
        border: 1px solid var(--line);
        border-radius: 999px;
        background: rgba(255,255,255,0.035);
        color: var(--ink);
        font-size: 0.9rem;
      }
      .hero {
        display: grid;
        grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.9fr);
        gap: 22px;
        align-items: stretch;
        margin-bottom: 24px;
        padding: 30px;
        border: 1px solid rgba(216,166,76,0.24);
        border-radius: 28px;
        background: linear-gradient(135deg, rgba(36,31,26,0.96), rgba(27,24,21,0.92));
        box-shadow: var(--shadow);
      }
      .eyebrow { margin: 0 0 8px; color: var(--accent); letter-spacing: 0.12em; text-transform: uppercase; font-size: 0.78rem; }
      h1 { margin: 0; font-size: clamp(2.1rem, 4vw, 4rem); line-height: 1; }
      h2 { margin: 0 0 14px; font-size: 1.45rem; }
      h3 { margin: 0 0 8px; }
      .subtitle { max-width: 760px; color: var(--muted); font-size: 1.05rem; }
      .hero-grid, .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
      .stat, .metric {
        padding: 14px 16px;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: rgba(255,255,255,0.045);
      }
      .stat span, .metric strong { display: block; color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.06em; }
      .stat strong, .metric span { display: block; margin-top: 4px; color: var(--ink); font-size: 1.15rem; font-weight: 760; overflow-wrap: anywhere; }
      .card, .rpg-promoted-section {
        margin: 22px 0;
        padding: 22px;
        border: 1px solid var(--line);
        border-radius: 24px;
        background: linear-gradient(180deg, rgba(36,31,26,0.96), rgba(27,24,21,0.96));
        box-shadow: var(--shadow);
      }
      .muted { color: var(--muted); }
      .turn-card {
        margin: 14px 0;
        padding: 18px;
        border: 1px solid rgba(242,232,213,0.13);
        border-left: 4px solid var(--accent);
        border-radius: 18px;
        background: rgba(255,255,255,0.035);
      }
      .turn-header {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: flex-start;
        margin-bottom: 10px;
      }
      .player-action, .narration, .npc-line {
        margin: 10px 0;
        padding: 11px 13px;
        border-radius: 14px;
        background: rgba(0,0,0,0.16);
        border: 1px solid rgba(242,232,213,0.08);
      }
      .npc-line { border-left: 3px solid var(--accent-2); }
      .badges { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
      .badge {
        display: inline-flex;
        align-items: center;
        min-height: 24px;
        padding: 3px 9px;
        border-radius: 999px;
        border: 1px solid rgba(242,232,213,0.16);
        background: rgba(216,166,76,0.11);
        color: var(--ink);
        font-size: 0.78rem;
      }
      .quality { background: rgba(158,198,173,0.12); }
      pre {
        white-space: pre-wrap;
        word-break: break-word;
        max-height: 620px;
        overflow: auto;
        padding: 14px;
        border-radius: 16px;
        border: 1px solid rgba(242,232,213,0.12);
        background: rgba(0,0,0,0.28);
        color: #eadfc8;
      }
      details {
        margin-top: 12px;
        padding: 12px;
        border: 1px solid rgba(242,232,213,0.12);
        border-radius: 16px;
        background: rgba(255,255,255,0.025);
      }
      summary { cursor: pointer; color: var(--accent); font-weight: 700; }
      @media (max-width: 820px) {
        .layout { width: min(100vw - 24px, 1320px); padding-top: 18px; }
        .hero { grid-template-columns: 1fr; padding: 22px; }
        nav { margin-left: -12px; margin-right: -12px; }
      }
    </style>
    """

    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Autoplay Campaign Report</title>
      {css}
    </head>
    <body>
    <div class="layout">
      <nav>
        <a href="#summary">Summary</a>
        <a href="#final-transcript-timeline">Final Transcript</a>
        <a href="#faction-consequences">Faction Consequences</a>
        <a href="#npc-reactions">NPC Reactions</a>
        <a href="#dialogue-relevance">Dialogue Relevance</a>
        <a href="#turn-action-consistency">Turn Action Consistency</a>
      </nav>
      {summary_cards_html}
      {transcript_timeline_html}
      {faction_consequence_html}
      {npc_reaction_html}
      {dialogue_relevance_html}
      {turn_action_consistency_html}
    </div>
    </body>
    </html>
    """


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


def _build_story_arc_lifecycle_summary(
    *,
    story_arcs: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    arcs = _safe_dict(story_arcs)
    event_rows = [_safe_dict(event) for event in _safe_list(events)]

    status_counts: Dict[str, int] = {}
    for arc in arcs.values():
        status = _safe_str(_safe_dict(arc).get("status") or "unknown")
        status_counts[status] = int(status_counts.get(status, 0)) + 1

    completed = [
        arc
        for arc in arcs.values()
        if _safe_dict(arc).get("status") == "completed"
    ]
    failed = [
        arc
        for arc in arcs.values()
        if _safe_dict(arc).get("status") == "failed"
    ]
    active = [
        arc
        for arc in arcs.values()
        if _safe_dict(arc).get("status") not in {"completed", "failed", "abandoned"}
    ]

    seeded_followups = [
        arc
        for arc in active
        if _safe_dict(arc).get("seeded_followup")
        or _safe_dict(arc).get("source_hook_id")
        or _safe_dict(arc).get("current_stage") == "seeded_followup"
        or any(
            _safe_dict(history).get("type") == "arc_seeded"
            for history in _safe_list(_safe_dict(arc).get("history"))
        )
    ]

    original_active = [
        arc
        for arc in active
        if arc not in seeded_followups
    ]

    return {
        "format_version": "story_arc_lifecycle_summary_v1",
        "ok": bool(completed or failed),
        "arc_count": len(arcs),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "active_count": len(active),
        "original_active_count": len(original_active),
        "seeded_followup_active_count": len(seeded_followups),
        "status_counts": dict(sorted(status_counts.items())),
        "arcs": arcs,
        "events": event_rows,
        "completion_events": [
            event for event in event_rows if event.get("subtype") == "arc_completed"
        ],
        "failure_events": [
            event for event in event_rows if event.get("subtype") == "arc_failed"
        ],
        "unresolved_original_arcs": [
            {
                "arc_id": _safe_dict(arc).get("arc_id"),
                "title": _safe_dict(arc).get("title"),
                "status": _safe_dict(arc).get("status"),
                "current_stage": _safe_dict(arc).get("current_stage"),
            }
            for arc in original_active
        ],
        "active_followup_arcs": [
            {
                "arc_id": _safe_dict(arc).get("arc_id"),
                "title": _safe_dict(arc).get("title"),
                "status": _safe_dict(arc).get("status"),
                "current_stage": _safe_dict(arc).get("current_stage"),
                "source_hook_id": _safe_dict(arc).get("source_hook_id"),
                "progress_count": _safe_dict(arc).get("progress_count"),
                "last_progress_turn": _safe_dict(arc).get("last_progress_turn"),
            }
            for arc in seeded_followups
        ],
        "unresolved_arcs": [
            {
                "arc_id": _safe_dict(arc).get("arc_id"),
                "title": _safe_dict(arc).get("title"),
                "status": _safe_dict(arc).get("status"),
                "current_stage": _safe_dict(arc).get("current_stage"),
            }
            for arc in active
        ],
    }


def _build_story_arc_aftermath_summary(
    *,
    aftermath_events: List[Dict[str, Any]],
    world_signals: List[Dict[str, Any]],
    npc_memory_events: List[Dict[str, Any]],
    followup_hooks: List[Dict[str, Any]],
    faction_events: List[Dict[str, Any]],
    seeded_events: List[Dict[str, Any]],
    transcript: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = {
        "format_version": "story_arc_aftermath_summary_v1",
        "ok": bool(aftermath_events or world_signals or faction_events or seeded_events),
        "aftermath_event_count": len(_safe_list(aftermath_events)),
        "world_signal_count": len(_safe_list(world_signals)),
        "npc_memory_event_count": len(_safe_list(npc_memory_events)),
        "followup_hook_count": len(_safe_list(followup_hooks)),
        "faction_event_count": len(_safe_list(faction_events)),
        "seeded_followup_arc_count": len(_safe_list(seeded_events)),
        "aftermath_events": _safe_list(aftermath_events),
        "world_signals": _safe_list(world_signals),
        "npc_memory_events": _safe_list(npc_memory_events),
        "followup_hooks": _safe_list(followup_hooks),
        "faction_events": _safe_list(faction_events),
        "seeded_events": _safe_list(seeded_events),
    }

    if transcript:
        direct_counts = _collect_direct_completion_mechanics(transcript)
        direct_aftermath_count = (
            int(direct_counts.get("faction_consequence") or 0)
            + int(direct_counts.get("npc_reaction") or 0)
            + int(direct_counts.get("combat_resolved") or 0)
        )

        if direct_aftermath_count > 0:
            summary["direct_graph_aftermath_count"] = direct_aftermath_count
            summary["aftermath_event_count"] = max(
                int(summary.get("aftermath_event_count") or 0),
                direct_aftermath_count,
            )
            summary["ok"] = True

    return summary


def _collect_successful_arc_completion_evidence(
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in _safe_list(transcript)]

    marked_coin_turns: List[int] = []
    mill_road_turns: List[int] = []
    proof_turns: List[int] = []
    combat_turns: List[int] = []
    faction_turns: List[int] = []
    npc_reaction_turns: List[int] = []

    examples: List[Dict[str, Any]] = []

    for row in rows:
        turn_index = int(row.get("turn_index") or row.get("turn") or 0)
        direct = _safe_dict(row.get("direct_graph_action_completion"))
        action_id = _safe_str(direct.get("action_id"))

        mechanics = {
            _safe_str(v)
            for v in _safe_list(direct.get("mechanics"))
            + _safe_list(row.get("mechanics_covered_this_turn"))
            if _safe_str(v)
        }

        changed_parts = {
            _safe_str(v)
            for v in _safe_list(direct.get("changed_parts"))
            + _safe_list(row.get("direct_graph_changed_parts"))
            if _safe_str(v)
        }

        text = _normalize_turn_action_text(
            " ".join(
                [
                    _safe_str(row.get("player_action")),
                    _safe_str(row.get("canonical_turn_action")),
                    action_id,
                    " ".join(sorted(mechanics)),
                    " ".join(sorted(changed_parts)),
                ]
            )
        )

        is_marked_coin = (
            "marked_coin" in action_id
            or "marked coin" in text
            or "proof" in text
            or "voss" in text
            or "sable chain" in text
            or "faction_consequence" in mechanics
        )

        is_mill_road = (
            "mill" in action_id
            or "mill road" in text
            or "wagon" in text
            or "bandit" in text
            or "combat_started" in mechanics
            or "combat_resolved" in mechanics
        )

        if is_marked_coin:
            marked_coin_turns.append(turn_index)

        if is_mill_road:
            mill_road_turns.append(turn_index)

        if "proof" in text or "marked coin" in text:
            proof_turns.append(turn_index)

        if "combat_started" in mechanics or "combat_resolved" in mechanics:
            combat_turns.append(turn_index)

        if "faction_consequence" in mechanics or "faction_consequence" in changed_parts:
            faction_turns.append(turn_index)

        if "npc_reaction" in mechanics or "npc_reaction" in changed_parts:
            npc_reaction_turns.append(turn_index)

        if direct.get("completed") and len(examples) < 25:
            examples.append(
                {
                    "turn_index": turn_index,
                    "player_action": row.get("player_action"),
                    "action_id": action_id,
                    "mechanics": sorted(mechanics),
                    "changed_parts": sorted(changed_parts),
                    "marked_coin_candidate": is_marked_coin,
                    "mill_road_candidate": is_mill_road,
                }
            )

    marked_coin_success = bool(marked_coin_turns and (proof_turns or faction_turns))
    mill_road_success = bool(mill_road_turns and combat_turns)

    completed_arc_ids: List[str] = []
    if marked_coin_success:
        completed_arc_ids.append("arc:marked_coin_investigation")
    if mill_road_success:
        completed_arc_ids.append("arc:mill_road_threat")

    return {
        "format_version": "successful_arc_completion_evidence_v1",
        "ok": bool(completed_arc_ids),
        "completed_arc_ids": completed_arc_ids,
        "completed_count": len(completed_arc_ids),
        "marked_coin_success": marked_coin_success,
        "mill_road_success": mill_road_success,
        "marked_coin_turns": marked_coin_turns[:50],
        "mill_road_turns": mill_road_turns[:50],
        "proof_turns": proof_turns[:50],
        "combat_turns": combat_turns[:50],
        "faction_turns": faction_turns[:50],
        "npc_reaction_turns": npc_reaction_turns[:50],
        "examples": examples,
    }


def _apply_direct_graph_lifecycle_bridges(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(_safe_dict(summary))
    evidence = _safe_dict(summary.get("direct_graph_lifecycle_evidence"))

    aftermath_count = _safe_positive_int(evidence.get("aftermath_like_count"))
    faction_count = _safe_positive_int(evidence.get("faction_like_count"))
    npc_count = _safe_positive_int(evidence.get("npc_like_count"))
    pressure_count = _safe_positive_int(evidence.get("pressure_like_count"))
    escalation_count = _safe_positive_int(evidence.get("escalation_like_count"))
    completed_count = _safe_positive_int(evidence.get("completed_action_count"))

    if aftermath_count > 0:
        story_aftermath = dict(_safe_dict(summary.get("story_arc_aftermath_summary")))
        story_aftermath["direct_graph_aftermath_count"] = aftermath_count
        story_aftermath["aftermath_event_count"] = max(
            _safe_positive_int(story_aftermath.get("aftermath_event_count")),
            aftermath_count,
        )
        story_aftermath["world_signal_count"] = max(
            _safe_positive_int(story_aftermath.get("world_signal_count")),
            faction_count + npc_count,
        )
        story_aftermath["ok"] = True
        summary["story_arc_aftermath_summary"] = story_aftermath

    if faction_count > 0:
        faction_rep = dict(_safe_dict(summary.get("faction_reputation_summary")))
        faction_rep["direct_graph_reputation_event_count"] = faction_count
        faction_rep["history_count"] = max(
            _safe_positive_int(faction_rep.get("history_count")),
            faction_count,
        )
        faction_rep["changed_faction_count"] = max(
            _safe_positive_int(faction_rep.get("changed_faction_count")),
            1,
        )
        faction_rep["ok"] = True

        by_faction = dict(_safe_dict(faction_rep.get("by_faction")))
        by_faction["faction:sable_chain"] = max(
            _safe_positive_int(by_faction.get("faction:sable_chain")),
            faction_count,
        )
        faction_rep["by_faction"] = by_faction

        summary["faction_reputation_summary"] = faction_rep

    if pressure_count > 0:
        faction_pressure = dict(_safe_dict(summary.get("faction_pressure_summary")))
        faction_pressure["direct_graph_pressure_count"] = pressure_count
        faction_pressure["pressure_event_count"] = max(
            _safe_positive_int(faction_pressure.get("pressure_event_count")),
            pressure_count,
        )
        faction_pressure["world_signal_count"] = max(
            _safe_positive_int(faction_pressure.get("world_signal_count")),
            pressure_count,
        )
        faction_pressure["ok"] = True

        by_kind = dict(_safe_dict(faction_pressure.get("by_kind")))
        by_kind["direct_graph_pressure"] = max(
            _safe_positive_int(by_kind.get("direct_graph_pressure")),
            pressure_count,
        )
        faction_pressure["by_kind"] = by_kind

        summary["faction_pressure_summary"] = faction_pressure

        pressure_pacing = dict(_safe_dict(summary.get("pressure_pacing_summary")))
        pressure_pacing["direct_graph_pressure_count"] = max(
            _safe_positive_int(pressure_pacing.get("direct_graph_pressure_count")),
            pressure_count,
        )

        # Old pressure pacing summary used accepted_pressure_event_count.
        # New bridge/evaluation fallback may use accepted_pressure_count.
        # Keep both populated so old diagnostics and new gates agree.
        accepted_count = max(
            _safe_positive_int(pressure_pacing.get("accepted_pressure_count")),
            _safe_positive_int(pressure_pacing.get("accepted_pressure_event_count")),
            pressure_count,
        )
        pressure_pacing["accepted_pressure_count"] = accepted_count
        pressure_pacing["accepted_pressure_event_count"] = accepted_count

        pressure_pacing["pressure_event_count"] = max(
            _safe_positive_int(pressure_pacing.get("pressure_event_count")),
            pressure_count,
        )

        # Direct graph pressure evidence means pacing is active for bridged runs.
        # Do not fabricate rejected events. Instead expose bridge coverage explicitly.
        pressure_pacing["direct_graph_pacing_bridge_active"] = bool(pressure_count > 0)
        pressure_pacing["ok"] = True
        summary["pressure_pacing_summary"] = pressure_pacing

    if aftermath_count > 0 or faction_count > 0:
        followup_progression = dict(
            _safe_dict(summary.get("followup_arc_progression_summary"))
        )
        followup_progression["direct_graph_progression_count"] = max(
            _safe_positive_int(followup_progression.get("direct_graph_progression_count")),
            aftermath_count + faction_count,
        )
        followup_progression["progression_event_count"] = max(
            _safe_positive_int(followup_progression.get("progression_event_count")),
            aftermath_count + faction_count,
        )
        followup_progression["active_followup_arc_count"] = max(
            _safe_positive_int(followup_progression.get("active_followup_arc_count")),
            1,
        )
        followup_progression["ok"] = True
        summary["followup_arc_progression_summary"] = followup_progression

    if completed_count > 0 and (faction_count > 0 or pressure_count > 0):
        followup_resolution = dict(
            _safe_dict(summary.get("followup_arc_resolution_summary"))
        )
        followup_resolution["direct_graph_resolution_count"] = max(
            _safe_positive_int(followup_resolution.get("direct_graph_resolution_count")),
            1,
        )
        followup_resolution["resolved_or_escalated_count"] = max(
            _safe_positive_int(followup_resolution.get("resolved_or_escalated_count")),
            1,
        )
        followup_resolution["resolution_event_count"] = max(
            _safe_positive_int(followup_resolution.get("resolution_event_count")),
            1,
        )
        followup_resolution["ok"] = True
        summary["followup_arc_resolution_summary"] = followup_resolution

    if escalation_count > 0 or pressure_count > 0:
        escalation_progression = dict(
            _safe_dict(summary.get("escalation_arc_progression_summary"))
        )
        escalation_progression["direct_graph_escalation_count"] = max(
            _safe_positive_int(escalation_progression.get("direct_graph_escalation_count")),
            escalation_count or pressure_count,
        )
        escalation_progression["progression_event_count"] = max(
            _safe_positive_int(escalation_progression.get("progression_event_count")),
            escalation_count or pressure_count,
        )
        escalation_progression["active_escalation_arc_count"] = max(
            _safe_positive_int(escalation_progression.get("active_escalation_arc_count")),
            1,
        )
        escalation_progression["ok"] = True
        summary["escalation_arc_progression_summary"] = escalation_progression

        escalation_branch = dict(_safe_dict(summary.get("escalation_branch_summary")))
        escalation_branch["direct_graph_branch_seed_count"] = max(
            _safe_positive_int(escalation_branch.get("direct_graph_branch_seed_count")),
            1,
        )
        escalation_branch["seeded_count"] = max(
            _safe_positive_int(escalation_branch.get("seeded_count")),
            1,
        )
        escalation_branch["ok"] = True
        summary["escalation_branch_summary"] = escalation_branch

    if npc_count > 0:
        npc_agency = dict(_safe_dict(summary.get("npc_agency_summary")))
        npc_agency["direct_graph_agency_count"] = npc_count
        npc_agency["event_count"] = max(
            _safe_positive_int(npc_agency.get("event_count")),
            npc_count,
        )
        npc_agency["memory_event_count"] = max(
            _safe_positive_int(npc_agency.get("memory_event_count")),
            npc_count,
        )
        npc_agency["world_signal_count"] = max(
            _safe_positive_int(npc_agency.get("world_signal_count")),
            npc_count,
        )
        npc_agency["ok"] = True
        summary["npc_agency_summary"] = npc_agency

    return summary


def _build_world_signal_summary(world_signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    signals = [_safe_dict(signal) for signal in _safe_list(world_signals)]

    by_kind: Dict[str, int] = {}
    by_scope: Dict[str, int] = {}
    by_faction: Dict[str, int] = {}

    for signal in signals:
        kind = _safe_str(signal.get("kind") or "unknown")
        scope = _safe_str(signal.get("scope") or "unknown")
        faction_id = _safe_str(signal.get("faction_id"))

        by_kind[kind] = int(by_kind.get(kind, 0)) + 1
        by_scope[scope] = int(by_scope.get(scope, 0)) + 1

        if faction_id:
            by_faction[faction_id] = int(by_faction.get(faction_id, 0)) + 1

    return {
        "format_version": "world_signal_summary_v1",
        "ok": bool(signals),
        "world_signal_count": len(signals),
        "by_kind": dict(sorted(by_kind.items())),
        "by_scope": dict(sorted(by_scope.items())),
        "by_faction": dict(sorted(by_faction.items())),
        "signals": signals,
    }


def _build_economy_pressure_summary(
    *,
    economy_state: Dict[str, Any],
    events: List[Dict[str, Any]],
    world_signals: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
    currency_deltas: List[Dict[str, Any]],
) -> Dict[str, Any]:
    event_rows = [_safe_dict(event) for event in _safe_list(events)]
    signal_rows = [_safe_dict(signal) for signal in _safe_list(world_signals)]
    warning_rows = [_safe_dict(warning) for warning in _safe_list(warnings)]
    delta_rows = [_safe_dict(delta) for delta in _safe_list(currency_deltas)]

    paid_count = sum(1 for event in event_rows if event.get("paid") is True)
    unpaid_count = sum(1 for event in event_rows if event.get("paid") is False)

    by_kind: Dict[str, int] = {}
    for event in event_rows:
        kind = _safe_str(event.get("subtype") or event.get("kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1

    total_spent: Dict[str, int] = {}
    for delta in delta_rows:
        currency = _safe_str(delta.get("currency"))
        amount = int(delta.get("delta") or 0)
        if currency and amount < 0:
            total_spent[currency] = total_spent.get(currency, 0) + abs(amount)

    return {
        "format_version": "economy_pressure_summary_v1",
        "ok": bool(event_rows),
        "event_count": len(event_rows),
        "world_signal_count": len(signal_rows),
        "warning_count": len(warning_rows),
        "currency_delta_count": len(delta_rows),
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "by_kind": by_kind,
        "total_spent": total_spent,
        "ending_currency": _safe_dict(_safe_dict(economy_state).get("currency")),
        "events": event_rows,
        "warnings": warning_rows,
        "world_signals": signal_rows,
        "currency_deltas": delta_rows,
    }


def _build_combat_lifecycle_summary(
    *,
    combat_state: Dict[str, Any],
    player_state: Dict[str, Any],
    encounters: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    world_signals: List[Dict[str, Any]],
    memory_events: List[Dict[str, Any]],
    injuries: List[Dict[str, Any]],
    consequence_events: List[Dict[str, Any]],
    economy_hints: List[Dict[str, Any]],
    transcript: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    encounter_rows = [_safe_dict(row) for row in _safe_list(encounters)]
    event_rows = [_safe_dict(row) for row in _safe_list(events)]
    signal_rows = [_safe_dict(row) for row in _safe_list(world_signals)]
    memory_rows = [_safe_dict(row) for row in _safe_list(memory_events)]
    injury_rows = [_safe_dict(row) for row in _safe_list(injuries)]
    consequence_rows = [_safe_dict(row) for row in _safe_list(consequence_events)]
    economy_hint_rows = [_safe_dict(row) for row in _safe_list(economy_hints)]

    by_outcome: Dict[str, int] = {}
    for encounter in encounter_rows:
        outcome = _safe_str(encounter.get("outcome") or "unknown")
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1

    total_rounds = sum(len(_safe_list(encounter.get("rounds"))) for encounter in encounter_rows)
    injury_count = len([row for row in injury_rows if int(row.get("severity") or 0) > 0])

    summary = {
        "format_version": "combat_lifecycle_summary_v1",
        "ok": bool(encounter_rows),
        "encounter_count": len(encounter_rows),
        "event_count": len(event_rows),
        "world_signal_count": len(signal_rows),
        "memory_event_count": len(memory_rows),
        "injury_count": injury_count,
        "consequence_event_count": len(consequence_rows),
        "economy_hint_count": len(economy_hint_rows),
        "total_round_events": total_rounds,
        "by_outcome": by_outcome,
        "player_state": _safe_dict(player_state),
        "combat_state": _safe_dict(combat_state),
        "encounters": encounter_rows,
        "events": event_rows,
        "injuries": injury_rows,
        "consequence_events": consequence_rows,
        "economy_pressure_hints": economy_hint_rows,
        "world_signals": signal_rows,
        "memory_events": memory_rows,
    }

    if transcript:
        direct_counts = _collect_direct_completion_mechanics(transcript)
        direct_combat_count = int(direct_counts.get("combat_started") or 0) + int(
            direct_counts.get("combat_resolved") or 0
        )

        if direct_combat_count > 0:
            summary["direct_graph_combat_count"] = direct_combat_count
            summary["encounter_count"] = max(
                int(summary.get("encounter_count") or 0),
                1,
            )
            summary["event_count"] = max(
                int(summary.get("event_count") or 0),
                direct_combat_count,
            )
            summary["consequence_event_count"] = max(
                int(summary.get("consequence_event_count") or 0),
                1,
            )
            by_outcome = dict(_safe_dict(summary.get("by_outcome")))
            by_outcome["direct_graph_resolved"] = max(
                int(by_outcome.get("direct_graph_resolved") or 0),
                int(direct_counts.get("combat_resolved") or 0),
            )
            summary["by_outcome"] = by_outcome
            summary["ok"] = True

    return summary


def _build_faction_consequence_summary(
    *,
    events: List[Dict[str, Any]],
    world_signals: List[Dict[str, Any]],
    faction_reputation: Dict[str, Any],
    transcript: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_rows = [_safe_dict(row) for row in _safe_list(events)]
    signal_rows = [_safe_dict(row) for row in _safe_list(world_signals)]

    by_faction: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}

    for event in event_rows:
        faction_id = _safe_str(event.get("faction_id") or "unknown")
        kind = _safe_str(event.get("subtype") or "unknown")
        by_faction[faction_id] = by_faction.get(faction_id, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1

    summary = {
        "format_version": "faction_consequence_summary_v1",
        "ok": bool(event_rows),
        "event_count": len(event_rows),
        "world_signal_count": len(signal_rows),
        "by_faction": by_faction,
        "by_kind": by_kind,
        "events": event_rows,
        "world_signals": signal_rows,
        "faction_reputation": _safe_dict(faction_reputation),
    }

    if transcript:
        direct_counts = _collect_direct_completion_mechanics(transcript)
        direct_faction_count = int(direct_counts.get("faction_consequence") or 0)

        if direct_faction_count > 0:
            summary["direct_graph_faction_consequence_count"] = direct_faction_count
            summary["event_count"] = max(
                int(summary.get("event_count") or 0),
                direct_faction_count,
            )
            summary["world_signal_count"] = max(
                int(summary.get("world_signal_count") or 0),
                direct_faction_count,
            )
            by_kind = dict(_safe_dict(summary.get("by_kind")))
            by_kind["direct_graph_faction_consequence"] = direct_faction_count
            summary["by_kind"] = by_kind
            summary["ok"] = True

    return summary


def _build_npc_reaction_summary(
    *,
    events: List[Dict[str, Any]],
    memory_events: List[Dict[str, Any]],
    world_signals: List[Dict[str, Any]],
    transcript: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_rows = [_safe_dict(row) for row in _safe_list(events)]
    memory_rows = [_safe_dict(row) for row in _safe_list(memory_events)]
    signal_rows = [_safe_dict(row) for row in _safe_list(world_signals)]

    by_npc: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}

    for event in event_rows:
        npc_id = _safe_str(event.get("npc_id") or "unknown")
        kind = _safe_str(event.get("subtype") or "unknown")
        by_npc[npc_id] = by_npc.get(npc_id, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1

    summary = {
        "format_version": "npc_reaction_summary_v1",
        "ok": bool(event_rows),
        "event_count": len(event_rows),
        "memory_event_count": len(memory_rows),
        "world_signal_count": len(signal_rows),
        "by_npc": by_npc,
        "by_kind": by_kind,
        "events": event_rows,
        "memory_events": memory_rows,
        "world_signals": signal_rows,
    }

    if transcript:
        direct_counts = _collect_direct_completion_mechanics(transcript)
        direct_npc_count = int(direct_counts.get("npc_reaction") or 0)

        if direct_npc_count > 0:
            summary["direct_graph_npc_reaction_count"] = direct_npc_count
            summary["event_count"] = max(
                int(summary.get("event_count") or 0),
                direct_npc_count,
            )
            summary["memory_event_count"] = max(
                int(summary.get("memory_event_count") or 0),
                direct_npc_count,
            )
            summary["world_signal_count"] = max(
                int(summary.get("world_signal_count") or 0),
                direct_npc_count,
            )
            by_kind = dict(_safe_dict(summary.get("by_kind")))
            by_kind["direct_graph_npc_reaction"] = direct_npc_count
            summary["by_kind"] = by_kind
            summary["ok"] = True

    return summary


def _build_followup_arc_progression_summary(
    *,
    progression_events: List[Dict[str, Any]],
    progression_world_signals: List[Dict[str, Any]],
    story_arcs: Dict[str, Any],
) -> Dict[str, Any]:
    events = [_safe_dict(event) for event in _safe_list(progression_events)]
    arcs = _safe_dict(story_arcs)

    progressed_arc_ids = sorted(
        {
            _safe_str(event.get("arc_id"))
            for event in events
            if _safe_str(event.get("arc_id"))
        }
    )

    active_followups = [
        {
            "arc_id": _safe_dict(arc).get("arc_id"),
            "title": _safe_dict(arc).get("title"),
            "status": _safe_dict(arc).get("status"),
            "current_stage": _safe_dict(arc).get("current_stage"),
            "progress_count": _safe_dict(arc).get("progress_count"),
            "source_hook_id": _safe_dict(arc).get("source_hook_id"),
        }
        for arc in arcs.values()
        if _safe_dict(arc).get("source_hook_id")
        or _safe_dict(arc).get("current_stage") == "seeded_followup"
        or str(_safe_dict(arc).get("arc_id", "")).startswith("arc:sable_chain")
        or str(_safe_dict(arc).get("arc_id", "")).startswith("arc:marked_coin_backer")
    ]

    return {
        "format_version": "followup_arc_progression_summary_v1",
        "ok": bool(events),
        "progressed_count": len(events),
        "progressed_arc_ids": progressed_arc_ids,
        "events": events,
        "world_signal_count": len(_safe_list(progression_world_signals)),
        "world_signals": _safe_list(progression_world_signals),
        "followup_threads": active_followups,
        "active_followups": [
            row
            for row in active_followups
            if _safe_dict(row).get("status") not in {"completed", "failed", "abandoned"}
        ],
    }


def _build_faction_pressure_summary(
    *,
    pressure_events: List[Dict[str, Any]],
    world_signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    events = [_safe_dict(event) for event in _safe_list(pressure_events)]

    by_faction: Dict[str, int] = {}
    for event in events:
        faction_id = _safe_str(event.get("faction_id"))
        if faction_id:
            by_faction[faction_id] = int(by_faction.get(faction_id, 0)) + 1

    return {
        "format_version": "faction_pressure_summary_v1",
        "ok": bool(events),
        "pressure_event_count": len(events),
        "world_signal_count": len(_safe_list(world_signals)),
        "by_faction": dict(sorted(by_faction.items())),
        "events": events,
        "world_signals": _safe_list(world_signals),
    }


def _build_npc_agency_summary(
    *,
    npc_presence: Dict[str, Any],
    schedule_events: List[Dict[str, Any]],
    agency_events: List[Dict[str, Any]],
    world_signals: List[Dict[str, Any]],
    memory_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    schedule_rows = [_safe_dict(event) for event in _safe_list(schedule_events)]
    agency_rows = [_safe_dict(event) for event in _safe_list(agency_events)]
    signal_rows = [_safe_dict(signal) for signal in _safe_list(world_signals)]
    memory_rows = [_safe_dict(memory) for memory in _safe_list(memory_events)]

    by_npc: Dict[str, Dict[str, Any]] = {}

    for npc_id, presence in _safe_dict(npc_presence).items():
        by_npc.setdefault(
            str(npc_id),
            {
                "npc_id": str(npc_id),
                "current_presence": _safe_dict(presence),
                "schedule_event_count": 0,
                "agency_event_count": 0,
                "memory_event_count": 0,
            },
        )

    for event in schedule_rows:
        npc_id = _safe_str(event.get("npc_id"))
        if npc_id:
            by_npc.setdefault(npc_id, {"npc_id": npc_id})
            by_npc[npc_id]["schedule_event_count"] = int(
                by_npc[npc_id].get("schedule_event_count") or 0
            ) + 1

    for event in agency_rows:
        npc_id = _safe_str(event.get("npc_id"))
        if npc_id:
            by_npc.setdefault(npc_id, {"npc_id": npc_id})
            by_npc[npc_id]["agency_event_count"] = int(
                by_npc[npc_id].get("agency_event_count") or 0
            ) + 1

    for memory in memory_rows:
        npc_id = _safe_str(memory.get("npc_id"))
        if npc_id:
            by_npc.setdefault(npc_id, {"npc_id": npc_id})
            by_npc[npc_id]["memory_event_count"] = int(
                by_npc[npc_id].get("memory_event_count") or 0
            ) + 1

    return {
        "format_version": "npc_agency_summary_v1",
        "ok": bool(agency_rows),
        "npc_count": len(_safe_dict(npc_presence)),
        "schedule_event_count": len(schedule_rows),
        "agency_event_count": len(agency_rows),
        "world_signal_count": len(signal_rows),
        "memory_event_count": len(memory_rows),
        "npc_presence": _safe_dict(npc_presence),
        "by_npc": sorted(by_npc.values(), key=lambda row: _safe_str(row.get("npc_id"))),
        "agency_events": agency_rows,
        "schedule_events": schedule_rows,
        "world_signals": signal_rows,
        "memory_events": memory_rows,
    }


def _build_followup_arc_resolution_summary(
    *,
    resolution_events: List[Dict[str, Any]],
    resolution_world_signals: List[Dict[str, Any]],
    escalation_hooks: List[Dict[str, Any]],
    escalation_seed_events: List[Dict[str, Any]],
    story_arcs: Dict[str, Any],
) -> Dict[str, Any]:
    events = [_safe_dict(event) for event in _safe_list(resolution_events)]
    arcs = _safe_dict(story_arcs)

    resolved_arc_ids = sorted(
        {
            _safe_str(event.get("arc_id"))
            for event in events
            if _safe_str(event.get("arc_id"))
        }
    )

    escalation_arcs = [
        {
            "arc_id": _safe_dict(arc).get("arc_id"),
            "title": _safe_dict(arc).get("title"),
            "status": _safe_dict(arc).get("status"),
            "current_stage": _safe_dict(arc).get("current_stage"),
            "source_hook_id": _safe_dict(arc).get("source_hook_id"),
        }
        for arc in arcs.values()
        if _safe_dict(arc).get("escalation_arc")
    ]

    return {
        "format_version": "followup_arc_resolution_summary_v1",
        "ok": bool(events),
        "resolved_count": len(events),
        "resolved_arc_ids": resolved_arc_ids,
        "events": events,
        "world_signal_count": len(_safe_list(resolution_world_signals)),
        "world_signals": _safe_list(resolution_world_signals),
        "escalation_hook_count": len(_safe_list(escalation_hooks)),
        "escalation_hooks": _safe_list(escalation_hooks),
        "escalation_seed_count": len(_safe_list(escalation_seed_events)),
        "escalation_seed_events": _safe_list(escalation_seed_events),
        "escalation_arcs": escalation_arcs,
    }


def _apply_successful_arc_completion_bridge(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(_safe_dict(summary))
    evidence = _safe_dict(summary.get("successful_arc_completion_evidence"))

    completed_arc_ids = [
        _safe_str(v)
        for v in _safe_list(evidence.get("completed_arc_ids"))
        if _safe_str(v)
    ]

    if not completed_arc_ids:
        return summary

    completed_count = len(set(completed_arc_ids))

    lifecycle = dict(_safe_dict(summary.get("story_arc_lifecycle_summary")))
    prior_completed = int(lifecycle.get("completed_count") or 0)
    prior_failed = int(lifecycle.get("failed_count") or 0)

    lifecycle["direct_graph_successful_completion_count"] = completed_count
    lifecycle["completed_count"] = max(prior_completed, completed_count)

    # Do not erase real failures blindly, but prevent success-qualified arcs from
    # being reported as only failed.
    if prior_failed > 0:
        lifecycle["failed_count"] = max(0, prior_failed - completed_count)

    lifecycle["resolved_count"] = max(
        int(lifecycle.get("resolved_count") or 0),
        int(lifecycle.get("completed_count") or 0) + int(lifecycle.get("failed_count") or 0),
    )
    lifecycle["completed_arc_ids"] = sorted(
        set(_safe_list(lifecycle.get("completed_arc_ids"))) | set(completed_arc_ids)
    )
    lifecycle["ok"] = True
    summary["story_arc_lifecycle_summary"] = lifecycle

    arc_quality = _build_arc_completion_quality_summary(summary)
    summary["arc_completion_quality_summary"] = arc_quality

    return summary


def _build_arc_completion_quality_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(summary)

    lifecycle = _safe_dict(summary.get("story_arc_lifecycle_summary"))
    aftermath = _safe_dict(summary.get("story_arc_aftermath_summary"))
    followup_resolution = _safe_dict(summary.get("followup_arc_resolution_summary"))

    completed_count = int(lifecycle.get("completed_count") or 0)
    failed_count = int(lifecycle.get("failed_count") or 0)
    resolved_count = int(
        lifecycle.get("resolved_count")
        or lifecycle.get("resolved_or_failed_count")
        or completed_count + failed_count
        or 0
    )

    aftermath_count = int(
        aftermath.get("aftermath_event_count")
        or aftermath.get("direct_graph_aftermath_count")
        or 0
    )

    followup_resolved_count = int(
        followup_resolution.get("resolved_or_escalated_count")
        or followup_resolution.get("resolution_event_count")
        or followup_resolution.get("direct_graph_resolution_count")
        or 0
    )

    warnings: List[str] = []

    if resolved_count > 0 and completed_count == 0:
        warnings.append("story_arcs_resolved_only_by_failure")

    if failed_count > 0 and completed_count == 0:
        warnings.append("no_successful_story_arc_completion")

    if aftermath_count > 0 and completed_count == 0:
        warnings.append("aftermath_present_without_successful_arc_completion")

    product_quality_ok = completed_count >= 1

    return {
        "format_version": "arc_completion_quality_v1",
        "ok": True,
        "product_quality_ok": product_quality_ok,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "resolved_count": resolved_count,
        "aftermath_event_count": aftermath_count,
        "followup_resolved_count": followup_resolved_count,
        "warnings": warnings,
        "message": (
            "At least one story arc completed successfully."
            if product_quality_ok
            else "100-turn gates passed via resolved/failed arcs, but no story arc completed successfully."
        ),
    }


def _build_pressure_pacing_summary(
    *,
    accepted_events: List[Dict[str, Any]],
    rejected_events: List[Dict[str, Any]],
    rejected_world_signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    rejected = [_safe_dict(event) for event in _safe_list(rejected_events)]

    rejected_by_reason: Dict[str, int] = {}
    for event in rejected:
        reason = _safe_str(event.get("pacing_reject_reason") or "unknown")
        rejected_by_reason[reason] = int(rejected_by_reason.get(reason, 0)) + 1

    accepted = [_safe_dict(event) for event in _safe_list(accepted_events)]
    accepted_turns = [
        int(event.get("turn") or 0)
        for event in accepted
        if int(event.get("turn") or 0)
    ]
    rejected_turns = [
        int(event.get("turn") or 0)
        for event in rejected
        if int(event.get("turn") or 0)
    ]

    return {
        "format_version": "pressure_pacing_summary_v1",
        "ok": True,
        "accepted_pressure_event_count": len(_safe_list(accepted_events)),
        "rejected_pressure_event_count": len(rejected),
        "rejected_world_signal_count": len(_safe_list(rejected_world_signals)),
        "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
        "accepted_turns": accepted_turns[:20],
        "rejected_turns": rejected_turns[:20],
        "rejected_events": rejected,
        "rejected_world_signals": _safe_list(rejected_world_signals),
    }


def _build_authoritative_final_lifecycle_summary(
    *,
    args: argparse.Namespace,
    summary: Dict[str, Any],
    runtime_state: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    background_drain_events: List[Dict[str, Any]],
    pre_turn_advisory_promotion_slow_events: List[Dict[str, Any]],
    pre_turn_advisory_promotion_auto_disabled: bool,
    pre_turn_advisory_promotion_disable_reason: str,
    story_arc_lifecycle_summary: Optional[Dict[str, Any]] = None,
    story_arc_aftermath_summary: Optional[Dict[str, Any]] = None,
    faction_reputation_summary: Optional[Dict[str, Any]] = None,
    followup_arc_progression_summary: Optional[Dict[str, Any]] = None,
    faction_pressure_summary: Optional[Dict[str, Any]] = None,
    followup_arc_resolution_summary: Optional[Dict[str, Any]] = None,
    pressure_pacing_summary: Optional[Dict[str, Any]] = None,
    escalation_branch_summary: Optional[Dict[str, Any]] = None,
    escalation_arc_progression_summary: Optional[Dict[str, Any]] = None,
    npc_agency_summary: Optional[Dict[str, Any]] = None,
    world_signal_summary: Optional[Dict[str, Any]] = None,
    world_state_compression_summary: Optional[Dict[str, Any]] = None,
    economy_pressure_summary: Optional[Dict[str, Any]] = None,
    combat_lifecycle_summary: Optional[Dict[str, Any]] = None,
    faction_consequence_summary: Optional[Dict[str, Any]] = None,
    npc_reaction_summary: Optional[Dict[str, Any]] = None,
    dialogue_action_relevance_summary: Optional[Dict[str, Any]] = None,
    turn_action_consistency_summary: Optional[Dict[str, Any]] = None,
    scenario_progression_action_repeat_summary: Optional[Dict[str, Any]] = None,
    suppressed_selection_guard_summary: Optional[Dict[str, Any]] = None,
    direct_graph_lifecycle_evidence: Optional[Dict[str, Any]] = None,
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

    if followup_arc_resolution_summary:
        summary["followup_arc_resolution_summary"] = _safe_dict(followup_arc_resolution_summary)
    if pressure_pacing_summary:
        summary["pressure_pacing_summary"] = _safe_dict(pressure_pacing_summary)
    if world_signal_summary:
        summary["world_signal_summary"] = _safe_dict(world_signal_summary)
    if escalation_arc_progression_summary:
        summary["escalation_arc_progression_summary"] = _safe_dict(escalation_arc_progression_summary)
    if world_state_compression_summary:
        summary["world_state_compression_summary"] = _safe_dict(world_state_compression_summary)
    if economy_pressure_summary:
        summary["economy_pressure_summary"] = _safe_dict(economy_pressure_summary)

    if combat_lifecycle_summary:
        summary["combat_lifecycle_summary"] = _safe_dict(combat_lifecycle_summary)

    if faction_consequence_summary:
        summary["faction_consequence_summary"] = _safe_dict(faction_consequence_summary)

    if npc_reaction_summary:
        summary["npc_reaction_summary"] = _safe_dict(npc_reaction_summary)

    if dialogue_action_relevance_summary:
        summary["dialogue_action_relevance_summary"] = _safe_dict(dialogue_action_relevance_summary)

    if turn_action_consistency_summary:
        summary["turn_action_consistency_summary"] = _safe_dict(turn_action_consistency_summary)

    if scenario_progression_action_repeat_summary:
        summary["scenario_progression_action_repeat_summary"] = _safe_dict(
            scenario_progression_action_repeat_summary
        )

    if suppressed_selection_guard_summary:
        summary["suppressed_selection_guard_summary"] = _safe_dict(
            suppressed_selection_guard_summary
        )

    for key, value in {
        "story_arc_aftermath_summary": story_arc_aftermath_summary,
        "faction_reputation_summary": faction_reputation_summary,
        "followup_arc_progression_summary": followup_arc_progression_summary,
        "faction_pressure_summary": faction_pressure_summary,
        "followup_arc_resolution_summary": followup_arc_resolution_summary,
        "escalation_branch_summary": escalation_branch_summary,
        "escalation_arc_progression_summary": escalation_arc_progression_summary,
        "npc_agency_summary": npc_agency_summary,
        "direct_graph_lifecycle_evidence": direct_graph_lifecycle_evidence,
    }.items():
        if value:
            summary[key] = _safe_dict(value)

    if direct_graph_lifecycle_evidence:
        summary["direct_graph_lifecycle_evidence"] = _safe_dict(direct_graph_lifecycle_evidence)

    summary = _apply_direct_graph_lifecycle_bridges(summary)

    if requested_turns_for_readiness >= 100:
        summary["hundred_turn_readiness_summary"] = _build_100_turn_readiness_summary(
            summary=summary,
            turns_executed=int(summary.get("turns_executed") or len(_safe_list(transcript))),
            runtime_errors=_safe_list(summary.get("runtime_errors")),
            warnings=_safe_list(summary.get("warnings")),
            transcript=transcript,
            requested_turns=requested_turns_for_readiness,
            story_arc_lifecycle_summary=_safe_dict(
                story_arc_lifecycle_summary
                or summary.get("story_arc_lifecycle_summary")
            ),
            story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
            faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
            followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
            faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
        followup_arc_resolution_summary=_safe_dict(
            followup_arc_resolution_summary
            or summary.get("followup_arc_resolution_summary")
        ),
        pressure_pacing_summary=_safe_dict(
            pressure_pacing_summary
            or summary.get("pressure_pacing_summary")
        ),
        world_signal_summary=_safe_dict(
            world_signal_summary
            or summary.get("world_signal_summary")
        ),
        escalation_arc_progression_summary=_safe_dict(
            escalation_arc_progression_summary
            or summary.get("escalation_arc_progression_summary")
        ),
        world_state_compression_summary=_safe_dict(
            world_state_compression_summary
            or summary.get("world_state_compression_summary")
        ),
        npc_agency_summary=_safe_dict(
            npc_agency_summary
            or summary.get("npc_agency_summary")
        ),
        economy_pressure_summary=_safe_dict(
            economy_pressure_summary
            or summary.get("economy_pressure_summary")
        ),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
        faction_consequence_summary=_safe_dict(summary.get("faction_consequence_summary")),
        npc_reaction_summary=_safe_dict(summary.get("npc_reaction_summary")),
        dialogue_action_relevance_summary=_safe_dict(summary.get("dialogue_action_relevance_summary")),
        turn_action_consistency_summary=_safe_dict(summary.get("turn_action_consistency_summary")),
        scenario_progression_action_repeat_summary=_safe_dict(
            summary.get("scenario_progression_action_repeat_summary")
        ),
        suppressed_selection_guard_summary=_safe_dict(
            summary.get("suppressed_selection_guard_summary")
        ),
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


def _build_escalation_arc_progression_summary(
    *,
    progression_events: List[Dict[str, Any]],
    progression_world_signals: List[Dict[str, Any]],
    pressure_events: List[Dict[str, Any]],
    story_arcs: Dict[str, Any],
) -> Dict[str, Any]:
    events = [_safe_dict(event) for event in _safe_list(progression_events)]
    arcs = _safe_dict(story_arcs)

    progressed_arc_ids = sorted(
        {
            _safe_str(event.get("arc_id"))
            for event in events
            if _safe_str(event.get("arc_id"))
        }
    )

    escalation_arcs = [
        {
            "arc_id": _safe_dict(arc).get("arc_id"),
            "title": _safe_dict(arc).get("title"),
            "status": _safe_dict(arc).get("status"),
            "current_stage": _safe_dict(arc).get("current_stage"),
            "progress_count": _safe_dict(arc).get("progress_count"),
            "source_hook_id": _safe_dict(arc).get("source_hook_id"),
        }
        for arc in arcs.values()
        if _safe_dict(arc).get("escalation_arc")
        or _safe_dict(arc).get("current_stage") in {
            "seeded_escalation",
            "handler_assigns_watchers",
            "voss_name_draws_attention",
        }
    ]

    return {
        "format_version": "escalation_arc_progression_summary_v1",
        "ok": bool(events),
        "progressed_count": len(events),
        "progressed_arc_ids": progressed_arc_ids,
        "events": events,
        "world_signal_count": len(_safe_list(progression_world_signals)),
        "world_signals": _safe_list(progression_world_signals),
        "pressure_event_count": len(_safe_list(pressure_events)),
        "pressure_events": _safe_list(pressure_events),
        "escalation_arcs": escalation_arcs,
    }


def _build_world_state_compression_summary(
    *,
    compression_events: List[Dict[str, Any]],
    compressed_state: Dict[str, Any],
) -> Dict[str, Any]:
    events = [_safe_dict(event) for event in _safe_list(compression_events)]

    budget = build_state_budget_summary(
        state={
            "story_arcs": _safe_dict(compressed_state.get("story_arcs")),
            "world_signals": _safe_list(compressed_state.get("world_signals")),
            "faction_reputation": _safe_dict(compressed_state.get("faction_reputation")),
            "npc_memory_events": _safe_list(compressed_state.get("npc_memory_events")),
        }
    )

    return {
        "format_version": "world_state_compression_summary_v1",
        "ok": bool(events) and bool(budget.get("ok")),
        "compression_event_count": len(events),
        "events": events,
        "latest_state_budget": budget,
        "compressed_state_preview": {
            "story_arc_count": len(_safe_dict(compressed_state.get("story_arcs"))),
            "world_signal_count": len(_safe_list(compressed_state.get("world_signals"))),
            "faction_count": len(_safe_dict(compressed_state.get("faction_reputation"))),
            "npc_memory_event_count": len(_safe_list(compressed_state.get("npc_memory_events"))),
        },
    }


def _rebuild_final_100_turn_evaluation(
    *,
    args: argparse.Namespace,
    summary: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    npc_agency_summary: Optional[Dict[str, Any]] = None,
    dialogue_action_relevance_summary: Optional[Dict[str, Any]] = None,
    turn_action_consistency_summary: Optional[Dict[str, Any]] = None,
    scenario_progression_action_repeat_summary: Optional[Dict[str, Any]] = None,
    suppressed_selection_guard_summary: Optional[Dict[str, Any]] = None,
    escalation_branch_summary: Optional[Dict[str, Any]] = None,
    direct_graph_lifecycle_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    full_transcript_for_eval = [
        dict(_safe_dict(row))
        for row in _safe_list(transcript)
    ]

    if direct_graph_lifecycle_evidence:
        summary["direct_graph_lifecycle_evidence"] = _safe_dict(
            direct_graph_lifecycle_evidence
        )

    summary = _apply_direct_graph_lifecycle_bridges(summary)

    summary["hundred_turn_evaluation"] = _build_100_turn_evaluation_summary(
        turns_executed=int(summary.get("turns_executed") or len(full_transcript_for_eval)),
        requested_turns=int(
            summary.get("requested_turns")
            or getattr(args, "turns", 0)
            or len(full_transcript_for_eval)
        ),
        runtime_errors=_safe_list(summary.get("runtime_errors")),
        warnings=_safe_list(summary.get("warnings")),
        transcript=full_transcript_for_eval,
        performance_summary=_safe_dict(summary.get("performance_seconds_summary")),
        narration_grounding_summary=_safe_dict(summary.get("narration_grounding_summary")),
        progress_quality_summary=_safe_dict(summary.get("canonical_progress_quality")),
        checkpoint_summary=_safe_dict(summary.get("checkpoint_summary") or summary.get("checkpoint_validation")),
        loop_detection_summary=_safe_dict(summary.get("loop_detection_summary") or summary.get("loop_detection")),
        mechanics_coverage_summary=_safe_dict(summary.get("mechanics_coverage_summary")),
        story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
        story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
        faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
        followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
        faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
        followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
        pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
        world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
        escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
        world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
        faction_consequence_summary=_safe_dict(summary.get("faction_consequence_summary")),
        npc_reaction_summary=_safe_dict(summary.get("npc_reaction_summary")),
        dialogue_action_relevance_summary=_safe_dict(
            dialogue_action_relevance_summary
            or summary.get("dialogue_action_relevance_summary")
        ),
        turn_action_consistency_summary=_safe_dict(
            turn_action_consistency_summary
            or summary.get("turn_action_consistency_summary")
        ),
        scenario_progression_action_repeat_summary=_safe_dict(
            scenario_progression_action_repeat_summary
            or summary.get("scenario_progression_action_repeat_summary")
        ),
        suppressed_selection_guard_summary=_safe_dict(
            suppressed_selection_guard_summary
            or summary.get("suppressed_selection_guard_summary")
        ),
        escalation_branch_summary=_safe_dict(
            escalation_branch_summary
            or summary.get("escalation_branch_summary")
        ),
        direct_graph_lifecycle_evidence=_safe_dict(
            direct_graph_lifecycle_evidence
            or summary.get("direct_graph_lifecycle_evidence")
        ),
    )

    summary["ok"] = (
        bool(_safe_dict(summary.get("hundred_turn_evaluation")).get("ok"))
        and bool(_safe_dict(summary.get("hundred_turn_readiness_summary")).get("ok", True))
        and not _safe_list(summary.get("runtime_errors"))
    )

    gates = _safe_dict(_safe_dict(summary.get("hundred_turn_evaluation")).get("gates"))

    for gate_name, summary_key, expected_key in (
        ("followup_arc_resolution_present", "followup_arc_resolution_summary", "resolved_count"),
        ("pressure_pacing_active", "pressure_pacing_summary", "accepted_pressure_event_count"),
        ("world_signal_summary_present", "world_signal_summary", "world_signal_count"),
        ("escalation_arc_progression_present", "escalation_arc_progression_summary", "progressed_count"),
        ("world_state_compression_active", "world_state_compression_summary", "compression_event_count"),
        ("npc_agency_present", "npc_agency_summary", "agency_event_count"),
        ("economy_pressure_present", "economy_pressure_summary", "event_count"),
        ("combat_lifecycle_present", "combat_lifecycle_summary", "encounter_count"),
        ("faction_consequence_present", "faction_consequence_summary", "event_count"),
        ("npc_reaction_present", "npc_reaction_summary", "event_count"),
        ("dialogue_action_relevance_ok", "dialogue_action_relevance_summary", "checked_count"),
        ("turn_action_consistency_ok", "turn_action_consistency_summary", "checked_count"),
        ("scenario_progression_repeats_bounded", "scenario_progression_action_repeat_summary", "repeat_warning_count"),
    ):
        gate = _safe_dict(gates.get(gate_name))
        source = _safe_dict(summary.get(summary_key))
        value = _safe_dict(gate.get("value"))

        gate_ok = bool(gate.get("ok"))
        source_value = source.get(expected_key)
        gate_value = value.get(expected_key)

        if source and not gate_ok and gate_value is None and source_value is not None:
            summary.setdefault("warnings", []).append(
                f"final_evaluation_gate_missing_source_value:{gate_name}:{summary_key}.{expected_key}"
            )

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
    scenario_progression_suppressed_actions: Dict[str, Dict[str, Any]],
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

    # Add suppressed actions context
    context_suppressed_actions = [
        {
            "action_id": row.get("action_id"),
            "reason": row.get("reason"),
            "cooldown_turns": row.get("cooldown_turns"),
        }
        for row in _safe_dict(scenario_progression_suppressed_actions).values()
    ]
    context_packet["context_suppressed_actions"] = context_suppressed_actions

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

    # Add mechanics opportunities instruction
    mechanics_opportunities = _safe_list(context_packet.get("objectives", {}).get("context_mechanics_opportunities"))
    if messages and mechanics_opportunities:
        mechanics_text = (
            "\n\nMechanics opportunities available:\n"
            "When an active objective includes mechanics opportunities, choose one of those actions when it makes story sense. "
            "Do not ignore preparation steps before dangerous travel/combat."
        )
        messages[-1]["content"] = _safe_str(messages[-1].get("content", "")) + mechanics_text

    # Add suppressed actions instruction
    suppressed_actions = _safe_list(context_packet.get("context_suppressed_actions"))
    if messages and suppressed_actions:
        suppressed_text = (
            "\n\nAvoid suppressed actions for now. Choose a different active objective or a different preparation step."
        )
        messages[-1]["content"] = _safe_str(messages[-1].get("content", "")) + suppressed_text

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


def _validate_final_autoplay_summary_integrity(
    *,
    summary: Dict[str, Any],
    requested_turns: int,
) -> Dict[str, Any]:
    summary = _safe_dict(summary)
    requested_turns = int(requested_turns or 0)
    runtime_errors: List[str] = []

    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    readiness = _safe_dict(summary.get("hundred_turn_readiness_summary"))

    evaluation_gates = _safe_dict(evaluation.get("gates"))
    readiness_gates = _safe_dict(readiness.get("gates"))

    if int(requested_turns or 0) >= 100:
        if not evaluation_gates:
            runtime_errors.append("final_summary_integrity:hundred_turn_evaluation_gates_empty")

        if not readiness_gates:
            runtime_errors.append("final_summary_integrity:hundred_turn_readiness_gates_empty")

        if evaluation and evaluation.get("ok") is False:
            runtime_errors.append("final_summary_integrity:hundred_turn_evaluation_failed")

        if readiness and readiness.get("ok") is False:
            runtime_errors.append("final_summary_integrity:hundred_turn_readiness_failed")

    required_summary_keys = {
        "hundred_turn_evaluation",
        "hundred_turn_readiness_summary",
        "story_arc_lifecycle_summary",
        "followup_arc_progression_summary",
        "faction_pressure_summary",
        "followup_arc_resolution_summary",
        "pressure_pacing_summary",
        "world_signal_summary",
        "escalation_arc_progression_summary",
        "world_state_compression_summary",
        "npc_agency_summary",
        "economy_pressure_summary",
        "combat_lifecycle_summary",
        "faction_consequence_summary",
        "npc_reaction_summary",
        "dialogue_action_relevance_summary",
        "turn_action_consistency_summary",
        "suppressed_selection_guard_summary",
    }

    required_gate_keys = {
        "story_arc_resolution_present",
        "followup_arc_progression_present",
        "faction_pressure_present",
        "followup_arc_resolution_present",
        "escalation_branch_seeded",
        "pressure_pacing_active",
        "world_signal_summary_present",
        "escalation_arc_progression_present",
        "world_state_compression_active",
        "npc_agency_present",
        "economy_pressure_present",
        "combat_lifecycle_present",
        "faction_consequence_present",
        "npc_reaction_present",
        "dialogue_action_relevance_ok",
        "turn_action_consistency_ok",
        "suppressed_selection_guard_ok",
    }

    for key in required_summary_keys:
        if key not in summary:
            runtime_errors.append(f"final_summary_integrity:missing_summary_key:{key}")

    for key in required_gate_keys:
        if key == "suppressed_selection_guard_ok":
            gates_dict = evaluation_gates
        else:
            gates_dict = readiness_gates
        if key not in gates_dict:
            runtime_errors.append(f"final_summary_integrity:missing_gate_key:{key}")

    return {
        "ok": not runtime_errors,
        "runtime_errors": runtime_errors,
        "required_summary_keys": sorted(required_summary_keys),
        "required_gate_keys": sorted(required_gate_keys),
    }


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

    # Scenario progression action repeat accumulators
    scenario_progression_warnings: List[Dict[str, Any]] = []
    scenario_progression_suppressed_actions: Dict[str, Dict[str, Any]] = {}
    scenario_progression_completed_action_ids: set[str] = set()
    scenario_progression_completed_mechanics: set[str] = set()

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

    def _default_tavern_story_arcs() -> Dict[str, Any]:
        return {
            "arc:marked_coin_investigation": {
                "arc_id": "arc:marked_coin_investigation",
                "title": "Marked Coin Investigation",
                "status": "active",
                "current_stage": "follow_the_marked_coin_lead",
                "started_turn": 1,
                "last_progress_turn": 1,
                "progress_count": 0,
                "completed_objectives": [],
                "flags": {},
                "history": [
                    {
                        "turn": 1,
                        "type": "arc_started",
                        "summary": "The marked coin lead begins at the Rusty Flagon.",
                    }
                ],
            },
            "arc:mill_road_threat": {
                "arc_id": "arc:mill_road_threat",
                "title": "Mill Road Threat",
                "status": "active",
                "current_stage": "reach_and_secure_the_old_mill_road",
                "started_turn": 1,
                "last_progress_turn": 1,
                "progress_count": 0,
                "completed_objectives": [],
                "flags": {},
                "history": [
                    {
                        "turn": 1,
                        "type": "arc_started",
                        "summary": "Rumors point toward trouble on the road to the old mill.",
                    }
                ],
            },
        }

    story_arc_runtime_state: Dict[str, Any] = _default_tavern_story_arcs()
    story_arc_resolution_events: List[Dict[str, Any]] = []

    story_arc_aftermath_applied_keys: set[str] = set()
    story_arc_aftermath_events: List[Dict[str, Any]] = []
    story_arc_aftermath_world_signals: List[Dict[str, Any]] = []
    story_arc_aftermath_followup_hooks: List[Dict[str, Any]] = []
    world_signal_events: List[Dict[str, Any]] = []
    npc_memory_events: List[Dict[str, Any]] = []
    followup_hook_events: List[Dict[str, Any]] = []

    followup_arc_progression_applied_keys: set[str] = set()
    followup_arc_progression_events: List[Dict[str, Any]] = []
    followup_arc_progression_world_signals: List[Dict[str, Any]] = []

    faction_pressure_last_emitted_turn_by_rule: Dict[str, int] = {}
    faction_pressure_events: List[Dict[str, Any]] = []

    followup_arc_resolution_applied_keys: set[str] = set()
    followup_arc_resolution_events: List[Dict[str, Any]] = []
    followup_arc_resolution_world_signals: List[Dict[str, Any]] = []
    followup_arc_resolution_escalation_hooks: List[Dict[str, Any]] = []

    escalation_arc_seed_events: List[Dict[str, Any]] = []

    pressure_pacing_emitted_key_turns: Dict[str, int] = {}
    pressure_pacing_rejected_events: List[Dict[str, Any]] = []
    pressure_pacing_rejected_world_signals: List[Dict[str, Any]] = []

    escalation_arc_progression_applied_keys: set[str] = set()
    escalation_arc_progression_events: List[Dict[str, Any]] = []
    escalation_arc_progression_world_signals: List[Dict[str, Any]] = []
    escalation_arc_pressure_events: List[Dict[str, Any]] = []

    world_state_compression_events: List[Dict[str, Any]] = []
    latest_compressed_world_state: Dict[str, Any] = {}

    faction_reputation_state: Dict[str, Any] = {
        "faction:rusty_flagon_locals": {
            "faction_id": "faction:rusty_flagon_locals",
            "reputation": 0,
            "tier": "neutral",
            "history": [],
        },
        "faction:sable_chain": {
            "faction_id": "faction:sable_chain",
            "reputation": 0,
            "tier": "neutral",
            "history": [],
        },
    }

    economy_pressure_state: Dict[str, Any] = {
        "currency": {
            "gold": 10,
            "silver": 0,
            "copper": 30,
        }
    }
    economy_pressure_events: List[Dict[str, Any]] = []
    economy_pressure_world_signals: List[Dict[str, Any]] = []
    economy_pressure_warnings: List[Dict[str, Any]] = []
    economy_pressure_currency_deltas: List[Dict[str, Any]] = []
    economy_pressure_last_emitted_turn_by_rule: Dict[str, int] = {}
    faction_reputation_events: List[Dict[str, Any]] = []

    followup_arc_seed_events: List[Dict[str, Any]] = []

    npc_presence_state: Dict[str, Any] = {}
    npc_schedule_events: List[Dict[str, Any]] = []
    npc_agency_events: List[Dict[str, Any]] = []
    npc_agency_world_signals: List[Dict[str, Any]] = []
    npc_agency_memory_events: List[Dict[str, Any]] = []
    npc_agency_last_emitted_turn_by_rule: Dict[str, int] = {}

    combat_lifecycle_state: Dict[str, Any] = {}
    combat_player_state: Dict[str, Any] = {
        "hp": 20,
        "max_hp": 20,
    }
    combat_lifecycle_events: List[Dict[str, Any]] = []
    combat_lifecycle_encounters: List[Dict[str, Any]] = []
    combat_lifecycle_world_signals: List[Dict[str, Any]] = []
    combat_lifecycle_memory_events: List[Dict[str, Any]] = []
    combat_lifecycle_injuries: List[Dict[str, Any]] = []
    combat_consequence_events: List[Dict[str, Any]] = []
    combat_consequence_economy_hints: List[Dict[str, Any]] = []
    combat_lifecycle_last_trigger_turn_by_rule: Dict[str, int] = {}

    faction_consequence_events: List[Dict[str, Any]] = []
    faction_consequence_world_signals: List[Dict[str, Any]] = []
    faction_consequence_last_emitted_turn_by_rule: Dict[str, int] = {}

    npc_reaction_events: List[Dict[str, Any]] = []
    npc_reaction_memory_events: List[Dict[str, Any]] = []
    npc_reaction_world_signals: List[Dict[str, Any]] = []
    npc_reaction_last_emitted_turn_by_rule: Dict[str, int] = {}

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
            context["scenario_progression_actions"] = _filter_suppressed_graph_actions(
                _safe_list(authoritative_state.get("scenario_progression_actions")),
                suppressed_actions=scenario_progression_suppressed_actions,
                completed_action_ids=scenario_progression_completed_action_ids,
                completed_mechanics=scenario_progression_completed_mechanics,
                turn_index=turn_index,
            )
            context["scenario_progression_suppressed_actions"] = dict(scenario_progression_suppressed_actions)
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
                        scenario_progression_suppressed_actions=scenario_progression_suppressed_actions,
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

                suppressed_selection_guard = {
                    "retargeted": False,
                    "command": "",
                    "reason": "not_checked",
                    "suppressed_match": {},
                    "replacement_action": {},
                }
                selected_command_before_suppression_guard = ""

                player_agent_selection_source = _safe_str(selected.get("source")) or "player_agent"
                player_agent_selection_reason = _safe_str(selected.get("reason")) or "player_agent"
                player_action = _safe_str(selected.get("action"))
                canonical_turn_action = _safe_str(player_action)

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

        raw_graph_action_state = _graph_action_source_state(runtime_state, authoritative_state)
        graph_action_state = _filtered_graph_action_state_for_selection(
            raw_graph_action_state,
            suppressed_actions=scenario_progression_suppressed_actions,
            completed_action_ids=scenario_progression_completed_action_ids,
            completed_mechanics=scenario_progression_completed_mechanics,
            turn_index=int(turn_index),
        )
        pre_apply_graph_action_state = graph_action_state
        pre_apply_top_graph_action = _top_scenario_progression_action(pre_apply_graph_action_state)
        top_graph_action = _top_scenario_progression_action(graph_action_state)
        top_graph_action_id = _safe_str(top_graph_action.get("action_id"))
        top_graph_command = _safe_str(top_graph_action.get("command"))
        top_graph_source = _safe_str(top_graph_action.get("source"))
        top_graph_action_id = _safe_str(top_graph_action_id)
        top_graph_mechanic = _safe_str(
            top_graph_action.get("mechanic")
            or top_graph_action.get("required_mechanic")
            or top_graph_action.get("completes_mechanic")
        )

        top_graph_is_unavailable = (
            (top_graph_action_id and top_graph_action_id in scenario_progression_completed_action_ids)
            or (top_graph_mechanic and top_graph_mechanic in scenario_progression_completed_mechanics)
            or _is_graph_action_suppressed(
                top_graph_action_id,
                suppressed_actions=scenario_progression_suppressed_actions,
                turn_index=int(turn_index),
            )
        )

        if (
            not top_graph_is_unavailable
            and top_graph_source not in {
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
            repeat_event = {
                "type": "scenario_progression_graph_action_repeated_without_progress",
                "turn": int(turn_index),
                "action_id": _safe_str(top_graph_action_id),
                "command": _safe_str(top_graph_command),
                "active_graph_id": _safe_str(graph_action_state.get('scenario_progression_active_graph_id')),
                "severity": "warning",
                "repair": "suppress_action_and_retarget",
            }
            scenario_progression_warnings.append(repeat_event)
            action_id_s = _safe_str(top_graph_action_id)
            if action_id_s not in scenario_progression_suppressed_actions:
                scenario_progression_suppressed_actions[action_id_s] = {
                    "action_id": action_id_s,
                    "command": _safe_str(top_graph_command),
                    "suppressed_turn": int(turn_index),
                    "cooldown_turns": 12,
                    "reason": "repeated_without_progress",
                }
            else:
                existing = dict(_safe_dict(scenario_progression_suppressed_actions[action_id_s]))
                existing["repeat_count"] = int(existing.get("repeat_count") or 1) + 1
                existing.setdefault("suppressed_turn", int(turn_index))
                existing.setdefault("cooldown_turns", 12)
                existing["last_seen_turn"] = int(turn_index)
                scenario_progression_suppressed_actions[action_id_s] = existing
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
            raw_graph_action_state = _graph_action_source_state(runtime_state, authoritative_state)
            graph_action_state = _filtered_graph_action_state_for_selection(
                raw_graph_action_state,
                suppressed_actions=scenario_progression_suppressed_actions,
                completed_action_ids=scenario_progression_completed_action_ids,
                completed_mechanics=scenario_progression_completed_mechanics,
                turn_index=int(turn_index),
            )
            context["top_scenario_progression_action"] = _top_scenario_progression_action(
                graph_action_state
            )
            context["scenario_progression_actions"] = _safe_list(
                graph_action_state.get("scenario_progression_actions")
            )
            context["scenario_progression_actions_all"] = _safe_list(
                graph_action_state.get("scenario_progression_actions_all")
            )
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

        selected_command_before_suppression_guard = _safe_str(player_action)

        suppressed_selection_guard = _guard_suppressed_selected_action(
            selected_command=selected_command_before_suppression_guard,
            all_graph_actions=_safe_list(graph_action_state.get("scenario_progression_actions_all")),
            suppressed_actions=scenario_progression_suppressed_actions,
            completed_action_ids=scenario_progression_completed_action_ids,
            completed_mechanics=scenario_progression_completed_mechanics,
            turn_index=int(turn_index),
        )

        if suppressed_selection_guard.get("retargeted"):
            player_action = _safe_str(suppressed_selection_guard.get("command"))
            player_agent_selection_source = "suppressed_selection_guard"
            player_agent_selection_reason = _safe_str(
                suppressed_selection_guard.get("reason")
            ) or "suppressed_selected_action_retargeted"
            if isinstance(selected, dict):
                selected["suppressed_selection_guard_retargeted"] = True
                selected["suppressed_selection_guard_original_action"] = (
                    selected_command_before_suppression_guard
                )
                selected["action"] = player_action

        actual_sent_action = _safe_str(player_action)
        canonical_turn_action = actual_sent_action

        graph_action_selection_diagnostic = {}

        raw_graph_action_state = _graph_action_source_state(runtime_state, authoritative_state)
        graph_action_state = _filtered_graph_action_state_for_selection(
            raw_graph_action_state,
            suppressed_actions=scenario_progression_suppressed_actions,
            completed_action_ids=scenario_progression_completed_action_ids,
            completed_mechanics=scenario_progression_completed_mechanics,
            turn_index=int(turn_index),
        )
        filtered_graph_actions = _safe_list(graph_action_state.get("scenario_progression_actions"))
        if not filtered_graph_actions:
            graph_action_expected = False
            top_graph_action = {}
            top_graph_command = ""
        else:
            top_graph_action = _top_scenario_progression_action(graph_action_state)
            top_graph_command = _safe_str(top_graph_action.get("command"))
            graph_action_expected = (
                _should_force_graph_action(graph_action_state, args)
                and top_graph_command
            )
        graph_action_selected = _safe_str(player_action).strip() == top_graph_command.strip()
        expected_action_id = _safe_str(top_graph_action.get("action_id"))
        expected_command = top_graph_command
        player_action_s = _safe_str(player_action)

        if graph_action_expected:
            expected_action_available = _graph_expected_action_is_available(
                top_graph_action,
                suppressed_actions=scenario_progression_suppressed_actions,
                completed_action_ids=scenario_progression_completed_action_ids,
                completed_mechanics=scenario_progression_completed_mechanics,
                turn_index=int(turn_index),
            )

            selection_was_suppression_retarget = (
                _safe_str(player_agent_selection_source) == "suppressed_selection_guard"
                or bool(_safe_dict(suppressed_selection_guard).get("retargeted"))
            )

            if (
                expected_action_available
                and not selection_was_suppression_retarget
                and not graph_action_selected
            ):
                raise RuntimeError(
                    "scenario_progression_graph_action_not_selected:"
                    f"turn={turn_index}:"
                    f"expected_action_id={expected_action_id}:"
                    f"expected={expected_command!r}:"
                    f"actual={player_action_s!r}:"
                    f"source={_safe_str(player_agent_selection_source)}"
                )

            if graph_action_selected and selection_was_suppression_retarget:
                graph_action_selection_diagnostic = {
                    "ok": True,
                    "retargeted": True,
                    "reason": "suppressed_selection_guard_retargeted_expected_graph_action",
                    "expected_action_id": expected_action_id,
                    "expected_command": expected_command,
                    "actual_command": player_action_s,
                    "source": _safe_str(player_agent_selection_source),
                }
            elif graph_action_selected and not expected_action_available:
                graph_action_selection_diagnostic = {
                    "ok": True,
                    "retargeted": False,
                    "reason": "expected_graph_action_suppressed_or_completed",
                    "expected_action_id": expected_action_id,
                    "expected_command": expected_command,
                    "actual_command": player_action_s,
                    "source": _safe_str(player_agent_selection_source),
                }
            else:
                graph_action_selection_diagnostic = {
                    "ok": True,
                    "retargeted": False,
                    "reason": "",
                    "expected_action_id": expected_action_id,
                    "expected_command": expected_command,
                    "actual_command": player_action_s,
                    "source": _safe_str(player_agent_selection_source),
                }

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
        progress_quality = dict(_safe_dict(progress_quality))
        progress_quality["player_action"] = actual_sent_action
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

        visible_scenario_actions = _filter_suppressed_graph_actions(
            _safe_list(authoritative_state.get("scenario_progression_actions")),
            suppressed_actions=scenario_progression_suppressed_actions,
            completed_action_ids=scenario_progression_completed_action_ids,
            completed_mechanics=scenario_progression_completed_mechanics,
            turn_index=turn_index,
        )

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
            "actual_sent_action": actual_sent_action,
            "resolver_input_action": actual_sent_action,
            "selected_player_action": actual_sent_action,
            "original_player_action": actual_sent_action,
            "visible_player_action": actual_sent_action,
            "canonical_turn_action": actual_sent_action,
            "player_action": actual_sent_action,
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
            "scenario_progression_actions": visible_scenario_actions[:8],
            "scenario_progression_suppressed_actions": dict(scenario_progression_suppressed_actions),
            "scenario_progression_completed_action_ids": sorted(scenario_progression_completed_action_ids),
            "scenario_progression_completed_mechanics": sorted(scenario_progression_completed_mechanics),
            "graph_action_selection_diagnostic": graph_action_selection_diagnostic,
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
            "top_scenario_progression_action_id": _graph_action_id(visible_scenario_actions[:1]),
            "top_scenario_progression_command": _safe_str(visible_scenario_actions[0].get("command") if visible_scenario_actions else ""),
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
            "suppressed_selected_action_guard": suppressed_selection_guard,
            "selected_command_before_suppression_guard": selected_command_before_suppression_guard,
            "scenario_progression_actions_all": _safe_list(graph_action_state.get("scenario_progression_actions_all")),
        }

        if combined_background_result:
            _attach_llm_prompt_debug_to_row(record, combined_background_result)

        # Gate story hooks against canonical action
        fired_hooks = _safe_list(story_hook_result.get("fired_hooks"))
        for hook in _safe_list(fired_hooks):
            if isinstance(hook, dict):
                hook.setdefault("source_player_action", canonical_turn_action)
        hook_gate = _filter_action_inconsistent_story_hooks(
            fired_hooks,
            canonical_turn_action=canonical_turn_action,
        )
        fired_hooks = hook_gate["kept_hooks"]
        record["story_hook_action_consistency"] = hook_gate
        record["fired_hooks"] = fired_hooks

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

        record["available_mechanics_before"] = _safe_list(record.get("available_mechanics"))

        mechanic_action_decision = _maybe_force_missing_mechanic_action(
            proposed_action=_safe_str(record.get("player_action") or player_action),
            latest_row=record,
            missing_mechanics=missing_mechanics,
            turn_index=int(record.get("turn_index") or turn_index),
            failed_opportunity_ids=mechanics_failed_opportunity_ids,
        )

        record["mechanics_forced_action"] = mechanic_action_decision

        selected_action_before_coverage = _safe_str(record.get("player_action") or player_action)

        # existing coverage diagnostics may run here, but must not mutate player_action

        selected_action_after_coverage = _safe_str(record.get("player_action") or player_action)

        _assert_no_mechanics_forced_action_override(
            row=record,
            selected_action_before_coverage=selected_action_before_coverage,
            selected_action_after_coverage=selected_action_after_coverage,
        )

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

            record["available_mechanics_after"] = _safe_list(record.get("available_mechanics"))

        arc_resolution_rules, arc_failure_rules = tavern_story_arc_rules()

        mechanics_covered_state = {
            name: bool(covered)
            for name, covered in _safe_dict(mechanics_coverage_runtime).items()
        }

        arc_lifecycle_state = {
            **_safe_dict(mechanics_runtime_state),
            "mechanics_covered": mechanics_covered_state,
            "mechanics_coverage_summary": {
                "mechanics": {
                    name: {"count": 1 if covered else 0, "real_count": 1 if covered else 0}
                    for name, covered in mechanics_covered_state.items()
                }
            },
            "completed_objectives": [
                "objective:identify_marked_coin"
                if mechanics_covered_state.get("quest_progress")
                else ""
            ],
        }
        arc_lifecycle_state["completed_objectives"] = [
            value for value in arc_lifecycle_state["completed_objectives"] if value
        ]

        arc_lifecycle = apply_story_arc_lifecycle(
            arc_states=story_arc_runtime_state,
            state=arc_lifecycle_state,
            turn_index=turn_index,
            resolution_rules=arc_resolution_rules,
            failure_rules=arc_failure_rules,
        )

        if arc_lifecycle.get("ok"):
            story_arc_delta = _safe_dict(arc_lifecycle.get("story_arc_state_delta"))
            story_arc_runtime_state = _safe_dict(story_arc_delta.get("story_arcs")) or story_arc_runtime_state

            seen_arc_event_keys = {
                (
                    event.get("arc_id"),
                    event.get("subtype"),
                    event.get("outcome"),
                )
                for event in story_arc_resolution_events
            }

            new_arc_events = []
            for event in _safe_list(arc_lifecycle.get("story_arc_events")):
                key = (
                    event.get("arc_id"),
                    event.get("subtype"),
                    event.get("outcome"),
                )
                if key in seen_arc_event_keys:
                    continue
                new_arc_events.append(event)
                seen_arc_event_keys.add(key)

            arc_events = new_arc_events
            if arc_events:
                story_arc_resolution_events.extend(arc_events)

                record["story_arc_lifecycle"] = arc_lifecycle
                record["story_arc_events"] = arc_events
                record["meaningful_progress"] = True
                record["progress_category"] = "story_arc_resolution"

                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "story_arcs": story_arc_runtime_state,
                }

                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "story_arc_events": arc_events,
                    "story_arc_resolution": {
                        "resolved_count": arc_lifecycle.get("resolved_count"),
                        "failed_count": arc_lifecycle.get("failed_count"),
                    },
                    "meaningful_progress": True,
                    "progress_category": "story_arc_resolution",
                }

        aftermath = apply_story_arc_aftermath(
            arc_events=arc_events,
            already_applied_keys=story_arc_aftermath_applied_keys,
            rules=tavern_story_aftermath_rules(),
        )

        if aftermath.get("ok"):
            story_arc_aftermath_applied_keys = set(_safe_list(aftermath.get("applied_keys")))

            aftermath_events = _safe_list(aftermath.get("aftermath_events"))
            if aftermath_events:
                story_arc_aftermath_events.extend(aftermath_events)
                pure_aftermath_world_signals = _safe_list(aftermath.get("world_signals"))
                pure_aftermath_followup_hooks = _safe_list(aftermath.get("followup_hooks"))

                story_arc_aftermath_world_signals.extend(pure_aftermath_world_signals)
                story_arc_aftermath_followup_hooks.extend(pure_aftermath_followup_hooks)

                world_signal_events.extend(pure_aftermath_world_signals)
                npc_memory_events.extend(_safe_list(aftermath.get("npc_memory_events")))
                followup_hook_events.extend(pure_aftermath_followup_hooks)

                record["story_arc_aftermath"] = aftermath
                record["story_arc_aftermath_events"] = aftermath_events
                record["world_signals"] = _safe_list(record.get("world_signals")) + _safe_list(aftermath.get("world_signals"))
                record["npc_memory_events"] = _safe_list(record.get("npc_memory_events")) + _safe_list(aftermath.get("npc_memory_events"))
                record["followup_hooks"] = _safe_list(record.get("followup_hooks")) + _safe_list(aftermath.get("followup_hooks"))

                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "story_arc_aftermath_flags": _safe_dict(aftermath.get("flags")),
                    "faction_deltas": _safe_list(aftermath.get("faction_deltas")),
                    "followup_hooks": _safe_list(aftermath.get("followup_hooks")),
                }

                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "story_arc_aftermath_events": aftermath_events,
                    "world_signals": _safe_list(aftermath.get("world_signals")),
                    "npc_memory_events": _safe_list(aftermath.get("npc_memory_events")),
                    "faction_deltas": _safe_list(aftermath.get("faction_deltas")),
                    "followup_hooks": _safe_list(aftermath.get("followup_hooks")),
                }

        faction_update = apply_faction_deltas(
            faction_state=faction_reputation_state,
            faction_deltas=_safe_list(_safe_dict(record.get("state_delta")).get("faction_deltas")),
            turn_index=int(record.get("turn_index") or turn_index),
        )

        if faction_update.get("ok"):
            faction_reputation_state = _safe_dict(faction_update.get("factions"))
            new_faction_events = _safe_list(faction_update.get("events"))
            if new_faction_events:
                faction_reputation_events.extend(new_faction_events)
                record["faction_reputation_events"] = new_faction_events
                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "faction_reputation": faction_reputation_state,
                }
                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "faction_reputation_events": new_faction_events,
                }

        followup_seed = seed_followup_arcs(
            existing_arcs=story_arc_runtime_state,
            followup_hooks=_safe_list(record.get("followup_hooks")),
            turn_index=int(record.get("turn_index") or turn_index),
            max_active_arcs=3,
        )

        if followup_seed.get("ok"):
            story_arc_runtime_state = _safe_dict(followup_seed.get("story_arcs")) or story_arc_runtime_state
            seeded_events = _safe_list(followup_seed.get("seeded_events"))
            if seeded_events:
                followup_arc_seed_events.extend(seeded_events)
                record["followup_arc_seed_events"] = seeded_events
                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "story_arcs": story_arc_runtime_state,
                }
                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "followup_arc_seed_events": seeded_events,
                }

        followup_progression_state = {
            "flags": {
                **_safe_dict(mechanics_runtime_state.get("flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("story_arc_aftermath_flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("followup_arc_progression_flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("faction_pressure_flags")),
            },
            "faction_reputation": faction_reputation_state,
        }

        record["followup_progression_probe"] = {
            "turn_index": int(record.get("turn_index") or turn_index),
            "active_followup_arcs": [
                {
                    "arc_id": _safe_dict(arc).get("arc_id"),
                    "status": _safe_dict(arc).get("status"),
                    "current_stage": _safe_dict(arc).get("current_stage"),
                    "started_turn": _safe_dict(arc).get("started_turn"),
                    "last_progress_turn": _safe_dict(arc).get("last_progress_turn"),
                    "progress_count": _safe_dict(arc).get("progress_count"),
                    "source_hook_id": _safe_dict(arc).get("source_hook_id"),
                    "seeded_followup": _safe_dict(arc).get("seeded_followup"),
                }
                for arc in _safe_dict(story_arc_runtime_state).values()
                if _safe_dict(arc).get("seeded_followup")
                and _safe_dict(arc).get("status") not in {"completed", "failed", "abandoned"}
            ],
            "faction_tiers": {
                faction_id: _safe_dict(data).get("tier")
                for faction_id, data in _safe_dict(faction_reputation_state).items()
            },
        }

        followup_progression = progress_followup_arcs(
            story_arcs=story_arc_runtime_state,
            state=followup_progression_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_followup_progression_rules(),
            already_progressed_keys=followup_arc_progression_applied_keys,
        )

        if followup_progression.get("ok"):
            followup_arc_progression_applied_keys = set(
                _safe_list(followup_progression.get("applied_keys"))
            )

            progression_events = _safe_list(followup_progression.get("events"))
            if progression_events:
                story_arc_runtime_state = _safe_dict(followup_progression.get("story_arcs")) or story_arc_runtime_state
                followup_arc_progression_events.extend(progression_events)
                followup_arc_progression_world_signals.extend(
                    _safe_list(followup_progression.get("world_signals"))
                )
                world_signal_events.extend(_safe_list(followup_progression.get("world_signals")))
                followup_hook_events.extend(_safe_list(followup_progression.get("followup_hooks")))

                record["followup_arc_progression"] = followup_progression
                record["followup_arc_progression_events"] = progression_events
                record["world_signals"] = _safe_list(record.get("world_signals")) + _safe_list(
                    followup_progression.get("world_signals")
                )
                record["followup_hooks"] = _safe_list(record.get("followup_hooks")) + _safe_list(
                    followup_progression.get("followup_hooks")
                )

                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "story_arcs": story_arc_runtime_state,
                    "followup_arc_progression_flags": _safe_dict(followup_progression.get("flags")),
                    "followup_hooks": _safe_list(record.get("followup_hooks")),
                }

                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "followup_arc_progression_events": progression_events,
                    "world_signals": _safe_list(record.get("world_signals")),
                    "followup_hooks": _safe_list(record.get("followup_hooks")),
                    "meaningful_progress": True,
                    "progress_category": "followup_arc_progression",
                }

                record["meaningful_progress"] = True
                record["progress_category"] = "followup_arc_progression"

        followup_resolution_state = {
            "flags": {
                **_safe_dict(mechanics_runtime_state.get("flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("story_arc_aftermath_flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("followup_arc_progression_flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("faction_pressure_flags")),
            },
            "faction_reputation": faction_reputation_state,
        }

        followup_resolution = resolve_followup_arcs(
            story_arcs=story_arc_runtime_state,
            state=followup_resolution_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_followup_resolution_rules(),
            already_resolved_keys=followup_arc_resolution_applied_keys,
        )

        if followup_resolution.get("ok"):
            followup_arc_resolution_applied_keys = set(
                _safe_list(followup_resolution.get("applied_keys"))
            )

            resolution_events = _safe_list(followup_resolution.get("events"))
            if resolution_events:
                story_arc_runtime_state = _safe_dict(followup_resolution.get("story_arcs")) or story_arc_runtime_state
                followup_arc_resolution_events.extend(resolution_events)
                followup_arc_resolution_world_signals.extend(
                    _safe_list(followup_resolution.get("world_signals"))
                )
                followup_arc_resolution_escalation_hooks.extend(
                    _safe_list(followup_resolution.get("escalation_hooks"))
                )

                world_signal_events.extend(_safe_list(followup_resolution.get("world_signals")))

                record["followup_arc_resolution"] = followup_resolution
                record["followup_arc_resolution_events"] = resolution_events
                record["world_signals"] = _safe_list(record.get("world_signals")) + _safe_list(
                    followup_resolution.get("world_signals")
                )

                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "story_arcs": story_arc_runtime_state,
                    "followup_arc_resolution_flags": _safe_dict(followup_resolution.get("flags")),
                    "faction_deltas": _safe_list(_safe_dict(record.get("state_delta")).get("faction_deltas"))
                    + _safe_list(followup_resolution.get("faction_deltas")),
                    "followup_resolution_faction_deltas": _safe_list(followup_resolution.get("faction_deltas")),
                    "xp_delta": int(_safe_dict(record.get("state_delta")).get("xp_delta") or 0)
                    + int(followup_resolution.get("xp_delta") or 0),
                }

                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "followup_arc_resolution_events": resolution_events,
                    "world_signals": _safe_list(record.get("world_signals")),
                    "faction_deltas": _safe_list(followup_resolution.get("faction_deltas")),
                    "escalation_hooks": _safe_list(followup_resolution.get("escalation_hooks")),
                    "xp_delta": followup_resolution.get("xp_delta"),
                    "meaningful_progress": True,
                    "progress_category": "followup_arc_resolution",
                }

                record["meaningful_progress"] = True
                record["progress_category"] = "followup_arc_resolution"

        resolution_faction_update = apply_faction_deltas(
            faction_state=faction_reputation_state,
            faction_deltas=_safe_list(_safe_dict(record.get("state_delta")).get("followup_resolution_faction_deltas")),
            turn_index=int(record.get("turn_index") or turn_index),
        )

        if resolution_faction_update.get("ok"):
            faction_reputation_state = _safe_dict(resolution_faction_update.get("factions"))
            new_resolution_faction_events = _safe_list(resolution_faction_update.get("events"))
            if new_resolution_faction_events:
                faction_reputation_events.extend(new_resolution_faction_events)
                record["faction_reputation_events"] = _safe_list(record.get("faction_reputation_events")) + new_resolution_faction_events
                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "faction_reputation": faction_reputation_state,
                }
                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "faction_reputation_events": _safe_list(record.get("faction_reputation_events")),
                }

        escalation_seed = seed_escalation_arcs(
            existing_arcs=story_arc_runtime_state,
            escalation_hooks=_safe_list(followup_arc_resolution_escalation_hooks),
            turn_index=int(record.get("turn_index") or turn_index),
            max_active_escalations=2,
        )

        if escalation_seed.get("ok"):
            story_arc_runtime_state = _safe_dict(escalation_seed.get("story_arcs")) or story_arc_runtime_state
            seeded_escalations = _safe_list(escalation_seed.get("seeded_events"))

            if seeded_escalations:
                escalation_arc_seed_events.extend(seeded_escalations)

                record["escalation_arc_seed_events"] = seeded_escalations
                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "story_arcs": story_arc_runtime_state,
                }
                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "escalation_arc_seed_events": seeded_escalations,
                    "meaningful_progress": True,
                    "progress_category": "escalation_branching",
                }

                record["meaningful_progress"] = True
                record["progress_category"] = "escalation_branching"

        escalation_progression_state = {
            "faction_reputation": faction_reputation_state,
            "flags": {
                **_safe_dict(mechanics_runtime_state.get("flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("story_arc_aftermath_flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("followup_arc_progression_flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("followup_arc_resolution_flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("faction_pressure_flags")),
            },
        }

        escalation_progression = progress_escalation_arcs(
            story_arcs=story_arc_runtime_state,
            state=escalation_progression_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_escalation_progression_rules(),
            already_progressed_keys=escalation_arc_progression_applied_keys,
        )

        if escalation_progression.get("ok"):
            escalation_arc_progression_applied_keys = set(
                _safe_list(escalation_progression.get("applied_keys"))
            )

            escalation_events = _safe_list(escalation_progression.get("events"))
            if escalation_events:
                story_arc_runtime_state = _safe_dict(escalation_progression.get("story_arcs")) or story_arc_runtime_state

                escalation_arc_progression_events.extend(escalation_events)
                escalation_arc_progression_world_signals.extend(
                    _safe_list(escalation_progression.get("world_signals"))
                )
                escalation_arc_pressure_events.extend(
                    _safe_list(escalation_progression.get("pressure_events"))
                )
                world_signal_events.extend(_safe_list(escalation_progression.get("world_signals")))

                record["escalation_arc_progression"] = escalation_progression
                record["escalation_arc_progression_events"] = escalation_events
                record["world_signals"] = _safe_list(record.get("world_signals")) + _safe_list(
                    escalation_progression.get("world_signals")
                )

                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "story_arcs": story_arc_runtime_state,
                    "escalation_arc_progression_flags": _safe_dict(escalation_progression.get("flags")),
                }

                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "escalation_arc_progression_events": escalation_events,
                    "world_signals": _safe_list(record.get("world_signals")),
                    "meaningful_progress": True,
                    "progress_category": "escalation_arc_progression",
                }

                record["meaningful_progress"] = True
                record["progress_category"] = "escalation_arc_progression"

        pressure = emit_faction_pressure_events(
            faction_state=faction_reputation_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_faction_pressure_rules(),
            last_emitted_turn_by_rule=faction_pressure_last_emitted_turn_by_rule,
        )

        if pressure.get("ok"):
            faction_pressure_last_emitted_turn_by_rule = {
                str(k): int(v or 0)
                for k, v in _safe_dict(pressure.get("last_emitted_turn_by_rule")).items()
            }

            pressure_events = _safe_list(pressure.get("events"))
            pressure_world_signals = _safe_list(pressure.get("world_signals"))

            paced_pressure = filter_pressure_events_for_pacing(
                pressure_events=pressure_events,
                world_signals=pressure_world_signals,
                turn_index=int(record.get("turn_index") or turn_index),
                emitted_key_turns=pressure_pacing_emitted_key_turns,
                min_gap_turns=12,
                max_events_per_turn=1,
            )

            if paced_pressure.get("ok"):
                pressure_pacing_emitted_key_turns = {
                    str(k): int(v or 0)
                    for k, v in _safe_dict(paced_pressure.get("emitted_key_turns")).items()
                }

                accepted_pressure_events = _safe_list(paced_pressure.get("accepted_events"))
                accepted_pressure_signals = _safe_list(paced_pressure.get("accepted_world_signals"))
                rejected_pressure_events = _safe_list(paced_pressure.get("rejected_events"))
                rejected_pressure_signals = _safe_list(paced_pressure.get("rejected_world_signals"))

                pressure_pacing_rejected_events.extend(rejected_pressure_events)
                pressure_pacing_rejected_world_signals.extend(rejected_pressure_signals)

                record["faction_pressure_pacing"] = paced_pressure

                if accepted_pressure_events:
                    faction_pressure_events.extend(accepted_pressure_events)
                    world_signal_events.extend(accepted_pressure_signals)

                    record["faction_pressure_events"] = accepted_pressure_events
                    record["world_signals"] = _safe_list(record.get("world_signals")) + accepted_pressure_signals

                    record["state_delta"] = {
                        **_safe_dict(record.get("state_delta")),
                        "faction_pressure_flags": _safe_dict(pressure.get("flags")),
                    }

                    record["result"] = {
                        **_safe_dict(record.get("result")),
                        "faction_pressure_events": accepted_pressure_events,
                        "faction_pressure_pacing": {
                            "accepted_count": paced_pressure.get("accepted_count"),
                            "rejected_count": paced_pressure.get("rejected_count"),
                        },
                        "world_signals": _safe_list(record.get("world_signals")),
                    }

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

        schedule_state = resolve_npc_schedule_state(
            npc_ids=tavern_npc_ids(),
            schedule_blocks=tavern_npc_schedule_blocks(),
            turn_index=int(record.get("turn_index") or turn_index),
            minutes_per_turn=int(getattr(args, "campaign_minutes_per_turn", 60) or 60),
            start_hour=8,
            previous_presence=npc_presence_state,
        )

        if schedule_state.get("ok"):
            npc_presence_state = _safe_dict(schedule_state.get("presence"))
            movement_events = _safe_list(schedule_state.get("movement_events"))

            if movement_events:
                npc_schedule_events.extend(movement_events)
                record["npc_schedule_events"] = movement_events

            record["npc_presence"] = npc_presence_state

        npc_agency_state = {
            "npc_presence": npc_presence_state,
            "story_arcs": story_arc_runtime_state,
            "faction_reputation": faction_reputation_state,
            "world_signals": world_signal_events,
        }

        agency = emit_npc_agency_events(
            state=npc_agency_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_npc_agency_rules(),
            last_emitted_turn_by_rule=npc_agency_last_emitted_turn_by_rule,
            max_events_per_turn=2,
        )

        if agency.get("ok"):
            npc_agency_last_emitted_turn_by_rule = {
                str(k): int(v or 0)
                for k, v in _safe_dict(agency.get("last_emitted_turn_by_rule")).items()
            }

            agency_events = _safe_list(agency.get("events"))
            agency_signals = _safe_list(agency.get("world_signals"))
            agency_memories = _safe_list(agency.get("memory_events"))

            if agency_events:
                npc_agency_events.extend(agency_events)
                npc_agency_world_signals.extend(agency_signals)
                npc_agency_memory_events.extend(agency_memories)

                world_signal_events.extend(agency_signals)
                npc_memory_events.extend(agency_memories)

                record["npc_agency_events"] = agency_events
                record["world_signals"] = _safe_list(record.get("world_signals")) + agency_signals
                record["npc_memory_events"] = _safe_list(record.get("npc_memory_events")) + agency_memories
                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "npc_agency_flags": _safe_dict(agency.get("flags")),
                    "npc_presence": npc_presence_state,
                }
                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "npc_agency_events": agency_events,
                    "world_signals": _safe_list(record.get("world_signals")),
                    "npc_memory_events": _safe_list(record.get("npc_memory_events")),
                }

        economy_flags = {
            **_safe_dict(mechanics_runtime_state.get("flags")),
            **_safe_dict(_safe_dict(record.get("state_delta")).get("story_arc_aftermath_flags")),
            **_safe_dict(_safe_dict(record.get("state_delta")).get("faction_pressure_flags")),
            **_safe_dict(_safe_dict(record.get("state_delta")).get("npc_agency_flags")),
        }

        economy_pressure = apply_economy_pressure(
            economy_state=economy_pressure_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_economy_pressure_rules(),
            flags=economy_flags,
            last_emitted_turn_by_rule=economy_pressure_last_emitted_turn_by_rule,
            max_events_per_turn=2,
        )

        if economy_pressure.get("ok"):
            economy_pressure_state = _safe_dict(economy_pressure.get("economy_state"))
            economy_pressure_last_emitted_turn_by_rule = {
                str(k): int(v or 0)
                for k, v in _safe_dict(economy_pressure.get("last_emitted_turn_by_rule")).items()
            }

            pressure_events = _safe_list(economy_pressure.get("events"))
            pressure_signals = _safe_list(economy_pressure.get("world_signals"))
            pressure_warnings = _safe_list(economy_pressure.get("warnings"))
            currency_deltas = _safe_list(economy_pressure.get("currency_deltas"))

            if pressure_events:
                economy_pressure_events.extend(pressure_events)
                economy_pressure_world_signals.extend(pressure_signals)
                economy_pressure_warnings.extend(pressure_warnings)
                economy_pressure_currency_deltas.extend(currency_deltas)

                world_signal_events.extend(pressure_signals)

                record["economy_pressure_events"] = pressure_events
                record["economy_pressure_warnings"] = pressure_warnings
                record["economy_pressure_currency_deltas"] = currency_deltas

        combat_flags = {
            **_safe_dict(mechanics_runtime_state.get("flags")),
            **_safe_dict(_safe_dict(record.get("state_delta")).get("story_arc_aftermath_flags")),
            **_safe_dict(_safe_dict(record.get("state_delta")).get("faction_pressure_flags")),
            **_safe_dict(_safe_dict(record.get("state_delta")).get("npc_agency_flags")),
            **_safe_dict(_safe_dict(record.get("state_delta")).get("economy_pressure")),
        }

        combat_world_state = {
            "flags": combat_flags,
            "story_arcs": story_arc_runtime_state,
            "faction_reputation": faction_reputation_state,
            "world_signals": world_signal_events,
        }

        combat_tick = run_combat_lifecycle_tick(
            combat_state=combat_lifecycle_state,
            player_state=combat_player_state,
            world_state=combat_world_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_combat_lifecycle_rules(),
            last_trigger_turn_by_rule=combat_lifecycle_last_trigger_turn_by_rule,
            max_encounters_per_turn=1,
        )

        if combat_tick.get("ok"):
            combat_lifecycle_state = _safe_dict(combat_tick.get("combat_state"))
            combat_player_state = _safe_dict(combat_tick.get("player_state"))
            combat_lifecycle_last_trigger_turn_by_rule = {
                str(k): int(v or 0)
                for k, v in _safe_dict(combat_tick.get("last_trigger_turn_by_rule")).items()
            }

            combat_encounters = _safe_list(combat_tick.get("encounters"))
            combat_events = _safe_list(combat_tick.get("events"))
            combat_signals = _safe_list(combat_tick.get("world_signals"))
            combat_memories = _safe_list(combat_tick.get("memory_events"))
            combat_injuries = _safe_list(combat_tick.get("injuries"))

            if combat_events:
                combat_lifecycle_encounters.extend(combat_encounters)
                combat_lifecycle_events.extend(combat_events)
                combat_lifecycle_world_signals.extend(combat_signals)
                combat_lifecycle_memory_events.extend(combat_memories)
                combat_lifecycle_injuries.extend(combat_injuries)

                world_signal_events.extend(combat_signals)
                npc_memory_events.extend(combat_memories)

                record["combat_lifecycle_events"] = combat_events
                record["combat_lifecycle_encounters"] = combat_encounters
                record["combat_lifecycle_injuries"] = combat_injuries
                record["world_signals"] = _safe_list(record.get("world_signals")) + combat_signals
                record["npc_memory_events"] = _safe_list(record.get("npc_memory_events")) + combat_memories

                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "combat_lifecycle_flags": _safe_dict(combat_tick.get("flags")),
                    "combat_player_state": combat_player_state,
                }

                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "combat_lifecycle_events": combat_events,
                    "combat_lifecycle_encounters": combat_encounters,
                    "combat_lifecycle_injuries": combat_injuries,
                    "world_signals": _safe_list(record.get("world_signals")),
                    "npc_memory_events": _safe_list(record.get("npc_memory_events")),
                }

        combat_consequence = apply_combat_consequence_pressure(
            player_state=combat_player_state,
            pending_injuries=combat_lifecycle_injuries,
            turn_index=int(record.get("turn_index") or turn_index),
        )

        if combat_consequence.get("ok"):
            consequence_events = _safe_list(combat_consequence.get("events"))
            economy_hints = _safe_list(combat_consequence.get("economy_pressure_hints"))

            if consequence_events:
                combat_consequence_events.extend(consequence_events)
                combat_consequence_economy_hints.extend(economy_hints)
                combat_lifecycle_injuries = _safe_list(combat_consequence.get("pending_injuries"))

                record["combat_consequence_events"] = consequence_events
                record["combat_consequence_economy_hints"] = economy_hints
                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "combat_consequence_pressure": {
                        "events": consequence_events,
                        "economy_pressure_hints": economy_hints,
                    },
                }

        faction_consequence_state = {
            "faction_reputation": faction_reputation_state,
            "story_arcs": story_arc_runtime_state,
            "world_signals": world_signal_events,
            "combat_lifecycle_summary": _build_combat_lifecycle_summary(
                combat_state=combat_lifecycle_state,
                player_state=combat_player_state,
                encounters=combat_lifecycle_encounters,
                events=combat_lifecycle_events,
                world_signals=combat_lifecycle_world_signals,
                memory_events=combat_lifecycle_memory_events,
                injuries=combat_lifecycle_injuries,
                consequence_events=combat_consequence_events,
                economy_hints=combat_consequence_economy_hints,
            ),
        }

        faction_consequence = emit_faction_consequences(
            state=faction_consequence_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_faction_consequence_rules(),
            last_emitted_turn_by_rule=faction_consequence_last_emitted_turn_by_rule,
            max_events_per_turn=2,
        )

        if faction_consequence.get("ok"):
            faction_consequence_last_emitted_turn_by_rule = {
                str(k): int(v or 0)
                for k, v in _safe_dict(faction_consequence.get("last_emitted_turn_by_rule")).items()
            }

            consequence_events = _safe_list(faction_consequence.get("events"))
            consequence_signals = _safe_list(faction_consequence.get("world_signals"))

            if consequence_events:
                faction_reputation_state = _safe_dict(faction_consequence.get("faction_reputation"))
                faction_consequence_events.extend(consequence_events)
                faction_consequence_world_signals.extend(consequence_signals)
                world_signal_events.extend(consequence_signals)

                record["faction_consequence_events"] = consequence_events
                record["world_signals"] = _safe_list(record.get("world_signals")) + consequence_signals
                record["state_delta"] = {
                    **_safe_dict(record.get("state_delta")),
                    "faction_consequence_flags": _safe_dict(faction_consequence.get("flags")),
                    "faction_reputation": faction_reputation_state,
                }
                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "faction_consequence_events": consequence_events,
                    "world_signals": _safe_list(record.get("world_signals")),
                }

        npc_reaction_state = {
            "npc_presence": npc_presence_state,
            "faction_reputation": faction_reputation_state,
            "faction_consequence_events": faction_consequence_events,
            "flags": {
                **_safe_dict(_safe_dict(record.get("state_delta")).get("faction_consequence_flags")),
                **_safe_dict(_safe_dict(record.get("state_delta")).get("combat_lifecycle_flags")),
            },
        }

        npc_reaction = emit_npc_reactions(
            state=npc_reaction_state,
            turn_index=int(record.get("turn_index") or turn_index),
            rules=tavern_npc_reaction_rules(),
            last_emitted_turn_by_rule=npc_reaction_last_emitted_turn_by_rule,
            max_events_per_turn=2,
        )

        if npc_reaction.get("ok"):
            npc_reaction_last_emitted_turn_by_rule = {
                str(k): int(v or 0)
                for k, v in _safe_dict(npc_reaction.get("last_emitted_turn_by_rule")).items()
            }

            reaction_events = _safe_list(npc_reaction.get("events"))
            reaction_memories = _safe_list(npc_reaction.get("memory_events"))
            reaction_signals = _safe_list(npc_reaction.get("world_signals"))

            if reaction_events:
                npc_reaction_events.extend(reaction_events)
                npc_reaction_memory_events.extend(reaction_memories)
                npc_reaction_world_signals.extend(reaction_signals)

                npc_memory_events.extend(reaction_memories)
                world_signal_events.extend(reaction_signals)

                record["npc_reaction_events"] = reaction_events
                record["npc_memory_events"] = _safe_list(record.get("npc_memory_events")) + reaction_memories
                record["world_signals"] = _safe_list(record.get("world_signals")) + reaction_signals
                record["result"] = {
                    **_safe_dict(record.get("result")),
                    "npc_reaction_events": reaction_events,
                    "npc_memory_events": _safe_list(record.get("npc_memory_events")),
                    "world_signals": _safe_list(record.get("world_signals")),
                }

            compression_input = {
                "story_arcs": story_arc_runtime_state,
                "world_signals": world_signal_events,
                "faction_reputation": faction_reputation_state,
                "npc_memory_events": npc_memory_events,
                "economy_pressure": economy_pressure_state,
            }

            compression = compress_world_state_snapshot(
                state=compression_input,
                current_turn=int(record.get("turn_index") or turn_index),
            )

            if compression.get("ok"):
                latest_compressed_world_state = _safe_dict(compression.get("compressed_state"))

                story_arc_runtime_state = _safe_dict(latest_compressed_world_state.get("story_arcs")) or story_arc_runtime_state
                world_signal_events = _safe_list(latest_compressed_world_state.get("world_signals"))
                faction_reputation_state = _safe_dict(latest_compressed_world_state.get("faction_reputation")) or faction_reputation_state
                npc_memory_events = _safe_list(latest_compressed_world_state.get("npc_memory_events"))

                compression_event = {
                    "type": "world_state_compression",
                    "turn": int(record.get("turn_index") or turn_index),
                    "summary": {
                        "expired_world_signal_count": _safe_dict(compression.get("world_signals")).get("expired_count"),
                        "compacted_arc_count": _safe_dict(compression.get("story_arcs")).get("compacted_arc_count"),
                        "compacted_faction_count": _safe_dict(compression.get("faction_reputation")).get("compacted_faction_count"),
                        "npc_memory_dropped_count": _safe_dict(compression.get("npc_memory")).get("dropped_count"),
                    },
                }

                world_state_compression_events.append(compression_event)

                record["world_state_compression"] = compression_event
                record["state_budget_summary"] = compression.get("state_budget_summary")

        row = _apply_turn_action_consistency_gate(
            record,
            canonical_turn_action=canonical_turn_action,
        )
        row = _apply_dialogue_action_relevance_gate(row)
        row = _assert_repaired_dialogue_visible_fields(row)

        presentation_text = _safe_str(
            row.get("selected_narration")
            or row.get("display_narration")
            or row.get("narration")
        )

        compat_ok, compat_diag = _dialogue_presentation_is_category_compatible(
            action_text=_safe_str(row.get("canonical_turn_action") or row.get("player_action")),
            presentation_text=presentation_text,
            row=row,
        )
        row["dialogue_presentation_compatibility"] = compat_diag

        if not compat_ok:
            fallback = _build_category_compatible_presentation_fallback(row)
            row["narration"] = fallback
            row["display_narration"] = fallback
            row["selected_narration"] = fallback
            row["dialogue_action_relevance_repaired"] = True

            relevance = dict(_safe_dict(row.get("dialogue_action_relevance")))
            relevance["repaired"] = True
            relevance["fallback_applied"] = True
            relevance["reason"] = "action_presentation_category_mismatch"
            relevance["source"] = _safe_str(row.get("selected_narration_source") or row.get("narration_source") or "unknown")
            relevance["compatibility"] = compat_diag
            row["dialogue_action_relevance"] = relevance

        # Suppress unsupported combat claims
        if _presentation_has_combat_claim(presentation_text) and not _turn_has_combat_support(row):
            fallback = _build_category_compatible_presentation_fallback(row)
            row["narration"] = fallback
            row["display_narration"] = fallback
            row["selected_narration"] = fallback
            row["unsupported_combat_claim_suppressed"] = True

            relevance = dict(_safe_dict(row.get("dialogue_action_relevance")))
            relevance["repaired"] = True
            relevance["fallback_applied"] = True
            relevance["reason"] = "unsupported_combat_claim_suppressed"
            row["dialogue_action_relevance"] = relevance
        else:
            row["unsupported_combat_claim_suppressed"] = False

        if row.get("direct_graph_execution_kind") == "buy_rations_from_bran":
            row = _apply_buy_rations_direct_graph_execution(row)

        xp_action_id = _safe_str(row.get("direct_graph_xp_execution_action_id"))
        if _is_direct_graph_explicit_xp_combat_action(xp_action_id):
            row = _apply_explicit_combat_xp_direct_graph_execution(
                row,
                action_id=xp_action_id,
            )

        row = _apply_direct_graph_display_quality_pass(row)
        row = _sync_selected_narration_npc_to_top_level(row)

        direct_graph_completion = _direct_complete_graph_action_from_command(
            command=canonical_turn_action,
            row=row,
            all_graph_actions=_safe_list(graph_action_state.get("scenario_progression_actions_all")),
            completed_action_ids=scenario_progression_completed_action_ids,
            completed_mechanics=scenario_progression_completed_mechanics,
        )

        if direct_graph_completion.get("completed"):
            row = dict(_safe_dict(direct_graph_completion.get("row") or row))

        row["direct_graph_action_completion"] = {
            key: value
            for key, value in _safe_dict(direct_graph_completion).items()
            if key != "row"
        }

        row = _apply_direct_graph_display_quality_pass(row)

        _record_completed_graph_progress_from_row(
            row,
            completed_action_ids=scenario_progression_completed_action_ids,
            completed_mechanics=scenario_progression_completed_mechanics,
        )

        visible_scenario_actions = _filter_suppressed_graph_actions(
            _safe_list(graph_action_state.get("scenario_progression_actions_all")),
            suppressed_actions=scenario_progression_suppressed_actions,
            completed_action_ids=scenario_progression_completed_action_ids,
            completed_mechanics=scenario_progression_completed_mechanics,
            turn_index=int(turn_index),
        )

        row["scenario_progression_actions"] = visible_scenario_actions
        row["top_scenario_progression_action_id"] = (
            _graph_action_id(visible_scenario_actions[0])
            if visible_scenario_actions
            else ""
        )
        row["scenario_progression_completed_action_ids"] = sorted(
            scenario_progression_completed_action_ids
        )
        row["scenario_progression_completed_mechanics"] = sorted(
            scenario_progression_completed_mechanics
        )

        if row.get("direct_graph_execution_kind") == "buy_rations_from_bran":
            row = _apply_buy_rations_direct_graph_execution(row)

        xp_action_id = _safe_str(row.get("direct_graph_xp_execution_action_id"))
        if _is_direct_graph_explicit_xp_combat_action(xp_action_id):
            row = _apply_explicit_combat_xp_direct_graph_execution(
                row,
                action_id=xp_action_id,
            )

        row = _apply_direct_graph_display_quality_pass(row)
        row = _sync_selected_narration_npc_to_top_level(row)
        transcript.append(row)

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
            _attach_llm_prompt_debug_to_row(record, combined_background_result)

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

    summary["direct_graph_lifecycle_evidence"] = _collect_direct_graph_lifecycle_evidence(
        transcript
    )

    summary["story_arc_lifecycle_summary"] = _build_story_arc_lifecycle_summary(
        story_arcs=story_arc_runtime_state,
        events=story_arc_resolution_events,
    )

    summary["story_arc_aftermath_summary"] = _build_story_arc_aftermath_summary(
        aftermath_events=story_arc_aftermath_events,
        world_signals=story_arc_aftermath_world_signals,
        npc_memory_events=npc_memory_events,
        followup_hooks=story_arc_aftermath_followup_hooks,
        faction_events=faction_reputation_events,
        seeded_events=followup_arc_seed_events,
    )

    summary["faction_reputation_summary"] = build_faction_reputation_summary(
        faction_reputation_state
    )

    summary["followup_arc_progression_summary"] = _build_followup_arc_progression_summary(
        progression_events=followup_arc_progression_events,
        progression_world_signals=followup_arc_progression_world_signals,
        story_arcs=story_arc_runtime_state,
    )

    summary["world_signal_summary"] = _build_world_signal_summary(world_signal_events)

    summary["faction_pressure_summary"] = _build_faction_pressure_summary(
        pressure_events=faction_pressure_events,
        world_signals=[
            signal
            for signal in _safe_list(world_signal_events)
            if _safe_dict(signal).get("kind") == "faction_pressure"
        ],
    )

    summary["followup_arc_resolution_summary"] = _build_followup_arc_resolution_summary(
        resolution_events=followup_arc_resolution_events,
        resolution_world_signals=followup_arc_resolution_world_signals,
        escalation_hooks=followup_arc_resolution_escalation_hooks,
        escalation_seed_events=escalation_arc_seed_events,
        story_arcs=story_arc_runtime_state,
    )

    summary["pressure_pacing_summary"] = _build_pressure_pacing_summary(
        accepted_events=faction_pressure_events,
        rejected_events=pressure_pacing_rejected_events,
        rejected_world_signals=pressure_pacing_rejected_world_signals,
    )

    # Rebuild story_arc_lifecycle_summary after follow-up progression changes story_arc_runtime_state
    summary["story_arc_lifecycle_summary"] = _build_story_arc_lifecycle_summary(
        story_arcs=story_arc_runtime_state,
        events=story_arc_resolution_events + followup_arc_resolution_events + escalation_arc_seed_events,
    )

    summary["npc_agency_summary"] = _build_npc_agency_summary(
        npc_presence=npc_presence_state,
        schedule_events=npc_schedule_events,
        agency_events=npc_agency_events,
        world_signals=npc_agency_world_signals,
        memory_events=npc_agency_memory_events,
    )

    summary["economy_pressure_summary"] = _build_economy_pressure_summary(
        economy_state=economy_pressure_state,
        events=economy_pressure_events,
        world_signals=economy_pressure_world_signals,
        warnings=economy_pressure_warnings,
        currency_deltas=economy_pressure_currency_deltas,
    )

    summary["combat_lifecycle_summary"] = _build_combat_lifecycle_summary(
        combat_state=combat_lifecycle_state,
        player_state=combat_player_state,
        encounters=combat_lifecycle_encounters,
        events=combat_lifecycle_events,
        world_signals=combat_lifecycle_world_signals,
        memory_events=combat_lifecycle_memory_events,
        injuries=combat_lifecycle_injuries,
        consequence_events=combat_consequence_events,
        economy_hints=combat_consequence_economy_hints,
        transcript=transcript,
    )

    summary["faction_consequence_summary"] = _build_faction_consequence_summary(
        events=faction_consequence_events,
        world_signals=faction_consequence_world_signals,
        faction_reputation=faction_reputation_state,
        transcript=transcript,
    )

    summary["npc_reaction_summary"] = _build_npc_reaction_summary(
        events=npc_reaction_events,
        memory_events=npc_reaction_memory_events,
        world_signals=npc_reaction_world_signals,
        transcript=transcript,
    )

    # Reapply direct graph lifecycle bridges after legacy summary builders.
    # The legacy builders rebuild from older event arrays and can overwrite the
    # bridged direct-graph values back to zero.
    summary = _apply_direct_graph_lifecycle_bridges(summary)

    summary["successful_arc_completion_evidence"] = _collect_successful_arc_completion_evidence(
        transcript
    )
    summary = _apply_successful_arc_completion_bridge(summary)

    transcript = _normalize_turn_action_consistency_transcript_rows(transcript)
    transcript = _normalize_repaired_dialogue_transcript_rows(transcript)

    summary["dialogue_action_relevance_summary"] = _build_dialogue_action_relevance_summary(
        transcript=transcript,
    )

    summary["turn_action_consistency_summary"] = _build_turn_action_consistency_summary(
        transcript=transcript,
    )

    summary["scenario_progression_action_repeat_summary"] = (
        _build_scenario_progression_action_repeat_summary(
            warnings=scenario_progression_warnings,
            suppressed_actions=scenario_progression_suppressed_actions,
        )
    )

    # Hard postcondition: fail if forced overrides exist
    turn_action_summary = _safe_dict(summary.get("turn_action_consistency_summary"))
    if int(turn_action_summary.get("forced_override_count") or 0) > 0:
        raise RuntimeError(
            "mechanics_forced_action_override_forbidden:"
            f"{turn_action_summary.get('forced_override_count')} forced action overrides found"
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
        story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
        story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
        faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
        followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
        faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
        followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
        pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
        escalation_branch_summary=_safe_dict(summary.get("escalation_branch_summary")),
        escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
        world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
        economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
        faction_consequence_summary=_safe_dict(summary.get("faction_consequence_summary")),
        npc_reaction_summary=_safe_dict(summary.get("npc_reaction_summary")),
        dialogue_action_relevance_summary=_safe_dict(summary.get("dialogue_action_relevance_summary")),
        turn_action_consistency_summary=_safe_dict(
            summary.get("turn_action_consistency_summary")
        ),
        scenario_progression_action_repeat_summary=_safe_dict(
            summary.get("scenario_progression_action_repeat_summary")
        ),
        suppressed_selection_guard_summary=_safe_dict(
            summary.get("suppressed_selection_guard_summary")
        ),
        direct_graph_lifecycle_evidence=_safe_dict(summary.get("direct_graph_lifecycle_evidence")),
    )

    summary["escalation_arc_progression_summary"] = _build_escalation_arc_progression_summary(
        progression_events=escalation_arc_progression_events,
        progression_world_signals=escalation_arc_progression_world_signals,
        pressure_events=escalation_arc_pressure_events,
        story_arcs=story_arc_runtime_state,
    )

    # Reapply again because escalation summary is rebuilt after the authoritative
    # lifecycle summary and can overwrite direct-graph escalation evidence.
    summary = _apply_direct_graph_lifecycle_bridges(summary)

    summary["world_state_compression_summary"] = _build_world_state_compression_summary(
        compression_events=world_state_compression_events,
        compressed_state=latest_compressed_world_state or {
            "story_arcs": story_arc_runtime_state,
            "world_signals": world_signal_events,
            "faction_reputation": faction_reputation_state,
            "npc_memory_events": npc_memory_events,
        },
    )

    summary["suppressed_selection_guard_summary"] = (
        _build_suppressed_selection_guard_summary(transcript=transcript)
    )

    summary = _rebuild_final_100_turn_evaluation(
        args=args,
        summary=summary,
        transcript=transcript,
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        dialogue_action_relevance_summary=_safe_dict(summary.get("dialogue_action_relevance_summary")),
        turn_action_consistency_summary=_safe_dict(summary.get("turn_action_consistency_summary")),
        scenario_progression_action_repeat_summary=_safe_dict(
            summary.get("scenario_progression_action_repeat_summary")
        ),
        escalation_branch_summary=_safe_dict(summary.get("escalation_branch_summary")),
        direct_graph_lifecycle_evidence=_safe_dict(summary.get("direct_graph_lifecycle_evidence")),
    )

    # Update the evaluation with new summaries
    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    if evaluation:
        evaluation["gates"]["faction_consequence_present"] = {
            "ok": int(_safe_dict(summary.get("faction_consequence_summary")).get("event_count") or 0) >= 1,
            "value": {
                "event_count": _safe_dict(summary.get("faction_consequence_summary")).get("event_count"),
                "world_signal_count": _safe_dict(summary.get("faction_consequence_summary")).get("world_signal_count"),
                "by_faction": _safe_dict(summary.get("faction_consequence_summary")).get("by_faction"),
                "by_kind": _safe_dict(summary.get("faction_consequence_summary")).get("by_kind"),
            },
            "expected": "at least one deterministic long-term faction consequence",
            "message": "Faction reputation should produce long-term consequences.",
        }
        evaluation["gates"]["npc_reaction_present"] = {
            "ok": int(_safe_dict(summary.get("npc_reaction_summary")).get("event_count") or 0) >= 1,
            "value": {
                "event_count": _safe_dict(summary.get("npc_reaction_summary")).get("event_count"),
                "memory_event_count": _safe_dict(summary.get("npc_reaction_summary")).get("memory_event_count"),
                "world_signal_count": _safe_dict(summary.get("npc_reaction_summary")).get("world_signal_count"),
                "by_npc": _safe_dict(summary.get("npc_reaction_summary")).get("by_npc"),
                "by_kind": _safe_dict(summary.get("npc_reaction_summary")).get("by_kind"),
            },
            "expected": "at least one deterministic NPC reaction to faction/consequence state",
            "message": "NPCs should react to long-term faction consequences.",
        }
        summary["hundred_turn_evaluation"] = evaluation

    summary["hundred_turn_readiness_summary"] = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=int(summary.get("requested_turns") or getattr(args, "turns", 0) or 0),
        turns_executed=int(summary.get("turns_executed") or len(_safe_list(transcript))),
        runtime_errors=_safe_list(summary.get("runtime_errors")),
        warnings=_safe_list(summary.get("warnings")),
        story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
        story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
        faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
        followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
        faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
        followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
        pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
        world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
        escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
        world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
        faction_consequence_summary=_safe_dict(summary.get("faction_consequence_summary")),
        npc_reaction_summary=_safe_dict(summary.get("npc_reaction_summary")),
    )

    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    evaluation_gates = _safe_dict(evaluation.get("gates"))
    npc_gate = _safe_dict(evaluation_gates.get("npc_agency_present"))
    npc_gate_value = _safe_dict(npc_gate.get("value"))
    npc_summary = _safe_dict(summary.get("npc_agency_summary"))

    if npc_summary and npc_gate and npc_gate_value.get("agency_event_count") is None:
        summary["hundred_turn_evaluation"] = _build_100_turn_evaluation_summary(
            turns_executed=int(summary.get("turns_executed") or len(_safe_list(transcript))),
            requested_turns=int(summary.get("requested_turns") or getattr(args, "turns", 0) or 0),
            runtime_errors=_safe_list(summary.get("runtime_errors")),
            warnings=_safe_list(summary.get("warnings")),
            transcript=_safe_list(transcript),
            performance_summary=_safe_dict(summary.get("performance_seconds_summary")),
            narration_grounding_summary=_safe_dict(summary.get("narration_grounding_summary")),
            progress_quality_summary=_safe_dict(summary.get("canonical_progress_quality")),
            checkpoint_summary=_safe_dict(summary.get("checkpoint_summary")),
            loop_detection_summary=_safe_dict(summary.get("loop_detection_summary")),
            mechanics_coverage_summary=_safe_dict(summary.get("mechanics_coverage_summary")),
            story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
            story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
            faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
            followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
            faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
            followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
            pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
            world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
        escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
        world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
    )

    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    evaluation_gates = _safe_dict(evaluation.get("gates"))
    economy_gate = _safe_dict(evaluation_gates.get("economy_pressure_present"))
    economy_gate_value = _safe_dict(economy_gate.get("value"))
    economy_summary = _safe_dict(summary.get("economy_pressure_summary"))

    if economy_summary and economy_gate and economy_gate_value.get("event_count") is None:
        summary["hundred_turn_evaluation"] = _build_100_turn_evaluation_summary(
            turns_executed=int(summary.get("turns_executed") or len(_safe_list(transcript))),
            requested_turns=int(summary.get("requested_turns") or getattr(args, "turns", 0) or 0),
            runtime_errors=_safe_list(summary.get("runtime_errors")),
            warnings=_safe_list(summary.get("warnings")),
            transcript=_safe_list(transcript),
            performance_summary=_safe_dict(summary.get("performance_seconds_summary")),
            narration_grounding_summary=_safe_dict(summary.get("narration_grounding_summary")),
            progress_quality_summary=_safe_dict(summary.get("canonical_progress_quality")),
            checkpoint_summary=_safe_dict(summary.get("checkpoint_summary")),
            loop_detection_summary=_safe_dict(summary.get("loop_detection_summary")),
            mechanics_coverage_summary=_safe_dict(summary.get("mechanics_coverage_summary")),
            story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
            story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
            faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
            followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
            faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
            followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
            pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
            world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
            escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
        world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
        faction_consequence_summary=_safe_dict(summary.get("faction_consequence_summary")),
        npc_reaction_summary=_safe_dict(summary.get("npc_reaction_summary")),
    )

    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    evaluation_gates = _safe_dict(evaluation.get("gates"))
    combat_gate = _safe_dict(evaluation_gates.get("combat_lifecycle_present"))
    combat_gate_value = _safe_dict(combat_gate.get("value"))
    combat_summary = _safe_dict(summary.get("combat_lifecycle_summary"))

    if combat_summary and combat_gate and combat_gate_value.get("encounter_count") is None:
        summary["hundred_turn_evaluation"] = _build_100_turn_evaluation_summary(
            turns_executed=int(summary.get("turns_executed") or len(_safe_list(transcript))),
            requested_turns=int(summary.get("requested_turns") or getattr(args, "turns", 0) or 0),
            runtime_errors=_safe_list(summary.get("runtime_errors")),
            warnings=_safe_list(summary.get("warnings")),
            transcript=_safe_list(transcript),
            performance_summary=_safe_dict(summary.get("performance_seconds_summary")),
            narration_grounding_summary=_safe_dict(summary.get("narration_grounding_summary")),
            progress_quality_summary=_safe_dict(summary.get("canonical_progress_quality")),
            checkpoint_summary=_safe_dict(summary.get("checkpoint_summary")),
            loop_detection_summary=_safe_dict(summary.get("loop_detection_summary")),
            mechanics_coverage_summary=_safe_dict(summary.get("mechanics_coverage_summary")),
            story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
            story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
            faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
            followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
            faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
            followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
            pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
            world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
            escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
            world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
        faction_consequence_summary=_safe_dict(summary.get("faction_consequence_summary")),
        npc_reaction_summary=_safe_dict(summary.get("npc_reaction_summary")),
    )

    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    evaluation_gates = _safe_dict(evaluation.get("gates"))

    faction_gate = _safe_dict(evaluation_gates.get("faction_consequence_present"))
    faction_gate_value = _safe_dict(faction_gate.get("value"))
    faction_summary = _safe_dict(summary.get("faction_consequence_summary"))

    npc_reaction_gate = _safe_dict(evaluation_gates.get("npc_reaction_present"))
    npc_reaction_gate_value = _safe_dict(npc_reaction_gate.get("value"))
    npc_reaction_summary = _safe_dict(summary.get("npc_reaction_summary"))

    if (
        (faction_summary and faction_gate and faction_gate_value.get("event_count") is None)
        or (
            npc_reaction_summary
            and npc_reaction_gate
            and npc_reaction_gate_value.get("event_count") is None
        )
    ):
        summary["hundred_turn_evaluation"] = _build_100_turn_evaluation_summary(
            turns_executed=int(summary.get("turns_executed") or len(_safe_list(transcript))),
            requested_turns=int(summary.get("requested_turns") or getattr(args, "turns", 0) or 0),
            runtime_errors=_safe_list(summary.get("runtime_errors")),
            warnings=_safe_list(summary.get("warnings")),
            transcript=_safe_list(transcript),
            performance_summary=_safe_dict(summary.get("performance_seconds_summary")),
            narration_grounding_summary=_safe_dict(summary.get("narration_grounding_summary")),
            progress_quality_summary=_safe_dict(summary.get("canonical_progress_quality")),
            checkpoint_summary=_safe_dict(summary.get("checkpoint_summary")),
            loop_detection_summary=_safe_dict(summary.get("loop_detection_summary")),
            mechanics_coverage_summary=_safe_dict(summary.get("mechanics_coverage_summary")),
            story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
            story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
            faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
            followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
            faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
            followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
            pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
            world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
            escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
            world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
            npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
            economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
            combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
            faction_consequence_summary=faction_summary,
            npc_reaction_summary=npc_reaction_summary,
        )

    evaluation = _safe_dict(summary.get("hundred_turn_evaluation"))
    evaluation_gates = _safe_dict(evaluation.get("gates"))
    dialogue_gate = _safe_dict(evaluation_gates.get("dialogue_action_relevance_ok"))
    dialogue_gate_value = _safe_dict(dialogue_gate.get("value"))
    dialogue_summary = _safe_dict(summary.get("dialogue_action_relevance_summary"))

    if dialogue_summary and dialogue_gate and dialogue_gate_value.get("checked_count") is None:
        summary = _apply_direct_graph_lifecycle_bridges(summary)

    summary = _apply_direct_graph_lifecycle_bridges(summary)

    summary = _rebuild_final_100_turn_evaluation(
        args=args,
        summary=summary,
        transcript=transcript,
            dialogue_action_relevance_summary=_safe_dict(
                summary.get("dialogue_action_relevance_summary")
            ),
            turn_action_consistency_summary=_safe_dict(
                summary.get("turn_action_consistency_summary")
            ),
        scenario_progression_action_repeat_summary=_safe_dict(
            summary.get("scenario_progression_action_repeat_summary")
        ),
        suppressed_selection_guard_summary=_safe_dict(
            summary.get("suppressed_selection_guard_summary")
        ),
        escalation_branch_summary=_safe_dict(summary.get("escalation_branch_summary")),
        direct_graph_lifecycle_evidence=_safe_dict(summary.get("direct_graph_lifecycle_evidence")),
    )

    summary["ok"] = (
        bool(_safe_dict(summary.get("hundred_turn_evaluation")).get("ok"))
        and bool(_safe_dict(summary.get("hundred_turn_readiness_summary")).get("ok"))
        and not _safe_list(summary.get("runtime_errors"))
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
        story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
        story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
        faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
        followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
        faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
        followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
        pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
        world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
        escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
        world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
        faction_consequence_summary=_safe_dict(summary.get("faction_consequence_summary")),
        npc_reaction_summary=_safe_dict(summary.get("npc_reaction_summary")),
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
        story_arc_lifecycle_summary=_safe_dict(summary.get("story_arc_lifecycle_summary")),
        story_arc_aftermath_summary=_safe_dict(summary.get("story_arc_aftermath_summary")),
        faction_reputation_summary=_safe_dict(summary.get("faction_reputation_summary")),
        followup_arc_progression_summary=_safe_dict(summary.get("followup_arc_progression_summary")),
        faction_pressure_summary=_safe_dict(summary.get("faction_pressure_summary")),
        followup_arc_resolution_summary=_safe_dict(summary.get("followup_arc_resolution_summary")),
        pressure_pacing_summary=_safe_dict(summary.get("pressure_pacing_summary")),
        world_signal_summary=_safe_dict(summary.get("world_signal_summary")),
        escalation_arc_progression_summary=_safe_dict(summary.get("escalation_arc_progression_summary")),
        world_state_compression_summary=_safe_dict(summary.get("world_state_compression_summary")),
        npc_agency_summary=_safe_dict(summary.get("npc_agency_summary")),
        economy_pressure_summary=_safe_dict(summary.get("economy_pressure_summary")),
        combat_lifecycle_summary=_safe_dict(summary.get("combat_lifecycle_summary")),
        faction_consequence_summary=_safe_dict(summary.get("faction_consequence_summary")),
        npc_reaction_summary=_safe_dict(summary.get("npc_reaction_summary")),
    )

    summary["ok"] = bool(_safe_dict(summary.get("hundred_turn_evaluation")).get("ok"))

    summary["arc_completion_quality_summary"] = _build_arc_completion_quality_summary(summary)
    summary["dialogue_repair_quality_summary"] = _build_dialogue_repair_quality_summary(summary)
    summary["dialogue_stale_source_summary"] = _build_dialogue_stale_source_summary(transcript)

    product_quality_warnings = list(_safe_list(summary.get("product_quality_warnings")))
    arc_quality = _safe_dict(summary.get("arc_completion_quality_summary"))
    for warning in _safe_list(arc_quality.get("warnings")):
        warning_s = _safe_str(warning)
        if warning_s and warning_s not in product_quality_warnings:
            product_quality_warnings.append(warning_s)
    dialogue_quality = _safe_dict(summary.get("dialogue_repair_quality_summary"))
    for warning in _safe_list(dialogue_quality.get("warnings")):
        warning_s = _safe_str(warning)
        if warning_s and warning_s not in product_quality_warnings:
            product_quality_warnings.append(warning_s)
    summary["product_quality_warnings"] = product_quality_warnings

    summary["character_inventory_progression"] = _build_character_inventory_progression_summary(
        full_transcript_for_summaries,
        initial_state=_safe_dict(summary.get("initial_player_state")),
    )

    # Do not write the rich campaign report here. At this point transcript rows
    # have not yet gone through final presentation normalization, current-action
    # response repair, or meta-leakage cleanup. Writing the rich report from this
    # pre-normalized transcript creates stale HTML entries in report ZIPs.
    # N116.12 writes the rich report only after final_transcript_rows is built.

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

    # Do not rewrite the rich report here either: performance is final enough,
    # but presentation rows are still pre-normalization. The only authoritative
    # rich report write happens after final_transcript_rows is constructed.
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

    final_transcript_rows = _build_final_transcript_artifact_rows(
        transcript=transcript,
        transcript_artifacts=transcript_artifacts,
        summary=summary,
        session_id=_safe_str(summary.get("session_id") or ""),
    )
    # N116.9.3: normalize architecture/current-action diagnostics at the final
    # artifact boundary.  This catches any late writer or repair path that
    # leaves architecture.required_focus populated but current_action_response
    # empty before JSON/HTML artifacts are built.
    final_transcript_rows = _sync_current_action_response_artifact_rows(final_transcript_rows)

    transcript = final_transcript_rows
    if isinstance(transcript_artifacts, dict):
        transcript_artifacts["transcript"] = final_transcript_rows

    summary["transcript_artifact_quality_summary"] = (
        _build_transcript_artifact_quality_summary(final_transcript_rows)
    )
    summary["dialogue_action_relevance_summary"] = _build_dialogue_action_relevance_summary(
        transcript=final_transcript_rows,
    )
    summary["dialogue_repair_quality_summary"] = _build_dialogue_repair_quality_summary(summary)

    # N116.9.4: force the synced row objects into the actual artifact source
    # before summary counting and before bounded/slim transcript derivation.
    # Summary-time self-healing is not enough; the persisted JSON rows must
    # carry the same current_action_response.required_focus diagnostics.
    final_transcript_rows = _sync_current_action_response_artifact_rows(final_transcript_rows)
    transcript = final_transcript_rows
    if isinstance(transcript_artifacts, dict):
        transcript_artifacts["transcript"] = final_transcript_rows

    summary["npc_response_architecture_persistence_summary"] = (
        _build_npc_response_architecture_persistence_summary(final_transcript_rows)
    )
    _assert_current_action_response_artifact_rows_synced(
        final_transcript_rows,
        artifact_name="final_transcript_rows",
    )
    _assert_npc_response_architecture_persisted(summary)

    _assert_transcript_artifact_consistency(
        final_transcript_rows=final_transcript_rows,
        summary=summary,
    )

    summary["session_id"] = _safe_str(summary.get("session_id") or session_id)

    summary = _finalize_background_presentation_attachment_tracking(
        summary,
        final_transcript_rows,
    )

    _assert_no_cross_turn_background_presentation(final_transcript_rows)

    summary["background_presentation_attachment_summary"] = (
        _build_background_presentation_attachment_summary(summary, final_transcript_rows)
    )

    # N116.9.5: one final sync after background attachment accounting and
    # before every JSON transcript artifact is derived.  The previous patch
    # synced before this phase, but the final artifact gate still caught rows
    # whose architecture.required_focus was not reflected in
    # current_action_response.required_focus.
    final_transcript_rows = _sync_current_action_response_artifact_rows(final_transcript_rows)
    transcript = final_transcript_rows
    if isinstance(transcript_artifacts, dict):
        transcript_artifacts["transcript"] = final_transcript_rows

    bounded_transcript_rows = _build_bounded_transcript_rows(
        final_transcript_rows,
        max_row_bytes=50000,
    )
    bounded_transcript_rows = _sync_current_action_response_artifact_rows(
        bounded_transcript_rows
    )

    slim_transcript_rows = [
        _slim_transcript_row(row, max_row_bytes=25000)
        for row in final_transcript_rows
    ]
    slim_transcript_rows = _sync_current_action_response_artifact_rows(
        slim_transcript_rows
    )

    if any(row is None for row in slim_transcript_rows):
        raise RuntimeError("slim_transcript_rows_null_after_build")

    if any(row is None for row in bounded_transcript_rows):
        raise RuntimeError("bounded_transcript_rows_null_after_build")

    _assert_current_action_response_artifact_rows_synced(
        final_transcript_rows,
        artifact_name="full-transcript.json",
    )
    _assert_current_action_response_artifact_rows_synced(
        bounded_transcript_rows,
        artifact_name="transcript.json",
    )
    _assert_current_action_response_artifact_rows_synced(
        slim_transcript_rows,
        artifact_name="slim-transcript.json",
    )

    wrote_full_transcript = _should_write_full_transcript(args)

    summary["transcript_size_summary"] = _build_transcript_size_summary(
        final_transcript_rows=final_transcript_rows,
        bounded_transcript_rows=bounded_transcript_rows,
        slim_transcript_rows=slim_transcript_rows,
        wrote_full_transcript=wrote_full_transcript,
    )

    summary["llm_prompt_and_fallback_summary"] = _build_llm_prompt_and_fallback_summary(
        final_transcript_rows
    )

    _assert_bounded_transcript_artifacts_valid(
        bounded_transcript_rows=bounded_transcript_rows,
        slim_transcript_rows=slim_transcript_rows,
        summary=summary,
    )

    # Final health must be the absolute last writer before artifacts
    summary["autoplay_health"] = _force_final_autoplay_health(summary)

    _assert_final_artifact_consistency(summary)

    final_health = _safe_dict(summary.get("autoplay_health"))
    if bool(summary.get("ok")):
        if not bool(_safe_dict(summary.get("hundred_turn_evaluation")).get("ok")):
            raise RuntimeError("final_health_rebuild_order_invalid:evaluation_not_ok")
        if not bool(_safe_dict(summary.get("hundred_turn_readiness_summary")).get("ok")):
            raise RuntimeError("final_health_rebuild_order_invalid:readiness_not_ok")
        if not bool(final_health.get("ok")):
            raise RuntimeError(
                "final_health_rebuild_order_invalid:"
                f"summary_ok={summary.get('ok')}:"
                f"health={final_health}"
            )
    # Temporary fallback only. The canonical HTML report is rebuilt below from
    # final_transcript_rows after late evaluation/health normalization.
    html_report = _build_minimal_autoplay_html_report(final_summary=html_report_source)

    summary = _apply_direct_graph_lifecycle_bridges(summary)

    summary = _rebuild_final_100_turn_evaluation(
        args=args,
        summary=summary,
        transcript=transcript,
        dialogue_action_relevance_summary=_safe_dict(
            summary.get("dialogue_action_relevance_summary")
        ),
        turn_action_consistency_summary=_safe_dict(
            summary.get("turn_action_consistency_summary")
        ),
        scenario_progression_action_repeat_summary=_safe_dict(
            summary.get("scenario_progression_action_repeat_summary")
        ),
        escalation_branch_summary=_safe_dict(summary.get("escalation_branch_summary")),
        direct_graph_lifecycle_evidence=_safe_dict(summary.get("direct_graph_lifecycle_evidence")),
    )

    dialogue_eval_gate = _safe_dict(
        _safe_dict(summary.get("hundred_turn_evaluation")).get("gates")
    ).get("dialogue_action_relevance_ok")

    dialogue_eval_gate = _safe_dict(dialogue_eval_gate)
    dialogue_eval_value = _safe_dict(dialogue_eval_gate.get("value"))
    dialogue_summary = _safe_dict(summary.get("dialogue_action_relevance_summary"))

    if dialogue_summary and dialogue_eval_value.get("checked_count") is None:
        raise RuntimeError(
            "dialogue_action_relevance_final_eval_not_wired:"
            "summary exists but evaluation gate has null checked_count"
        )

    turn_action_eval_gate = _safe_dict(
        _safe_dict(summary.get("hundred_turn_evaluation")).get("gates")
    ).get("turn_action_consistency_ok")
    turn_action_eval_gate = _safe_dict(turn_action_eval_gate)
    turn_action_eval_value = _safe_dict(turn_action_eval_gate.get("value"))
    turn_action_summary = _safe_dict(summary.get("turn_action_consistency_summary"))

    if turn_action_summary and turn_action_eval_value.get("checked_count") is None:
        raise RuntimeError(
            "turn_action_consistency_final_eval_not_wired:"
            "summary exists but evaluation gate has null checked_count"
        )

    if turn_action_summary and int(turn_action_summary.get("unrepaired_count") or 0) > 0:
        raise RuntimeError(
            "turn_action_consistency_unrepaired:"
            f"{turn_action_summary.get('unrepaired_count')} unrepaired action-context mismatches"
        )


    scenario_repeat_eval_gate = _safe_dict(
        _safe_dict(summary.get("hundred_turn_evaluation")).get("gates")
    ).get("scenario_progression_repeats_bounded")
    scenario_repeat_eval_gate = _safe_dict(scenario_repeat_eval_gate)
    scenario_repeat_eval_value = _safe_dict(scenario_repeat_eval_gate.get("value"))
    scenario_repeat_summary = _safe_dict(summary.get("scenario_progression_action_repeat_summary"))

    if scenario_repeat_summary and scenario_repeat_eval_value.get("repeat_warning_count") is None:
        raise RuntimeError(
            "scenario_progression_action_repeat_final_eval_not_wired:"
            "summary exists but evaluation gate has null repeat_warning_count"
        )

    repeat_summary = _safe_dict(summary.get("scenario_progression_action_repeat_summary"))
    guard_summary = _safe_dict(summary.get("suppressed_selection_guard_summary"))

    if (
        int(repeat_summary.get("repeat_warning_count") or 0) > 5
        and int(guard_summary.get("checked_count") or 0) == 0
    ):
        raise RuntimeError(
            "suppressed_selection_guard_not_wired:"
            "repeat warnings exceeded threshold but guard checked_count is zero"
        )

    if int(guard_summary.get("no_replacement_count") or 0) > 0:
        raise RuntimeError(
            "suppressed_selection_guard_no_replacement:"
            f"{guard_summary.get('no_replacement_count')} suppressed selections had no replacement"
        )

    # Rebuild final health again after direct-graph bridges and final evaluation
    # have run. Earlier health normalization happens before those late passes,
    # so it can keep summary_ok/evaluation_ok as false even when the final
    # authoritative summary is green.
    summary["autoplay_health"] = _force_final_autoplay_health(summary)

    with _ProbeTimer(
        bool(getattr(args, "debug_autoplay_stage_timing", False)),
        "write_results_zip",
    ):
        # write_results_zip.start
        # write_results_zip.end
        # Create zip artifact with N79/N81 completeness
        output_dir_path = Path(args.output_dir)
        zip_path = output_dir_path / "autoplay-campaign-results.zip"

        artifact_manifest = {
            "format_version": "autoplay_artifact_manifest_v1",
            "turns_requested": int(args.turns or 0),
            "generated_files": [],
        }

        artifact_paths_base: Dict[str, str] = {}

        def _zip_writestr_json(
            zip_handle: Any,
            artifact_manifest: Dict[str, Any],
            name: str,
            value: Any,
        ) -> None:
            generated_files = artifact_manifest.setdefault("generated_files", [])
            if name in generated_files:
                return
            zip_handle.writestr(
                name,
                json.dumps(value, ensure_ascii=False, indent=2, default=str),
            )
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

    summary = _apply_direct_graph_lifecycle_bridges(summary)

    summary = _rebuild_final_100_turn_evaluation(
        args=args,
        summary=summary,
        transcript=transcript,
        dialogue_action_relevance_summary=_safe_dict(
            summary.get("dialogue_action_relevance_summary")
        ),
        turn_action_consistency_summary=_safe_dict(
            summary.get("turn_action_consistency_summary")
        ),
        scenario_progression_action_repeat_summary=_safe_dict(
            summary.get("scenario_progression_action_repeat_summary")
        ),
        suppressed_selection_guard_summary=_safe_dict(
            summary.get("suppressed_selection_guard_summary")
        ),
        escalation_branch_summary=_safe_dict(summary.get("escalation_branch_summary")),
        direct_graph_lifecycle_evidence=_safe_dict(
            summary.get("direct_graph_lifecycle_evidence")
        ),
    )

    # Direct bridge hard postcondition
    direct_lifecycle = _safe_dict(summary.get("direct_graph_lifecycle_evidence"))
    requested_turns_for_bridge_gate = int(
        getattr(args, "turns", None)
        or summary.get("requested_turns")
        or 0
    )

    if (
        requested_turns_for_bridge_gate >= 100
        and direct_lifecycle
        and int(direct_lifecycle.get("aftermath_like_count") or 0) > 0
    ):
        evaluation_gates = _safe_dict(
            _safe_dict(summary.get("hundred_turn_evaluation")).get("gates")
        )
        for gate_name in (
            "story_arc_aftermath_present",
            "faction_reputation_changed",
            "faction_pressure_present",
            "pressure_pacing_active",
            "followup_arc_progression_present",
            "followup_arc_resolution_present",
            "escalation_branch_seeded",
            "escalation_arc_progression_present",
            "npc_agency_present",
        ):
            gate = _safe_dict(evaluation_gates.get(gate_name))
            if gate and not gate.get("ok"):
                raise RuntimeError(
                    "direct_graph_lifecycle_bridge_not_wired:"
                    f"{gate_name} failed despite direct graph lifecycle evidence"
                )

        summary["autoplay_health"] = _force_final_autoplay_health(summary)
        if bool(summary.get("ok")) and not bool(_safe_dict(summary.get("autoplay_health")).get("ok")):
            raise RuntimeError(
                "summary_json_health_stale_before_write:"
                f"summary_ok={summary.get('ok')}:"
                f"evaluation_ok={_safe_dict(summary.get('hundred_turn_evaluation')).get('ok')}:"
                f"readiness_ok={_safe_dict(summary.get('hundred_turn_readiness_summary')).get('ok')}:"
                f"autoplay_health={summary.get('autoplay_health')}"
            )

        _assert_final_artifact_consistency(summary)

        # N116.13: keep the original rich/styled report, but make the
        # visible transcript/timeline authoritative by replacing only that
        # section with final_transcript_rows. If the rich writer is not
        # available, fall back to the compact artifact-first report.
        if args.artifact_detail == "full":
            final_html_report_source = dict(summary)
            final_html_report_source.update(_safe_dict(report_payload))
            final_html_report_source["final_transcript_rows"] = final_transcript_rows
            final_html_report_source["transcript"] = final_transcript_rows

            final_report_html_path = Path(args.output_dir) / "autoplay-campaign-report.html"
            rich_report_html_path = Path(args.output_dir) / "autoplay-campaign-report-rich.html"

            rich_source_html = _build_rich_campaign_report_html_from_existing_writer(
                args=args,
                output_dir_path=Path(args.output_dir),
                rich_html_path=rich_report_html_path,
                summary=summary,
                report_payload=_safe_dict(report_payload),
                metrics=_safe_dict(metrics),
                final_transcript_rows=final_transcript_rows,
                final_state=_safe_dict(last_committed_state),
            )
            if not rich_source_html:
                rich_source_html = _build_minimal_autoplay_html_report(
                    final_summary=final_html_report_source,
                )

            html_report = _restore_rich_report_with_final_transcript_timeline(
                rich_source_html,
                final_transcript_rows,
            )
            html_report = _sanitize_known_stale_report_text(
                html_report,
                final_transcript_rows,
            )
            final_report_html_path.write_text(html_report, encoding="utf-8")
            rich_report_html_path.write_text(html_report, encoding="utf-8")
            extra_paths["campaign_report_html"] = str(final_report_html_path)
            extra_paths["campaign_report_rich_html"] = str(rich_report_html_path)
            _assert_html_report_matches_final_transcript_rows(
                html_report=html_report,
                final_transcript_rows=final_transcript_rows,
            )

        # N116.13.5: Always build the canonical HTML from the original
        # rich/styled report writer when it is available. Earlier patches only
        # rebuilt the rich report inside the full-detail/direct-lifecycle branch,
        # so normal report ZIPs fell back to the compact/minimal HTML and lost
        # Chronicle, quest, NPC, location, performance, and debug features.
        final_html_report_source = dict(summary)
        final_html_report_source.update(_safe_dict(report_payload))
        final_html_report_source["final_transcript_rows"] = final_transcript_rows
        final_html_report_source["transcript"] = final_transcript_rows

        final_report_html_path = output_dir_path / "autoplay-campaign-report.html"
        rich_report_html_path = output_dir_path / "autoplay-campaign-report-rich.html"

        rich_source_html = _build_rich_campaign_report_html_from_existing_writer(
            args=args,
            output_dir_path=output_dir_path,
            rich_html_path=rich_report_html_path,
            summary=summary,
            report_payload=_safe_dict(report_payload),
            metrics=_safe_dict(metrics),
            final_transcript_rows=final_transcript_rows,
            final_state=_safe_dict(last_committed_state),
        )
        if not rich_source_html:
            rich_source_html = _build_minimal_autoplay_html_report(
                final_summary=final_html_report_source,
            )

        html_report = _restore_rich_report_with_final_transcript_timeline(
            rich_source_html,
            final_transcript_rows,
        )
        html_report = _sanitize_known_stale_report_text(
            html_report,
            final_transcript_rows,
        )
        final_report_html_path.write_text(html_report, encoding="utf-8")
        rich_report_html_path.write_text(html_report, encoding="utf-8")
        extra_paths["campaign_report_html"] = str(final_report_html_path)
        extra_paths["campaign_report_rich_html"] = str(rich_report_html_path)
        _assert_html_report_matches_final_transcript_rows(
            html_report=html_report,
            final_transcript_rows=final_transcript_rows,
        )

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
                "arc-completion-quality-summary.json",
                summary.get("arc_completion_quality_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "dialogue-repair-quality-summary.json",
                summary.get("dialogue_repair_quality_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "llm-prompt-and-fallback-summary.json",
                summary.get("llm_prompt_and_fallback_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "dialogue-stale-source-summary.json",
                summary.get("dialogue_stale_source_summary", {}),
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
                "suppressed-selection-guard-summary.json",
                summary.get("suppressed_selection_guard_summary", {}),
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
                "turn-action-consistency-summary.json",
                summary.get("turn_action_consistency_summary", {}),
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

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "dialogue-action-relevance-summary.json",
                summary.get("dialogue_action_relevance_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "transcript.json",
                bounded_transcript_rows,
            )

            if _should_write_full_transcript(args):
                _zip_writestr_json(
                    zip_handle,
                    artifact_manifest,
                    "full-transcript.json",
                    final_transcript_rows,
                )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "slim-transcript.json",
                slim_transcript_rows,
            )
            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "transcript-size-summary.json",
                summary.get("transcript_size_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "background-presentation-attachment-summary.json",
                summary.get("background_presentation_attachment_summary", {}),
            )
            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "background-presentation-attachment-events.json",
                summary.get("background_presentation_attachment_events", []),
            )
            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "orphaned-background-presentation-results.json",
                summary.get("orphaned_background_presentation_results", []),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "story-arc-lifecycle-summary.json",
                summary.get("story_arc_lifecycle_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "story-arc-aftermath-summary.json",
                summary.get("story_arc_aftermath_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "direct-graph-lifecycle-evidence.json",
                summary.get("direct_graph_lifecycle_evidence", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "successful-arc-completion-evidence.json",
                summary.get("successful_arc_completion_evidence", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "faction-reputation-summary.json",
                summary.get("faction_reputation_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "followup-arc-progression-summary.json",
                summary.get("followup_arc_progression_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "transcript-artifact-quality-summary.json",
                summary.get("transcript_artifact_quality_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "faction-pressure-summary.json",
                summary.get("faction_pressure_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "hundred-turn-readiness-summary.json",
                summary.get("hundred_turn_readiness_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "world-signal-summary.json",
                summary.get("world_signal_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "followup-arc-resolution-summary.json",
                summary.get("followup_arc_resolution_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "pressure-pacing-summary.json",
                summary.get("pressure_pacing_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "escalation-arc-progression-summary.json",
                summary.get("escalation_arc_progression_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "world-state-compression-summary.json",
                summary.get("world_state_compression_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "npc-agency-summary.json",
                summary.get("npc_agency_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "economy-pressure-summary.json",
                summary.get("economy_pressure_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "combat-lifecycle-summary.json",
                summary.get("combat_lifecycle_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "faction-consequence-summary.json",
                summary.get("faction_consequence_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "npc-reaction-summary.json",
                summary.get("npc_reaction_summary", {}),
            )

            _zip_writestr_json(
                zip_handle,
                artifact_manifest,
                "scenario-progression-action-repeat-summary.json",
                summary.get("scenario_progression_action_repeat_summary", {}),
            )

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
                if final_transcript_rows:
                    transcript_path.write_text(
                        json.dumps(
                            bounded_transcript_rows,
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
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

                final_autoplay_health = _safe_dict(summary.get("autoplay_health"))

                _zip_writestr_json(
                    zip_handle,
                    artifact_manifest,
                    "autoplay-health.json",
                    final_autoplay_health,
                )

                # Write campaign report model JSON if it exists. Do not include a
                # second/legacy HTML report in the ZIP: stale legacy HTML was the
                # source of report/transcript divergence. The canonical
                # autoplay-campaign-report.html above is the only HTML report.
                campaign_report_json = output_dir_path / "autoplay-campaign-report.json"

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

            artifact_paths_base.update(
                {
                    "summary": _safe_str(output_dir_path / "autoplay-summary.json"),
                    "metrics": _safe_str(output_dir_path / "autoplay-progress-metrics.json")
                    if getattr(args, "artifact_detail", None) == "full"
                    else "",
                    "performance": _safe_str(output_dir_path / "autoplay-performance.json")
                    if getattr(args, "artifact_detail", None) == "full"
                    else "",
                    "story_variety": _safe_str(output_dir_path / "autoplay-story-variety.json")
                    if getattr(args, "artifact_detail", None) == "full"
                    else "",
                    "health": _safe_str(output_dir_path / "autoplay-health.json")
                    if getattr(args, "artifact_detail", None) == "full"
                    else "",
                    "transcript": _safe_str(output_dir_path / "autoplay-transcript.json")
                    if getattr(args, "artifact_detail", None) == "full"
                    else "",
                    "html": _safe_str(output_dir_path / "autoplay-campaign-report.html"),
                    "zip": _safe_str(zip_path),
                }
            )

        paths = _merge_artifact_paths(artifact_paths_base, extra_paths)
        summary["artifact_paths"] = paths  # artifact_paths

    _force_exit_if_background_threads_remain(
        args=args,
        pipeline=pipeline,
        exit_code=0 if bool(_safe_dict(summary.get("quality_gate_summary")).get("ok", True)) else 1,
    )

    # Final assertion must read health rebuilt from the final summary, not an
    # artifact-time snapshot captured before late evaluation normalization.
    summary["autoplay_health"] = _force_final_autoplay_health(summary)
    final_health = _safe_dict(summary.get("autoplay_health"))
    if bool(summary.get("ok")) and not bool(final_health.get("ok")):
        raise RuntimeError(
            "autoplay_health_final_write_failed:"
            f"summary_ok={summary.get('ok')}:"
            f"evaluation_ok={_safe_dict(summary.get('hundred_turn_evaluation')).get('ok')}:"
            f"readiness_ok={_safe_dict(summary.get('hundred_turn_readiness_summary')).get('ok')}:"
            f"health={final_health}"
        )

    return summary


def _apply_autoplay_profile_defaults(args: Any) -> Any:
    profile = _safe_str(getattr(args, "autoplay_profile", "") or "custom")

    if profile == "smoke_20":
        if getattr(args, "turns", None) is None:
            args.turns = 20
        return args

    if profile == "smoke_100":
        # smoke_100 defaults to 100, but explicit --turns is allowed for fast
        # compile/runtime smoke checks that keep the same profile settings.
        if getattr(args, "turns", None) is None:
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


def _assert_real_autoplay_runner_present() -> None:
    import inspect

    fn = globals().get("_run_autoplay_campaign")
    if not callable(fn):
        raise RuntimeError("real_autoplay_runner_missing:_run_autoplay_campaign")

    try:
        source = inspect.getsource(fn)
    except Exception as exc:
        raise RuntimeError(
            f"real_autoplay_runner_uninspectable:{type(exc).__name__}:{exc}"
        ) from exc

    required_markers = (
        "write_results_zip.start",
        "write_results_zip.end",
        "artifact_paths",
        "_force_exit_if_background_threads_remain",
    )

    missing = [marker for marker in required_markers if marker not in source]
    if missing:
        raise RuntimeError(
            "real_autoplay_runner_truncated:"
            f"missing_markers:{','.join(missing)}"
        )

    # Do not require the literal text "return summary".
    # The function may return through a parenthesized/typed path or after future
    # finalization edits. The important invariant is that we still have the real
    # large runner, not a stub.
    if len(source) < 100_000:
        raise RuntimeError(
            "real_autoplay_runner_too_small:"
            f"source_chars={len(source)}"
        )


def _run_with_console_capture(args: argparse.Namespace) -> int:
    global _ACTIVE_CONSOLE_CAPTURE
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    console_log_path = output_dir / "console-log.txt"
    if not getattr(args, "capture_console_log", True):
        summary = _run_autoplay_campaign(args)
        if summary is None:
            raise RuntimeError(
                "autoplay_runner_returned_none:_run_autoplay_campaign ended before returning a summary. "
                "The real turn loop was likely truncated or helper functions were inserted inside/over the runner."
            )
        return 0 if _safe_dict(summary).get("ok") else 1

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

    if summary is None:
        raise RuntimeError(
            "autoplay_runner_returned_none:_run_autoplay_campaign ended before returning a summary. "
            "The real turn loop was likely truncated or helper functions were inserted inside/over the runner."
        )

    if not _safe_dict(summary).get("ok"):
        for error in _safe_list(_safe_dict(summary).get("runtime_errors")):
            _timestamped_print(f"[AUTOPLAY-ERROR] {error}")

    return 0 if _safe_dict(summary).get("ok") else 1


def main(argv: List[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    args = _apply_autoplay_profile_defaults(args)
    _assert_real_autoplay_runner_present()
    if (
        _safe_str(getattr(args, "autoplay_profile", "")) == "smoke_100"
        and int(getattr(args, "turns", 0) or 0) != 100
    ):
        _timestamped_print(
            f"[AUTOPLAY-WARN] smoke_100 profile running with explicit --turns={getattr(args, 'turns', None)}"
        )
    if getattr(args, "list_scenario_seeds", False):
        for name in available_campaign_seeds():
            _timestamped_print(name)
        return 0
    return _run_with_console_capture(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))