from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual import output_artifacts
from tests.rpg.manual.campaign_director_m22_m24_checks import (
    run_campaign_director_m22_m24_checks,
)
from tests.rpg.manual.campaign_journal_m31_m33_checks import (
    run_campaign_journal_m31_m33_checks,
)
from tests.rpg.manual.companion_m28_m30_checks import run_companion_m28_m30_checks
from tests.rpg.manual.dialogue_m16_m18_checks import run_dialogue_m16_m18_checks
from tests.rpg.manual.escalation_m7_m9_checks import run_escalation_m7_m9_checks
from tests.rpg.manual.memory_checks import run_memory_checks
from tests.rpg.manual.npc_evolution_m19_m21_checks import (
    run_npc_evolution_m19_m21_checks,
)
from tests.rpg.manual.output_state import (
    _REGRESSION_WARNING_LOCK,
    _REGRESSION_WARNING_ROWS,
    _REGRESSION_WARNINGS,
)
from tests.rpg.manual.player_action_context_m52_m54_checks import (
    run_player_action_context_m52_m54_checks,
)
from tests.rpg.manual.quest_log_m49_m51_checks import (
    run_quest_log_m49_m51_checks,
)
from tests.rpg.manual.quest_puzzle_checks import run_quest_puzzle_checks
from tests.rpg.manual.safe import _compact_json, _safe_dict, _safe_list
from tests.rpg.manual.scenario_setup import (
    _apply_manual_scenario_setup,
    apply_manual_scenario_setup_by_session_id,
)
from tests.rpg.manual.scenario_summary import (
    _build_service_summary_row,
    _extract_player_inventory,
    _extract_service_memories,
    _extract_simulation_state,
    _pre_turn_contamination_snapshot,
)
from tests.rpg.manual.session_helpers import (
    _ensure_manual_session,
    _manual_service_session_id,
    _reset_manual_session_artifacts,
    _seed_session_currency,
    _thread_label,
)
from tests.rpg.manual.social_checks import run_social_checks
from tests.rpg.manual.spatial_checks import run_spatial_checks
from tests.rpg.manual.story_arc_milestones_m46_m48_checks import (
    run_story_arc_milestones_m46_m48_checks,
)
from tests.rpg.manual.story_authoring_approval_m37_m39_checks import (
    run_story_authoring_approval_m37_m39_checks,
)
from tests.rpg.manual.story_authoring_inspector_m40_m42_checks import (
    run_story_authoring_inspector_m40_m42_checks,
)
from tests.rpg.manual.story_authoring_m34_m36_checks import (
    run_story_authoring_m34_m36_checks,
)
from tests.rpg.manual.story_event_m4_m6_checks import run_story_event_m4_m6_checks
from tests.rpg.manual.story_event_queue_m25_m27_checks import (
    run_story_event_queue_m25_m27_checks,
)
from tests.rpg.manual.story_m1_m3_checks import run_story_m1_m3_checks
from tests.rpg.manual.story_pack_activation_m43_m45_checks import (
    run_story_pack_activation_m43_m45_checks,
)
from tests.rpg.manual.story_pack_m13_m15_checks import run_story_pack_m13_m15_checks
from tests.rpg.manual.story_proposal_m10_m12_checks import (
    run_story_proposal_m10_m12_checks,
)
from tests.rpg.manual.turn_execution import _run_one_manual_turn


def _reset_regression_warnings() -> None:
    with _REGRESSION_WARNING_LOCK:
        _REGRESSION_WARNING_ROWS.clear()
        _REGRESSION_WARNINGS.clear()


def _record_regression_warnings(row: Dict[str, Any]) -> None:
    warnings = _safe_list(row.get("regression_warnings")) + _safe_list(row.get("scenario_warnings"))
    if warnings:
        with _REGRESSION_WARNING_LOCK:
            _REGRESSION_WARNING_ROWS.append(row)


