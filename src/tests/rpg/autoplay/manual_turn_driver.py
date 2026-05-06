from __future__ import annotations

import time
import os
from copy import deepcopy
from typing import Any, Dict

from app.providers.provider_trace import clear_provider_trace, get_provider_trace
from app.rpg.session.deferred_narration_guard import deferred_runtime_narration_context
from app.rpg.session.narration_trace import (
    clear_narration_trace,
    enable_narration_trace,
    get_narration_trace,
    record_narration_trace,
)
from tests.rpg.manual.perf_trace import (
    clear_manual_harness_trace,
    get_manual_harness_trace,
    summarize_manual_harness_trace,
)
from app.rpg.session.turn_perf_trace import (
    clear_turn_perf_trace,
    get_turn_perf_trace,
    summarize_turn_perf_trace,
)
from tests.rpg.manual.session_helpers import (
    _ensure_manual_session,
    _ensure_manual_simulation_roots,
    _reset_manual_session_artifacts,
    _save_manual_session_for_test,
)
from tests.rpg.manual.turn_execution import _run_one_manual_turn


def _trace_stage(rows: list, event: str, **fields: Any) -> None:
    rows.append({"event": event, "time": round(time.perf_counter(), 6), **fields})


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


AUTOPLAY_PRESERVED_SIMULATION_ROOTS = {
    "scene",
    "location",
    "runtime",
    "story_arc_state",
    "story_arc_milestone_state",
    "quest_log_state",
    "campaign_journal_state",
    "inventory_state",
    "story_event_queue_state",
    "story_pack_state",
    "campaign_director_state",
    "lore_state",
    "npc_evolution_state",
    "npc_profile_state",
    "npc_progression_state",
    "player_state",
    "social_state",
}


def _merge_list_by_id(
    before_items: Any,
    returned_items: Any,
    *,
    id_key: str,
) -> list:
    before_list = before_items if isinstance(before_items, list) else []
    returned_list = returned_items if isinstance(returned_items, list) else []
    merged_by_id = {}
    order = []

    for item in before_list:
        if not isinstance(item, dict):
            continue
        item_id = item.get(id_key)
        if not item_id:
            continue
        if item_id not in merged_by_id:
            order.append(item_id)
        merged_by_id[item_id] = deepcopy(item)

    for item in returned_list:
        if not isinstance(item, dict):
            continue
        item_id = item.get(id_key)
        if not item_id:
            continue
        if item_id not in merged_by_id:
            order.append(item_id)
            merged_by_id[item_id] = deepcopy(item)
            continue
        merged = deepcopy(merged_by_id[item_id])
        merged.update(deepcopy(item))
        merged_by_id[item_id] = merged

    return [merged_by_id[item_id] for item_id in order]


def _merge_campaign_journal_state(before: Any, returned: Any) -> Dict[str, Any]:
    before = deepcopy(_safe_dict(before))
    returned = deepcopy(_safe_dict(returned))
    merged = deepcopy(before)
    merged.update(returned)
    before_entries = _safe_dict(before).get("entries", [])
    returned_entries = _safe_dict(returned).get("entries", [])
    merged["entries"] = _merge_list_by_id(
        before_entries,
        returned_entries,
        id_key="entry_id",
    )
    return merged


def _merge_story_event_queue_state(before: Any, returned: Any) -> Dict[str, Any]:
    before = deepcopy(_safe_dict(before))
    returned = deepcopy(_safe_dict(returned))
    merged = deepcopy(before)
    merged.update(returned)
    merged["queue"] = _merge_list_by_id(
        before.get("queue", []),
        returned.get("queue", []),
        id_key="event_id",
    )
    return merged


def _merge_story_arc_state(before: Any, returned: Any) -> Dict[str, Any]:
    before = deepcopy(_safe_dict(before))
    returned = deepcopy(_safe_dict(returned))
    merged = deepcopy(before)
    merged.update(returned)
    before_arcs = _safe_dict(before.get("arcs"))
    returned_arcs = _safe_dict(returned.get("arcs"))
    arcs = deepcopy(before_arcs)
    for arc_id, returned_arc in returned_arcs.items():
        if not isinstance(returned_arc, dict):
            continue
        existing = deepcopy(_safe_dict(arcs.get(arc_id)))
        existing.update(deepcopy(returned_arc))
        arcs[arc_id] = existing
    merged["arcs"] = arcs
    return merged


