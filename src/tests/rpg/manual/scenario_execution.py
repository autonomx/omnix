from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual import output_artifacts
from tests.rpg.manual.output_state import (
    _REGRESSION_WARNING_LOCK,
    _REGRESSION_WARNING_ROWS,
    _REGRESSION_WARNINGS,
)
from tests.rpg.manual.safe import _compact_json, _safe_dict, _safe_list
from tests.rpg.manual.scenario_setup import _apply_manual_scenario_setup
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

    # Check for unexpected world event changes
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

    # Check for unexpected service/memory contamination
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

    seeded = _seed_session_currency(session_id, currency)
    setup_applied = _apply_manual_scenario_setup(session_id, scenario)
    if not seeded or not setup_applied:
        scenario_error = "scenario_session_seed_failed"
        _record_scenario_error(
            scenario_name=scenario_name,
            session_id=session_id,
            error=scenario_error,
        )
        return {
            "scenario": scenario_name,
            "session_id": session_id,
            "seeded_currency": currency,
            "error": scenario_error,
            "turns": [],
            "scenario_warnings": [scenario_error],
            "regression_warnings": [scenario_error],
        }

    # Run turns
    turn_summaries = []
    pre_turn_snapshot = _pre_turn_contamination_snapshot(_ensure_manual_session(session_id)["simulation_state"])
    for turn_index, turn in enumerate(turns, start=1):
        turn_summary = _run_one_manual_turn(
            session_id=session_id,
            turn=turn,
            turn_index=turn_index,
            scenario_name=scenario_name,
            target_channel=target_channel,
            console_llm=console_llm,
            console_llm_raw=console_llm_raw,
            console_llm_max_chars=console_llm_max_chars,
        )
        turn_summaries.append(turn_summary)

        # Check for contamination
        contamination_warnings = _scenario_contamination_warnings(
            scenario_name=scenario_name,
            turn_index=turn_index,
            before_currency=currency,
            before_items=_extract_player_inventory(_ensure_manual_session(session_id)["simulation_state"]),
            result=turn_summary.get("result") or {},
            pre_turn_snapshot=pre_turn_snapshot,
            allows_seeded_world_events=bool(scenario.get("allows_seeded_world_events")),
            allows_seeded_journal_entries=bool(scenario.get("allows_seeded_journal_entries")),
            allows_seeded_quest_state=bool(scenario.get("allows_seeded_quest_state")),
        )
        if contamination_warnings:
            for warning in contamination_warnings:
                _add_regression_warning(
                    scenario=scenario_name,
                    turn=turn_index,
                    warning=warning,
                )
            turn_summary.setdefault("scenario_warnings", []).extend(contamination_warnings)

    # Build summary
    summary_row = _build_service_summary_row(
        scenario_name=scenario_name,
        session_id=session_id,
        seeded_currency=currency,
        turns=turn_summaries,
    )
    _record_regression_warnings(summary_row)

    output_artifacts._emit("", channel=target_channel)
    output_artifacts._emit("#" * 80, channel=target_channel)
    output_artifacts._emit(f"SCENARIO COMPLETE: {scenario_name}", channel=target_channel)
    output_artifacts._emit("#" * 80, channel=target_channel)

    return summary_row