def _record_scenario_error(
    *,
    scenario_name: str,
    session_id: str = "",
    error: str,
) -> None:
    row = {
        "scenario": scenario_name,
        "session_id": session_id,
        "turn": 0,
        "player_input": "",
        "scenario_warnings": [f"scenario_runtime_error:{scenario_name}:{error}"],
        "regression_warnings": [f"scenario_runtime_error:{scenario_name}:{error}"],
    }
    with _REGRESSION_WARNING_LOCK:
        _REGRESSION_WARNING_ROWS.append(row)


def _add_regression_warning(
    *,
    scenario: str,
    turn: int,
    warning: str,
) -> None:
    warning_entry = f"{scenario}:turn_{turn}:{warning}"
    with _REGRESSION_WARNING_LOCK:
        _REGRESSION_WARNINGS.append(warning_entry)


def _scenario_contamination_warnings(
    *,
    scenario_name: str,
    turn_index: int,
    before_currency: Dict[str, Any],
    before_items: List[Dict[str, Any]],
    result: Dict[str, Any],
    pre_turn_snapshot: Dict[str, int],
    allows_seeded_world_events: bool,
    allows_seeded_journal_entries: bool,
    allows_seeded_quest_state: bool,
) -> List[str]:
    """Check for scenario contamination warnings."""
    warnings: List[str] = []

    after_snapshot = _pre_turn_contamination_snapshot(_extract_simulation_state(result))

    if not allows_seeded_world_events:
        if after_snapshot["world_event_count"] > pre_turn_snapshot["world_event_count"]:
            warnings.append("unexpected_world_event_creation")

    if not allows_seeded_journal_entries:
        if after_snapshot["journal_entry_count"] > pre_turn_snapshot["journal_entry_count"]:
            warnings.append("unexpected_journal_entry_creation")

    if not allows_seeded_quest_state:
        if after_snapshot["quest_count"] > pre_turn_snapshot["quest_count"]:
            warnings.append("unexpected_quest_creation")

    allows_service_memories = scenario_name in {
        "npc_bran_refuses_unpaid_room",
        "npc_bran_negotiates_high_trust_room",
        "npc_bran_escalates_when_threatened",
    }

    service_memories = _extract_service_memories(result)
    if service_memories and not allows_service_memories:
        warnings.append("unexpected_service_memory_creation")

    return warnings