def _merge_story_arc_milestone_state(before: Any, returned: Any) -> Dict[str, Any]:
    before = deepcopy(_safe_dict(before))
    returned = deepcopy(_safe_dict(returned))
    merged = deepcopy(before)
    merged.update(returned)

    before_arcs = _safe_dict(before.get("arcs"))
    returned_arcs = _safe_dict(returned.get("arcs"))
    arcs = deepcopy(before_arcs)

    for arc_id, returned_bucket in returned_arcs.items():
        if not isinstance(returned_bucket, dict):
            continue
        existing_bucket = deepcopy(_safe_dict(arcs.get(arc_id)))
        existing_bucket.update(deepcopy(returned_bucket))
        existing_bucket["milestones"] = _merge_list_by_id(
            _safe_dict(arcs.get(arc_id)).get("milestones", []),
            returned_bucket.get("milestones", []),
            id_key="milestone_id",
        )
        arcs[arc_id] = existing_bucket

    merged["arcs"] = arcs
    return merged


def _merge_preserved_root(key: str, before_value: Any, returned_value: Any) -> Any:
    if key == "campaign_journal_state":
        return _merge_campaign_journal_state(before_value, returned_value)
    if key == "story_event_queue_state":
        return _merge_story_event_queue_state(before_value, returned_value)
    if key == "story_arc_state":
        return _merge_story_arc_state(before_value, returned_value)
    if key == "story_arc_milestone_state":
        return _merge_story_arc_milestone_state(before_value, returned_value)

    if isinstance(before_value, dict) and isinstance(returned_value, dict):
        if before_value and not returned_value:
            return deepcopy(before_value)
        merged = deepcopy(before_value)
        merged.update(deepcopy(returned_value))
        return merged

    return deepcopy(returned_value if returned_value is not None else before_value)