def _run_one_service_scenario(
    *,
    scenario_name: str,
    scenario: Dict[str, Any],
    run_id: str,
    split_files: bool,
    legacy_channel: str,
    stable_session_ids: bool,
    reset_session_state: bool,
    console_llm: bool = True,
    console_llm_raw: bool = True,
    console_llm_max_chars: int = 1200,
    fail_on_regression_warnings: bool = False,
    artifact_detail: str = "debug",
) -> Dict[str, Any]:
    scenario_channel = f"service_{scenario_name}"
    target_channel = scenario_channel if split_files else legacy_channel
    from tests.rpg.manual.runner import _new_manual_run_id
    session_id = _manual_service_session_id(
        scenario_name,
        run_id or _new_manual_run_id(),
        stable=stable_session_ids,
    )
    currency = _safe_dict(scenario.get("currency"))
    turns = _safe_list(scenario.get("turns"))

    print(
        f"[manual][worker {_thread_label()}] scenario {scenario_name}: "
        f"{len(turns)} turns session_id={session_id}",
        flush=True,
    )

    if reset_session_state:
        _reset_manual_session_artifacts(session_id)

    output_artifacts._emit("", channel=target_channel)
    output_artifacts._emit("#" * 80, channel=target_channel)
    output_artifacts._emit(f"SCENARIO: {scenario_name}", channel=target_channel)
    output_artifacts._emit(f"session_id: {session_id}", channel=target_channel)
    output_artifacts._emit(f"manual_run_id: {run_id}", channel=target_channel)
    output_artifacts._emit("SEEDED CURRENCY:", channel=target_channel)
    output_artifacts._emit(_compact_json(currency), channel=target_channel)
    output_artifacts._emit("#" * 80, channel=target_channel)

    setup_error_type = None
    setup_error = None
    setup_error_repr = None
    try:
        seeded = _seed_session_currency(session_id, currency)
        apply_manual_scenario_setup_by_session_id(
            session_id,
            scenario,
            scenario_name=scenario_name,
        )
        setup_applied = True
    except Exception as exc:
        setup_error_type = type(exc).__name__
        setup_error = str(exc)
        setup_error_repr = repr(exc)
        warning = (
            "scenario_runtime_error:"
            + str(scenario_name)
            + ":scenario_session_seed_failed:"
            + setup_error_type
            + ":"
            + setup_error
        )
        summary = {
            "scenario": scenario_name,
            "session_id": session_id,
            "seeded_currency": currency,
            "error": "scenario_session_seed_failed",
            "setup_error_type": setup_error_type,
            "setup_error": setup_error,
            "setup_error_repr": setup_error_repr,
            "scenario_warnings": [warning],
            "regression_warnings": [warning],
            "turns": [],
        }
        output_artifacts._emit(f"SETUP ERROR: {setup_error_type}: {setup_error}", channel=target_channel)
        return summary

    turn_summaries = []
    pre_turn_snapshot = _pre_turn_contamination_snapshot(_ensure_manual_session(session_id)["simulation_state"])
    for turn_index, turn in enumerate(turns, start=1):
        story_event_queue_checks_for_turn = []
        if isinstance(turn, dict):
            story_event_queue_checks_for_turn = turn.get("story_event_queue_checks") or []

        turn_record = _run_one_manual_turn(
            session_id=session_id,
            turn=turn,
            turn_index=turn_index,
            scenario_name=scenario_name,
            target_channel=target_channel,
            console_llm=console_llm,
            console_llm_raw=console_llm_raw,
            console_llm_max_chars=console_llm_max_chars,
            story_event_queue_checks=story_event_queue_checks_for_turn if story_event_queue_checks_for_turn else None,
        )

        checks = scenario.get("checks") or []
        spatial_checks = [
            check for check in checks
            if isinstance(check, dict) and str(check.get("type") or "").startswith("spatial_")
        ]
        if spatial_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            spatial_check_results = run_spatial_checks(
                checks=spatial_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["spatial_check_results"] = spatial_check_results
            for check_result in spatial_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"spatial_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        memory_checks = [
            check for check in checks
            if isinstance(check, dict) and str(check.get("type") or "").startswith("memory_")
        ]
        if memory_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            memory_check_results = run_memory_checks(
                checks=memory_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["memory_check_results"] = memory_check_results
            for check_result in memory_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"memory_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        social_checks = [
            check for check in checks
            if isinstance(check, dict) and str(check.get("type") or "").startswith("social_")
        ]
        if social_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            social_check_results = run_social_checks(
                checks=social_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["social_check_results"] = social_check_results
            for check_result in social_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"social_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        quest_puzzle_checks = [
            check for check in checks
            if isinstance(check, dict) and (
                str(check.get("type") or "") in {
                    "quest_stage", "quest_objective", "quest_condition", "quest_reward_payload",
                    "puzzle_state", "puzzle_flag", "puzzle_condition"
                }
            )
        ]
        if quest_puzzle_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            quest_puzzle_check_results = run_quest_puzzle_checks(
                checks=quest_puzzle_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["quest_puzzle_check_results"] = quest_puzzle_check_results
            for check_result in quest_puzzle_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"quest_puzzle_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        story_m1_m3_checks = []
        for check in checks:
            if not isinstance(check, dict):
                continue
            check_type = str(check.get("type") or "")
            if check_type.startswith("story_arc_milestone"):
                continue
            if check_type.startswith("story_objective"):
                continue
            if check_type == "story_event_apply_for_milestone":
                continue
            if check_type.startswith("lore_") or check_type.startswith("story_arc"):
                story_m1_m3_checks.append(check)
        if story_m1_m3_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            story_m1_m3_check_results = run_story_m1_m3_checks(
                checks=story_m1_m3_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["story_m1_m3_check_results"] = story_m1_m3_check_results
            for check_result in story_m1_m3_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"story_m1_m3_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        story_event_m4_m6_checks = []
        for check in checks:
            if not isinstance(check, dict):
                continue
            check_type = str(check.get("type") or "")
            if check_type == "story_event_apply_for_milestone":
                continue
            if (
                check_type.startswith("story_event_")
                and not check_type.startswith("story_event_queue_")
            ):
                story_event_m4_m6_checks.append(check)
        if story_event_m4_m6_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            story_event_m4_m6_check_results = run_story_event_m4_m6_checks(
                checks=story_event_m4_m6_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["story_event_m4_m6_check_results"] = story_event_m4_m6_check_results
            for check_result in story_event_m4_m6_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"story_event_m4_m6_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        escalation_m7_m9_checks = [
            check for check in checks
            if isinstance(check, dict) and str(check.get("type") or "").startswith("escalation_")
        ]
        if escalation_m7_m9_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            escalation_m7_m9_check_results = run_escalation_m7_m9_checks(
                checks=escalation_m7_m9_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["escalation_m7_m9_check_results"] = escalation_m7_m9_check_results
            for check_result in escalation_m7_m9_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"escalation_m7_m9_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        story_proposal_m10_m12_checks = [
            check for check in checks
            if isinstance(check, dict) and str(check.get("type") or "").startswith("story_proposal_")
        ]
        if story_proposal_m10_m12_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            story_proposal_m10_m12_check_results = run_story_proposal_m10_m12_checks(
                checks=story_proposal_m10_m12_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["story_proposal_m10_m12_check_results"] = story_proposal_m10_m12_check_results
            for check_result in story_proposal_m10_m12_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"story_proposal_m10_m12_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        story_pack_m13_m15_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and str(check.get("type") or "").startswith("story_pack")
            and not str(check.get("type") or "").startswith("story_pack_activation")
        ]
        if story_pack_m13_m15_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            story_pack_m13_m15_check_results = run_story_pack_m13_m15_checks(
                checks=story_pack_m13_m15_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["story_pack_m13_m15_check_results"] = story_pack_m13_m15_check_results
            for check_result in story_pack_m13_m15_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"story_pack_m13_m15_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        dialogue_m16_m18_checks = [
            check for check in checks
            if isinstance(check, dict) and (str(check.get("type") or "").startswith("dialogue_") or str(check.get("type") or "").startswith("rumor_"))
        ]
        if dialogue_m16_m18_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            dialogue_m16_m18_check_results = run_dialogue_m16_m18_checks(
                checks=dialogue_m16_m18_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["dialogue_m16_m18_check_results"] = dialogue_m16_m18_check_results
            for check_result in dialogue_m16_m18_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"dialogue_m16_m18_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        npc_evolution_m19_m21_checks = [
            check for check in checks
            if isinstance(check, dict) and str(check.get("type") or "").startswith("npc_evolution")
        ]
        if npc_evolution_m19_m21_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            npc_evolution_m19_m21_check_results = run_npc_evolution_m19_m21_checks(
                checks=npc_evolution_m19_m21_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["npc_evolution_m19_m21_check_results"] = npc_evolution_m19_m21_check_results
            for check_result in npc_evolution_m19_m21_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"npc_evolution_m19_m21_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        campaign_director_m22_m24_checks = [
            check for check in checks
            if isinstance(check, dict) and str(check.get("type") or "").startswith("campaign_director")
        ]
        if campaign_director_m22_m24_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            campaign_director_m22_m24_check_results = run_campaign_director_m22_m24_checks(
                checks=campaign_director_m22_m24_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            for check_result in campaign_director_m22_m24_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"campaign_director_m22_m24_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        story_event_queue_m25_m27_checks = [
            check for check in checks
            if isinstance(check, dict) and str(check.get("type") or "").startswith("story_event_queue_")
        ]
        if story_event_queue_m25_m27_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session
            story_event_queue_m25_m27_check_results = run_story_event_queue_m25_m27_checks(
                checks=story_event_queue_m25_m27_checks, result=turn_record.get("result") or turn_record, session=current_session,
            )
            turn_record["story_event_queue_m25_m27_check_results"] = story_event_queue_m25_m27_check_results
            for check_result in story_event_queue_m25_m27_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        f"story_event_queue_m25_m27_check_failed:{scenario_name}:turn_{turn_index}:"
                        + str(check_result.get("check_type")) + ":" + str(check_result.get("error") or "")
                    )

        companion_m28_m30_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and (
                str(check.get("type") or "").startswith("companion_")
                or str(check.get("type") or "") == "party_member"
                or str(check.get("type") or "") == "npc_runtime_context"
            )
        ]
        if companion_m28_m30_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            companion_m28_m30_check_results = run_companion_m28_m30_checks(
                checks=companion_m28_m30_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["companion_m28_m30_check_results"] = companion_m28_m30_check_results
            for check_result in companion_m28_m30_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "companion_m28_m30_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        campaign_journal_m31_m33_checks = []
        for check in checks:
            if not isinstance(check, dict):
                continue
            check_type = str(check.get("type") or "")
            if check_type == "campaign_journal_objective_contains":
                continue
            if (
                check_type.startswith("campaign_journal")
                or check_type.startswith("campaign_story_recap")
            ):
                campaign_journal_m31_m33_checks.append(check)
        if campaign_journal_m31_m33_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            campaign_journal_m31_m33_check_results = run_campaign_journal_m31_m33_checks(
                checks=campaign_journal_m31_m33_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["campaign_journal_m31_m33_check_results"] = campaign_journal_m31_m33_check_results
            for check_result in campaign_journal_m31_m33_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "campaign_journal_m31_m33_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        story_authoring_m34_m36_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and str(check.get("type") or "").startswith("story_authoring_m34_m36")
        ]
        if story_authoring_m34_m36_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            story_authoring_m34_m36_check_results = run_story_authoring_m34_m36_checks(
                checks=story_authoring_m34_m36_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["story_authoring_m34_m36_check_results"] = story_authoring_m34_m36_check_results
            for check_result in story_authoring_m34_m36_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "story_authoring_m34_m36_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        story_authoring_approval_m37_m39_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and str(check.get("type") or "").startswith("story_authoring_approval")
        ]
        if story_authoring_approval_m37_m39_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            story_authoring_approval_m37_m39_check_results = run_story_authoring_approval_m37_m39_checks(
                checks=story_authoring_approval_m37_m39_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["story_authoring_approval_m37_m39_check_results"] = story_authoring_approval_m37_m39_check_results
            for check_result in story_authoring_approval_m37_m39_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "story_authoring_approval_m37_m39_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        story_authoring_inspector_m40_m42_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and str(check.get("type") or "").startswith("story_authoring_inspector")
        ]
        if story_authoring_inspector_m40_m42_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            story_authoring_inspector_m40_m42_check_results = run_story_authoring_inspector_m40_m42_checks(
                checks=story_authoring_inspector_m40_m42_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["story_authoring_inspector_m40_m42_check_results"] = story_authoring_inspector_m40_m42_check_results
            for check_result in story_authoring_inspector_m40_m42_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "story_authoring_inspector_m40_m42_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        story_pack_activation_m43_m45_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and str(check.get("type") or "").startswith("story_pack_activation")
        ]
        if story_pack_activation_m43_m45_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            story_pack_activation_m43_m45_check_results = run_story_pack_activation_m43_m45_checks(
                checks=story_pack_activation_m43_m45_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["story_pack_activation_m43_m45_check_results"] = story_pack_activation_m43_m45_check_results
            for check_result in story_pack_activation_m43_m45_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "story_pack_activation_m43_m45_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        story_arc_milestones_m46_m48_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and (
                str(check.get("type") or "").startswith("story_arc_milestone")
                or str(check.get("type") or "").startswith("story_objective")
                or str(check.get("type") or "") == "story_event_apply_for_milestone"
                or str(check.get("type") or "") == "campaign_journal_objective_contains"
                or str(check.get("type") or "") == "campaign_recap_objective"
            )
        ]
        if story_arc_milestones_m46_m48_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            story_arc_milestones_m46_m48_check_results = run_story_arc_milestones_m46_m48_checks(
                checks=story_arc_milestones_m46_m48_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["story_arc_milestones_m46_m48_check_results"] = story_arc_milestones_m46_m48_check_results
            for check_result in story_arc_milestones_m46_m48_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "story_arc_milestones_m46_m48_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        quest_log_m49_m51_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and (
                str(check.get("type") or "").startswith("quest_log")
                or str(check.get("type") or "").startswith("objective_tracker")
                or str(check.get("type") or "") == "campaign_recap_objective_tracker"
            )
        ]
        if quest_log_m49_m51_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            quest_log_m49_m51_check_results = run_quest_log_m49_m51_checks(
                checks=quest_log_m49_m51_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["quest_log_m49_m51_check_results"] = quest_log_m49_m51_check_results
            for check_result in quest_log_m49_m51_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "quest_log_m49_m51_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        player_action_context_m52_m54_checks = [
            check
            for check in checks
            if isinstance(check, dict)
            and (
                str(check.get("type") or "").startswith("player_action_context")
                or str(check.get("type") or "") == "suggested_actions"
            )
        ]
        if player_action_context_m52_m54_checks:
            current_session = {}
            try:
                current_session = _ensure_manual_session(session_id)
            except Exception:
                current_session = session

            player_action_context_m52_m54_check_results = run_player_action_context_m52_m54_checks(
                checks=player_action_context_m52_m54_checks,
                result=turn_record.get("result") or turn_record,
                session=current_session,
            )
            turn_record["player_action_context_m52_m54_check_results"] = player_action_context_m52_m54_check_results
            for check_result in player_action_context_m52_m54_check_results:
                if not check_result.get("ok"):
                    turn_record.setdefault("scenario_warnings", []).append(
                        "player_action_context_m52_m54_check_failed:"
                        + str(scenario_name)
                        + ":turn_"
                        + str(turn_index)
                        + ":"
                        + str(check_result.get("check_type"))
                        + ":"
                        + str(check_result.get("error") or "")
                    )

        contamination_warnings = _scenario_contamination_warnings(
            scenario_name=scenario_name,
            turn_index=turn_index,
            before_currency=currency,
            before_items=_extract_player_inventory(_ensure_manual_session(session_id)["simulation_state"]),
            result=turn_record.get("result") or {},
            pre_turn_snapshot=pre_turn_snapshot,
            allows_seeded_world_events=bool(scenario.get("allows_seeded_world_events")),
            allows_seeded_journal_entries=bool(scenario.get("allows_seeded_journal_entries")),
            allows_seeded_quest_state=bool(scenario.get("allows_seeded_quest_state")),
        )
        if contamination_warnings:
            for warning in contamination_warnings:
                _add_regression_warning(
                    scenario=scenario_name, turn=turn_index, warning=warning,
                )
            turn_record.setdefault("scenario_warnings", []).extend(contamination_warnings)

        turn_summaries.append(turn_record)

    summary_row = _build_service_summary_row(
        scenario_name=scenario_name, session_id=session_id, seeded_currency=currency,
        turns=turn_summaries, detail=artifact_detail,
    )
    _record_regression_warnings(summary_row)

    if artifact_detail in ("debug", "full"):
        from tests.rpg.manual.constants import TEST_RESULTS_ROOT
        from tests.rpg.manual.summary_sanitizer import write_scenario_debug_artifact

        debug_file = write_scenario_debug_artifact(
            scenario_name=scenario_name, scenario_summary=summary_row,
            output_dir=str(TEST_RESULTS_ROOT), detail=artifact_detail,
        )
        print(f"Wrote debug artifact: {debug_file}", flush=True)

    output_artifacts._emit("", channel=target_channel)
    output_artifacts._emit("#" * 80, channel=target_channel)
    output_artifacts._emit(f"SCENARIO COMPLETE: {scenario_name}", channel=target_channel)
    output_artifacts._emit("#" * 80, channel=target_channel)

    return summary_row