def merge_autoplay_simulation_state(
    *,
    before_state: Dict[str, Any],
    returned_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge raw apply_turn state without letting partial state erase campaign roots.

    Some manual/app turn paths return only a compact session simulation_state
    containing memory/presentation roots. Autoplay seeds campaign/objective
    state before the turn, so a partial returned state must be merged over the
    pre-turn state rather than replacing it wholesale.
    """
    before_state = deepcopy(_safe_dict(before_state))
    returned_state = deepcopy(_safe_dict(returned_state))
    merged = deepcopy(before_state)

    for key, value in returned_state.items():
        if key in AUTOPLAY_PRESERVED_SIMULATION_ROOTS:
            merged[key] = _merge_preserved_root(
                key,
                before_state.get(key),
                value,
            )
            continue
        merged[key] = deepcopy(value)

    for key in AUTOPLAY_PRESERVED_SIMULATION_ROOTS:
        if key in before_state and key not in returned_state:
            merged[key] = deepcopy(before_state[key])

    return merged


def _save_through_app_session_service(session: Dict[str, Any]) -> None:
    """Best-effort save through the same app service manual setup relies on."""
    try:
        from app.rpg.session.service import save_session

        save_session(session)
    except Exception:
        # _save_manual_session_for_test already wrote the fallback harness file.
        # Some partial test environments do not expose the app save path.
        return


def prepare_autoplay_manual_session(
    *,
    session_id: str,
    simulation_state: Dict[str, Any],
    reset_session_state: bool = True,
    runtime_narration: str = "blocking",
) -> Dict[str, Any]:
    """Create the same kind of session manual_llm_transcript.py uses.

    The autoplay runner owns player input selection, but the turn execution
    should be identical to manual scenarios: save a manual session, then call
    the same apply_turn path via _run_one_manual_turn().
    """
    if reset_session_state:
        _reset_manual_session_artifacts(session_id)

    session = _ensure_manual_session(session_id)
    sim = _ensure_manual_simulation_roots(session)
    sim.clear()
    sim.update(deepcopy(_safe_dict(simulation_state)))

    session["simulation_state"] = sim
    runtime_state = session.setdefault("runtime_state", {})
    performance = runtime_state.setdefault("performance", {})
    if runtime_narration == "deferred":
        runtime_state["autoplay_deferred_narration"] = True
        runtime_state["deferred_runtime_narration"] = True
        runtime_state["narration_mode"] = "deferred"
        performance["enable_live_narration_llm"] = False
        performance["enable_narration_retry"] = False
        performance["enable_provider_runtime_narration"] = False
    else:
        runtime_state["autoplay_deferred_narration"] = False
        runtime_state["deferred_runtime_narration"] = False
        runtime_state["narration_mode"] = "blocking"

    session.setdefault("setup_payload", {})
    session["setup_payload"].setdefault("metadata", {})
    session["setup_payload"]["metadata"]["simulation_state"] = deepcopy(sim)
    session["manual_autoplay_session"] = True

    _save_manual_session_for_test(session_id, session)
    _save_through_app_session_service(session)
    return _ensure_manual_session(session_id)


def load_autoplay_manual_session(session_id: str) -> Dict[str, Any]:
    return _ensure_manual_session(session_id)


def load_autoplay_simulation_state(session_id: str) -> Dict[str, Any]:
    return _safe_dict(load_autoplay_manual_session(session_id).get("simulation_state"))


def _extract_turn_contract_from_raw_result(raw_result: Dict[str, Any]) -> Dict[str, Any]:
    raw_result = _safe_dict(raw_result)
    return _safe_dict(
        raw_result.get("turn_contract")
        or _safe_dict(raw_result.get("result")).get("turn_contract")
        or _safe_dict(raw_result.get("contract"))
    )


def _extract_simulation_state_from_raw_result(
    raw_result: Dict[str, Any],
    fallback_state: Dict[str, Any],
) -> Dict[str, Any]:
    raw_result = _safe_dict(raw_result)
    candidates = [
        raw_result.get("simulation_state"),
        _safe_dict(raw_result.get("session")).get("simulation_state"),
        _safe_dict(raw_result.get("result")).get("simulation_state"),
        _safe_dict(_safe_dict(raw_result.get("result")).get("session")).get("simulation_state"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return fallback_state


def run_autoplay_manual_turn(
    *,
    session_id: str,
    player_input: str,
    turn_index: int,
    scenario_name: str = "autoplay_campaign",
    target_channel: str = "autoplay_runtime",
    console_llm: bool = False,
    console_llm_raw: bool = False,
    console_llm_max_chars: int = 10_000,
    runtime_narration: str = "blocking",
    debug_narration_trace: bool = False,
) -> Dict[str, Any]:
    """Run one autoplay turn through the manual harness turn function."""
    pre_turn_session = load_autoplay_manual_session(session_id)
    if runtime_narration == "deferred":
        runtime_state = pre_turn_session.setdefault("runtime_state", {})
        performance = runtime_state.setdefault("performance", {})
        runtime_state["autoplay_deferred_narration"] = True
        runtime_state["deferred_runtime_narration"] = True
        runtime_state["narration_mode"] = "deferred"
        performance["enable_live_narration_llm"] = False
        performance["enable_narration_retry"] = False
        performance["enable_provider_runtime_narration"] = False

        setup_payload = pre_turn_session.setdefault("setup_payload", {})
        metadata = setup_payload.setdefault("metadata", {})
        metadata["runtime_narration"] = "deferred"
        metadata["autoplay_deferred_narration"] = True

        _save_manual_session_for_test(session_id, pre_turn_session)
        _save_through_app_session_service(pre_turn_session)

    pre_turn_state = deepcopy(_safe_dict(pre_turn_session.get("simulation_state")))

    enable_narration_trace(bool(debug_narration_trace))
    clear_narration_trace()
    clear_provider_trace()
    previous_manual_trace_env = os.environ.get("RPG_TRACE_MANUAL_HARNESS")
    previous_turn_trace_env = os.environ.get("RPG_TRACE_SESSION_TURN")
    if debug_narration_trace:
        os.environ["RPG_TRACE_MANUAL_HARNESS"] = "1"
        os.environ["RPG_TRACE_SESSION_TURN"] = "1"
    clear_manual_harness_trace()
    clear_turn_perf_trace()
    manual_stage_trace = []
    _trace_stage(
        manual_stage_trace,
        "manual_driver_enter",
        session_id=session_id,
        turn_index=turn_index,
        runtime_narration=runtime_narration,
    )
    record_narration_trace(
        "manual_turn_driver_before_call",
        session_id=session_id,
        turn_index=turn_index,
        runtime_narration=runtime_narration,
        deferred_requested=runtime_narration == "deferred",
    )
    _trace_stage(manual_stage_trace, "manual_driver_before_run_one_manual_turn")
    try:
        with deferred_runtime_narration_context(runtime_narration == "deferred"):
            turn_summary = _run_one_manual_turn(
                session_id=session_id,
                turn=player_input,
                turn_index=turn_index,
                scenario_name=scenario_name,
                target_channel=target_channel,
                console_llm=console_llm,
                console_llm_raw=console_llm_raw,
                console_llm_max_chars=console_llm_max_chars,
                story_event_queue_checks=None,
                include_raw_result=True,
            )
    finally:
        if debug_narration_trace:
            if previous_manual_trace_env is None:
                os.environ.pop("RPG_TRACE_MANUAL_HARNESS", None)
            else:
                os.environ["RPG_TRACE_MANUAL_HARNESS"] = previous_manual_trace_env
            if previous_turn_trace_env is None:
                os.environ.pop("RPG_TRACE_SESSION_TURN", None)
            else:
                os.environ["RPG_TRACE_SESSION_TURN"] = previous_turn_trace_env
    _trace_stage(manual_stage_trace, "manual_driver_after_run_one_manual_turn")
    record_narration_trace(
        "manual_turn_driver_after_call",
        session_id=session_id,
        turn_index=turn_index,
        result_source=(
            ((turn_summary.get("raw_result") or {}).get("narration_payload") or {}).get("source")
            if isinstance(turn_summary, dict) and isinstance(turn_summary.get("raw_result"), dict)
            else ""
        ),
    )

    post_turn_session = load_autoplay_manual_session(session_id)
    post_turn_state = _safe_dict(post_turn_session.get("simulation_state"))
    after_session = post_turn_session
    raw_result = _safe_dict(turn_summary.get("raw_result"))
    returned_after_state = _extract_simulation_state_from_raw_result(
        raw_result,
        post_turn_state,
    )
    after_state = merge_autoplay_simulation_state(
        before_state=pre_turn_state,
        returned_state=returned_after_state,
    )
    after_session["simulation_state"] = after_state
    after_session.setdefault("setup_payload", {}).setdefault("metadata", {})[
        "simulation_state"
    ] = deepcopy(after_state)
    _save_manual_session_for_test(session_id, after_session)
    _save_through_app_session_service(after_session)
    turn_contract = _safe_dict(
        turn_summary.get("raw_turn_contract")
        or _extract_turn_contract_from_raw_result(raw_result)
    )
    narration = (
        _safe_str(turn_summary.get("raw_narration"))
        or _extract_narration_from_manual_turn_summary(turn_summary)
    )
    result = {
        "ok": not bool(turn_summary.get("error")),
        "runtime_name": "manual_harness._run_one_manual_turn",
        "manual_turn_summary": turn_summary,
        "simulation_state": after_state,
        "turn_contract": turn_contract,
        "narration": narration,
        "player_input": player_input,
    }
    if debug_narration_trace:
        result["narration_trace"] = get_narration_trace()
        result["provider_trace"] = get_provider_trace()
        result["manual_stage_trace"] = manual_stage_trace
        manual_harness_trace = get_manual_harness_trace()
        result["manual_harness_trace"] = manual_harness_trace
        result["manual_harness_trace_summary"] = summarize_manual_harness_trace(
            manual_harness_trace
        )
        turn_perf_trace = get_turn_perf_trace()
        result["turn_perf_trace"] = turn_perf_trace
        result["turn_perf_trace_summary"] = summarize_turn_perf_trace(turn_perf_trace)
    return result


def _extract_narration_from_manual_turn_summary(turn_summary: Dict[str, Any]) -> str:
    result = _safe_dict(turn_summary.get("result"))
    candidates = [
        result.get("narration"),
        result.get("narrative"),
        result.get("text"),
        result.get("message"),
        result.get("rendered_narration"),
        result.get("deterministic_fallback_narration"),
        _safe_dict(result.get("result")).get("narration"),
        _safe_dict(result.get("session")).get("runtime_state", {}).get("last_narration")
        if isinstance(_safe_dict(result.get("session")).get("runtime_state"), dict)
        else "",
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""